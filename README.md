# Linderos360CO

> QGIS plugin for automated generation of boundary descriptions, cartographic plans and coordinate tables following Colombian cadastral regulations (IGAC-SNR).

---

## What it does

If you work in cadastre or land surveying in Colombia, you already know what generating a technical boundary description involves: checking the regulation, calculating coordinates, writing the normative text, building the cartographic plan... all of it manually or with poorly automated workflows.

**Linderos360CO** handles that complete process from QGIS. Select your parcels, map the fields from your layer, and the plugin generates the three products required by the cadastral workflow:

| Product | Format | Description |
|---|---|---|
| Technical boundary description | `.txt` | Normative text per IGAC-SNR resolution: northwest starting vertex, clockwise direction, segments grouped by cardinal quadrant, neighbor identification, area in hectares (rural) or m² (urban) |
| Cartographic plan | `.pdf` | Layout from a `.qpt` template with automatic scale bar, OSM localization map, dynamic legend and configurable header |
| Coordinate table | `.xlsx` | Vertices with MAGNA-SIRGAS / EPSG:9377 projected coordinates, WGS84 geographic coordinates, distance and azimuth to the next vertex, and perimeter total row |

All geometry processing runs in **EPSG:9377** internally, regardless of your source layer CRS. Works with SHP, GPKG, GDB and any vector format supported by QGIS, including **MultiPolygonZ** geometry — which is what most Colombian cadastral entities deliver.

---

## Requirements

- QGIS 3.16 LTR or later
- Python 3.x (included with QGIS)
- **openpyxl** — required only for `.xlsx` export

If `openpyxl` is not installed, run this in the QGIS Python console:

```python
import subprocess
subprocess.run(['pip', 'install', 'openpyxl', '--break-system-packages'])
```

- Internet connection recommended for the OSM localization basemap (optional — the plan is generated even without connectivity)

---

## Installation

### From the QGIS Plugin Repository (recommended)

1. Open QGIS → **Plugins** → **Manage and Install Plugins...**
2. Search for `Linderos360CO`
3. Click **Install Plugin**

### Manual installation

1. Download the latest release `.zip` from the [Releases](https://github.com/cmfernandezicg/linderos360co/releases) page
2. Open QGIS → **Plugins** → **Manage and Install Plugins...** → **Install from ZIP**
3. Select the downloaded file and click **Install Plugin**

---

## Usage

1. Load a polygon layer with your parcels into QGIS
2. Select one or more polygons on the map
3. Open the plugin: **Plugins** → **Linderos360CO** or click the toolbar icon
4. On the **Inicio** tab:
   - Select the layer
   - Check the products you want to generate
   - Set the output folder
5. Configure each active module on its tab:
   - **Descripción** — map the NUPRE, FMI and name fields; optionally enable automatic neighbor identification
   - **Plano cartográfico** — fill in the header data and optional logo
   - **Tabla de coordenadas** — no additional configuration needed when the Descripción module is active
6. Click **Generar**

The plugin validates topology before processing and reports any issues so you can decide whether to continue.

---

## Project structure

```
linderos360co/
├── __init__.py
├── metadata.txt
├── linderos_plugin.py          ← plugin entry point
├── core/
│   ├── geometry_utils.py       ← reprojection, vertices, azimuth, distance
│   ├── clasificador.py         ← quadrant classification, segment numbering
│   ├── colindantes.py          ← spatial neighbor detection
│   ├── descripcion_txt.py      ← normative text generator
│   ├── excel_generator.py      ← .xlsx coordinate table
│   └── topology_validator.py   ← pre-processing topological validation
├── layout/
│   ├── capas_temporales.py     ← in-memory layers with symbology and labels
│   └── pdf_generator.py        ← QPT template loader, dynamic variables, PDF export
├── ui/
│   └── main_dialog.py          ← main dialog with dynamic tabs
└── resources/
    ├── icon.png
    └── plantilla_linderos.qpt  ← cartographic template (designed in QGIS)
```

---

## Coordinate system

The plugin always works in **EPSG:9377** (MAGNA-SIRGAS — the mandatory projection for Colombian cadastre as defined by the IGAC-SNR joint resolution on multipurpose cadastre). Your input layer can be in any CRS — reprojection is handled automatically.

---

## Known limitations

- Parcels with interior rings (holes) are processed using the exterior ring only. Full support for interior rings is planned for a future release.
- The OSM localization map requires an internet connection. If unavailable, the map area will be empty but the rest of the plan is generated normally.
- `.xlsx` export requires `openpyxl` (see Requirements above).

---

## Contributing

Contributions are welcome. If you find a bug or want to suggest an improvement:

1. Check the [Issues](https://github.com/cmfernandezicg/linderos360co/issues) page to see if it has already been reported
2. Open a new issue describing the problem or suggestion — include your QGIS version, OS, and a sample layer if relevant
3. For code contributions, fork the repository and open a pull request against the `main` branch

If you work in Colombian cadastre and have edge cases the plugin does not handle well (unusual parcel shapes, specific field naming conventions, institutional templates), opening an issue with real data examples is the most useful contribution you can make.

---

## License

This plugin is distributed under the [GPL-2.0 License](LICENSE).

---

## Author

**Carlos Mario Fernández Barrios**
cmfernandezicg@gmail.com

Built for the Colombian cadastral and land surveying community.
