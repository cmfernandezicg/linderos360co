import os
from .geometry_utils import preparar_vertices_normativos, reproyectar_geometry
from .clasificador import construir_segmentos, agrupar_por_cuadrante, CUADRANTES

# Valores considerados como vacíos/nulos
_VALORES_NULOS = {"", "NULL", "None", "null", "nan", "NaN", "none"}


def _valor_campo(feature, campo: str, default: str = "Sin información") -> str:
    if not campo:
        return default
    try:
        val = feature[campo]
        if val is None:
            return default
        val_str = str(val).strip()
        return default if val_str in _VALORES_NULOS else val_str
    except Exception:
        return default


def _formato_area(area_m2: float, es_urbano: bool) -> str:
    if es_urbano:
        return f"{area_m2:.2f} metros cuadrados (m²)"
    else:
        hectareas = int(area_m2 // 10000)
        residuo   = area_m2 % 10000
        return (
            f"{hectareas} hectáreas (ha) y "
            f"{residuo:.2f} metros cuadrados (m²)"
        )


def _texto_colindante(col: dict) -> str:
    """
    Retorna el texto del colindante o None si no hay información.
    None indica que la frase 'colindando con...' debe omitirse.
    """
    nupre    = col.get("nupre", "").strip()
    fmi      = col.get("fmi", "").strip()
    elemento = col.get("elemento", "").strip()

    # Limpia valores nulos
    nupre    = "" if nupre    in _VALORES_NULOS else nupre
    fmi      = "" if fmi      in _VALORES_NULOS else fmi
    elemento = "" if elemento in _VALORES_NULOS else elemento

    tiene_predio   = bool(nupre or fmi)
    tiene_elemento = bool(elemento)

    if tiene_predio and tiene_elemento:
        return (
            f"el predio identificado con NUPRE/Código Predial {nupre} "
            f"y F.M.I. {fmi}, separado por {elemento}"
        )
    elif tiene_predio:
        return (
            f"el predio identificado con NUPRE/Código Predial {nupre} "
            f"y F.M.I. {fmi}"
        )
    elif tiene_elemento:
        return elemento
    else:
        return None  # Sin colindante identificado — se omite la frase


def _texto_segmento(seg: dict, marcas: list) -> str:
    p1  = seg["p_inicio"]
    p2  = seg["p_fin"]
    col = seg["colindante"]
    n   = len(marcas)

    marca_inicio = marcas[seg["idx"]]
    marca_fin    = marcas[(seg["idx"] + 1) % n]

    lineas = [
        f"Lindero {seg['num_lindero']}: Inicia en el punto {marca_inicio} "
        f"con coordenadas N= {p1.y():.4f} m, E= {p1.x():.4f} m, "
        f"en línea {'quebrada' if col.get('intermedios') else 'recta'} "
        f"en sentido {seg['sentido']}",
    ]

    intermedios = col.get("intermedios", [])
    if intermedios:
        pts_texto = ", ".join(
            f"N= {p.y():.4f} m, E= {p.x():.4f} m"
            for p in intermedios
        )
        lineas.append(
            f"pasando por los puntos con coordenadas {pts_texto}"
        )

    # Tramo de distancia y punto final
    tramo_distancia = (
        f"en distancia de {seg['distancia_m']:.1f} m "
        f"hasta el punto {marca_fin} "
        f"con coordenadas N= {p2.y():.4f} m, E= {p2.x():.4f} m"
    )

    # Colindante — se omite si no hay información
    texto_col = _texto_colindante(col)
    if texto_col:
        tramo_distancia += f", colindando con {texto_col}."
    else:
        tramo_distancia += "."

    lineas.append(tramo_distancia)

    return " ".join(lineas)


def _generar_marcas(n_vertices: int) -> list:
    return [f"P{i + 1}" for i in range(n_vertices)]


def generar_descripcion(feature, config: dict) -> str:
    from .colindantes import resolver_colindantes

    capa      = config["capa"]
    es_urbano = config["es_urbano"]

    nupre_val = _valor_campo(feature, config["campo_nupre"])
    fmi_val   = _valor_campo(feature, config["campo_fmi"])

    vertices = preparar_vertices_normativos(feature.geometry(), capa.crs())
    n        = len(vertices)
    marcas   = _generar_marcas(n)

    if config.get("usar_colindantes", True):
        colindantes_por_segmento = resolver_colindantes(
            vertices      = vertices,
            fid_principal = feature.id(),
            config        = config
        )
    else:
        colindantes_por_segmento = {}

    geom_9377 = reproyectar_geometry(feature.geometry(), capa.crs())
    segmentos = construir_segmentos(vertices, colindantes_por_segmento, geom_9377)
    grupos    = agrupar_por_cuadrante(segmentos)
    area_m2   = geom_9377.area()

    lineas = []
    lineas.append("ANEXO — DESCRIPCIÓN TÉCNICA DE LINDEROS")
    lineas.append("")
    lineas.append(
        f"El bien inmueble identificado catastralmente con NUPRE/Número Predial "
        f"{nupre_val} y folio de matrícula inmobiliaria {fmi_val}, presenta los "
        f"siguientes linderos referidos al Sistema de Referencia MAGNA-SIRGAS, "
        f"con proyección cartográfica EPSG:9377 \"Sistema de proyección único "
        f"para Colombia\":"
    )
    lineas.append("")

    for cuadrante in CUADRANTES:
        segs = grupos[cuadrante]
        if not segs:
            continue
        lineas.append(f"POR EL {cuadrante}:")
        lineas.append("")
        for seg in segs:
            texto = _texto_segmento(seg, marcas)
            lineas.append(texto)
            lineas.append("")

    lineas.append(
        f"De acuerdo con los anteriores linderos, el área del citado bien "
        f"inmueble es de: {_formato_area(area_m2, es_urbano)}."
    )

    return "\n".join(lineas)


def exportar_txt(feature, config: dict) -> str:
    if not config.get("ruta_salida"):
        raise ValueError("Debes seleccionar una carpeta de salida.")

    nupre_val = _valor_campo(feature, config["campo_nupre"], "")
    fmi_val   = _valor_campo(feature, config["campo_fmi"],   "")

    # Fallback en cascada para nombre de archivo
    if nupre_val and nupre_val != "Sin información":
        identificador = nupre_val
    elif fmi_val and fmi_val != "Sin información":
        identificador = fmi_val
    else:
        identificador = f"FID_{feature.id()}"

    for char in ['/', '\\', ':', '*', '?', '"', '<', '>', '|', ' ', "'", '´']:
        identificador = identificador.replace(char, '_')

    nombre_archivo = f"linderos_{identificador}.txt"
    ruta_completa  = os.path.join(config["ruta_salida"], nombre_archivo)

    # Evita sobreescritura con sufijo numérico
    if os.path.exists(ruta_completa):
        base     = f"linderos_{identificador}"
        contador = 1
        while os.path.exists(
            os.path.join(config["ruta_salida"], f"{base}_{contador}.txt")
        ):
            contador += 1
        ruta_completa = os.path.join(
            config["ruta_salida"], f"{base}_{contador}.txt"
        )

    texto = generar_descripcion(feature, config)

    with open(ruta_completa, "w", encoding="utf-8") as f:
        f.write(texto)

    return ruta_completa
