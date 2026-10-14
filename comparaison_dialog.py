# -*- coding: utf-8 -*-
"""
Dialogue de zoom comparatif — EDEA_EraseTools v6.0.1

Affiche deux cartes synchronisées (avant / après) pour comparer visuellement
le résultat d'un traitement d'effacement (erase/difference).
"""

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QSplitter
from qgis.gui import QgsMapCanvas
from qgis.core import QgsProject, QgsRectangle


class ComparaisonDialog(QDialog):
    """Fenêtre avec deux QgsMapCanvas synchronisés : couche avant vs couche après."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("EDEA_EraseTools — Zoom comparatif (avant / après)")
        self.resize(1100, 600)

        self._syncing = False

        layout = QVBoxLayout(self)

        splitter = QSplitter(Qt.Horizontal)

        # Panneau AVANT
        panneau_avant = QVBoxLayout()
        label_avant = QLabel("AVANT")
        label_avant.setAlignment(Qt.AlignCenter)
        label_avant.setStyleSheet("font-weight:bold;color:#1976D2;padding:4px;")
        self.canvas_avant = QgsMapCanvas()
        self.canvas_avant.setCanvasColor(Qt.white)
        conteneur_avant = _wrap(label_avant, self.canvas_avant)

        # Panneau APRÈS
        label_apres = QLabel("APRÈS")
        label_apres.setAlignment(Qt.AlignCenter)
        label_apres.setStyleSheet("font-weight:bold;color:#2E7D32;padding:4px;")
        self.canvas_apres = QgsMapCanvas()
        self.canvas_apres.setCanvasColor(Qt.white)
        conteneur_apres = _wrap(label_apres, self.canvas_apres)

        splitter.addWidget(conteneur_avant)
        splitter.addWidget(conteneur_apres)
        splitter.setSizes([550, 550])

        layout.addWidget(splitter)

        # Synchronisation des deux cartes (pan/zoom lié)
        self.canvas_avant.extentsChanged.connect(self._sync_from_avant)
        self.canvas_apres.extentsChanged.connect(self._sync_from_apres)

    def _sync_from_avant(self):
        if self._syncing:
            return
        self._syncing = True
        self.canvas_apres.setExtent(self.canvas_avant.extent())
        self.canvas_apres.refresh()
        self._syncing = False

    def _sync_from_apres(self):
        if self._syncing:
            return
        self._syncing = True
        self.canvas_avant.setExtent(self.canvas_apres.extent())
        self.canvas_avant.refresh()
        self._syncing = False

    def set_layers(self, couche_avant, couche_apres):
        """Configure les deux cartes avec leurs couches respectives et cadre l'étendue combinée."""
        if couche_avant is not None:
            self.canvas_avant.setLayers([couche_avant])
            self.canvas_avant.setDestinationCrs(couche_avant.crs())
        if couche_apres is not None:
            self.canvas_apres.setLayers([couche_apres])
            self.canvas_apres.setDestinationCrs(couche_apres.crs())

        etendue = None
        for couche in (couche_avant, couche_apres):
            if couche is not None and couche.isValid() and not couche.extent().isEmpty():
                if etendue is None:
                    etendue = QgsRectangle(couche.extent())
                else:
                    etendue.combineExtentWith(couche.extent())

        if etendue is not None and not etendue.isEmpty():
            etendue.scale(1.1)
            self.canvas_avant.setExtent(etendue)
            self.canvas_apres.setExtent(etendue)

        self.canvas_avant.refresh()
        self.canvas_apres.refresh()


def _wrap(label, canvas):
    from qgis.PyQt.QtWidgets import QWidget
    conteneur = QWidget()
    v = QVBoxLayout(conteneur)
    v.setContentsMargins(0, 0, 0, 0)
    v.addWidget(label)
    v.addWidget(canvas)
    return conteneur
