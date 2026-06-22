"""
layout/pdf_generator.py

Generador de planos PDF usando plantilla .qpt + variables de proyecto.
Estrategia:
  1. Cargar plantilla plantilla_linderos.qpt
  2. Inyectar variables @linderos_* al proyecto
  3. Crear capas temporales (predio, colindantes, vértices, segmentos)
  4. Vincular capas al mapa_principal
  5. Configurar barra_escala y logo
  6. Reconstruir leyenda_convenciones
  7. Exportar PDF
  8. Limpiar (variables y capas temporales)

QGIS 4.x / PyQt6 — Cambios respecto a v1.x:
  - QIODevice.ReadOnly → QIODevice.OpenModeFlag.ReadOnly
  - QgsUnitTypes.DistanceMeters → Qgis.DistanceUnit.Meters
  - QgsUnitTypes.LayoutMillimeters → Qgis.LayoutUnit.Millimeters
  - QgsLayoutPoint/QgsLayoutSize: unidad como Qgis.LayoutUnit.Millimeters
"""

import os
import math as _math
from datetime import datetime

from qgis.core import (
    Qgis,
    QgsProject, QgsPrintLayout, QgsReadWriteContext,
    QgsLayoutExporter, QgsLayoutItemMap,
    QgsLayoutItemScaleBar, QgsLayoutItemPicture,
    QgsLayoutPoint, QgsLayoutSize,
    QgsCoordinateReferenceSystem, QgsCoordinateTransform,
    QgsGeometry, QgsRectangle,
    QgsRasterLayer, QgsVectorLayer, QgsFeature,
)
from qgis.PyQt.QtCore import QFile, QIODevice
from qgis.PyQt.QtXml import QDomDocument

from .capas_temporales import preparar_capas_layout, construir_leyenda, limpiar_capas_temporales

# ------------------------------------------------------------------ Constantes

_CRS_STR        = "EPSG:9377"
_RUTA_PLANTILLA = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "resources", "plantilla_linderos.qpt"
)

_VALORES_NULOS = {"", "NULL", "None", "null", "nan", "NaN", "none"}


# ------------------------------------------------------------------ Helpers

def _valor_campo(feature, campo: str) -> str:
    """Lee un campo del feature y retorna string limpio o 'Sin información'."""
    if not campo:
        return "Sin información"
    try:
        v = feature[campo]
        s = str(v).strip() if v is not None else ""
        return s if s not in _VALORES_NULOS else "Sin información"
    except Exception:
        return "Sin información"


