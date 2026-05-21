# -*- coding: utf-8 -*-
from qgis.core import (
    QgsGeometry,
    QgsWkbTypes,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsProject,
)

_CRS_9377 = QgsCoordinateReferenceSystem("EPSG:9377")
_AREA_MINIMA_M2 = 0.01

NIVEL_CRITICO     = "CRITICO"
NIVEL_ERROR       = "ERROR"
NIVEL_ADVERTENCIA = "ADVERTENCIA"


def _extraer_anillos(geom_proy) -> list:
    """
    Extrae los anillos del primer poligono de forma segura para cualquier
    tipo: Polygon, PolygonZ, MultiPolygon, MultiPolygonZ.

    Usa QgsGeometry.constGet() + iteracion sobre partes y anillos para
    obtener vertices XY puros sin depender de asPolygon() ni convertTo(),
    que fallan o crashean con geometrias Z o multipart en QGIS 3.x LTR.
    """
    from qgis.core import QgsPointXY

    try:
        geom_abs = geom_proy.constGet()
        if geom_abs is None:
            return []

        # Detectar si es multipart navegando la coleccion de geometrias
        coleccion = geom_proy.asGeometryCollection()
        if coleccion:
            # Tomar la primera parte como geometria de trabajo
            primera = coleccion[0]
        else:
            primera = geom_proy

        # Extraer vertices del anillo exterior usando vertexAt() sobre
        # indices conocidos — mas seguro que asPolygon() con Z
        n_vertices = primera.constGet().nCoordinates() if primera.constGet() else 0
        if n_vertices == 0:
            return []

        anillo_ext = []
        for i in range(n_vertices):
            v = primera.vertexAt(i)
            anillo_ext.append(QgsPointXY(v.x(), v.y()))

        # vertexAt recorre TODOS los anillos en secuencia; para la validacion
        # basica el anillo exterior completo es suficiente
        return [anillo_ext] if anillo_ext else []

    except Exception:
        return []


def validar_feature(feature, crs_capa) -> list:
    problemas = []
    geom = feature.geometry()

    # -- Nivel 1: geometría básica --
    if geom is None or geom.isEmpty():
        problemas.append((NIVEL_CRITICO, "Geometria nula o vacia"))
        return problemas

    tipo_base = QgsWkbTypes.geometryType(geom.wkbType())
    if tipo_base != QgsWkbTypes.PolygonGeometry:
        tipo_str = QgsWkbTypes.displayString(geom.wkbType())
        problemas.append((NIVEL_CRITICO,
            "La geometria no es un poligono (tipo: " + tipo_str + ")"))
        return problemas

    # Reproyectar a EPSG:9377
    transform = QgsCoordinateTransform(crs_capa, _CRS_9377, QgsProject.instance())
    geom_proy = QgsGeometry(geom)
    geom_proy.transform(transform)

    # -- Nivel 2: validez OGC --
    if not geom_proy.isGeosValid():
        errores_geos = geom_proy.validateGeometry()
        for error in errores_geos:
            problemas.append((NIVEL_ERROR,
                "Geometria invalida OGC: " + error.what()))

    area = geom_proy.area()
    if area <= _AREA_MINIMA_M2:
        problemas.append((NIVEL_ERROR,
            "Area igual o menor a cero (" + str(round(area, 4)) + " m2)"))

    # -- Nivel 3: reglas topológicas --
    anillos = _extraer_anillos(geom_proy)
    if not anillos:
        problemas.append((NIVEL_ADVERTENCIA,
            "No fue posible extraer el anillo exterior para validacion detallada"))
        return problemas

    vertices = anillos[0]
    n = len(vertices)

    # Cierre del anillo exterior
    if n >= 2:
        p_ini = vertices[0]
        p_fin = vertices[-1]
        if abs(p_ini.x() - p_fin.x()) > 1e-6 or abs(p_ini.y() - p_fin.y()) > 1e-6:
            problemas.append((NIVEL_ADVERTENCIA,
                "El anillo exterior no esta cerrado correctamente"))

    # Vértices duplicados consecutivos
    duplicados = 0
    for i in range(n - 1):
        if (abs(vertices[i].x() - vertices[i + 1].x()) < 1e-8 and
                abs(vertices[i].y() - vertices[i + 1].y()) < 1e-8):
            duplicados += 1
    if duplicados > 0:
        problemas.append((NIVEL_ADVERTENCIA,
            str(duplicados) + " vertice(s) duplicado(s) consecutivo(s) detectado(s)"))

    # Mínimo de vértices únicos
    n_validos = n - 1
    if n_validos < 3:
        problemas.append((NIVEL_ERROR,
            "El poligono tiene solo " + str(n_validos) +
            " vertice(s) unicos; minimo requerido: 3"))

    # Anillos interiores
    if len(anillos) > 1:
        n_huecos = len(anillos) - 1
        problemas.append((NIVEL_ADVERTENCIA,
            "El poligono tiene " + str(n_huecos) +
            " anillo(s) interior(es) (huecos). " +
            "El plugin procesa unicamente el anillo exterior."))

    return problemas


def validar_features(features, crs_capa) -> dict:
    """
    Valida todos los features. Retorna {fid: [problemas]} solo para
    los que tienen al menos un problema.
    """
    resultado = {}
    for feature in features:
        problemas = validar_feature(feature, crs_capa)
        if problemas:
            resultado[feature.id()] = problemas
    return resultado


def tiene_bloqueantes(problemas_feature: list) -> bool:
    """True si hay al menos un CRITICO o ERROR."""
    return any(nivel in (NIVEL_CRITICO, NIVEL_ERROR) for nivel, _ in problemas_feature)


def resumen_validacion(resultado: dict, features) -> str:
    """Texto del dialogo de advertencia previo al procesamiento."""
    fid_a_label = {f.id(): str(f.id()) for f in features}
    total = len(resultado)

    lineas = [
        "Se detectaron problemas topologicos en " + str(total) + " predio(s):",
        "",
    ]
    prefijos = {
        NIVEL_CRITICO:     "[X] CRITICO     ",
        NIVEL_ERROR:       "[!] ERROR       ",
        NIVEL_ADVERTENCIA: "[?] ADVERTENCIA ",
    }
    for fid, problemas in resultado.items():
        lineas.append("Predio FID " + fid_a_label.get(fid, str(fid)) + ":")
        for nivel, mensaje in problemas:
            lineas.append("  " + prefijos[nivel] + mensaje)
        lineas.append("")

    lineas.append("---")
    lineas.append("[X] CRITICO / [!] ERROR    -> puede producir resultados incorrectos.")
    lineas.append("[?] ADVERTENCIA            -> procesamiento posible con limitaciones.")
    lineas.append("")
    lineas.append("Desea continuar de todas formas?")
    return "\n".join(lineas)