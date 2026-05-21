from qgis.core import QgsPointXY, QgsGeometry
from .geometry_utils import calcular_azimut, azimut_a_sentido, calcular_distancia

CUADRANTES = ["NORTE", "ESTE", "SUR", "OESTE"]


def _distancia(p1: QgsPointXY, p2: QgsPointXY) -> float:
    return ((p1.x() - p2.x()) ** 2 + (p1.y() - p2.y()) ** 2) ** 0.5


def encontrar_vertice_mas_cercano(vertices: list, punto_ref: QgsPointXY) -> int:
    """
    Encuentra el índice del vértice más cercano a punto_ref.
    En empate de distancia, prioriza el de mayor X (más al Este),(p_este_n > p_este).
    """
    idx_min  = 0
    dist_min = _distancia(vertices[0], punto_ref)
    x_min    = vertices[0].x()

    for i, v in enumerate(vertices[1:], 1):
        d = _distancia(v, punto_ref)
        if d < dist_min or (abs(d - dist_min) < 1e-6 and v.x() > x_min):
            dist_min = d
            idx_min  = i
            x_min    = v.x()

    return idx_min


def obtener_puntos_corte(vertices: list, geom: QgsGeometry) -> dict:
    """
    Encuentra los 4 vértices del polígono más cercanos a las
    4 esquinas del bounding box (NW, NE, SE, SW).
    Estos vértices son los puntos de corte entre cuadrantes.

    Returns:
        dict con índices: {"nw": int, "ne": int, "se": int, "sw": int}
    """
    bbox = geom.boundingBox()

    # Esquinas del envelope — mismo orden que ArcGIS:
    # p0=upperLeft(NW), p1=upperRight(NE), p2=lowerRight(SE), p3=lowerLeft(SW)
    esquinas = {
        "nw": QgsPointXY(bbox.xMinimum(), bbox.yMaximum()),
        "ne": QgsPointXY(bbox.xMaximum(), bbox.yMaximum()),
        "se": QgsPointXY(bbox.xMaximum(), bbox.yMinimum()),
        "sw": QgsPointXY(bbox.xMinimum(), bbox.yMinimum()),
    }

    return {
        nombre: encontrar_vertice_mas_cercano(vertices, esquina)
        for nombre, esquina in esquinas.items()
    }


def asignar_cuadrantes(vertices: list, puntos_corte: dict) -> list:
    """
    Asigna cuadrante a cada segmento usando los puntos de corte.

    Lógica de tramos (igual que ArcGIS dump_poly):
      Norte: desde idx_nw hasta idx_ne  (siguiendo orden de la lista)
      Este:  desde idx_ne hasta idx_se
      Sur:   desde idx_se hasta idx_sw
      Oeste: desde idx_sw hasta idx_nw (cierre del perímetro)

    Maneja el caso en que los índices no estén en orden creciente
    (ocurre cuando el polígono fue reordenado desde el noroccidental).
    """
    n   = len(vertices)
    nw  = puntos_corte["nw"]
    ne  = puntos_corte["ne"]
    se  = puntos_corte["se"]
    sw  = puntos_corte["sw"]

    # Construye mapa índice → cuadrante recorriendo los 4 tramos
    cuadrante_por_idx = {}

    tramos = [
        ("NORTE", nw, ne),
        ("ESTE",  ne, se),
        ("SUR",   se, sw),
        ("OESTE", sw, nw),
    ]

    for cuadrante, inicio, fin in tramos:
        if inicio == fin:
            cuadrante_por_idx[inicio] = cuadrante
            continue
        idx = inicio
        while True:
            cuadrante_por_idx[idx] = cuadrante
            if idx == fin:
                break
            idx = (idx + 1) % n

    return cuadrante_por_idx


def construir_segmentos(vertices: list, colindantes_por_segmento: dict,
                        geom: QgsGeometry = None) -> list:
    """
    Construye los segmentos con cuadrante asignado por puntos de corte.
    """
    n              = len(vertices)
    puntos_corte   = obtener_puntos_corte(vertices, geom) if geom else None
    cuadrante_map  = asignar_cuadrantes(vertices, puntos_corte) if puntos_corte else {}

    segmentos = []
    for i in range(n):
        p1     = vertices[i]
        p2     = vertices[(i + 1) % n]
        azimut = calcular_azimut(p1, p2)

        # Cuadrante por punto de corte; fallback por posición si no hay geom
        cuadrante = cuadrante_map.get(i, "NORTE")

        segmentos.append({
            "idx":         i,
            "p_inicio":    p1,
            "p_fin":       p2,
            "azimut":      azimut,
            "cuadrante":   cuadrante,
            "sentido":     azimut_a_sentido(azimut),
            "distancia_m": calcular_distancia(p1, p2),
            "colindante":  colindantes_por_segmento.get(i, {}),
        })
    return segmentos


def agrupar_por_cuadrante(segmentos: list) -> dict:
    grupos   = {c: [] for c in CUADRANTES}
    contador = 1
    for seg in segmentos:
        seg["num_lindero"] = contador
        grupos[seg["cuadrante"]].append(seg)
        contador += 1
    return grupos
