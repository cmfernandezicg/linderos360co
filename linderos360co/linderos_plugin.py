import os
from qgis.PyQt.QtWidgets import QAction
from qgis.PyQt.QtGui import QIcon
from .ui.main_dialog import MainDialog


class LinderosPlugin:

    def __init__(self, iface):
        self.iface  = iface
        self.action = None
        self.dialog = None

    def initGui(self):
        icono = QIcon(
            os.path.join(os.path.dirname(__file__), "resources", "icon.png")
        )
        self.action = QAction(icono, "Linderos360CO", self.iface.mainWindow())
        self.action.setToolTip("Linderos360CO — Descripción técnica, plano y coordenadas")
        self.action.triggered.connect(self.run)
        self.iface.addToolBarIcon(self.action)
        self.iface.addPluginToMenu("Linderos360CO", self.action)

    def unload(self):
        self.iface.removePluginMenu("Linderos360CO", self.action)
        self.iface.removeToolBarIcon(self.action)

    def run(self):
        # Recrea el diálogo si fue cerrado por el usuario
        if self.dialog is None or not self.dialog.isVisible():
            self.dialog = MainDialog(self.iface)
        self.dialog.show()
        self.dialog.raise_()
        self.dialog.activateWindow()