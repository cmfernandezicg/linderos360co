"""
layout/capas_temporales.py

Crea y gestiona las capas temporales en memoria que se inyectan
al layout PDF. Cada ejecución limpia las capas anteriores antes
de crear las nuevas.
"""

from qgis.core import (
    QgsVectorLayer, QgsFeature, QgsGeometry, QgsPointXY,
    QgsProject, QgsField, QgsFields,
    QgsCoordinateReferenceSystem, QgsCoordinateTransform,
    QgsFillSymbol, QgsLineSymbol, QgsMarkerSymbol,
    QgsSingleSymbolRenderer,
    QgsPalLayerSettings, QgsVectorLayerSimpleLabeling,
    QgsTextFormat, QgsUnitTypes,
    QgsLayerTreeLayer, QgsLayoutItemLegend,
    QgsMapLayerLegendUtils, QgsLabelObstacleSettings,
)
from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtGui import QColor, QFont

# ------------------------------------------------------------------ Constantes

_CRS_STR  = "EPSG:9377"
_CRS_9377 = QgsCoordinateReferenceSystem(_CRS_STR)

_NOMBRE_PREDIO      = "_lind_predio"
_NOMBRE_COLINDANTES = "_lind_colindantes"
_NOMBRE_VERTICES    = "_lind_vertices"
_NOMBRE_SEGMENTOS   = "_lind_segmentos"

_NOMBRES_TEMPORALES = {
    _NOMBRE_PREDIO,
    _NOMBRE_COLINDANTES,
    _NOMBRE_VERTICES,
    _NOMBRE_SEGMENTOS,
    "_lind_basemap",
}

_ETIQUETAS_LEYENDA = {
    _NOMBRE_PREDIO:       "Predio",
    _NOMBRE_COLINDANTES:  "Predios colindantes",
    _NOMBRE_VERTICES:     "Vértices",
    _NOMBRE_SEGMENTOS:    "Linderos",
}

_NULOS = {"", "NULL", "None", "null", "nan", "NaN"}


# ------------------------------------------------------------------ Limpieza

def limpiar_capas_temporales() -> None:
    """Elimina del proyecto las capas temporales de ejecuciones anteriores."""
    proyecto = QgsProject.instance()
    ids_eliminar = [
        capa_id
        for capa_id, capa in proyecto.mapLayers().items()
        if capa.name() in _NOMBRES_TEMPORALES
        or (capa.name().startswith("_lind_") and capa.name().endswith("_loc"))
    ]
    for capa_id in ids_eliminar:
        proyecto.removeMapLayer(capa_id)


# ------------------------------------------------------------------ Helpers

def _reproyectar(geom: QgsGeometry, crs_origen) -> QgsGeometry:
    if crs_origen.authid() == _CRS_STR:
        return QgsGeometry(geom)
    transform = QgsCoordinateTransform(crs_origen, _CRS_9377, QgsProject.instance())
    geom_out  = QgsGeometry(geom)
    geom_out.transform(transform)
    return geom_out


def _fuente(tamanio: int, negrita: bool = False) -> QFont:
    f = QFont("Arial", tamanio)
    f.setBold(negrita)
    return f


def _fmt_texto(tamanio: int, color: QColor = QColor(0, 0, 0)) -> QgsTextFormat:
    fmt = QgsTextFormat()
    fmt.setFont(_fuente(tamanio))
    fmt.setSize(tamanio)
    fmt.setSizeUnit(QgsUnitTypes.RenderPoints)
    fmt.setColor(color)
    return fmt


def _agregar_al_proyecto(capa: QgsVectorLayer) -> None:
    QgsProject.instance().addMapLayer(capa, addToLegend=False)


