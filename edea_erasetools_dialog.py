# -*- coding: utf-8 -*-
"""
Dialogue du plugin EDEA_EraseTools v6.0
Généralisé à tout type de couche vectorielle (points, lignes, polygones).
"""

import os
import csv
import io
from qgis.PyQt import uic
from qgis.PyQt.QtCore import QSettings, Qt
from qgis.PyQt.QtWidgets import QDialog, QFileDialog, QMessageBox, QLabel, QTableWidgetItem
from qgis.PyQt.QtGui import QPixmap
from qgis.core import QgsProject, QgsCoordinateReferenceSystem, QgsVectorLayer

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

    def show_help(self):
        QMessageBox.information(
            self, "Aide — EDEA_EraseTools v6.0",
            "<h2>EDEA_EraseTools v6.0</h2>"
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
