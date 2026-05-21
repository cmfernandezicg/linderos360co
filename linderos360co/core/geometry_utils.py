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
    geom_proy = reproyectar_geometry(geom, crs_capa)
    vertices  = obtener_vertices(geom_proy)
    vertices  = asegurar_sentido_horario(vertices)
    idx       = punto_noroccidental(vertices)
    return reordenar_desde_inicio(vertices, idx)