def _campos_desde_pdf(config: dict) -> tuple:
    """
    Extrae los campos identificadores del predio desde pdf_campos.
    Retorna (campo_nupre, campo_fmi, campo_nombre) leyendo la tabla
    del módulo PDF por etiquetas conocidas.
    Usado como fallback cuando el módulo TXT no está activo.
    """
    _ETIQUETAS_NUPRE  = {"céd. catastral", "cedula catastral", "nupre", "cédula"}
    _ETIQUETAS_FMI    = {"matrícula", "matricula", "fmi", "folio"}
    _ETIQUETAS_NOMBRE = {"nombre", "name"}

    campo_nupre  = None
    campo_fmi    = None
    campo_nombre = None

    for campo_cfg in config.get("pdf_campos", []):
        etiqueta = campo_cfg.get("etiqueta", "").strip().lower()
        campo    = campo_cfg.get("campo")
        if not campo:
            continue
        if any(e in etiqueta for e in _ETIQUETAS_NUPRE):
            campo_nupre = campo_nupre or campo
        elif any(e in etiqueta for e in _ETIQUETAS_FMI):
            campo_fmi = campo_fmi or campo
        elif any(e in etiqueta for e in _ETIQUETAS_NOMBRE):
            campo_nombre = campo_nombre or campo

    return campo_nupre, campo_fmi, campo_nombre

