# -*- coding: utf-8 -*-
"""
Dialogue du plugin EDEA_EraseTools v6.0.1
Généralisé à tout type de couche vectorielle (points, lignes, polygones).
"""

import os
import csv
import io
from qgis.PyQt import uic
from qgis.PyQt.QtCore import QSettings, Qt, QVariant
from qgis.PyQt.QtWidgets import (
    QDialog, QFileDialog, QMessageBox, QLabel, QTableWidgetItem,
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QFormLayout,
    QComboBox, QTableWidget, QPushButton, QLineEdit, QCheckBox,
    QTextEdit, QGroupBox, QHeaderView, QAbstractItemView,
)
from qgis.PyQt.QtGui import QPixmap
from qgis.core import QgsProject, QgsCoordinateReferenceSystem, QgsVectorLayer

try:
    from qgis.gui import QgsExpressionBuilderDialog
    _HAS_EXPR_BUILDER = True
except ImportError:
    _HAS_EXPR_BUILDER = False

FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), 'edea_erasetools_dialog_base.ui'))


class EdeaEraseToolsDialog(QDialog, FORM_CLASS):
    def __init__(self, parent=None):
        super(EdeaEraseToolsDialog, self).__init__(parent)
        self.setupUi(self)
        self.settings = QSettings("SIG_Essor_Benin", "EDEA_EraseTools")

        # Connexions
        self.btnBrowseDossier.clicked.connect(self.browse_folder)
        self.radioSimple.toggled.connect(self.update_ui_state)
        self.radioBatch.toggled.connect(self.update_ui_state)
        self.radioPreview.toggled.connect(self.update_ui_state)
        self.comboDecoupe.currentIndexChanged.connect(self.on_decoupe_changed)
        self.comboSource.currentIndexChanged.connect(self.on_source_changed)
        self.comboFormat.currentIndexChanged.connect(self.on_format_changed)
        self.btnFermer.clicked.connect(self.reject)
        self.btnAide.clicked.connect(self.show_help)
        self.checkBuffer.stateChanged.connect(self.update_ui_state)
        self.checkSelectionCarte.stateChanged.connect(self.on_selection_changed)
        self.btnEffacerHistorique.clicked.connect(self.effacer_historique)
        self.btnExporterHistorique.clicked.connect(self.exporter_historique)

        self.populate_scr()
        self.load_settings()
        self.update_ui_state()
        self.on_format_changed()
        self.charger_historique()

        # v6.1 : onglet « Regrouper / Agréger » construit dynamiquement
        self._build_aggregate_tab()

    def populate_scr(self):
        self.comboSCR.clear()
        self.comboSCR.addItem("Conserver le SCR source", None)
        crs_list = [
            ("WGS 84 (EPSG:4326)", "EPSG:4326"),
            ("UTM 31N WGS84 (EPSG:32631)", "EPSG:32631"),
            ("UTM 32N WGS84 (EPSG:32632)", "EPSG:32632"),
            ("RGF93 / Lambert-93 (EPSG:2154)", "EPSG:2154"),
            ("WGS 84 / Pseudo-Mercator (EPSG:3857)", "EPSG:3857"),
        ]
        for name, authid in crs_list:
            self.comboSCR.addItem(name, authid)

    def load_settings(self):
        s = self.settings
        self.checkValiderGeom.setChecked(s.value("valider_geom", True, type=bool))
        self.checkFusionnerARRD.setChecked(s.value("fusionner_decoupe", True, type=bool))
        self.checkVerifierSCR.setChecked(s.value("verifier_scr", True, type=bool))
        self.checkValidationChevauchement.setChecked(s.value("validation_chevauchement", False, type=bool))
        self.checkBuffer.setChecked(s.value("buffer_actif", False, type=bool))
        self.spinBufferDist.setValue(s.value("buffer_dist", 10.0, type=float))
        self.spinBufferSegments.setValue(s.value("buffer_segments", 8, type=int))
        self.checkModeInverse.setChecked(s.value("mode_inverse", False, type=bool))
        self.checkDiffSymetrique.setChecked(s.value("diff_symetrique", False, type=bool))
        self.checkCoucheSupprimee.setChecked(s.value("couche_supprimee", True, type=bool))
        self.checkSelectionCarte.setChecked(s.value("selection_carte", False, type=bool))
        self.comboFormat.setCurrentIndex(s.value("format", 0, type=int))
        self.comboAction.setCurrentIndex(s.value("action", 0, type=int))
        self.lineEditDossier.setText(s.value("dossier", "", type=str))
        self.lineEditPrefixe.setText(s.value("prefixe", "couche_hors_decoupe_", type=str))
        self.lineEditExprBatch.setText(s.value("expr_batch", "", type=str))
        self.checkMergeBatch.setChecked(s.value("merge_batch", False, type=bool))
        self.checkAjouterCouche.setChecked(s.value("ajouter_couche", True, type=bool))
        self.checkSymbologie.setChecked(s.value("symbologie", True, type=bool))
        self.checkRapportHTML.setChecked(s.value("rapport_html", True, type=bool))
        self.checkExportCSV.setChecked(s.value("export_csv", True, type=bool))
        self.checkTableBatch.setChecked(s.value("table_batch", True, type=bool))
        self.checkJournal.setChecked(s.value("journal", True, type=bool))
        self.checkTopologie.setChecked(s.value("topologie", True, type=bool))
        self.checkMetadonnees.setChecked(s.value("metadonnees", True, type=bool))
        self.checkHistorique.setChecked(s.value("historique", True, type=bool))
        self.checkSauvegarderParams.setChecked(s.value("sauvegarder_params", True, type=bool))
        scr_idx = s.value("scr_index", 0, type=int)
        if scr_idx < self.comboSCR.count():
            self.comboSCR.setCurrentIndex(scr_idx)
        # PostGIS
        self.lineEditPgHost.setText(s.value("pg_host", "localhost", type=str))
        self.spinPgPort.setValue(s.value("pg_port", 5432, type=int))
        self.lineEditPgDb.setText(s.value("pg_db", "", type=str))
        self.lineEditPgUser.setText(s.value("pg_user", "postgres", type=str))
        self.lineEditPgPass.setText(s.value("pg_pass", "", type=str))
        self.lineEditPgSchema.setText(s.value("pg_schema", "public", type=str))
        self.lineEditPgTable.setText(s.value("pg_table", "", type=str))
        # GeoServer
        self.lineEditGsUrl.setText(s.value("gs_url", "http://localhost:8080/geoserver", type=str))
        self.lineEditGsWorkspace.setText(s.value("gs_workspace", "", type=str))
        self.lineEditGsDatastore.setText(s.value("gs_datastore", "", type=str))
        self.lineEditGsUser.setText(s.value("gs_user", "admin", type=str))
        self.lineEditGsPass.setText(s.value("gs_pass", "", type=str))
        self.lineEditGsLayer.setText(s.value("gs_layer", "", type=str))

    def save_settings(self):
        if not self.checkSauvegarderParams.isChecked():
            return
        s = self.settings
        s.setValue("valider_geom", self.checkValiderGeom.isChecked())
        s.setValue("fusionner_decoupe", self.checkFusionnerARRD.isChecked())
        s.setValue("verifier_scr", self.checkVerifierSCR.isChecked())
        s.setValue("validation_chevauchement", self.checkValidationChevauchement.isChecked())
        s.setValue("buffer_actif", self.checkBuffer.isChecked())
        s.setValue("buffer_dist", self.spinBufferDist.value())
        s.setValue("buffer_segments", self.spinBufferSegments.value())
        s.setValue("mode_inverse", self.checkModeInverse.isChecked())
        s.setValue("diff_symetrique", self.checkDiffSymetrique.isChecked())
        s.setValue("couche_supprimee", self.checkCoucheSupprimee.isChecked())
        s.setValue("selection_carte", self.checkSelectionCarte.isChecked())
        s.setValue("format", self.comboFormat.currentIndex())
        s.setValue("action", self.comboAction.currentIndex())
        s.setValue("dossier", self.lineEditDossier.text())
        s.setValue("prefixe", self.lineEditPrefixe.text())
        s.setValue("expr_batch", self.lineEditExprBatch.text())
        s.setValue("merge_batch", self.checkMergeBatch.isChecked())
        s.setValue("ajouter_couche", self.checkAjouterCouche.isChecked())
        s.setValue("symbologie", self.checkSymbologie.isChecked())
        s.setValue("rapport_html", self.checkRapportHTML.isChecked())
        s.setValue("export_csv", self.checkExportCSV.isChecked())
        s.setValue("table_batch", self.checkTableBatch.isChecked())
        s.setValue("journal", self.checkJournal.isChecked())
        s.setValue("topologie", self.checkTopologie.isChecked())
        s.setValue("metadonnees", self.checkMetadonnees.isChecked())
        s.setValue("historique", self.checkHistorique.isChecked())
        s.setValue("sauvegarder_params", self.checkSauvegarderParams.isChecked())
        s.setValue("scr_index", self.comboSCR.currentIndex())
        s.setValue("pg_host", self.lineEditPgHost.text())
        s.setValue("pg_port", self.spinPgPort.value())
        s.setValue("pg_db", self.lineEditPgDb.text())
        s.setValue("pg_user", self.lineEditPgUser.text())
        s.setValue("pg_pass", self.lineEditPgPass.text())
        s.setValue("pg_schema", self.lineEditPgSchema.text())
        s.setValue("pg_table", self.lineEditPgTable.text())
        s.setValue("gs_url", self.lineEditGsUrl.text())
        s.setValue("gs_workspace", self.lineEditGsWorkspace.text())
        s.setValue("gs_datastore", self.lineEditGsDatastore.text())
        s.setValue("gs_user", self.lineEditGsUser.text())
        s.setValue("gs_pass", self.lineEditGsPass.text())
        s.setValue("gs_layer", self.lineEditGsLayer.text())

    def on_source_changed(self):
        layer = self.comboSource.currentData()
        if layer and layer.isValid():
            self.labelSCRSource.setText(f"SCR: {layer.crs().authid()}")
            if layer.fields().count() > 0:
                champs = ', '.join([f.name() for f in layer.fields()][:5])
                self.lineEditFiltreSource.setPlaceholderText(f"Filtre couche source (ex: {champs}…)")
        else:
            self.labelSCRSource.setText("SCR: —")

    def on_decoupe_changed(self):
        self.comboChampId.clear()
        layer = self.comboDecoupe.currentData()
        if layer and layer.isValid():
            self.labelSCRDecoupe.setText(f"SCR: {layer.crs().authid()}")
            for field in layer.fields():
                self.comboChampId.addItem(field.name(), field.name())
            if layer.fields().count() > 0:
                champs = ', '.join([f.name() for f in layer.fields()][:5])
                self.lineEditFiltreDecoupe.setPlaceholderText(f"Filtre couche de découpe (ex: {champs}…)")
        else:
            self.labelSCRDecoupe.setText("SCR: —")

    # Alias conservés pour compatibilité interne
    def on_arrd_changed(self):
        self.on_decoupe_changed()

    def on_reseau_changed(self):
        self.on_source_changed()

    def on_format_changed(self):
        is_postgis = (self.comboFormat.currentIndex() == 4)
        is_geoserver = (self.comboFormat.currentIndex() == 5)
        self.groupBox_postgis.setVisible(is_postgis)
        self.groupBox_geoserver.setVisible(is_geoserver)
        est_local = not (is_postgis or is_geoserver)
        self.comboAction.setEnabled(est_local)
        self.lineEditDossier.setEnabled(est_local)
        self.btnBrowseDossier.setEnabled(est_local)
        self.lineEditPrefixe.setEnabled(est_local)

    def on_selection_changed(self):
        if self.checkSelectionCarte.isChecked():
            self.comboDecoupe.setEnabled(False)
            self.lineEditFiltreDecoupe.setEnabled(False)
            # La fusion reste disponible : elle est utile si plusieurs entités
            # sont sélectionnées sur la carte et doivent être fusionnées avant traitement.
            self.checkFusionnerARRD.setEnabled(True)
        else:
            self.comboDecoupe.setEnabled(True)
            self.lineEditFiltreDecoupe.setEnabled(True)
            self.checkFusionnerARRD.setEnabled(True)

    def update_ui_state(self):
        is_preview = self.radioPreview.isChecked()
        is_batch = self.radioBatch.isChecked()
        buffer_actif = self.checkBuffer.isChecked()
        is_postgis = (self.comboFormat.currentIndex() == 4)
        is_geoserver = (self.comboFormat.currentIndex() == 5)
        est_distant = is_postgis or is_geoserver

        self.spinBufferDist.setEnabled(buffer_actif)
        self.spinBufferSegments.setEnabled(buffer_actif)

        if not est_distant:
            self.groupBox_sortie.setEnabled(not is_preview)
            self.comboAction.setEnabled(not is_batch)
            self.lineEditDossier.setEnabled(not is_preview)
            self.btnBrowseDossier.setEnabled(not is_preview)
            self.lineEditPrefixe.setEnabled(is_batch and not is_preview)

        self.comboSCR.setEnabled(not is_preview)
        self.comboFormat.setEnabled(not is_preview)
        self.comboChampId.setEnabled(is_batch and not is_preview)
        self.checkMergeBatch.setEnabled(is_batch and not is_preview)
        self.lineEditExprBatch.setEnabled(is_batch and not is_preview)
        self.checkAjouterCouche.setEnabled(not is_preview)
        self.checkSymbologie.setEnabled(not is_preview)
        self.checkRapportHTML.setEnabled(not is_preview)
        self.checkExportCSV.setEnabled(not is_preview)
        self.checkTableBatch.setEnabled(is_batch and not is_preview)
        self.checkJournal.setEnabled(not is_preview)
        self.checkTopologie.setEnabled(not is_preview)
        self.checkMetadonnees.setEnabled(not is_preview)

        if is_preview:
            self.lineEditDossier.setText("(Prévisualisation temporaire)")
        elif self.lineEditDossier.text().startswith("("):
            self.lineEditDossier.setText("")

    def browse_folder(self):
        dossier = QFileDialog.getExistingDirectory(self, "Choisir le dossier de sortie", "")
        if dossier:
            self.lineEditDossier.setText(dossier)

    def log(self, message):
        self.textLog.append(message)

    def reset_stats(self):
        self.labelValLongAvant.setText("—")
        self.labelValLongApres.setText("—")
        self.labelValPourcent.setText("—")
        self.labelValSurface.setText("—")
        self.labelValSupprime.setText("—")
        self.labelValTopo.setText("—")
        self.labelValChevauchement.setText("—")
        self.labelGraphPlaceholder.setText("Le graphique apparaîtra ici après le traitement.")
        self.labelGraphPlaceholder.setPixmap(QPixmap())

    def set_stats(self, mesure_avant, mesure_apres, pourcent, mesure_decoupe, mesure_supprime="—", topo="—", chevauchement="—"):
        self.labelValLongAvant.setText(mesure_avant)
        self.labelValLongApres.setText(mesure_apres)
        self.labelValPourcent.setText(pourcent)
        self.labelValSurface.setText(mesure_decoupe)
        self.labelValSupprime.setText(mesure_supprime)
        self.labelValTopo.setText(topo)
        self.labelValChevauchement.setText(chevauchement)

    def set_graph(self, pixmap):
        self.labelGraphPlaceholder.setPixmap(pixmap)
        self.labelGraphPlaceholder.setText("")

    # ------------------------------------------------------------------
    # HISTORIQUE DES ACTIONS
    # ------------------------------------------------------------------

    def ajouter_entree_historique(self, date_str, mode, algo, nom_source, nom_decoupe, resultat, nb_entites):
        row = self.tableHistorique.rowCount()
        self.tableHistorique.insertRow(row)
        valeurs = [date_str, mode, algo, nom_source, nom_decoupe, str(resultat), str(nb_entites)]
        for col, val in enumerate(valeurs):
            self.tableHistorique.setItem(row, col, QTableWidgetItem(val))
        self.tableHistorique.scrollToBottom()
        self._sauvegarder_historique()

    def _sauvegarder_historique(self):
        lignes = []
        for row in range(self.tableHistorique.rowCount()):
            valeurs = []
            for col in range(self.tableHistorique.columnCount()):
                item = self.tableHistorique.item(row, col)
                valeurs.append(item.text() if item else "")
            lignes.append("\t".join(valeurs))
        self.settings.setValue("historique_lignes", "\n".join(lignes))

    def charger_historique(self):
        contenu = self.settings.value("historique_lignes", "", type=str)
        if not contenu:
            return
        for ligne in contenu.split("\n"):
            if not ligne:
                continue
            valeurs = ligne.split("\t")
            row = self.tableHistorique.rowCount()
            self.tableHistorique.insertRow(row)
            for col, val in enumerate(valeurs):
                if col < self.tableHistorique.columnCount():
                    self.tableHistorique.setItem(row, col, QTableWidgetItem(val))

    def effacer_historique(self):
        reply = QMessageBox.question(
            self, "Confirmer", "Effacer tout l'historique des actions ?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.tableHistorique.setRowCount(0)
            self.settings.remove("historique_lignes")

    def exporter_historique(self):
        if self.tableHistorique.rowCount() == 0:
            QMessageBox.information(self, "Historique", "Aucune entrée à exporter.")
            return
        chemin, _ = QFileDialog.getSaveFileName(
            self, "Exporter l'historique", "historique_edea_erasetools.csv", "CSV (*.csv)")
        if not chemin:
            return
        with open(chemin, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f, delimiter=';')
            entetes = [self.tableHistorique.horizontalHeaderItem(c).text()
                       for c in range(self.tableHistorique.columnCount())]
            writer.writerow(entetes)
            for row in range(self.tableHistorique.rowCount()):
                valeurs = []
                for col in range(self.tableHistorique.columnCount()):
                    item = self.tableHistorique.item(row, col)
                    valeurs.append(item.text() if item else "")
                writer.writerow(valeurs)
        QMessageBox.information(self, "Historique", f"Exporté : {chemin}")

    # ==================================================================
    # ONGLET v6.1 : REGROUPER / AGRÉGER (dissolve + statistiques)
    # ==================================================================

    # Catalogue (libellé affiché -> mot-clé natif QGIS native:aggregate)
    AGG_FUNCTIONS = [
        ("(Ignorer ce champ)", None),
        ("Première valeur", "first_value"),
        ("Dernière valeur", "last_value"),
        ("Nombre", "count"),
        ("Nombre (distinct)", "count_distinct"),
        ("Minimum", "min"),
        ("Maximum", "max"),
        ("Somme", "sum"),
        ("Moyenne", "mean"),
        ("Médiane", "median"),
        ("Écart type", "stdev"),
        ("Concaténation", "concatenate"),
        ("Concaténation sans doublon", "concatenate_unique"),
        ("Minorité", "minority"),
        ("Majorité", "majority"),
    ]

    def _build_aggregate_tab(self):
        """Construit dynamiquement l'onglet Regrouper/Agréger et l'ajoute au QTabWidget."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # --- Bloc entrée / regroupement ---
        grp_in = QGroupBox("1. Couche et champ de regroupement")
        form = QFormLayout(grp_in)
        self.comboAggInput = QComboBox()
        self.comboAggGroup = QComboBox()
        self.comboAggGroup.setEditable(True)
        self.lineEditAggFilter = QLineEdit()
        self.lineEditAggFilter.setPlaceholderText('Filtre attributaire QGIS, ex. "population" > 100 AND "pays" = \'Pays A\'  (vide = toutes les entités)')
        # Boutons « constructeur d'expressions » (ε)
        self.btnAggFilterExpr = QPushButton("ε…")
        self.btnAggFilterExpr.setToolTip("Ouvrir le constructeur d'expressions QGIS")
        self.btnAggFilterExpr.setMaximumWidth(36)
        self.btnAggFilterExpr.clicked.connect(lambda: self._open_expr_builder(self.lineEditAggFilter))
        self.btnAggGroupExpr = QPushButton("ε…")
        self.btnAggGroupExpr.setToolTip("Ouvrir le constructeur d'expressions QGIS")
        self.btnAggGroupExpr.setMaximumWidth(36)
        self.btnAggGroupExpr.clicked.connect(lambda: self._open_expr_builder(self.comboAggGroup, is_combo=True))

        hf = QHBoxLayout()
        hf.addWidget(self.lineEditAggFilter)
        hf.addWidget(self.btnAggFilterExpr)
        wf = QWidget(); wf.setLayout(hf)
        hg = QHBoxLayout()
        hg.addWidget(self.comboAggGroup)
        hg.addWidget(self.btnAggGroupExpr)
        wg = QWidget(); wg.setLayout(hg)

        form.addRow("Couche en entrée :", self.comboAggInput)
        form.addRow("Filtre avant agrégation :", wf)
        form.addRow("Regrouper par (champ / expression) :", wg)
        layout.addWidget(grp_in)

        # --- Bloc agrégats ---
        grp_agg = QGroupBox("2. Statistiques par champ")
        v2 = QVBoxLayout(grp_agg)
        self.tableAgg = QTableWidget(0, 4)
        self.tableAgg.setHorizontalHeaderLabels(["Champ source", "Fonction", "Délimiteur", "Nom de sortie"])
        self.tableAgg.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tableAgg.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.tableAgg.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.tableAgg.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.tableAgg.setEditTriggers(QAbstractItemView.AllEditTriggers)
        v2.addWidget(self.tableAgg)
        layout.addWidget(grp_agg)

        # --- Bloc sortie ---
        grp_out = QGroupBox("3. Sortie")
        g = QGridLayout(grp_out)
        self.lineEditAggOutput = QLineEdit()
        self.lineEditAggOutput.setPlaceholderText("Fichier de sortie (.gpkg / .shp / .geojson) — vide = couche temporaire")
        self.btnAggBrowse = QPushButton("Parcourir…")
        self.btnAggBrowse.clicked.connect(self._browse_agg_output)
        self.checkAggAjouter = QCheckBox("Ajouter la couche agrégée au projet")
        self.checkAggAjouter.setChecked(True)
        self.checkAggExportStats = QCheckBox("Export automatique des statistiques (CSV)")
        self.checkAggExportStats.setChecked(True)
        self.checkAggReportHtml = QCheckBox("Rapport HTML récapitulatif des statistiques")
        self.checkAggReportHtml.setChecked(True)
        self.checkAggExportPdf = QCheckBox("Export PDF des statistiques")
        self.checkAggExportPdf.setChecked(False)
        self.checkAggExportExcel = QCheckBox("Export Excel des statistiques (.xlsx)")
        self.checkAggExportExcel.setChecked(False)
        self.checkAggGeom = QCheckBox("Calculer la géométrie après agrégation (aire/périmètre ou longueur, ellipsoïdal)")
        self.checkAggGeom.setChecked(True)
        g.addWidget(QLabel("Fichier :"), 0, 0)
        g.addWidget(self.lineEditAggOutput, 0, 1)
        g.addWidget(self.btnAggBrowse, 0, 2)
        g.addWidget(self.checkAggAjouter, 1, 0, 1, 3)
        g.addWidget(self.checkAggExportStats, 2, 0, 1, 3)
        g.addWidget(self.checkAggReportHtml, 3, 0, 1, 3)
        g.addWidget(self.checkAggExportPdf, 4, 0, 1, 3)
        g.addWidget(self.checkAggExportExcel, 5, 0, 1, 3)
        g.addWidget(self.checkAggGeom, 6, 0, 1, 3)
        layout.addWidget(grp_out)

        # --- Bouton + journal ---
        hb = QHBoxLayout()
        self.btnAggRun = QPushButton("∑  Regrouper et agréger")
        hb.addStretch()
        hb.addWidget(self.btnAggRun)
        layout.addLayout(hb)
        self.textAggLog = QTextEdit()
        self.textAggLog.setReadOnly(True)
        self.textAggLog.setMaximumHeight(120)
        layout.addWidget(self.textAggLog)

        self.tabWidget.addTab(tab, "Regrouper / Agréger")
        self.comboAggInput.currentIndexChanged.connect(self.on_agg_input_changed)

    def agg_log(self, message):
        self.textAggLog.append(message)

    def _browse_agg_output(self):
        chemin, _ = QFileDialog.getSaveFileName(
            self, "Fichier de sortie agrégé", "couche_agregee.gpkg",
            "GeoPackage (*.gpkg);;Shapefile (*.shp);;GeoJSON (*.geojson)")
        if chemin:
            self.lineEditAggOutput.setText(chemin)

    def _open_expr_builder(self, target, is_combo=False):
        """Ouvre le constructeur d'expressions QGIS pour remplir un champ."""
        if not _HAS_EXPR_BUILDER:
            QMessageBox.information(self, "Constructeur d'expressions",
                "Le constructeur d'expressions n'est pas disponible dans cette version de QGIS.\n"
                "Saisissez l'expression manuellement.")
            return
        layer = self.comboAggInput.currentData()
        texte_actuel = target.currentText() if is_combo else target.text()
        if is_combo and texte_actuel.startswith("NULL"):
            texte_actuel = ""
        try:
            dlg = QgsExpressionBuilderDialog(layer, texte_actuel, self)
            dlg.setWindowTitle("Constructeur d'expressions")
            if dlg.exec_():
                expr = dlg.expressionText()
                if is_combo:
                    target.setCurrentText(expr)
                else:
                    target.setText(expr)
        except Exception as e:
            QMessageBox.warning(self, "Constructeur d'expressions",
                f"Impossible d'ouvrir le constructeur : {e}")

    def populate_agg_combo(self):
        """Remplit la liste des couches de l'onglet Agréger (toutes couches vectorielles)."""
        self.comboAggInput.blockSignals(True)
        self.comboAggInput.clear()
        for layer in QgsProject.instance().mapLayers().values():
            if layer.type() == layer.VectorLayer:
                self.comboAggInput.addItem(layer.name(), layer)
        if self.comboAggInput.count() == 0:
            self.comboAggInput.addItem("-- Aucune couche vectorielle --", None)
        self.comboAggInput.blockSignals(False)
        self.on_agg_input_changed()

    def on_agg_input_changed(self):
        """Reconstruit la liste des champs de regroupement et le tableau d'agrégats."""
        layer = self.comboAggInput.currentData()
        self.comboAggGroup.clear()
        self.comboAggGroup.addItem("NULL  (fusionner toutes les entités)")
        self.tableAgg.setRowCount(0)
        if not layer or not getattr(layer, 'isValid', lambda: False)():
            return
        for field in layer.fields():
            self.comboAggGroup.addItem(field.name())
        for field in layer.fields():
            self._add_agg_row(field)

    def _add_agg_row(self, field):
        row = self.tableAgg.rowCount()
        self.tableAgg.insertRow(row)
        # Champ source (lecture seule)
        item = QTableWidgetItem(field.name())
        item.setFlags(item.flags() & ~Qt.ItemIsEditable)
        self.tableAgg.setItem(row, 0, item)
        # Fonction (combo) — défaut : somme si numérique, sinon première valeur
        combo = QComboBox()
        for libelle, _kw in self.AGG_FUNCTIONS:
            combo.addItem(libelle)
        is_num = field.type() in (QVariant.Int, QVariant.UInt, QVariant.LongLong,
                                  QVariant.ULongLong, QVariant.Double)
        combo.setCurrentText("Somme" if is_num else "Première valeur")
        self.tableAgg.setCellWidget(row, 1, combo)
        # Délimiteur
        self.tableAgg.setItem(row, 2, QTableWidgetItem(","))
        # Nom de sortie
        self.tableAgg.setItem(row, 3, QTableWidgetItem(field.name()))

    def get_aggregate_config(self):
        """Lit l'onglet et retourne (couche, group_by, liste AGGREGATES native QGIS)."""
        layer = self.comboAggInput.currentData()
        if layer is None:
            return None, None, None
        texte_group = self.comboAggGroup.currentText().strip()
        if texte_group.startswith("NULL") or texte_group == "":
            group_by = "NULL"
        elif texte_group in [f.name() for f in layer.fields()]:
            group_by = '"%s"' % texte_group
        else:
            group_by = texte_group  # expression libre

        kw_by_label = {lib: kw for lib, kw in self.AGG_FUNCTIONS}
        fields_by_name = {f.name(): f for f in layer.fields()}
        aggregates = []
        for row in range(self.tableAgg.rowCount()):
            nom_source = self.tableAgg.item(row, 0).text()
            combo = self.tableAgg.cellWidget(row, 1)
            kw = kw_by_label.get(combo.currentText())
            if kw is None:
                continue  # champ ignoré
            delim = self.tableAgg.item(row, 2).text() if self.tableAgg.item(row, 2) else ","
            nom_sortie = self.tableAgg.item(row, 3).text() if self.tableAgg.item(row, 3) else nom_source
            field = fields_by_name[nom_source]
            vtype, type_name, length, precision = self._agg_output_type(field, kw)
            aggregates.append({
                'aggregate': kw,
                'delimiter': delim,
                'input': '"%s"' % nom_source,
                'length': length,
                'name': nom_sortie or nom_source,
                'precision': precision,
                'type': int(vtype),
                'type_name': type_name,
                'sub_type': 0,
            })
        return layer, group_by, aggregates

    @staticmethod
    def _agg_output_type(field, kw):
        """Déduit le type de sortie selon la fonction d'agrégation."""
        if kw in ('count', 'count_distinct'):
            return (QVariant.LongLong, 'integer', 0, 0)
        if kw in ('mean', 'median', 'stdev'):
            return (QVariant.Double, 'double precision', 20, 6)
        if kw in ('concatenate', 'concatenate_unique'):
            return (QVariant.String, 'string', 0, 0)
        # first_value, last_value, min, max, sum, minority, majority -> type d'origine
        tn = field.typeName() or 'string'
        return (field.type(), tn, field.length(), field.precision())

    def show_help(self):
        QMessageBox.information(
            self, "Aide — EDEA_EraseTools v6.0.1",
            "<h2>EDEA_EraseTools v6.0.1</h2>"
            "<p><b>Objectif :</b> Supprimer la partie d'une couche vectorielle (points, lignes ou "
            "polygones) située à l'intérieur d'une couche de découpe, quel que soit le type de "
            "géométrie des deux couches.</p>"
            "<h3>Modes</h3><ul>"
            "<li><b>Simple :</b> un seul fichier de sortie</li>"
            "<li><b>Par lot :</b> un fichier par entité de la couche de découpe</li>"
            "<li><b>Prévisualisation :</b> couche temporaire sans écriture</li>"
            "</ul>"
            "<h3>Options clés</h3><ul>"
            "<li><b>Buffer :</b> élargit la couche source avant traitement</li>"
            "<li><b>Mode inversé :</b> conserve l'intérieur (CLIP)</li>"
            "<li><b>Différence symétrique :</b> les deux parties séparément</li>"
            "<li><b>Sélection carte :</b> utilise les entités sélectionnées sur la carte</li>"
            "<li><b>Validation des chevauchements :</b> détecte les recouvrements dans la couche de découpe</li>"
            "<li><b>PostGIS / GeoServer :</b> exporte directement vers une base ou un serveur cartographique</li>"
            "<li><b>Topologie :</b> vérifie les coupures après traitement</li>"
            "<li><b>Métadonnées :</b> ajoute des métadonnées INSPIRE</li>"
            "<li><b>Graphique :</b> visualisation matplotlib des statistiques</li>"
            "<li><b>Historique :</b> conserve la trace des traitements exécutés</li>"
            "<li><b>Zoom comparatif :</b> compare visuellement l'avant et l'après</li>"
            "</ul>"
            "<p><b>Dépôt du projet / signaler un problème :</b><br>"
            "<a href='https://github.com/edeaemile72-bit/EDEA_EraseTools'>"
            "github.com/edeaemile72-bit/EDEA_EraseTools</a></p>"
        )
