import math
from qgis.core import (
    QgsGeometry, QgsPointXY, QgsCoordinateReferenceSystem,
    QgsCoordinateTransform, QgsProject, QgsWkbTypes
)


def reproyectar_geometry(geom: QgsGeometry, crs_origen) -> QgsGeometry:
    crs_destino = QgsCoordinateReferenceSystem("EPSG:9377")
    if crs_origen == crs_destino:
        return QgsGeometry(geom)
    transform = QgsCoordinateTransform(crs_origen, crs_destino, QgsProject.instance())
    geom_repr = QgsGeometry(geom)
    geom_repr.transform(transform)
    return geom_repr


def obtener_vertices(geom: QgsGeometry) -> list:
    """Retorna los vértices del anillo exterior (sin vértice de cierre)."""
    vertices = []
    abstract = geom.constGet()
    if geom.isMultipart():
        exterior = abstract.geometryN(0).exteriorRing()
    else:
        exterior = abstract.exteriorRing()
    for i in range(exterior.numPoints() - 1):
        pt = exterior.pointN(i)
        vertices.append(QgsPointXY(pt.x(), pt.y()))
    return vertices


def obtener_anillos_interiores(geom: QgsGeometry) -> list:
    """
    Retorna los anillos interiores de un polígono como lista de listas de QgsPointXY.

    Cada anillo interior se entrega sin el vértice de cierre (último == primero),
    listo para el mismo pipeline normativo que el anillo exterior:
    asegurar_sentido_horario → punto_noroccidental → reordenar_desde_inicio.

    Para MultiPolygon se usa la parte de mayor área.

    Retorna lista vacía si no hay anillos interiores.
    """
    abstract = geom.constGet()
    if abstract is None:
        return []

    # Seleccionar la parte principal en caso de MultiPolygon
    if geom.isMultipart():
        n_partes = abstract.numGeometries()
        parte_idx = 0
        area_max = 0.0
        for i in range(n_partes):
            parte_geom = QgsGeometry(abstract.geometryN(i).clone())
            area = parte_geom.area()
            if area > area_max:
                area_max = area
                parte_idx = i
        parte = abstract.geometryN(parte_idx)
    else:
        parte = abstract

    n_interiores = parte.numInteriorRings()
    if n_interiores == 0:
        return []

    resultado = []
    for i in range(n_interiores):
        anillo = parte.interiorRing(i)
        pts = []
        # numPoints() incluye el vértice de cierre — se excluye con -1
        for j in range(anillo.numPoints() - 1):
            pt = anillo.pointN(j)
            pts.append(QgsPointXY(pt.x(), pt.y()))
        if len(pts) >= 3:
            resultado.append(pts)

    return resultado


def preparar_vertices_anillo(puntos: list) -> list:
    """
    Aplica el pipeline normativo a una lista cruda de QgsPointXY:
    sentido horario → inicio noroccidental.

    Reutilizable para anillo exterior e interiores.
    """
    pts = asegurar_sentido_horario(puntos)
    idx = punto_noroccidental(pts)
    return reordenar_desde_inicio(pts, idx)


def es_sentido_horario(vertices: list) -> bool:
    area = sum(
        (vertices[i].x() * vertices[(i + 1) % len(vertices)].y()) -
        (vertices[(i + 1) % len(vertices)].x() * vertices[i].y())
        for i in range(len(vertices))
    )
    return area < 0


def asegurar_sentido_horario(vertices: list) -> list:
    if not es_sentido_horario(vertices):
        return list(reversed(vertices))
    return vertices


def punto_noroccidental(vertices: list) -> int:
    idx = 0
    for i, pt in enumerate(vertices):
        mejor = vertices[idx]
        if pt.y() > mejor.y() or (pt.y() == mejor.y() and pt.x() < mejor.x()):
            idx = i
    return idx


def reordenar_desde_inicio(vertices: list, idx_inicio: int) -> list:
    return vertices[idx_inicio:] + vertices[:idx_inicio]


def calcular_azimut(p1: QgsPointXY, p2: QgsPointXY) -> float:
    dx = p2.x() - p1.x()
    dy = p2.y() - p1.y()
    return math.degrees(math.atan2(dx, dy)) % 360


def azimut_a_sentido(azimut: float) -> str:
    if 0 <= azimut < 90:
        return "noreste"
    elif 90 <= azimut < 180:
        return "sureste"
    elif 180 <= azimut < 270:
        return "suroeste"
    else:
        return "noroeste"


def calcular_distancia(p1: QgsPointXY, p2: QgsPointXY) -> float:
    dx = p2.x() - p1.x()
    dy = p2.y() - p1.y()
    return round(math.sqrt(dx ** 2 + dy ** 2), 1)


def preparar_vertices_normativos(geom: QgsGeometry, crs_capa) -> list:
    """Pipeline normativo completo para el anillo exterior."""
    geom_proy = reproyectar_geometry(geom, crs_capa)
    vertices  = obtener_vertices(geom_proy)
    vertices  = asegurar_sentido_horario(vertices)
    idx       = punto_noroccidental(vertices)
    return reordenar_desde_inicio(vertices, idx)


def preparar_anillos_interiores_normativos(geom: QgsGeometry, crs_capa) -> list:
    """
    Retorna lista de listas de vértices, una por anillo interior,
    con el mismo pipeline normativo que el exterior:
    reproyección → sentido horario → inicio noroccidental.

    Retorna lista vacía si el predio no tiene anillos interiores.
    """
    geom_proy   = reproyectar_geometry(geom, crs_capa)
    anillos_raw = obtener_anillos_interiores(geom_proy)
    return [preparar_vertices_anillo(anillo) for anillo in anillos_raw]