def _crear_capa_predio(geom_9377: QgsGeometry, config: dict,
                       feature) -> QgsVectorLayer:
    """
    Crea la capa del predio principal.
    Etiqueta: nombre + FMI/NUPRE según campos mapeados + área calculada.
    """
    capa = QgsVectorLayer(
        f"Polygon?crs={_CRS_STR}&field=etiqueta:string",
        _NOMBRE_PREDIO, "memory"
    )

    # Campos desde módulo TXT; fallback a pdf_campos si TXT no está activo
    campo_nupre_cfg, campo_fmi_cfg, campo_nombre_cfg = _campos_desde_pdf(config)

    partes = []
    for campo_key, campo_fallback in (
        ("campo_nombre", campo_nombre_cfg),
        ("campo_fmi",    campo_fmi_cfg),
        ("campo_nupre",  campo_nupre_cfg),
    ):
        campo = config.get(campo_key) or campo_fallback
        if campo:
            try:
                v = feature[campo]
                s = str(v).strip() if v is not None else ""
                if s and s not in _NULOS:
                    partes.append(s)
            except Exception:
                pass

    # Área siempre incluida — calculada desde geometría reproyectada
    area_m2   = geom_9377.area()
    es_urbano = config.get("es_urbano", False)
    if es_urbano:
        area_str = f"Área: {area_m2:.2f} m²"
    else:
        ha       = int(area_m2 // 10000)
        residuo  = area_m2 % 10000
        area_str = f"Área: {ha} ha y {residuo:.2f} m²"
    partes.append(area_str)

    etiqueta = "\n".join(partes)

    feat = QgsFeature()
    feat.setGeometry(geom_9377)
    feat.setAttributes([etiqueta])
    capa.dataProvider().addFeature(feat)
    capa.updateExtents()

    simbolo = QgsFillSymbol.createSimple({
        "color":         "255,255,255,0",
        "outline_color": "220,50,50,255",
        "outline_width": "0.8",
        "style":         "solid",
    })
    capa.setRenderer(QgsSingleSymbolRenderer(simbolo))

    pal = QgsPalLayerSettings()
    pal.fieldName  = "etiqueta"
    # Horizontal: QGIS busca el mejor punto libre dentro del polígono
    pal.placement  = QgsPalLayerSettings.Placement.Horizontal
    pal.displayAll = True
    pal.priority   = 8  # prioridad alta — es el predio principal
    pal.setFormat(_fmt_texto(6, QColor(180, 0, 0)))
    capa.setLabeling(QgsVectorLayerSimpleLabeling(pal))
    capa.setLabelsEnabled(True)

    return capa


# ------------------------------------------------------------------ Capa colindantes

def _crear_capa_colindantes(feature, capa_origen, config: dict) -> QgsVectorLayer:
    """
    Busca colindantes que intersecten el predio y crea la capa temporal.
    Etiqueta: campos mapeados (col_nupre/col_fmi) → campos del predio
    como fallback → primer campo string con valor como último recurso.
    """
    from linderos_plugin.core.colindantes import TOLERANCIA_M
    from qgis.core import QgsFeatureRequest

    capa = QgsVectorLayer(
        f"Polygon?crs={_CRS_STR}&field=etiqueta:string",
        _NOMBRE_COLINDANTES, "memory"
    )
    prov = capa.dataProvider()

    geom_principal = _reproyectar(feature.geometry(), capa_origen.crs())

    bbox = geom_principal.boundingBox()
    bbox.grow(TOLERANCIA_M + 1.0)

    if capa_origen.crs().authid() != _CRS_STR:
        tr_inv    = QgsCoordinateTransform(_CRS_9377, capa_origen.crs(), QgsProject.instance())
        bbox_capa = tr_inv.transformBoundingBox(bbox)
    else:
        bbox_capa = bbox

    # Preferir campos de colindantes → campos del predio → pdf_campos
    _nupre_pdf, _fmi_pdf, _ = _campos_desde_pdf(config)
    campo_nupre = config.get("col_nupre") or config.get("campo_nupre") or _nupre_pdf
    campo_fmi   = config.get("col_fmi")   or config.get("campo_fmi")   or _fmi_pdf

    feats = []
    for candidato in capa_origen.getFeatures(QgsFeatureRequest().setFilterRect(bbox_capa)):
        if candidato.id() == feature.id():
            continue

        geom_c = _reproyectar(candidato.geometry(), capa_origen.crs())
        if not geom_principal.intersects(geom_c.buffer(TOLERANCIA_M, 5)):
            continue

        # Intentar campos mapeados
        nupre = ""
        fmi   = ""
        try:
            if campo_nupre:
                v     = candidato[campo_nupre]
                nupre = str(v).strip() if v is not None else ""
            if campo_fmi:
                v   = candidato[campo_fmi]
                fmi = str(v).strip() if v is not None else ""
        except Exception:
            pass

        etiqueta = ""
        if nupre and nupre not in _NULOS:
            etiqueta = nupre
        if fmi and fmi not in _NULOS:
            etiqueta += f"\n{fmi}" if etiqueta else fmi

        # Fallback: primer campo string con valor significativo
        if not etiqueta:
            for field in capa_origen.fields():
                if field.isNumeric():
                    continue
                try:
                    v = candidato[field.name()]
                    s = str(v).strip() if v is not None else ""
                    if s and s not in _NULOS and len(s) > 2:
                        etiqueta = s
                        break
                except Exception:
                    continue

        feat = QgsFeature()
        feat.setGeometry(geom_c)
        feat.setAttributes([etiqueta])
        feats.append(feat)

    prov.addFeatures(feats)
    capa.updateExtents()

    simbolo = QgsFillSymbol.createSimple({
        "color":         "200,220,240,80",
        "outline_color": "80,120,180,200",
        "outline_width": "0.3",
        "style":         "solid",
    })
    capa.setRenderer(QgsSingleSymbolRenderer(simbolo))

    pal = QgsPalLayerSettings()
    pal.fieldName  = "etiqueta"
    # Horizontal: busca espacio libre dentro del polígono colindante
    pal.placement  = QgsPalLayerSettings.Placement.Horizontal
    pal.displayAll = False
    pal.priority   = 3  # prioridad baja — cede ante vértices y distancias

    obs = QgsLabelObstacleSettings()
    obs.setIsObstacle(True)
    obs.setFactor(0.5)
    pal.setObstacleSettings(obs)

    pal.setFormat(_fmt_texto(5, QColor(60, 60, 60)))
    capa.setLabeling(QgsVectorLayerSimpleLabeling(pal))
    capa.setLabelsEnabled(True)

    return capa


# ------------------------------------------------------------------ Capa vértices

def _crear_capa_vertices(vertices: list, escala: float = 1000.0) -> QgsVectorLayer:
    """
    vertices: lista de QgsPointXY en EPSG:9377, ordenados desde NW.
    Filtra etiquetas según escala del mapa: mínimo 3mm entre etiquetas en papel.
    """
    # 3mm en papel convertidos a metros según escala
    DIST_MIN_LABEL = max(3.0 * escala / 1000.0, 5.0)

    campos = QgsFields()
    campos.append(QgsField("etiqueta", QVariant.String))

    capa = QgsVectorLayer(f"Point?crs={_CRS_STR}", _NOMBRE_VERTICES, "memory")
    capa.dataProvider().addAttributes(campos)
    capa.updateFields()

    feats = []
    vertices_etiquetados = []

    for i, v in enumerate(vertices):
        demasiado_cerca = any(
            ((v.x() - vp.x()) ** 2 + (v.y() - vp.y()) ** 2) ** 0.5 < DIST_MIN_LABEL
            for vp in vertices_etiquetados
        )
        feat = QgsFeature()
        feat.setGeometry(QgsGeometry.fromPointXY(v))
        etiqueta = f"P{i + 1}" if not demasiado_cerca else ""
        feat.setAttributes([etiqueta])
        feats.append(feat)
        if not demasiado_cerca:
            vertices_etiquetados.append(v)

    capa.dataProvider().addFeatures(feats)
    capa.updateExtents()

    simbolo = QgsMarkerSymbol.createSimple({
        "name":          "circle",
        "color":         "220,50,50,255",
        "outline_style": "no",
        "size":          "1.5",
    })
    capa.setRenderer(QgsSingleSymbolRenderer(simbolo))

    pal = QgsPalLayerSettings()
    pal.fieldName  = "etiqueta"
    pal.placement  = QgsPalLayerSettings.Placement.OrderedPositionsAroundPoint
    pal.dist       = 1.0
    pal.displayAll = False
    pal.setFormat(_fmt_texto(6))
    capa.setLabeling(QgsVectorLayerSimpleLabeling(pal))
    capa.setLabelsEnabled(True)

    return capa


# ------------------------------------------------------------------ Capa segmentos

def _crear_capa_segmentos(vertices: list) -> QgsVectorLayer:
    """
    Crea segmentos entre vértices consecutivos con etiqueta de distancia.
    Solo etiqueta segmentos >= 10m para evitar ruido visual.
    """
    LONG_MIN_LABEL = 10.0

    campos = QgsFields()
    campos.append(QgsField("distancia", QVariant.String))

    capa = QgsVectorLayer(f"LineString?crs={_CRS_STR}", _NOMBRE_SEGMENTOS, "memory")
    capa.dataProvider().addAttributes(campos)
    capa.updateFields()

    n     = len(vertices)
    feats = []
    for i in range(n):
        p1   = vertices[i]
        p2   = vertices[(i + 1) % n]
        dist = ((p2.x() - p1.x()) ** 2 + (p2.y() - p1.y()) ** 2) ** 0.5
        feat = QgsFeature()
        feat.setGeometry(QgsGeometry.fromPolylineXY([p1, p2]))
        etiqueta = f"{dist:.1f}m" if dist >= LONG_MIN_LABEL else ""
        feat.setAttributes([etiqueta])
        feats.append(feat)

    capa.dataProvider().addFeatures(feats)
    capa.updateExtents()

    simbolo = QgsLineSymbol.createSimple({
        "line_style":  "solid",
        "line_color":  "180,0,0,255",
        "line_width":  "0.4",
    })
    capa.setRenderer(QgsSingleSymbolRenderer(simbolo))

    pal = QgsPalLayerSettings()
    pal.fieldName  = "distancia"
    pal.placement  = QgsPalLayerSettings.Placement.Curved
    pal.displayAll = False
    pal.setFormat(_fmt_texto(5, QColor(100, 0, 0)))
    capa.setLabeling(QgsVectorLayerSimpleLabeling(pal))
    capa.setLabelsEnabled(True)

    return capa


# ------------------------------------------------------------------ Leyenda

def construir_leyenda(layout, mapa_principal, capas: dict) -> None:
    """
    Reconstruye el modelo de la leyenda existente en el layout (.qpt)
    con las capas temporales del plugin. Preserva posición y tamaño.
    Desactiva resizeToContents para evitar desborde del panel.
    """
    leyenda = layout.itemById("leyenda_convenciones")
    if leyenda is None:
        return

    leyenda.setLinkedMap(mapa_principal)
    leyenda.setAutoUpdateModel(False)

    # Desactivar auto-resize — evita que la leyenda desborde el panel
    leyenda.setResizeToContents(False)

    # Fijar tamaño máximo seguro dentro del panel (panel termina en y=211mm)
    from qgis.core import QgsLayoutSize, QgsUnitTypes
    LEYENDA_H_MAX = 55.0  # mm — espacio disponible hasta el fondo del panel
    leyenda.attemptResize(
        QgsLayoutSize(40.0, LEYENDA_H_MAX, QgsUnitTypes.LayoutMillimeters)
    )

    root = leyenda.model().rootGroup()
    root.clear()

    orden = ["predio", "colindantes", "segmentos", "vertices"]
    for key in orden:
        capa = capas.get(key)
        if capa is None:
            continue
        nodo = QgsLayerTreeLayer(capa)
        QgsMapLayerLegendUtils.setLegendNodeUserLabel(
            nodo, 0, _ETIQUETAS_LEYENDA[capa.name()]
        )
        root.addChildNode(nodo)

    from qgis.core import QgsLegendStyle
    leyenda.setStyleFont(QgsLegendStyle.Style.Title,       _fuente(7, negrita=True))
    leyenda.setStyleFont(QgsLegendStyle.Style.Group,       _fuente(6))
    leyenda.setStyleFont(QgsLegendStyle.Style.Subgroup,    _fuente(6))
    leyenda.setStyleFont(QgsLegendStyle.Style.SymbolLabel, _fuente(6))

    leyenda.setStyleMargin(QgsLegendStyle.Style.Title,       2.0)
    leyenda.setStyleMargin(QgsLegendStyle.Style.Symbol,      1.5)
    leyenda.setStyleMargin(QgsLegendStyle.Style.SymbolLabel, 1.5)

    leyenda.setTitle("")
    leyenda.setSymbolWidth(5.0)
    leyenda.setSymbolHeight(3.5)

    leyenda.refresh()


# ------------------------------------------------------------------ Punto de entrada

def preparar_capas_layout(feature, capa_origen, config: dict,
                          vertices: list) -> dict:
    """
    Punto de entrada único. Limpia capas anteriores, crea las 4 capas
    temporales, las agrega al proyecto (sin mostrar en panel) y retorna el dict.

    Args:
        feature:      QgsFeature del predio principal
        capa_origen:  QgsVectorLayer fuente
        config:       dict de configuración del plugin
        vertices:     lista de QgsPointXY en EPSG:9377

    Returns:
        dict con keys: 'predio', 'colindantes', 'vertices', 'segmentos'
    """
    limpiar_capas_temporales()

    geom_9377 = _reproyectar(feature.geometry(), capa_origen.crs())

    capas = {
        "predio":      _crear_capa_predio(geom_9377, config, feature),
        "colindantes": _crear_capa_colindantes(feature, capa_origen, config),
        "vertices":    _crear_capa_vertices(vertices),
        "segmentos":   _crear_capa_segmentos(vertices),
    }

    for capa in capas.values():
        _agregar_al_proyecto(capa)

    return capas