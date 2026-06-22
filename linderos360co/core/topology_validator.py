# -*- coding: utf-8 -*-
"""
core/topology_validator.py

QGIS 4.x — Cambios respecto a v1.x:
  - QgsWkbTypes.PolygonGeometry → Qgis.GeometryType.Polygon
  - QgsWkbTypes.geometryType() sigue disponible para obtener el tipo base
  - QgsWkbTypes.displayString() sigue disponible para el mensaje de error
"""
from qgis.core import (
    Qgis,
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
    Extrae los anillos del primer polígono de forma segura para cualquier
    tipo: Polygon, PolygonZ, MultiPolygon, MultiPolygonZ.

    Retorna lista donde [0] es el anillo exterior y [1..N] son interiores.
    Cada anillo es una lista de QgsPointXY incluyendo vértice de cierre.
    """
    from qgis.core import QgsPointXY

    try:
        abstract = geom_proy.constGet()
        if abstract is None:
            return []

        # Seleccionar la parte principal en caso de MultiPolygon
        if geom_proy.isMultipart():
            n_partes  = abstract.numGeometries()
            parte_idx = 0
            area_max  = 0.0
            for i in range(n_partes):
                parte_geom = QgsGeometry(abstract.geometryN(i).clone())
                area = parte_geom.area()
                if area > area_max:
                    area_max  = area
                    parte_idx = i
            parte = abstract.geometryN(parte_idx)
        else:
            parte = abstract

        # Anillo exterior
        exterior_ring = parte.exteriorRing()
        if exterior_ring is None or exterior_ring.numPoints() == 0:
            return []

        anillo_ext = []
        for i in range(exterior_ring.numPoints()):
            pt = exterior_ring.pointN(i)
            anillo_ext.append(QgsPointXY(pt.x(), pt.y()))

        anillos = [anillo_ext]

        # Anillos interiores
        n_interiores = parte.numInteriorRings()
        for i in range(n_interiores):
            ring      = parte.interiorRing(i)
            anillo_int = []
            for j in range(ring.numPoints()):
                pt = ring.pointN(j)
                anillo_int.append(QgsPointXY(pt.x(), pt.y()))
            if anillo_int:
                anillos.append(anillo_int)

        return anillos

    except Exception:
        return []


def validar_feature(feature, crs_capa) -> list:
    problemas = []
    geom = feature.geometry()

    # -- Nivel 1: geometría básica --
    if geom is None or geom.isEmpty():
        problemas.append((NIVEL_CRITICO, "Geometria nula o vacia"))
        return problemas

    # QGIS 4.x: QgsWkbTypes.PolygonGeometry → Qgis.GeometryType.Polygon
    tipo_base = QgsWkbTypes.geometryType(geom.wkbType())
    if tipo_base != Qgis.GeometryType.Polygon:
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

    # -- Nivel 4: anillos interiores — informativo, no bloqueante --
    n_interiores = len(anillos) - 1
    if n_interiores > 0:
        problemas.append((NIVEL_ADVERTENCIA,
            "El poligono tiene " + str(n_interiores) +
            " anillo(s) interior(es). "
            "Se procesaran como linderos independientes en TXT y XLSX."))

        for idx_anillo, anillo_int in enumerate(anillos[1:], start=1):
            n_int = len(anillo_int)

            n_int_validos = n_int - 1
            if n_int_validos < 3:
                problemas.append((NIVEL_ERROR,
                    "Anillo interior N°" + str(idx_anillo) +
                    " tiene solo " + str(n_int_validos) +
                    " vertice(s) unicos; minimo requerido: 3"))

            if n_int >= 2:
                p_ini_int = anillo_int[0]
                p_fin_int = anillo_int[-1]
                if (abs(p_ini_int.x() - p_fin_int.x()) > 1e-6 or
                        abs(p_ini_int.y() - p_fin_int.y()) > 1e-6):
                    problemas.append((NIVEL_ADVERTENCIA,
                        "Anillo interior N°" + str(idx_anillo) +
                        " no esta cerrado correctamente"))

            geom_int  = QgsGeometry.fromPolygonXY([anillo_int])
            area_int  = abs(geom_int.area())
            if area_int <= _AREA_MINIMA_M2:
                problemas.append((NIVEL_ADVERTENCIA,
                    "Anillo interior N°" + str(idx_anillo) +
                    " tiene area despreciable (" +
                    str(round(area_int, 4)) + " m2)"))

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
    """Texto del diálogo de advertencia previo al procesamiento."""
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
