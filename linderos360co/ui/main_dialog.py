from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout,
    QComboBox, QGroupBox, QFormLayout, QCheckBox,
    QPushButton, QFileDialog, QLineEdit, QMessageBox,
    QLabel, QProgressDialog, QTabWidget, QWidget,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QSizePolicy, QTextEdit, QFrame
)
from qgis.PyQt.QtCore import Qt, QSettings
from qgis.PyQt.QtGui import QPixmap, QFont, QColor
from qgis.core import QgsProject, QgsWkbTypes

try:
    from ..core.excel_generator import OPENPYXL_OK
except Exception:
    OPENPYXL_OK = False

# ── Clave base para QSettings ──────────────────────────────────────────────────
_SETTINGS_KEY = "linderos360co"


class MainDialog(QDialog):

    def __init__(self, iface, parent=None):
        super().__init__(parent)
        self.iface     = iface
        self.ruta_logo = ""
        self.setWindowTitle("Linderos360CO")
        self.setMinimumWidth(560)
        self.setMinimumHeight(520)
        self._build_ui()
        self._cargar_capas()
        self._conectar_signals()
        self._restaurar_configuracion()

    # ================================================================== UI

    def _build_ui(self):
        layout_principal = QVBoxLayout()
        layout_principal.setSpacing(8)

        self.tabs = QTabWidget()
        self.tab_home = QWidget()
        self._build_tab_home()
        self.tabs.addTab(self.tab_home, "Inicio")
        self.tab_txt  = None
        self.tab_pdf  = None
        self.tab_xlsx = None

        layout_principal.addWidget(self.tabs)

        # ── Barra de botones ───────────────────────────────────────────────
        layout_botones = QHBoxLayout()
        self.btn_generar = QPushButton("Generar")
        self.btn_generar.setEnabled(False)
        self.btn_generar.setMinimumHeight(32)
        self.btn_generar.setToolTip(
            "Selecciona una capa, activa al menos un módulo y elige la carpeta de salida."
        )
        btn_cerrar = QPushButton("Cerrar")
        btn_cerrar.clicked.connect(self.close)
        layout_botones.addStretch()
        layout_botones.addWidget(btn_cerrar)
        layout_botones.addWidget(self.btn_generar)

        layout_principal.addLayout(layout_botones)
        self.setLayout(layout_principal)

    # ------------------------------------------------------------------ Tab Inicio

    def _build_tab_home(self):
        layout = QVBoxLayout()
        layout.setSpacing(12)

        # ── Capa ──────────────────────────────────────────────────────────
        grp_capa = QGroupBox("Capa de predios")
        form_capa = QFormLayout()
        self.cmb_capa = QComboBox()
        form_capa.addRow("Capa:", self.cmb_capa)
        grp_capa.setLayout(form_capa)

        # ── Selección ─────────────────────────────────────────────────────
        grp_seleccion = QGroupBox("Predios a procesar")
        layout_sel = QVBoxLayout()
        layout_sel.setSpacing(6)
        self.lbl_seleccion = QLabel(
            "Selecciona una capa para continuar."
        )
        self.lbl_seleccion.setWordWrap(True)
        btn_verificar = QPushButton("Verificar selección")
        btn_verificar.setFixedWidth(160)
        btn_verificar.clicked.connect(self._verificar_seleccion)
        layout_sel.addWidget(self.lbl_seleccion)
        layout_sel.addWidget(btn_verificar, alignment=Qt.AlignLeft)
        grp_seleccion.setLayout(layout_sel)

        # ── Módulos ───────────────────────────────────────────────────────
        grp_modulos = QGroupBox("Productos a generar")
        layout_mod = QVBoxLayout()
        layout_mod.setSpacing(6)
        self.chk_mod_txt  = QCheckBox("Descripción técnica de linderos (.txt)")
        self.chk_mod_pdf  = QCheckBox("Plano cartográfico (.pdf)")
        self.chk_mod_xlsx = QCheckBox("Tabla de coordenadas de vértices (.xlsx)")
        self.chk_mod_txt.setChecked(False)
        self.chk_mod_pdf.setChecked(False)
        self.chk_mod_xlsx.setChecked(False)
        self.chk_mod_txt.toggled.connect(self._actualizar_pestanas)
        self.chk_mod_pdf.toggled.connect(self._actualizar_pestanas)
        self.chk_mod_xlsx.toggled.connect(self._actualizar_pestanas)
        layout_mod.addWidget(self.chk_mod_txt)
        layout_mod.addWidget(self.chk_mod_pdf)
        layout_mod.addWidget(self.chk_mod_xlsx)
        grp_modulos.setLayout(layout_mod)

        # ── Carpeta de salida ─────────────────────────────────────────────
        grp_salida = QGroupBox("Carpeta de salida")
        layout_salida = QHBoxLayout()
        self.txt_ruta = QLineEdit()
        self.txt_ruta.setPlaceholderText("Selecciona una carpeta de salida...")
        self.txt_ruta.setReadOnly(True)
        btn_ruta = QPushButton("Examinar...")
        btn_ruta.clicked.connect(self._seleccionar_ruta)
        layout_salida.addWidget(self.txt_ruta)
        layout_salida.addWidget(btn_ruta)
        grp_salida.setLayout(layout_salida)

        layout.addWidget(grp_capa)
        layout.addWidget(grp_seleccion)
        layout.addWidget(grp_modulos)
        layout.addWidget(grp_salida)
        layout.addStretch()
        self.tab_home.setLayout(layout)

    # ------------------------------------------------------------------ Tab Descripción

    def _build_tab_txt(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout()
        layout.setSpacing(10)

        # ── Predio principal ──────────────────────────────────────────────
        grp_campos = QGroupBox("Mapeo de campos — predio principal")
        form_campos = QFormLayout()
        self.cmb_nupre  = QComboBox()
        self.cmb_fmi    = QComboBox()
        self.cmb_nombre = QComboBox()
        self.cmb_nupre.setToolTip("Número único predial rural o urbano (NUPRE / cédula catastral)")
        self.cmb_fmi.setToolTip("Folio de matrícula inmobiliaria del predio")
        self.cmb_nombre.setToolTip("Nombre o denominación del predio")
        form_campos.addRow("NUPRE / Número predial:", self.cmb_nupre)
        form_campos.addRow("Matrícula inmobiliaria (FMI):", self.cmb_fmi)
        form_campos.addRow("Nombre del predio:", self.cmb_nombre)
        grp_campos.setLayout(form_campos)

        # ── Colindantes ───────────────────────────────────────────────────
        grp_col = QGroupBox("Colindantes")
        form_col = QFormLayout()
        self.chk_usar_colindantes = QCheckBox(
            "Identificar colindantes automáticamente"
        )
        self.chk_usar_colindantes.setChecked(True)
        self.chk_usar_colindantes.toggled.connect(self._toggle_colindantes)
        self.cmb_col_nupre = QComboBox()
        self.cmb_col_fmi   = QComboBox()
        self.cmb_col_elem  = QComboBox()
        self.cmb_col_elem.setToolTip(
            "Campo que describe el lindero o accidente geográfico colindante "
            "(río, carretera, quebrada, etc.)"
        )
        form_col.addRow(self.chk_usar_colindantes)
        form_col.addRow("NUPRE / Número predial:", self.cmb_col_nupre)
        form_col.addRow("Matrícula inmobiliaria (FMI):", self.cmb_col_fmi)
        form_col.addRow("Lindero o accidente geográfico:", self.cmb_col_elem)
        grp_col.setLayout(form_col)

        # ── Opciones ──────────────────────────────────────────────────────
        grp_opc = QGroupBox("Opciones")
        form_opc = QFormLayout()
        self.chk_urbano = QCheckBox("Suelo urbano  (área expresada en m²)")
        self.chk_urbano.setToolTip(
            "Activado: área en m² con 2 decimales.\n"
            "Desactivado: área en hectáreas + fracción en m² (suelo rural)."
        )
        self.chk_urbano.setChecked(False)
        form_opc.addRow(self.chk_urbano)
        grp_opc.setLayout(form_opc)

        layout.addWidget(grp_campos)
        layout.addWidget(grp_col)
        layout.addWidget(grp_opc)
        layout.addStretch()
        widget.setLayout(layout)
        return widget

    # ------------------------------------------------------------------ Tab Plano cartográfico

    def _build_tab_pdf(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout()
        layout.setSpacing(10)

        # ── Encabezado ────────────────────────────────────────────────────
        grp_enc = QGroupBox("Encabezado del plano")
        form_enc = QFormLayout()
        self.txt_empresa   = QLineEdit()
        self.txt_empresa.setToolTip("Razón social o nombre de la empresa / entidad que elabora el plano")
        self.txt_titulo    = QLineEdit()
        self.txt_titulo.setText("Descripción Técnica de Linderos")
        self.txt_titulo.setToolTip("Título que aparecerá en el panel derecho del plano")
        self.txt_elaborado = QLineEdit()
        self.txt_elaborado.setToolTip("Nombre del profesional responsable de la elaboración")
        self.txt_uso       = QLineEdit()
        self.txt_uso.setText("USO INTERNO")
        self.txt_uso.setToolTip("Clasificación del documento: USO INTERNO, RESERVADO, PÚBLICO, etc.")
        form_enc.addRow("Empresa / entidad:", self.txt_empresa)
        form_enc.addRow("Título del documento:", self.txt_titulo)
        form_enc.addRow("Elaborado por:", self.txt_elaborado)
        form_enc.addRow("Clasificación:", self.txt_uso)
        grp_enc.setLayout(form_enc)

        # ── Logo ──────────────────────────────────────────────────────────
        grp_logo = QGroupBox("Logo institucional")
        layout_logo = QHBoxLayout()
        self.txt_logo = QLineEdit()
        self.txt_logo.setPlaceholderText("Ruta de imagen (PNG, JPG, SVG)...")
        self.txt_logo.setReadOnly(True)
        btn_logo = QPushButton("Seleccionar...")
        btn_logo.clicked.connect(self._seleccionar_logo)
        self.lbl_logo_preview = QLabel()
        self.lbl_logo_preview.setFixedSize(80, 40)
        self.lbl_logo_preview.setAlignment(Qt.AlignCenter)
        self.lbl_logo_preview.setStyleSheet(
            "border: 1px solid #ccc; background: #f9f9f9;"
        )
        layout_logo.addWidget(self.txt_logo)
        layout_logo.addWidget(btn_logo)
        layout_logo.addWidget(self.lbl_logo_preview)
        grp_logo.setLayout(layout_logo)

        # ── Campos del predio en el plano ─────────────────────────────────
        grp_datos = QGroupBox("Campos del predio en el plano")
        layout_datos = QVBoxLayout()

        lbl_datos_hint = QLabel(
            "Solo se muestran en el plano los campos marcados como activos "
            "que tengan un campo de capa asignado. El área se incluye siempre de forma automática."
        )
        lbl_datos_hint.setWordWrap(True)
        lbl_datos_hint.setStyleSheet("color: #666666; font-size: 11px;")
        layout_datos.addWidget(lbl_datos_hint)

        self.tbl_campos_pdf = QTableWidget(0, 3)
        self.tbl_campos_pdf.setHorizontalHeaderLabels(
            ["Activo", "Etiqueta en plano", "Campo de la capa"]
        )
        self.tbl_campos_pdf.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeToContents
        )
        self.tbl_campos_pdf.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.Stretch
        )
        self.tbl_campos_pdf.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.Stretch
        )
        self.tbl_campos_pdf.setMinimumHeight(200)

        btn_agregar = QPushButton("Agregar")
        btn_agregar.setToolTip("Agregar una fila de campo personalizado")
        btn_agregar.clicked.connect(lambda: self._agregar_fila_campo_pdf())
        btn_quitar = QPushButton("Eliminar")
        btn_quitar.setToolTip("Eliminar la fila seleccionada")
        btn_quitar.clicked.connect(self._quitar_fila_campo_pdf)

        layout_btns = QHBoxLayout()
        layout_btns.addWidget(btn_agregar)
        layout_btns.addWidget(btn_quitar)
        layout_btns.addStretch()

        layout_datos.addWidget(self.tbl_campos_pdf)
        layout_datos.addLayout(layout_btns)
        grp_datos.setLayout(layout_datos)

        layout.addWidget(grp_enc)
        layout.addWidget(grp_logo)
        layout.addWidget(grp_datos)
        layout.addStretch()
        widget.setLayout(layout)
        return widget

    # ------------------------------------------------------------------ Tab Tabla de coordenadas

    def _build_tab_xlsx(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout()
        layout.setSpacing(10)

        # ── Descripción ───────────────────────────────────────────────────
        grp_info = QGroupBox("Descripción del archivo generado")
        layout_info = QVBoxLayout()
        layout_info.setSpacing(8)

        lbl_info = QLabel(
            "Exporta las coordenadas de cada vértice del predio a un archivo .xlsx. "
            "El orden sigue la normativa catastral colombiana: inicio en el vértice "
            "noroccidental, sentido horario, sistema MAGNA-SIRGAS / EPSG:9377."
        )
        lbl_info.setWordWrap(True)
        layout_info.addWidget(lbl_info)

        # ── Vista previa de columnas ───────────────────────────────────────
        lbl_prev = QLabel("Estructura de la hoja «Vértices»:")
        lbl_prev.setStyleSheet("font-weight: bold; margin-top: 4px;")
        layout_info.addWidget(lbl_prev)

        tbl_preview = QTableWidget(2, 8)
        tbl_preview.setHorizontalHeaderLabels([
            "N°", "Marca", "Norte (m)", "Este (m)",
            "Latitud (°)", "Longitud (°)", "Distancia (m)", "Azimut (°)"
        ])
        # Fila de ejemplo
        datos_ej = [
            ["1", "P1", "1 234 567.8901", "4 789 012.3456",
             "11.123456", "-74.654321", "45.3", "22.4512"],
            ["2", "P2", "1 234 589.1234", "4 789 038.7890",
             "11.123654", "-74.654098", "—", "—"],
        ]
        for r, fila in enumerate(datos_ej):
            for c, val in enumerate(fila):
                item = QTableWidgetItem(val)
                item.setFlags(Qt.ItemIsEnabled)
                item.setTextAlignment(Qt.AlignCenter)
                tbl_preview.setItem(r, c, item)

        tbl_preview.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        tbl_preview.verticalHeader().setVisible(False)
        tbl_preview.setEditTriggers(QTableWidget.NoEditTriggers)
        tbl_preview.setSelectionMode(QTableWidget.NoSelection)
        tbl_preview.setFixedHeight(
            tbl_preview.horizontalHeader().height() +
            tbl_preview.rowHeight(0) * 2 + 4
        )
        tbl_preview.setStyleSheet("font-size: 11px;")
        layout_info.addWidget(tbl_preview)

        lbl_nota = QLabel(
            "• La última fila (punto de cierre) no genera segmento — "
            "Distancia y Azimut quedan vacíos.\n"
            "• La fila final de totales incluye el conteo de vértices y el perímetro."
        )
        lbl_nota.setWordWrap(True)
        lbl_nota.setStyleSheet("color: #555555; font-size: 11px;")
        layout_info.addWidget(lbl_nota)

        grp_info.setLayout(layout_info)
        layout.addWidget(grp_info)

        # ── Campos para nombre de archivo ─────────────────────────────────
        # Visible solo cuando el módulo Descripción está desactivado.
        self.grp_xlsx_campos = QGroupBox("Campos para nombre de archivo")
        form_campos = QFormLayout()
        form_campos.setLabelAlignment(Qt.AlignRight)
        self.cmb_xlsx_nupre = QComboBox()
        self.cmb_xlsx_fmi   = QComboBox()
        self.cmb_xlsx_nupre.setToolTip("NUPRE / Cédula catastral del predio")
        self.cmb_xlsx_fmi.setToolTip("Folio de matrícula inmobiliaria")
        form_campos.addRow("NUPRE / Número predial:", self.cmb_xlsx_nupre)
        form_campos.addRow("Matrícula inmobiliaria (FMI):", self.cmb_xlsx_fmi)
        self.grp_xlsx_campos.setLayout(form_campos)
        layout.addWidget(self.grp_xlsx_campos)

        # Nota cuando módulo Descripción está activo
        self.lbl_xlsx_campos_info = QLabel(
            "ℹ  Los campos NUPRE y FMI se toman del módulo Descripción."
        )
        self.lbl_xlsx_campos_info.setWordWrap(True)
        self.lbl_xlsx_campos_info.setStyleSheet(
            "color: #555555; font-style: italic;"
        )
        self.lbl_xlsx_campos_info.setVisible(False)
        layout.addWidget(self.lbl_xlsx_campos_info)

        # Aviso si openpyxl no está disponible
        self.lbl_xlsx_aviso = QLabel(
            "⚠  openpyxl no está instalado. Ejecuta en la consola Python de QGIS:\n"
            "import subprocess; subprocess.run(['pip', 'install', 'openpyxl',"
            " '--break-system-packages'])"
        )
        self.lbl_xlsx_aviso.setWordWrap(True)
        self.lbl_xlsx_aviso.setStyleSheet("color: #B94A00;")
        self.lbl_xlsx_aviso.setVisible(not OPENPYXL_OK)
        layout.addWidget(self.lbl_xlsx_aviso)

        layout.addStretch()
        widget.setLayout(layout)
        return widget

    # ================================================================== Signals

    def _conectar_signals(self):
        self.cmb_capa.currentIndexChanged.connect(self._actualizar_campos)
        self.btn_generar.clicked.connect(self._ejecutar_generacion)

    # ================================================================== Lógica

    def _cargar_capas(self):
        self.cmb_capa.blockSignals(True)
        self.cmb_capa.clear()
        self.cmb_capa.addItem("-- Selecciona una capa --", None)
        for layer in QgsProject.instance().mapLayers().values():
            if not hasattr(layer, 'geometryType'):
                continue
            if layer.geometryType() == QgsWkbTypes.PolygonGeometry:
                self.cmb_capa.addItem(layer.name(), layer.id())
        self.cmb_capa.blockSignals(False)

    def _actualizar_pestanas(self):
        generar_txt  = self.chk_mod_txt.isChecked()
        generar_pdf  = self.chk_mod_pdf.isChecked()
        generar_xlsx = self.chk_mod_xlsx.isChecked()

        while self.tabs.count() > 1:
            self.tabs.removeTab(1)
        self.tab_txt  = None
        self.tab_pdf  = None
        self.tab_xlsx = None

        if generar_txt:
            self.tab_txt = self._build_tab_txt()
            self.tabs.addTab(self.tab_txt, "Descripción")
            self._poblar_combos_txt()

        if generar_pdf:
            self.tab_pdf = self._build_tab_pdf()
            self.tabs.addTab(self.tab_pdf, "Plano cartográfico")
            self._poblar_campos_pdf_default()

        if generar_xlsx:
            self.tab_xlsx = self._build_tab_xlsx()
            self.tabs.addTab(self.tab_xlsx, "Tabla de coordenadas")
            self._poblar_combos_xlsx()
            self._actualizar_visibilidad_xlsx_campos()

        self.btn_generar.setEnabled(
            (generar_txt or generar_pdf or generar_xlsx) and
            self._capa_seleccionada() is not None
        )
        self._actualizar_tooltip_generar()

    def _actualizar_campos(self):
        layer = self._capa_seleccionada()
        self._actualizar_label_seleccion(layer)
        if self.tab_txt is not None:
            self._poblar_combos_txt()
        if self.tab_pdf is not None:
            self._poblar_campos_pdf_default()
        if self.tab_xlsx is not None:
            self._poblar_combos_xlsx()
        activo = (
            layer is not None and
            (self.chk_mod_txt.isChecked() or
             self.chk_mod_pdf.isChecked() or
             self.chk_mod_xlsx.isChecked())
        )
        self.btn_generar.setEnabled(activo)
        self._actualizar_tooltip_generar()

    def _actualizar_tooltip_generar(self):
        """Actualiza el tooltip del botón Generar con el estado actual."""
        capa = self._capa_seleccionada()
        modulo = (
            self.chk_mod_txt.isChecked() or
            self.chk_mod_pdf.isChecked() or
            self.chk_mod_xlsx.isChecked()
        )
        if capa is None and not modulo:
            msg = "Selecciona una capa y activa al menos un módulo."
        elif capa is None:
            msg = "Selecciona una capa de predios."
        elif not modulo:
            msg = "Activa al menos un producto a generar."
        else:
            n = capa.selectedFeatureCount()
            if n == 0:
                msg = "Selecciona al menos un predio en QGIS antes de generar."
            else:
                productos = []
                if self.chk_mod_txt.isChecked():
                    productos.append(".txt")
                if self.chk_mod_pdf.isChecked():
                    productos.append(".pdf")
                if self.chk_mod_xlsx.isChecked():
                    productos.append(".xlsx")
                msg = (
                    f"Generará {', '.join(productos)} "
                    f"para {n} predio{'s' if n > 1 else ''}."
                )
        self.btn_generar.setToolTip(msg)

    def _poblar_combos_txt(self):
        if self.tab_txt is None:
            return
        layer = self._capa_seleccionada()
        combos = [
            self.cmb_nupre, self.cmb_fmi, self.cmb_nombre,
            self.cmb_col_nupre, self.cmb_col_fmi, self.cmb_col_elem
        ]
        for cmb in combos:
            cmb.clear()
            cmb.addItem("-- No aplica --", None)
        if layer is None:
            return
        for field in layer.fields():
            for cmb in combos:
                cmb.addItem(field.name(), field.name())

    def _poblar_campos_pdf_default(self):
        if self.tab_pdf is None:
            return
        self.tbl_campos_pdf.setRowCount(0)
        layer = self._capa_seleccionada()
        campos_capa = []
        if layer:
            campos_capa = [f.name() for f in layer.fields()]

        defaults = [
            "Nombre",
            "ID",
            "Matrícula",
            "Céd. Catastral",
            "Vereda",
            "Municipio",
            "Departamento",
        ]
        for etiqueta in defaults:
            self._agregar_fila_campo_pdf(
                etiqueta=etiqueta,
                campos_capa=campos_capa
            )

    def _poblar_combos_xlsx(self):
        if self.tab_xlsx is None:
            return
        layer = self._capa_seleccionada()
        opciones_vacias = [("-- No aplica --", None)]
        campos = []
        if layer:
            campos = [(f.name(), f.name()) for f in layer.fields()]

        for cmb in (self.cmb_xlsx_nupre, self.cmb_xlsx_fmi):
            texto_actual = cmb.currentText()
            cmb.clear()
            for texto, dato in opciones_vacias + campos:
                cmb.addItem(texto, dato)
            idx = cmb.findText(texto_actual)
            if idx >= 0:
                cmb.setCurrentIndex(idx)

    def _actualizar_visibilidad_xlsx_campos(self):
        if self.tab_xlsx is None:
            return
        txt_activo = self.chk_mod_txt.isChecked()
        self.grp_xlsx_campos.setVisible(not txt_activo)
        self.lbl_xlsx_campos_info.setVisible(txt_activo)

    def _agregar_fila_campo_pdf(self, etiqueta: str = "",
                                 campos_capa: list = None):
        if self.tab_pdf is None:
            return
        if campos_capa is None:
            layer = self._capa_seleccionada()
            campos_capa = (
                [f.name() for f in layer.fields()] if layer else []
            )
        fila = self.tbl_campos_pdf.rowCount()
        self.tbl_campos_pdf.insertRow(fila)

        chk = QCheckBox()
        chk.setChecked(True)
        chk.setStyleSheet("margin-left: 10px;")
        self.tbl_campos_pdf.setCellWidget(fila, 0, chk)

        self.tbl_campos_pdf.setItem(fila, 1, QTableWidgetItem(etiqueta))

        cmb = QComboBox()
        cmb.addItem("-- No aplica --", None)
        for campo in campos_capa:
            cmb.addItem(campo, campo)
        self.tbl_campos_pdf.setCellWidget(fila, 2, cmb)

    def _quitar_fila_campo_pdf(self):
        if self.tab_pdf is None:
            return
        fila = self.tbl_campos_pdf.currentRow()
        if fila >= 0:
            self.tbl_campos_pdf.removeRow(fila)

    def _toggle_colindantes(self, activo: bool):
        self.cmb_col_nupre.setEnabled(activo)
        self.cmb_col_fmi.setEnabled(activo)
        self.cmb_col_elem.setEnabled(activo)

    def _actualizar_label_seleccion(self, layer=None):
        if layer is None:
            layer = self._capa_seleccionada()
        if layer is None:
            self.lbl_seleccion.setText(
                "Selecciona una capa para continuar."
            )
            return
        n = layer.selectedFeatureCount()
        if n == 0:
            self.lbl_seleccion.setText(
                "⚠  Sin predios seleccionados — "
                "selecciona uno o más polígonos en QGIS."
            )
        elif n == 1:
            self.lbl_seleccion.setText(
                "✓  1 predio seleccionado."
            )
        else:
            self.lbl_seleccion.setText(
                f"✓  {n} predios seleccionados."
            )

    def _verificar_seleccion(self):
        layer = self._capa_seleccionada()
        if layer is None:
            QMessageBox.warning(self, "Aviso", "Primero selecciona una capa.")
            return
        self._actualizar_label_seleccion(layer)
        self._actualizar_tooltip_generar()

    def _seleccionar_ruta(self):
        ruta = QFileDialog.getExistingDirectory(
            self, "Seleccionar carpeta de salida", ""
        )
        if ruta:
            self.txt_ruta.setText(ruta)
            self._guardar_configuracion()

    def _seleccionar_logo(self):
        ruta, _ = QFileDialog.getOpenFileName(
            self, "Seleccionar logo",
            "", "Imágenes (*.png *.jpg *.jpeg *.svg)"
        )
        if ruta:
            self.txt_logo.setText(ruta)
            self.ruta_logo = ruta
            pixmap = QPixmap(ruta)
            if not pixmap.isNull():
                self.lbl_logo_preview.setPixmap(
                    pixmap.scaled(80, 40, Qt.KeepAspectRatio,
                                  Qt.SmoothTransformation)
                )

    # ================================================================== QSettings

    def _guardar_configuracion(self):
        """Persiste la configuración de la pestaña Inicio en QSettings."""
        s = QSettings()
        s.setValue(f"{_SETTINGS_KEY}/ruta_salida", self.txt_ruta.text())
        s.setValue(f"{_SETTINGS_KEY}/generar_txt",  self.chk_mod_txt.isChecked())
        s.setValue(f"{_SETTINGS_KEY}/generar_pdf",  self.chk_mod_pdf.isChecked())
        s.setValue(f"{_SETTINGS_KEY}/generar_xlsx", self.chk_mod_xlsx.isChecked())
        capa_id = self.cmb_capa.currentData()
        if capa_id:
            s.setValue(f"{_SETTINGS_KEY}/capa_id", capa_id)

    def _restaurar_configuracion(self):
        """Restaura la última configuración guardada en QSettings."""
        s = QSettings()
        ruta = s.value(f"{_SETTINGS_KEY}/ruta_salida", "")
        if ruta:
            self.txt_ruta.setText(ruta)

        # Módulos — blockSignals para evitar reconstruir tabs antes de tiempo
        self.chk_mod_txt.blockSignals(True)
        self.chk_mod_pdf.blockSignals(True)
        self.chk_mod_xlsx.blockSignals(True)
        self.chk_mod_txt.setChecked(
            s.value(f"{_SETTINGS_KEY}/generar_txt", False, type=bool)
        )
        self.chk_mod_pdf.setChecked(
            s.value(f"{_SETTINGS_KEY}/generar_pdf", False, type=bool)
        )
        self.chk_mod_xlsx.setChecked(
            s.value(f"{_SETTINGS_KEY}/generar_xlsx", False, type=bool)
        )
        self.chk_mod_txt.blockSignals(False)
        self.chk_mod_pdf.blockSignals(False)
        self.chk_mod_xlsx.blockSignals(False)

        # Reconstruir tabs si hay módulos activos
        if any([
            self.chk_mod_txt.isChecked(),
            self.chk_mod_pdf.isChecked(),
            self.chk_mod_xlsx.isChecked(),
        ]):
            self._actualizar_pestanas()

        # Restaurar capa seleccionada
        capa_id = s.value(f"{_SETTINGS_KEY}/capa_id", "")
        if capa_id:
            idx = self.cmb_capa.findData(capa_id)
            if idx >= 0:
                self.cmb_capa.setCurrentIndex(idx)

    # ================================================================== Generación

    def _ejecutar_generacion(self):
        config = self.obtener_configuracion()

        if config["capa"] is None:
            QMessageBox.warning(self, "Aviso", "Selecciona una capa.")
            return
        if not config["ruta_salida"]:
            QMessageBox.warning(self, "Aviso", "Selecciona una carpeta de salida.")
            return

        features = list(config["capa"].selectedFeatures())
        if not features:
            QMessageBox.warning(
                self, "Aviso",
                "No hay predios seleccionados.\n"
                "Selecciona al menos un polígono en QGIS antes de generar."
            )
            return

        # ── Validación topológica previa ───────────────────────────────────
        from ..core.topology_validator import (
            validar_features, resumen_validacion, tiene_bloqueantes
        )
        resultado_val = validar_features(features, config["capa"].crs())
        if resultado_val:
            resumen = resumen_validacion(resultado_val, features)
            respuesta = QMessageBox.question(
                self,
                "Problemas topológicos detectados",
                resumen,
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if respuesta == QMessageBox.No:
                return

        # ── Guardar configuración antes de procesar ────────────────────────
        self._guardar_configuracion()

        # ── Procesamiento con progreso detallado ──────────────────────────
        productos = sum([
            config["generar_txt"],
            config["generar_pdf"],
            config["generar_xlsx"],
        ])
        total_pasos = len(features) * productos

        progreso = QProgressDialog(
            "Iniciando...", "Cancelar", 0, total_pasos, self
        )
        progreso.setWindowTitle("Generando archivos")
        progreso.setWindowModality(Qt.WindowModal)
        progreso.setMinimumDuration(0)
        progreso.setMinimumWidth(400)
        progreso.show()

        errores   = []
        generados = []
        paso      = 0

        for i, feature in enumerate(features):
            if progreso.wasCanceled():
                break

            fid_label = f"FID {feature.id()}"
            nupre_campo = config.get("campo_nupre")
            if nupre_campo:
                val = feature[nupre_campo]
                if val and str(val).strip():
                    fid_label = str(val).strip()

            prefijo = f"Predio {i + 1}/{len(features)}"

            # ── TXT ───────────────────────────────────────────────────────
            if config["generar_txt"]:
                paso += 1
                progreso.setValue(paso)
                progreso.setLabelText(f"{prefijo} — Generando descripción (.txt)\n{fid_label}")
                if progreso.wasCanceled():
                    break
                try:
                    from ..core.descripcion_txt import exportar_txt
                    ruta = exportar_txt(feature, config)
                    generados.append(ruta)
                except Exception as e:
                    errores.append(f"[TXT] {fid_label}: {str(e)}")

            # ── PDF ───────────────────────────────────────────────────────
            if config["generar_pdf"]:
                paso += 1
                progreso.setValue(paso)
                progreso.setLabelText(f"{prefijo} — Generando plano cartográfico (.pdf)\n{fid_label}")
                if progreso.wasCanceled():
                    break
                try:
                    from ..layout.pdf_generator import generar_pdf
                    ruta = generar_pdf(feature, config, self.iface)
                    generados.append(ruta)
                except Exception as e:
                    errores.append(f"[PDF] {fid_label}: {str(e)}")

            # ── Excel ─────────────────────────────────────────────────────
            if config["generar_xlsx"]:
                paso += 1
                progreso.setValue(paso)
                progreso.setLabelText(f"{prefijo} — Generando tabla de coordenadas (.xlsx)\n{fid_label}")
                if progreso.wasCanceled():
                    break
                try:
                    from ..core.excel_generator import exportar_xlsx
                    ruta = exportar_xlsx(feature, config)
                    generados.append(ruta)
                except ImportError as e:
                    if self.tab_xlsx is not None:
                        self.lbl_xlsx_aviso.setVisible(True)
                    errores.append(f"[Excel] {fid_label}: {str(e)}")
                except Exception as e:
                    errores.append(f"[Excel] {fid_label}: {str(e)}")

        progreso.setValue(total_pasos)

        # ── Resultado ──────────────────────────────────────────────────────
        self._mostrar_resultado(generados, errores, config["ruta_salida"])

    def _mostrar_resultado(self, generados: list, errores: list, ruta_salida: str):
        """
        Muestra el resumen de la generación.
        Si hay errores, ofrece un diálogo con log exportable.
        """
        if not generados and not errores:
            # Cancelado antes de procesar cualquier archivo
            return

        if errores and not generados:
            # Solo errores — muestra log directamente
            self._mostrar_log_errores(errores)
            return

        # Construir mensaje de resumen
        partes_ok = []
        n_txt  = sum(1 for r in generados if r.endswith(".txt"))
        n_pdf  = sum(1 for r in generados if r.endswith(".pdf"))
        n_xlsx = sum(1 for r in generados if r.endswith(".xlsx"))
        if n_txt:  partes_ok.append(f"{n_txt} descripción{'es' if n_txt > 1 else ''} .txt")
        if n_pdf:  partes_ok.append(f"{n_pdf} plano{'s' if n_pdf > 1 else ''} .pdf")
        if n_xlsx: partes_ok.append(f"{n_xlsx} tabla{'s' if n_xlsx > 1 else ''} .xlsx")

        msg = f"Archivos generados correctamente:\n  {', '.join(partes_ok)}\n\nCarpeta: {ruta_salida}"
        if errores:
            msg += f"\n\n⚠  {len(errores)} error{'es' if len(errores) > 1 else ''} durante el proceso."

        if errores:
            dlg = QMessageBox(self)
            dlg.setWindowTitle("Generación completada con errores")
            dlg.setIcon(QMessageBox.Warning)
            dlg.setText(msg)
            dlg.addButton("Ver errores", QMessageBox.ActionRole)
            dlg.addButton("Cerrar", QMessageBox.AcceptRole)
            if dlg.exec_() == 0:  # "Ver errores"
                self._mostrar_log_errores(errores)
        else:
            QMessageBox.information(self, "Generación completada", msg)

    def _mostrar_log_errores(self, errores: list):
        """Diálogo con log de errores exportable a .txt."""
        dlg = QDialog(self)
        dlg.setWindowTitle("Log de errores")
        dlg.setMinimumSize(520, 340)
        layout = QVBoxLayout()

        lbl = QLabel(f"{len(errores)} error{'es' if len(errores) > 1 else ''} registrado{'s' if len(errores) > 1 else ''}:")
        layout.addWidget(lbl)

        txt = QTextEdit()
        txt.setReadOnly(True)
        txt.setFont(QFont("Monospace", 10))
        txt.setPlainText("\n".join(errores))
        layout.addWidget(txt)

        layout_btns = QHBoxLayout()
        btn_exportar = QPushButton("Exportar log (.txt)...")
        btn_cerrar   = QPushButton("Cerrar")

        def exportar_log():
            ruta, _ = QFileDialog.getSaveFileName(
                dlg, "Guardar log de errores", "linderos_errores.txt",
                "Archivos de texto (*.txt)"
            )
            if ruta:
                try:
                    with open(ruta, "w", encoding="utf-8") as f:
                        f.write("\n".join(errores))
                    QMessageBox.information(dlg, "Log exportado", f"Guardado en:\n{ruta}")
                except Exception as e:
                    QMessageBox.critical(dlg, "Error", f"No se pudo guardar:\n{str(e)}")

        btn_exportar.clicked.connect(exportar_log)
        btn_cerrar.clicked.connect(dlg.accept)

        layout_btns.addWidget(btn_exportar)
        layout_btns.addStretch()
        layout_btns.addWidget(btn_cerrar)
        layout.addLayout(layout_btns)

        dlg.setLayout(layout)
        dlg.exec_()

    # ================================================================== Helpers

    def _capa_seleccionada(self):
        layer_id = self.cmb_capa.currentData()
        if not layer_id:
            return None
        return QgsProject.instance().mapLayer(layer_id)

    def _campos_pdf_configurados(self) -> list:
        resultado = []
        if self.tab_pdf is None:
            return resultado
        for fila in range(self.tbl_campos_pdf.rowCount()):
            chk  = self.tbl_campos_pdf.cellWidget(fila, 0)
            item = self.tbl_campos_pdf.item(fila, 1)
            cmb  = self.tbl_campos_pdf.cellWidget(fila, 2)
            if chk and chk.isChecked() and item and cmb:
                resultado.append({
                    "etiqueta": item.text().strip(),
                    "campo":    cmb.currentData(),
                })
        return resultado

    def obtener_configuracion(self) -> dict:
        config = {
            "capa":         self._capa_seleccionada(),
            "ruta_salida":  self.txt_ruta.text(),
            "generar_txt":  self.chk_mod_txt.isChecked(),
            "generar_pdf":  self.chk_mod_pdf.isChecked(),
            "generar_xlsx": self.chk_mod_xlsx.isChecked(),
        }

        # ── Módulo Descripción TXT ─────────────────────────────────────────
        if self.tab_txt is not None:
            config.update({
                "campo_nupre":      self.cmb_nupre.currentData(),
                "campo_fmi":        self.cmb_fmi.currentData(),
                "campo_nombre":     self.cmb_nombre.currentData(),
                "col_nupre":        self.cmb_col_nupre.currentData(),
                "col_fmi":          self.cmb_col_fmi.currentData(),
                "col_elemento":     self.cmb_col_elem.currentData(),
                "usar_colindantes": self.chk_usar_colindantes.isChecked(),
                "es_urbano":        self.chk_urbano.isChecked(),
            })
        else:
            config.update({
                "campo_nupre":      None,
                "campo_fmi":        None,
                "campo_nombre":     None,
                "col_nupre":        None,
                "col_fmi":          None,
                "col_elemento":     None,
                "usar_colindantes": False,
                "es_urbano":        False,
            })

        # ── Módulo Plano cartográfico ──────────────────────────────────────
        if self.tab_pdf is not None:
            config.update({
                "pdf_empresa":   self.txt_empresa.text().strip(),
                "pdf_titulo":    self.txt_titulo.text().strip(),
                "pdf_elaborado": self.txt_elaborado.text().strip(),
                "pdf_uso":       self.txt_uso.text().strip(),
                "pdf_logo":      self.txt_logo.text().strip(),
                "pdf_campos":    self._campos_pdf_configurados(),
            })
        else:
            config.update({
                "pdf_empresa":   "",
                "pdf_titulo":    "",
                "pdf_elaborado": "",
                "pdf_uso":       "",
                "pdf_logo":      "",
                "pdf_campos":    [],
            })

        # ── Módulo Tabla de coordenadas ────────────────────────────────────
        # Si Descripción está activo, campo_nupre y campo_fmi ya están en config.
        # excel_generator los usa directamente con prioridad sobre los propios.
        if self.tab_xlsx is not None and not config["generar_txt"]:
            config.update({
                "campo_nupre_xlsx": self.cmb_xlsx_nupre.currentData(),
                "campo_fmi_xlsx":   self.cmb_xlsx_fmi.currentData(),
            })
        else:
            config.update({
                "campo_nupre_xlsx": None,
                "campo_fmi_xlsx":   None,
            })

        return config