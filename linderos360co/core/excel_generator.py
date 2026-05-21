# -*- coding: utf-8 -*-
"""
excel_generator.py
==================
Módulo de exportación de coordenadas de vértices a formato .xlsx.

Hoja "Vértices":
    N° | Marca | Norte (m) | Este (m) | Latitud (°) | Longitud (°) | Distancia (m) | Azimut (°)

Precisión:
    - Norte / Este  : 4 decimales  (EPSG:9377, consistente con módulo TXT)
    - Latitud / Lon : 6 decimales  (EPSG:4326, ~0.1 m catastral)
    - Distancia     : 1 decimal    (decímetro, según normativa IGAC)
    - Azimut        : 4 decimales  (grados decimales)

El orden de vértices es normativo: inicio en vértice noroccidental, sentido horario.
La última fila (punto de cierre) no incluye Distancia ni Azimut.
La fila de totales muestra el conteo de vértices y la suma de distancias perimetrales.

Lógica de nombre de archivo
---------------------------
Cuando el módulo TXT está activo junto con Excel, se reutilizan los campos
"campo_nupre" y "campo_fmi" ya mapeados — el usuario no necesita mapear dos veces.
Cuando el módulo TXT está desactivado, se usan "campo_nupre_xlsx" / "campo_fmi_xlsx"
propios del tab Excel. Fallback final: FID del feature.
"""

import os
from typing import Optional

from qgis.core import (
    QgsFeature,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsProject,
)

try:
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter
    OPENPYXL_OK = True
except ImportError:
    OPENPYXL_OK = False

from ..core.geometry_utils import (
    reproyectar_geometry,
    obtener_vertices,
    asegurar_sentido_horario,
    punto_noroccidental,
    reordenar_desde_inicio,
    calcular_azimut,
    calcular_distancia,
)

# ---------------------------------------------------------------------------
# Constantes de precisión
# ---------------------------------------------------------------------------
_DECIMALES_PLANAS = 4   # Norte / Este (EPSG:9377)
_DECIMALES_GEO    = 6   # Latitud / Longitud (EPSG:4326)
_DECIMALES_DIST   = 1   # Distancia (metros, 1 decimal)
_DECIMALES_AZIMUT = 4   # Azimut decimal

_CRS_9377 = QgsCoordinateReferenceSystem("EPSG:9377")
_CRS_4326 = QgsCoordinateReferenceSystem("EPSG:4326")

_NULOS = {"", "NULL", "None", "null", "nan", "NaN", "none"}

# ---------------------------------------------------------------------------
# Estilos visuales
# ---------------------------------------------------------------------------
_COLOR_ENCABEZADO = "1F4E79"  # azul institucional oscuro
_COLOR_FILA_PAR   = "DDEEFF"  # azul claro para filas alternas


def _estilos() -> tuple:
    """Construye y retorna los objetos de estilo openpyxl."""
    fuente_enc  = Font(name="Calibri", bold=True, color="FFFFFF", size=10)
    relleno_enc = PatternFill("solid", fgColor=_COLOR_ENCABEZADO)
    al_centro   = Alignment(horizontal="center", vertical="center", wrap_text=True)
    al_derecha  = Alignment(horizontal="right",  vertical="center")
    borde_fino  = Border(
        left=Side(style="thin"),
        right=Side(style="thin"),
        top=Side(style="thin"),
        bottom=Side(style="thin"),
    )
    return fuente_enc, relleno_enc, al_centro, al_derecha, borde_fino


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------

