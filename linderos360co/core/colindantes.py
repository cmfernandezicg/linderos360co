from qgis.core import (
    QgsFeatureRequest, QgsCoordinateTransform,
    QgsCoordinateReferenceSystem, QgsProject,
    QgsGeometry, QgsPointXY, QgsRectangle
)

TOLERANCIA_M = 0.05


def _get_transform(crs_origen, crs_destino_epsg: int = 9377):
    crs_destino = QgsCoordinateReferenceSystem(f"EPSG:{crs_destino_epsg}")
    if crs_origen == crs_destino:
        return None
    return QgsCoordinateTransform(
        crs_origen, crs_destino, QgsProject.instance()
    )


def _get_transform_inverso(crs_capa, crs_destino_epsg: int = 9377):
    """Transforma de EPSG:9377 al CRS de la capa — para el bbox del request."""
    crs_9377 = QgsCoordinateReferenceSystem(f"EPSG:{crs_destino_epsg}")
    if crs_capa == crs_9377:
        return None
    return QgsCoordinateTransform(
        crs_9377, crs_capa, QgsProject.instance()
    )


def _reproyectar_geom(geom: QgsGeometry, crs_origen,
                      crs_destino_epsg: int = 9377) -> QgsGeometry:
    transform = _get_transform(crs_origen, crs_destino_epsg)
    if transform is None:
        return QgsGeometry(geom)
    g = QgsGeometry(geom)
    g.transform(transform)
    return g


def _reproyectar_bbox(bbox: QgsRectangle, crs_capa,
                      crs_destino_epsg: int = 9377) -> QgsRectangle:
    """
    Reproyecta el bbox desde EPSG:9377 al CRS de la capa.
    Necesario para que QgsFeatureRequest filtre correctamente.
    """
    transform = _get_transform_inverso(crs_capa, crs_destino_epsg)
    if transform is None:
        return bbox
    return transform.transformBoundingBox(bbox)


def _segmento_a_geometria(p1: QgsPointXY, p2: QgsPointXY) -> QgsGeometry:
    return QgsGeometry.fromPolylineXY([p1, p2])


def _buscar_colindante_en_capa(geom_segmento: QgsGeometry,
                                capa, fid_excluir: int,
                                campo_nupre: str, campo_fmi: str,
                                campo_elemento: str) -> dict:
    # bbox en 9377 → reproyectado al CRS nativo de la capa para el filtro
    bbox_9377  = geom_segmento.boundingBox()
    bbox_9377.grow(TOLERANCIA_M)
    bbox_capa  = _reproyectar_bbox(bbox_9377, capa.crs())

    request = QgsFeatureRequest().setFilterRect(bbox_capa)

    mejor_candidato = {}
    mejor_longitud  = 0.0

    for candidato in capa.getFeatures(request):
        if candidato.id() == fid_excluir:
            continue

        # Reproyecta la geometría del candidato a 9377 para comparar
        geom_c     = _reproyectar_geom(candidato.geometry(), capa.crs())
        geom_c_buf = geom_c.buffer(TOLERANCIA_M, 5)

        if not geom_segmento.intersects(geom_c_buf):
            continue

        interseccion = geom_segmento.intersection(geom_c_buf)
        if interseccion.isEmpty():
            continue

        longitud = interseccion.length()
        if longitud <= mejor_longitud:
            continue

        mejor_longitud = longitud

        def _leer(campo, feat=candidato):
            if not campo:
                return ""
            try:
                v = feat[campo]
                return str(v).strip() if v is not None else ""
            except Exception:
                return ""

        mejor_candidato = {
            "nupre":    _leer(campo_nupre),
            "fmi":      _leer(campo_fmi),
            "elemento": _leer(campo_elemento),
        }

    return mejor_candidato


def resolver_colindantes(vertices: list, fid_principal: int,
                         config: dict) -> dict:
    capa           = config["capa"]
    campo_nupre    = config["col_nupre"]
    campo_fmi      = config["col_fmi"]
    campo_elemento = config["col_elemento"]

    n         = len(vertices)
    resultado = {}

    for i in range(n):
        p1       = vertices[i]
        p2       = vertices[(i + 1) % n]
        geom_seg = _segmento_a_geometria(p1, p2)

        colindante = _buscar_colindante_en_capa(
            geom_segmento  = geom_seg,
            capa           = capa,
            fid_excluir    = fid_principal,
            campo_nupre    = campo_nupre,
            campo_fmi      = campo_fmi,
            campo_elemento = campo_elemento
        )

        resultado[i] = colindante

    return resultado