def _formato_area(area_m2: float, es_urbano: bool) -> str:
    if es_urbano:
        return f"{area_m2:.2f} m²"
    else:
        hectareas = int(area_m2 // 10000)
        residuo   = area_m2 % 10000
        return f"{hectareas} ha y {residuo:.2f} m²"


def _nombre_archivo(feature, config: dict) -> str:
    """
    Genera el nombre del archivo PDF con fallback NUPRE → FMI → FID.
    Agrega sufijo numérico si ya existe.
    """
    _CHARS_INVALIDOS = ['/', '\\', ':', '*', '?', '"', '<', '>', '|', ' ', "'", '´']

    valor = ""
    for campo_key in ("campo_nupre", "campo_fmi"):
        campo = config.get(campo_key)
        if campo:
            v = _valor_campo(feature, campo)
            if v != "Sin información":
                valor = v
                break

    if not valor:
        valor = f"FID_{feature.id()}"

    for char in _CHARS_INVALIDOS:
        valor = valor.replace(char, "_")

    base     = f"plano_{valor}"
    ruta_pdf = os.path.join(config["ruta_salida"], f"{base}.pdf")

    if os.path.exists(ruta_pdf):
        cnt = 1
        while os.path.exists(os.path.join(config["ruta_salida"], f"{base}_{cnt}.pdf")):
            cnt += 1
        ruta_pdf = os.path.join(config["ruta_salida"], f"{base}_{cnt}.pdf")

    return ruta_pdf


# ------------------------------------------------------------------ Carga QPT

def _cargar_plantilla(proyecto: QgsProject) -> QgsPrintLayout:
    """Carga la plantilla .qpt y retorna el layout listo para usar."""
    if not os.path.exists(_RUTA_PLANTILLA):
        raise FileNotFoundError(
            f"Plantilla no encontrada: {_RUTA_PLANTILLA}\n"
            f"Coloca 'plantilla_linderos.qpt' en la carpeta 'resources/' del plugin."
        )

    doc = QDomDocument()
    archivo = QFile(_RUTA_PLANTILLA)
    # QGIS 4.x / PyQt6: QIODevice.ReadOnly → QIODevice.OpenModeFlag.ReadOnly
    if not archivo.open(QIODevice.OpenModeFlag.ReadOnly):
        raise IOError(f"No se pudo abrir la plantilla: {_RUTA_PLANTILLA}")
    doc.setContent(archivo)
    archivo.close()

    layout = QgsPrintLayout(proyecto)
    layout.setName("linderos_layout_temp")
    layout.initializeDefaults()

    nodo_layout = doc.elementsByTagName("Layout").at(0).toElement()
    contexto    = QgsReadWriteContext()
    ok          = layout.readXml(nodo_layout, doc, contexto)

    if not ok:
        raise RuntimeError(
            f"No se pudo parsear la plantilla .qpt: {_RUTA_PLANTILLA}\n"
            f"Verifica que el archivo no esté corrupto."
        )

    return layout


# ------------------------------------------------------------------ Variables proyecto

def _construir_variables(feature, config: dict,
                          area_m2: float, escala: float) -> dict:
    """
    Construye el dict completo de variables @linderos_* para el proyecto.
    """
    variables = {}

    variables["linderos_empresa"]   = config.get("pdf_empresa", "").strip()  or "Sin información"
    variables["linderos_titulo"]    = config.get("pdf_titulo", "").strip()   or "Sin información"
    variables["linderos_elaborado"] = config.get("pdf_elaborado", "").strip() or "Sin información"
    variables["linderos_uso"]       = config.get("pdf_uso", "").strip()      or "Sin información"
    variables["linderos_fecha"]     = datetime.now().strftime("%B de %Y")
    variables["linderos_escala"]    = f"1:{int(escala):,}".replace(",", ".")
    variables["linderos_area"]      = _formato_area(area_m2, config.get("es_urbano", False))

    lineas = []
    for campo_cfg in config.get("pdf_campos", []):
        etiqueta = campo_cfg.get("etiqueta", "").strip()
        campo    = campo_cfg.get("campo")
        if not etiqueta:
            continue
        valor = _valor_campo(feature, campo) if campo else ""
        if valor and valor != "Sin información":
            lineas.append(f"{etiqueta}: {valor}")

    lineas.append(f"Área: {variables['linderos_area']}")
    variables["linderos_datos_predio"] = "\n".join(lineas)

    return variables


def _inyectar_variables(proyecto: QgsProject, variables: dict) -> dict:
    previas  = proyecto.customVariables()
    actuales = dict(previas)
    actuales.update(variables)
    proyecto.setCustomVariables(actuales)
    return previas


def _restaurar_variables(proyecto: QgsProject, previas: dict) -> None:
    proyecto.setCustomVariables(previas)


# ------------------------------------------------------------------ Configuración items

def _configurar_mapa_principal(layout, capas: dict,
                                bbox_con_margen: QgsRectangle) -> QgsLayoutItemMap:
    """Vincula capas, extensión, CRS y grid al mapa principal."""
    mapa = layout.itemById("mapa_principal")
    if mapa is None:
        raise RuntimeError("No se encontró el item 'mapa_principal' en la plantilla.")

    orden_capas = [
        capas["colindantes"],
        capas["segmentos"],
        capas["predio"],
        capas["vertices"],
    ]
    mapa.setLayers(orden_capas)
    mapa.setKeepLayerSet(True)
    mapa.setKeepLayerStyles(True)
    mapa.setCrs(QgsCoordinateReferenceSystem(_CRS_STR))
    mapa.zoomToExtent(bbox_con_margen)
    mapa.refresh()

    ancho_m    = bbox_con_margen.width()
    intervalos = [5, 10, 20, 50, 100, 200, 250, 500, 1000, 2000, 5000, 10000]
    intervalo  = next((v for v in intervalos if 3 <= ancho_m / v <= 5), None)
    if intervalo is None:
        intervalo = 10 ** len(str(int(ancho_m / 4)))

    grids = mapa.grids()
    if grids.size() > 0:
        grid = grids.grid(0)
        grid.setIntervalX(intervalo)
        grid.setIntervalY(intervalo)
        grid.refresh()

    return mapa


def _crear_capa_basemap() -> QgsRasterLayer:
    """
    Crea una capa XYZ tile de OpenStreetMap para el mapa de localización.
    Retorna None si la capa no es válida (sin conexión).
    """
    uri = (
        "type=xyz"
        "&url=https://tile.openstreetmap.org/{z}/{x}/{y}.png"
        "&zmax=19&zmin=0"
        "&crs=EPSG:3857"
    )
    capa = QgsRasterLayer(uri, "_lind_basemap", "wms")
    if not capa.isValid():
        return None
    return capa


def _configurar_mapa_localizacion(layout, capas: dict,
                                   bbox_predio: object) -> list:
    """
    Mapa de localización con basemap OSM centrado en el predio.
    """
    mapa_loc = layout.itemById("mapa_localizacion")
    if mapa_loc is None:
        return []

    capas_a_limpiar = []

    basemap = _crear_capa_basemap()
    if basemap:
        QgsProject.instance().addMapLayer(basemap, addToLegend=False)
        capas_a_limpiar.append(basemap)
        mapa_loc.setLayers([basemap])
    else:
        mapa_loc.setLayers([])

    mapa_loc.setKeepLayerSet(True)
    mapa_loc.setKeepLayerStyles(True)

    centro   = bbox_predio.center()
    radio    = 3000.0
    bbox_loc = QgsRectangle(
        centro.x() - radio, centro.y() - radio,
        centro.x() + radio, centro.y() + radio
    )
    mapa_loc.zoomToExtent(bbox_loc)
    mapa_loc.refresh()

    return capas_a_limpiar


def _configurar_barra_escala(layout, mapa: QgsLayoutItemMap) -> None:
    """
    Vincula la barra de escala al mapa principal y calcula unitsPerSegment
    para que la barra quepa dentro del ancho del item en la plantilla.
    """
    barra = layout.itemById("barra_escala")
    if barra is None:
        return

    barra.setLinkedMap(mapa)
    # QGIS 4.x: QgsUnitTypes.DistanceMeters → Qgis.DistanceUnit.Meters
    barra.setUnits(Qgis.DistanceUnit.Meters)

    escala_real = mapa.scale()
    if escala_real <= 0:
        return

    barra.setNumberOfSegmentsLeft(0)
    barra.setNumberOfSegments(3)

    ANCHO_MAX_MM = 57.0
    n_segmentos  = 3

    unidades_seg = (ANCHO_MAX_MM * escala_real) / (n_segmentos * 1000)
    if unidades_seg > 0:
        magnitud     = 10 ** (len(str(int(unidades_seg))) - 1)
        unidades_seg = max(_math.floor(unidades_seg / magnitud) * magnitud, 1)
        barra.setUnitsPerSegment(unidades_seg)

    PANEL_CX = 244.0
    BARRA_Y  = 109.239
    barra_x  = PANEL_CX - (ANCHO_MAX_MM / 2)
    # QGIS 4.x: QgsUnitTypes.LayoutMillimeters → Qgis.LayoutUnit.Millimeters
    barra.attemptMove(
        QgsLayoutPoint(barra_x, BARRA_Y, Qgis.LayoutUnit.Millimeters)
    )
    barra.attemptResize(
        QgsLayoutSize(ANCHO_MAX_MM, 9.175, Qgis.LayoutUnit.Millimeters)
    )
    barra.refresh()


def _configurar_logo(layout, config: dict) -> None:
    """Actualiza la ruta del logo y centra el contenido dentro del frame."""
    logo = layout.itemById("logo_empresa")
    if logo is None:
        return

    ruta_logo = config.get("pdf_logo", "").strip()
    if ruta_logo and os.path.exists(ruta_logo):
        logo.setPicturePath(ruta_logo)
        logo.setResizeMode(QgsLayoutItemPicture.ResizeMode.Zoom)
        logo.setPictureAnchor(4)


# ------------------------------------------------------------------ Exportación

def _exportar(layout, ruta_pdf: str) -> None:
    exporter  = QgsLayoutExporter(layout)
    settings  = QgsLayoutExporter.PdfExportSettings()
    resultado = exporter.exportToPdf(ruta_pdf, settings)
    if resultado != QgsLayoutExporter.ExportResult.Success:
        raise RuntimeError(
            f"Error al exportar PDF. Código: {resultado}\n"
            f"Ruta: {ruta_pdf}"
        )


# ------------------------------------------------------------------ Función principal

def generar_pdf(feature, config: dict, iface=None) -> str:
    """
    Genera el plano PDF para un feature usando la plantilla .qpt.

    Args:
        feature: QgsFeature del predio a procesar
        config:  dict de configuración del plugin
        iface:   QgisInterface (no usado directamente, reservado)

    Returns:
        Ruta absoluta del PDF generado.
    """
    from linderos360co.core.geometry_utils import (
        preparar_vertices_normativos,
        preparar_anillos_interiores_normativos,
    )

    proyecto  = QgsProject.instance()
    capa      = config["capa"]
    ruta_pdf  = _nombre_archivo(feature, config)

    # 1. Geometría en EPSG:9377
    crs_9377 = QgsCoordinateReferenceSystem(_CRS_STR)
    geom = feature.geometry()
    if capa.crs().authid() != _CRS_STR:
        transform = QgsCoordinateTransform(capa.crs(), crs_9377, proyecto)
        geom = QgsGeometry(geom)
        geom.transform(transform)

    area_m2 = geom.area()
    bbox    = geom.boundingBox()
    margen  = max(bbox.width(), bbox.height()) * 0.15
    bbox.grow(margen)

    # 2. Vértices (ordenados desde NW, sentido horario)
    vertices           = preparar_vertices_normativos(feature.geometry(), capa.crs())
    anillos_interiores = preparar_anillos_interiores_normativos(feature.geometry(), capa.crs())

    # 3. Capas temporales
    capas = preparar_capas_layout(feature, capa, config, vertices,
                                  anillos_interiores=anillos_interiores)

    # 4. Cargar plantilla
    layout = _cargar_plantilla(proyecto)

    # 5. Configurar mapa principal
    mapa = _configurar_mapa_principal(layout, capas, bbox)

    # 6. Variables de proyecto
    variables = _construir_variables(feature, config, area_m2, mapa.scale())
    previas   = _inyectar_variables(proyecto, variables)

    capas_loc_tmp = []
    try:
        # 7. Resto de items del layout
        capas_loc_tmp = _configurar_mapa_localizacion(layout, capas, bbox)
        _configurar_barra_escala(layout, mapa)
        _configurar_logo(layout, config)
        construir_leyenda(layout, mapa, capas)

        # 8. Exportar
        _exportar(layout, ruta_pdf)

    finally:
        # 9. Limpieza garantizada aunque falle la exportación
        _restaurar_variables(proyecto, previas)
        limpiar_capas_temporales()
        for capa_tmp in capas_loc_tmp:
            try:
                proyecto.removeMapLayer(capa_tmp.id())
            except Exception:
                pass
        proyecto.layoutManager().removeLayout(layout)

    return ruta_pdf