def _nombre_archivo(feature: QgsFeature, config: dict) -> str:
    """
    Determina la ruta del archivo de salida.

    Prioridad para el nombre base:
      1. campo_nupre       → módulo TXT activo (reutilización directa)
      2. campo_nupre_xlsx  → módulo TXT desactivado, campo propio del tab Excel
      3. campo_fmi         → módulo TXT activo
      4. campo_fmi_xlsx    → módulo TXT desactivado
      5. FID del feature   → último recurso

    Si el archivo ya existe agrega sufijo _1, _2...
    """
    ruta_salida = config["ruta_salida"]

    def _val_campo(campo_key: str) -> Optional[str]:
        campo = config.get(campo_key)
        if not campo:
            return None
        try:
            val = str(feature[campo]).strip()
        except Exception:
            return None
        return val if val not in _NULOS else None

    base = (
        _val_campo("campo_nupre")
        or _val_campo("campo_nupre_xlsx")
        or _val_campo("campo_fmi")
        or _val_campo("campo_fmi_xlsx")
        or str(feature.id())
    )
    base = "".join(c for c in base if c.isalnum() or c in "._- ").strip()
    base = base or str(feature.id())

    ruta = os.path.join(ruta_salida, f"{base}.xlsx")
    contador = 1
    while os.path.exists(ruta):
        ruta = os.path.join(ruta_salida, f"{base}_{contador}.xlsx")
        contador += 1
    return ruta


def _punto_a_wgs84(punto, transform: QgsCoordinateTransform) -> tuple:
    """
    Reproyecta un QgsPointXY de EPSG:9377 a EPSG:4326.
    Retorna (latitud, longitud) en grados decimales.
    """
    p = transform.transform(punto)
    return p.y(), p.x()


# ---------------------------------------------------------------------------
# Construcción de filas
# ---------------------------------------------------------------------------

def _construir_filas(vertices: list, transform: QgsCoordinateTransform) -> list:
    """
    Genera la lista de tuplas para la hoja Vértices.

    Cada tupla: (N°, Marca, Norte, Este, Latitud, Longitud, Distancia, Azimut)

    Distancia y Azimut corresponden al segmento P_i → P_{i+1}.
    La última fila lleva None en esos campos: el recorrido normativo
    cierra en P1 y ese segmento ya fue descrito en la fila anterior.

    Norte = coordenada Y en EPSG:9377 (Northing)
    Este  = coordenada X en EPSG:9377 (Easting)
    """
    filas = []
    n = len(vertices)

    for i, punto in enumerate(vertices):
        norte = round(punto.y(), _DECIMALES_PLANAS)
        este  = round(punto.x(), _DECIMALES_PLANAS)
        lat, lon = _punto_a_wgs84(punto, transform)
        lat = round(lat, _DECIMALES_GEO)
        lon = round(lon, _DECIMALES_GEO)

        if i < n - 1:
            p_sig  = vertices[i + 1]
            dist   = round(calcular_distancia(punto, p_sig), _DECIMALES_DIST)
            azimut = round(calcular_azimut(punto, p_sig), _DECIMALES_AZIMUT)
        else:
            # Último vértice: cierra el recorrido, sin segmento nuevo
            dist   = None
            azimut = None

        filas.append((i + 1, f"P{i + 1}", norte, este, lat, lon, dist, azimut))

    return filas


# ---------------------------------------------------------------------------
# Escritura de la hoja Excel
# ---------------------------------------------------------------------------

def _escribir_hoja_vertices(wb, filas: list) -> None:
    """Escribe, formatea y congela la hoja Vértices en el workbook."""
    fuente_enc, relleno_enc, al_centro, al_derecha, borde = _estilos()
    relleno_par  = PatternFill("solid", fgColor=_COLOR_FILA_PAR)
    fuente_dato  = Font(name="Calibri", size=10)
    fuente_total = Font(name="Calibri", bold=True, size=10)

    ws = wb.active
    ws.title = "Vértices"

    # --- Encabezados ---
    encabezados = [
        "N°", "Marca",
        "Norte (m)", "Este (m)",
        "Latitud (°)", "Longitud (°)",
        "Distancia (m)", "Azimut (°)",
    ]
    anchos_col = [6, 9, 16, 16, 14, 14, 15, 13]

    for col_idx, (texto, ancho) in enumerate(zip(encabezados, anchos_col), start=1):
        celda           = ws.cell(row=1, column=col_idx, value=texto)
        celda.font      = fuente_enc
        celda.fill      = relleno_enc
        celda.alignment = al_centro
        celda.border    = borde
        ws.column_dimensions[get_column_letter(col_idx)].width = ancho

    ws.row_dimensions[1].height = 28

    # --- Filas de datos ---
    for fila_idx, fila in enumerate(filas, start=2):
        es_par = (fila_idx % 2 == 0)
        for col_idx, valor in enumerate(fila, start=1):
            celda           = ws.cell(row=fila_idx, column=col_idx, value=valor)
            celda.font      = fuente_dato
            celda.border    = borde
            celda.alignment = al_centro if col_idx <= 2 else al_derecha
            if es_par:
                celda.fill = relleno_par

            # Formato numérico por columna
            if col_idx in (3, 4):    # Norte / Este
                celda.number_format = "#,##0.0000"
            elif col_idx in (5, 6):  # Latitud / Longitud
                celda.number_format = "0.000000"
            elif col_idx == 7:       # Distancia
                celda.number_format = "#,##0.0"
            elif col_idx == 8:       # Azimut
                celda.number_format = "0.0000"

    # --- Fila de totales ---
    fila_total = len(filas) + 2

    celda_lbl           = ws.cell(row=fila_total, column=2,
                                  value=f"Total: {len(filas)} vértices")
    celda_lbl.font      = fuente_total
    celda_lbl.border    = borde
    celda_lbl.alignment = al_centro

    total_dist               = round(sum(f[6] for f in filas if f[6] is not None),
                                     _DECIMALES_DIST)
    celda_dist               = ws.cell(row=fila_total, column=7, value=total_dist)
    celda_dist.font          = fuente_total
    celda_dist.border        = borde
    celda_dist.alignment     = al_derecha
    celda_dist.number_format = "#,##0.0"

    # Borde en celdas vacías de la fila de totales
    for col_idx in [1, 3, 4, 5, 6, 8]:
        ws.cell(row=fila_total, column=col_idx).border = borde

    ws.freeze_panes = "A2"


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------

def exportar_xlsx(feature: QgsFeature, config: dict) -> str:
    """
    Genera el archivo .xlsx de coordenadas de vértices para el feature dado.

    El pipeline geométrico es idéntico al módulo TXT:
    reproyección → vértices → sentido horario → inicio noroccidental.

    Parámetros
    ----------
    feature : QgsFeature
        Feature del predio seleccionado.
    config : dict
        Config dict del plugin. Claves relevantes para este módulo:
            - "capa"             : QgsVectorLayer
            - "ruta_salida"      : str
            - "campo_nupre"      : str | None  (del módulo TXT si está activo)
            - "campo_fmi"        : str | None  (del módulo TXT si está activo)
            - "campo_nupre_xlsx" : str | None  (propio, cuando TXT está desactivado)
            - "campo_fmi_xlsx"   : str | None  (propio, cuando TXT está desactivado)

    Retorna
    -------
    str
        Ruta absoluta del archivo .xlsx generado.

    Lanza
    -----
    ImportError
        Si openpyxl no está instalado en el entorno QGIS.
    Exception
        Si falla la escritura del archivo o el pipeline geométrico.
    """
    if not OPENPYXL_OK:
        raise ImportError(
            "openpyxl no está disponible en este entorno QGIS. "
            "Instálalo con: pip install openpyxl --break-system-packages"
        )

    capa = config["capa"]

    # Pipeline geométrico — idéntico al módulo TXT (§5.2 del contexto)
    geom      = reproyectar_geometry(feature.geometry(), capa.crs())
    verts_raw = obtener_vertices(geom)
    verts_cw  = asegurar_sentido_horario(verts_raw)
    idx_nw    = punto_noroccidental(verts_cw)
    vertices  = reordenar_desde_inicio(verts_cw, idx_nw)

    # Transformación EPSG:9377 → EPSG:4326 para columnas geográficas
    transform = QgsCoordinateTransform(_CRS_9377, _CRS_4326, QgsProject.instance())

    filas = _construir_filas(vertices, transform)

    wb   = openpyxl.Workbook()
    _escribir_hoja_vertices(wb, filas)

    ruta = _nombre_archivo(feature, config)
    wb.save(ruta)
    return ruta
