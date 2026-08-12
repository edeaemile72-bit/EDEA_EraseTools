# -*- coding: utf-8 -*-
"""
Plugin QGIS 3 — EDEA_EraseTools v6.0

Plugin généralisé à TOUT type de couche vectorielle (points, lignes, polygones) :
supprime la partie d'une couche source située à l'intérieur d'une couche de découpe.

Fonctionnalités :
  • Généraliste : fonctionne avec tout type de géométrie, sans restriction
  • Traitement asynchrone (QThread)
  • Mode simple / par lot / prévisualisation
  • Filtre attributaire QGIS sur couche source et couche de découpe
  • Sélection interactive des entités de découpe sur la carte
  • Buffer optionnel avant traitement
  • Fusion optionnelle des entités de découpe
  • Mode inversé (CLIP) et différence symétrique
  • Validation des chevauchements (détection de recouvrements)
  • Export multi-format : SHP, GPKG, GeoJSON, KML, PostGIS, GeoServer (API REST)
  • Couche "partie supprimée" automatique
  • Statistiques avec graphiques matplotlib
  • Rapport HTML stylisé
  • Export CSV des statistiques
  • Table de correspondance batch (CSV)
  • Journal détaillé exportable
  • Validation topologique post-traitement
  • Métadonnées INSPIRE automatiques
  • Symbologie automatique (vert/rouge/orange)
  • Vérification de compatibilité SCR
  • Historique des actions exécutées
  • Zoom comparatif avant / après
  • Sauvegarde des paramètres (QSettings)
  • Aide contextuelle intégrée
  • Algorithme Processing intégré
"""

import os
import shutil
from datetime import datetime

from qgis.PyQt.QtCore import QCoreApplication, Qt
from qgis.PyQt.QtGui import QIcon, QColor, QPixmap
from qgis.PyQt.QtWidgets import QAction, QMessageBox, QFileDialog

from qgis.core import (
    QgsVectorLayer, QgsVectorFileWriter, QgsProject,
    QgsCoordinateTransformContext, QgsCoordinateReferenceSystem,
    QgsWkbTypes, QgsFeature, QgsFields, QgsProcessing,
    QgsProcessingAlgorithm, QgsProcessingParameterFeatureSink,
    QgsProcessingParameterBoolean, QgsProcessingParameterCrs,
    QgsProcessingParameterFeatureSource, QgsProcessingParameterString,
    QgsProcessingParameterEnum, QgsProcessingParameterNumber,
    QgsProcessingUtils, QgsProcessingContext, QgsProcessingFeedback,
    QgsProcessingException, QgsProcessingProvider, QgsApplication,
    QgsFeatureSink, QgsSingleSymbolRenderer, QgsSymbol,
    QgsMapLayerProxyModel, QgsRectangle, QgsDataSourceUri,
)

import processing

from .edea_erasetools_dialog import EdeaEraseToolsDialog
from .worker import EraseWorker
from .comparaison_dialog import ComparaisonDialog


# =============================================================================
# ALGORITHME PROCESSING v6.0 — généralisé à tout type de géométrie
# =============================================================================

class EdeaEraseToolsAlgorithm(QgsProcessingAlgorithm):
    INPUT_SOURCE = 'INPUT_SOURCE'
    INPUT_DECOUPE = 'INPUT_DECOUPE'
    OUTPUT = 'OUTPUT'
    OUTPUT_SUPPRIME = 'OUTPUT_SUPPRIME'
    REPAIR_GEOM = 'REPAIR_GEOM'
    OUTPUT_CRS = 'OUTPUT_CRS'
    KEEP_FIELDS = 'KEEP_FIELDS'
    MODE_INVERSE = 'MODE_INVERSE'
    FUSION_DECOUPE = 'FUSION_DECOUPE'
    FILTRE_SOURCE = 'FILTRE_SOURCE'
    FILTRE_DECOUPE = 'FILTRE_DECOUPE'
    BUFFER_DIST = 'BUFFER_DIST'
    BUFFER_SEGMENTS = 'BUFFER_SEGMENTS'
    DIFF_SYM = 'DIFF_SYM'

    def name(self):
        return 'edea_erasetools'

    def displayName(self):
        return self.tr('EDEA_EraseTools')

    def group(self):
        return self.tr('Vector overlay')

    def groupId(self):
        return 'vectoroverlay'

    def shortHelpString(self):
        return self.tr(
            "Supprime la partie d'une couche source (tout type de géométrie) située à "
            "l'intérieur d'une couche de découpe (tout type de géométrie). "
            "Options : buffer, filtre attributaire, mode inversé, différence symétrique, "
            "fusion, réparation géométries, couche supprimée."
        )

    def tr(self, string):
        return QCoreApplication.translate('EdeaEraseToolsAlgorithm', string)

    def createInstance(self):
        return EdeaEraseToolsAlgorithm()

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.INPUT_SOURCE, self.tr('Couche source (tout type)'), [QgsProcessing.TypeVectorAnyGeometry]))
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.INPUT_DECOUPE, self.tr('Couche de découpe (tout type)'), [QgsProcessing.TypeVectorAnyGeometry]))
        self.addParameter(QgsProcessingParameterString(
            self.FILTRE_SOURCE, self.tr('Filtre attributaire couche source'), optional=True, defaultValue=''))
        self.addParameter(QgsProcessingParameterString(
            self.FILTRE_DECOUPE, self.tr('Filtre attributaire couche de découpe'), optional=True, defaultValue=''))
        self.addParameter(QgsProcessingParameterBoolean(
            self.REPAIR_GEOM, self.tr('Réparer les géométries'), defaultValue=True))
        self.addParameter(QgsProcessingParameterBoolean(
            self.FUSION_DECOUPE, self.tr('Fusionner les entités de la couche de découpe'), defaultValue=True))
        self.addParameter(QgsProcessingParameterNumber(
            self.BUFFER_DIST, self.tr('Buffer couche source (m, 0 = désactivé)'),
            type=QgsProcessingParameterNumber.Double, defaultValue=0, minValue=0))
        self.addParameter(QgsProcessingParameterNumber(
            self.BUFFER_SEGMENTS, self.tr('Segments buffer'),
            type=QgsProcessingParameterNumber.Integer, defaultValue=8, minValue=3))
        self.addParameter(QgsProcessingParameterBoolean(
            self.MODE_INVERSE, self.tr('Mode inversé (clip)'), defaultValue=False))
        self.addParameter(QgsProcessingParameterBoolean(
            self.DIFF_SYM, self.tr('Différence symétrique'), defaultValue=False))
        self.addParameter(QgsProcessingParameterCrs(
            self.OUTPUT_CRS, self.tr('SCR de sortie (vide = source)'), optional=True))
        self.addParameter(QgsProcessingParameterBoolean(
            self.KEEP_FIELDS, self.tr('Conserver les champs'), defaultValue=True))
        self.addParameter(QgsProcessingParameterFeatureSink(
            self.OUTPUT, self.tr('Couche source hors découpe')))
        self.addParameter(QgsProcessingParameterFeatureSink(
            self.OUTPUT_SUPPRIME, self.tr('Partie supprimée'), optional=True))

    def processAlgorithm(self, parameters, context, feedback):
        source = self.parameterAsSource(parameters, self.INPUT_SOURCE, context)
        decoupe = self.parameterAsSource(parameters, self.INPUT_DECOUPE, context)
        filtre_source = self.parameterAsString(parameters, self.FILTRE_SOURCE, context)
        filtre_decoupe = self.parameterAsString(parameters, self.FILTRE_DECOUPE, context)
        repair = self.parameterAsBool(parameters, self.REPAIR_GEOM, context)
        fusion = self.parameterAsBool(parameters, self.FUSION_DECOUPE, context)
        buffer_dist = self.parameterAsDouble(parameters, self.BUFFER_DIST, context)
        buffer_segments = self.parameterAsInt(parameters, self.BUFFER_SEGMENTS, context)
        mode_inverse = self.parameterAsBool(parameters, self.MODE_INVERSE, context)
        diff_sym = self.parameterAsBool(parameters, self.DIFF_SYM, context)
        out_crs = self.parameterAsCrs(parameters, self.OUTPUT_CRS, context)
        keep_fields = self.parameterAsBool(parameters, self.KEEP_FIELDS, context)

        layer_source = self.parameterAsVectorLayer(parameters, self.INPUT_SOURCE, context)
        layer_decoupe = self.parameterAsVectorLayer(parameters, self.INPUT_DECOUPE, context)
        couche_source = layer_source
        couche_decoupe = layer_decoupe

        # Filtres
        if filtre_source:
            res = processing.run("native:extractbyexpression", {
                'INPUT': couche_source, 'EXPRESSION': filtre_source, 'OUTPUT': 'TEMPORARY_OUTPUT'
            }, context=context, feedback=feedback)
            couche_source = res['OUTPUT']
        if filtre_decoupe:
            res = processing.run("native:extractbyexpression", {
                'INPUT': couche_decoupe, 'EXPRESSION': filtre_decoupe, 'OUTPUT': 'TEMPORARY_OUTPUT'
            }, context=context, feedback=feedback)
            couche_decoupe = res['OUTPUT']

        # Réparation — sur LES DEUX couches, et avant tout algorithme sensible
        # aux géométries invalides (fusion, buffer, difference/clip).
        if repair:
            res = processing.run("native:fixgeometries", {
                'INPUT': couche_source, 'OUTPUT': 'TEMPORARY_OUTPUT'
            }, context=context, feedback=feedback)
            couche_source = res['OUTPUT']
            res = processing.run("native:fixgeometries", {
                'INPUT': couche_decoupe, 'OUTPUT': 'TEMPORARY_OUTPUT'
            }, context=context, feedback=feedback)
            couche_decoupe = res['OUTPUT']

        # Buffer
        if buffer_dist > 0:
            res = processing.run("native:buffer", {
                'INPUT': couche_source, 'DISTANCE': buffer_dist, 'SEGMENTS': buffer_segments,
                'END_CAP_STYLE': 0, 'JOIN_STYLE': 0, 'MITER_LIMIT': 2, 'DISSOLVE': False,
                'OUTPUT': 'TEMPORARY_OUTPUT'
            }, context=context, feedback=feedback)
            couche_source = res['OUTPUT']

        # Fusion
        if fusion and couche_decoupe.featureCount() > 1:
            res = processing.run("native:dissolve", {
                'INPUT': couche_decoupe, 'FIELD': [], 'OUTPUT': 'TEMPORARY_OUTPUT'
            }, context=context, feedback=feedback)
            couche_decoupe = res['OUTPUT']

        # Traitement principal
        algo = "native:clip" if mode_inverse else "native:difference"
        res = processing.run(algo, {
            'INPUT': couche_source, 'OVERLAY': couche_decoupe, 'OUTPUT': 'TEMPORARY_OUTPUT'
        }, context=context, feedback=feedback)
        resultat = res['OUTPUT']

        # Partie supprimée
        couche_supprimee = None
        if self.OUTPUT_SUPPRIME in parameters and parameters[self.OUTPUT_SUPPRIME]:
            if diff_sym:
                algo_suppr = "native:intersection"
            else:
                algo_suppr = "native:difference" if mode_inverse else "native:intersection"
            res_suppr = processing.run(algo_suppr, {
                'INPUT': couche_source, 'OVERLAY': couche_decoupe, 'OUTPUT': 'TEMPORARY_OUTPUT'
            }, context=context, feedback=feedback)
            couche_supprimee = res_suppr['OUTPUT']

        # Reprojection
        if out_crs.isValid() and out_crs != resultat.crs():
            res = processing.run("native:reprojectlayer", {
                'INPUT': resultat, 'TARGET_CRS': out_crs, 'OUTPUT': 'TEMPORARY_OUTPUT'
            }, context=context, feedback=feedback)
            resultat = res['OUTPUT']
            if couche_supprimee:
                res = processing.run("native:reprojectlayer", {
                    'INPUT': couche_supprimee, 'TARGET_CRS': out_crs, 'OUTPUT': 'TEMPORARY_OUTPUT'
                }, context=context, feedback=feedback)
                couche_supprimee = res['OUTPUT']

        # Sink principal
        fields = resultat.fields() if keep_fields else QgsFields()
        (sink, dest_id) = self.parameterAsSink(
            parameters, self.OUTPUT, context, fields, resultat.wkbType(), resultat.crs())
        total = resultat.featureCount()
        for i, feat in enumerate(resultat.getFeatures()):
            if feedback.isCanceled(): break
            sink.addFeature(feat, QgsFeatureSink.FastInsert)
            feedback.setProgress(int(i / max(total, 1) * 50))

        # Sink supprimé
        dest_id_suppr = None
        if couche_supprimee:
            fields_suppr = couche_supprimee.fields() if keep_fields else QgsFields()
            (sink_suppr, dest_id_suppr) = self.parameterAsSink(
                parameters, self.OUTPUT_SUPPRIME, context, fields_suppr,
                couche_supprimee.wkbType(), couche_supprimee.crs())
            for i, feat in enumerate(couche_supprimee.getFeatures()):
                if feedback.isCanceled(): break
                sink_suppr.addFeature(feat, QgsFeatureSink.FastInsert)
            feedback.setProgress(100)

        return {self.OUTPUT: dest_id, self.OUTPUT_SUPPRIME: dest_id_suppr}


class EdeaEraseToolsProvider(QgsProcessingProvider):
    def __init__(self):
        super().__init__()
    def loadAlgorithms(self):
        self.addAlgorithm(EdeaEraseToolsAlgorithm())
    def id(self):
        return 'edea_erasetools_provider'
    def name(self):
        return 'EDEA_EraseTools'
    def icon(self):
        return QIcon(os.path.join(os.path.dirname(__file__), 'icon.png'))
    def supportsNonFileBasedOutput(self):
        return True


# =============================================================================
# PLUGIN PRINCIPAL
# =============================================================================

class EdeaEraseToolsPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        self.dlg = None
        self.action = None
        self.provider = None
        self.worker = None
        self.couches_crees = []
        self.dernier_rapport_html = ""
        self.dernier_csv = ""
        self.dernier_table_batch = ""
        self.dernier_journal = ""
        self.derniere_couche_avant = None
        self.derniere_couche_apres = None
        self.comparaison_dlg = None

        self.dlg = EdeaEraseToolsDialog()
        self.dlg.btnExecuter.clicked.connect(self.run_process)
        self.dlg.btnAnnuler.clicked.connect(self.annuler_traitement)
        self.dlg.btnRapport.clicked.connect(self.ouvrir_rapport)
        self.dlg.btnCSV.clicked.connect(self.ouvrir_csv)
        self.dlg.btnJournal.clicked.connect(self.ouvrir_journal)
        self.dlg.btnSelectionnerARRD.clicked.connect(self.selectionner_decoupe_carte)
        self.dlg.btnZoomComparatif.clicked.connect(self.zoom_comparatif)

    def initGui(self):
        icon_path = os.path.join(self.plugin_dir, 'icon.png')
        self.action = QAction(QIcon(icon_path), "EDEA_EraseTools", self.iface.mainWindow())
        self.action.triggered.connect(self.run)
        self.iface.addToolBarIcon(self.action)
        self.iface.addPluginToVectorMenu("&EDEA_EraseTools", self.action)

        self.action_undo = QAction("🗑 Supprimer les couches créées par EDEA_EraseTools", self.iface.mainWindow())
        self.action_undo.triggered.connect(self.supprimer_couches_crees)
        self.iface.addPluginToVectorMenu("&EDEA_EraseTools", self.action_undo)

        self.provider = EdeaEraseToolsProvider()
        QgsApplication.processingRegistry().addProvider(self.provider)

    def unload(self):
        self.iface.removePluginVectorMenu("&EDEA_EraseTools", self.action)
        self.iface.removePluginVectorMenu("&EDEA_EraseTools", self.action_undo)
        self.iface.removeToolBarIcon(self.action)
        del self.action
        if self.provider:
            QgsApplication.processingRegistry().removeProvider(self.provider)

    def run(self):
        self.populate_combos()
        self.dlg.progressBar.setValue(0)
        self.dlg.textLog.clear()
        self.dlg.reset_stats()
        self.dlg.btnRapport.setEnabled(False)
        self.dlg.btnCSV.setEnabled(False)
        self.dlg.btnJournal.setEnabled(False)
        self.dlg.btnExecuter.setEnabled(True)
        self.dlg.btnAnnuler.setEnabled(False)
        self.dlg.show()
        self.dlg.raise_()
        self.dlg.activateWindow()

    def populate_combos(self):
        """Liste TOUTES les couches vectorielles, sans restriction de type de géométrie :
        le plugin est généraliste et fonctionne avec points, lignes ou polygones."""
        self.dlg.comboSource.clear()
        self.dlg.comboDecoupe.clear()
        layers = QgsProject.instance().mapLayers().values()
        for layer in layers:
            if layer.type() != layer.VectorLayer:
                continue
            self.dlg.comboSource.addItem(layer.name(), layer)
            self.dlg.comboDecoupe.addItem(layer.name(), layer)
        if self.dlg.comboSource.count() == 0:
            self.dlg.comboSource.addItem("-- Aucune couche vectorielle --", None)
        if self.dlg.comboDecoupe.count() == 0:
            self.dlg.comboDecoupe.addItem("-- Aucune couche vectorielle --", None)
        self.dlg.on_decoupe_changed()
        self.dlg.on_source_changed()

    # ------------------------------------------------------------------
    # SÉLECTION INTERACTIVE
    # ------------------------------------------------------------------

    def selectionner_decoupe_carte(self):
        """Récupère les entités sélectionnées sur la couche de découpe active."""
        layer = self.dlg.comboDecoupe.currentData()
        if not layer or not layer.isValid():
            QMessageBox.warning(self.dlg, "Couche de découpe", "Veuillez d'abord sélectionner une couche de découpe.")
            return

        selected = layer.selectedFeatures()
        if not selected:
            QMessageBox.information(self.dlg, "Sélection",
                f"Aucune entité sélectionnée sur {layer.name()}.\n"
                f"Sélectionnez des entités sur la carte avec l'outil de sélection, puis recliquez.")
            return

        self.dlg.checkSelectionCarte.setChecked(True)
        self.dlg.log(f"✓ {len(selected)} entité(s) de découpe sélectionnée(s) sur la carte")
        QMessageBox.information(self.dlg, "Sélection", f"{len(selected)} entité(s) sélectionnée(s) utilisées.")

    # ------------------------------------------------------------------
    # ZOOM COMPARATIF (avant / après)
    # ------------------------------------------------------------------

    def zoom_comparatif(self):
        if self.derniere_couche_avant is None or self.derniere_couche_apres is None:
            QMessageBox.information(self.dlg, "Zoom comparatif",
                "Exécutez d'abord un traitement pour pouvoir comparer l'avant et l'après.")
            return
        if self.comparaison_dlg is None:
            self.comparaison_dlg = ComparaisonDialog(self.dlg)
        self.comparaison_dlg.set_layers(self.derniere_couche_avant, self.derniere_couche_apres)
        self.comparaison_dlg.show()
        self.comparaison_dlg.raise_()
        self.comparaison_dlg.activateWindow()

    # ------------------------------------------------------------------
    # LANCEMENT DU TRAITEMENT
    # ------------------------------------------------------------------

    def run_process(self):
        couche_source = self.dlg.comboSource.currentData()
        couche_decoupe = self.dlg.comboDecoupe.currentData()

        if couche_source is None or couche_decoupe is None:
            QMessageBox.warning(self.dlg, "Couches manquantes",
                                "Veuillez sélectionner une couche source et une couche de découpe.")
            return
        if not couche_source.isValid() or not couche_decoupe.isValid():
            QMessageBox.warning(self.dlg, "Couches invalides", "L'une des couches est invalide.")
            return

        # Gestion de la sélection sur la carte
        if self.dlg.checkSelectionCarte.isChecked():
            selected = couche_decoupe.selectedFeatures()
            if selected:
                geom_type_str = QgsWkbTypes.geometryDisplayString(couche_decoupe.geometryType())
                mem_layer = QgsVectorLayer(f"{geom_type_str}?crs=" + couche_decoupe.crs().authid(), "selection_decoupe", "memory")
                mem_layer.dataProvider().addAttributes(couche_decoupe.fields().toList())
                mem_layer.updateFields()
                mem_layer.dataProvider().addFeatures(selected)
                couche_decoupe = mem_layer
                self.dlg.log(f"✓ Utilisation de {len(selected)} entité(s) sélectionnée(s)")
            else:
                QMessageBox.warning(self.dlg, "Sélection vide",
                    "Aucune entité sélectionnée sur la couche de découpe.")
                return

        # Vérification SCR
        if self.dlg.checkVerifierSCR.isChecked():
            crs_source = couche_source.crs()
            crs_decoupe = couche_decoupe.crs()
            if crs_source != crs_decoupe:
                reply = QMessageBox.question(
                    self.dlg, "SCR différents",
                    f"Les couches ont des SCR différents :\n"
                    f"• Source : {crs_source.authid()}\n"
                    f"• Découpe : {crs_decoupe.authid()}\n\n"
                    f"Continuer quand même ?",
                    QMessageBox.Yes | QMessageBox.No
                )
                if reply == QMessageBox.No:
                    return

        # Mode
        if self.dlg.radioPreview.isChecked():
            mode = 'preview'
        elif self.dlg.radioBatch.isChecked():
            mode = 'batch'
        else:
            mode = 'simple'

        # Paramètres
        params = {
            'source': couche_source,
            'source_orig': self.dlg.comboSource.currentData(),
            'decoupe': couche_decoupe,
            'decoupe_orig': self.dlg.comboDecoupe.currentData(),
            'mode': mode,
            'filtre_source': self.dlg.lineEditFiltreSource.text().strip() or None,
            'filtre_decoupe': self.dlg.lineEditFiltreDecoupe.text().strip() or None,
            'valider_geom': self.dlg.checkValiderGeom.isChecked(),
            'fusionner_decoupe': self.dlg.checkFusionnerARRD.isChecked(),
            'verifier_scr': self.dlg.checkVerifierSCR.isChecked(),
            'validation_chevauchement': self.dlg.checkValidationChevauchement.isChecked(),
            'buffer_actif': self.dlg.checkBuffer.isChecked(),
            'buffer_dist': self.dlg.spinBufferDist.value(),
            'buffer_segments': self.dlg.spinBufferSegments.value(),
            'mode_inverse': self.dlg.checkModeInverse.isChecked(),
            'diff_symetrique': self.dlg.checkDiffSymetrique.isChecked(),
            'couche_supprimee': self.dlg.checkCoucheSupprimee.isChecked(),
            'overwrite': (self.dlg.comboAction.currentIndex() == 1),
            'dossier': self.dlg.lineEditDossier.text().strip(),
            'prefixe': self.dlg.lineEditPrefixe.text().strip(),
            'expr_batch': self.dlg.lineEditExprBatch.text().strip(),
            'champ_id': self.dlg.comboChampId.currentData(),
            'scr': self.dlg.comboSCR.currentData(),
            'format': self.dlg.comboFormat.currentIndex(),
            'ajouter_couche': self.dlg.checkAjouterCouche.isChecked(),
            'symbologie': self.dlg.checkSymbologie.isChecked(),
            'rapport_html': self.dlg.checkRapportHTML.isChecked(),
            'export_csv': self.dlg.checkExportCSV.isChecked(),
            'table_batch': self.dlg.checkTableBatch.isChecked(),
            'journal': self.dlg.checkJournal.isChecked(),
            'topologie': self.dlg.checkTopologie.isChecked(),
            'metadonnees': self.dlg.checkMetadonnees.isChecked(),
            'historique': self.dlg.checkHistorique.isChecked(),
            'merge_batch': self.dlg.checkMergeBatch.isChecked(),
            # PostGIS
            'pg_host': self.dlg.lineEditPgHost.text(),
            'pg_port': self.dlg.spinPgPort.value(),
            'pg_db': self.dlg.lineEditPgDb.text(),
            'pg_user': self.dlg.lineEditPgUser.text(),
            'pg_pass': self.dlg.lineEditPgPass.text(),
            'pg_schema': self.dlg.lineEditPgSchema.text(),
            'pg_table': self.dlg.lineEditPgTable.text(),
            # GeoServer
            'gs_url': self.dlg.lineEditGsUrl.text(),
            'gs_workspace': self.dlg.lineEditGsWorkspace.text(),
            'gs_datastore': self.dlg.lineEditGsDatastore.text(),
            'gs_user': self.dlg.lineEditGsUser.text(),
            'gs_pass': self.dlg.lineEditGsPass.text(),
            'gs_layer': self.dlg.lineEditGsLayer.text(),
        }

        # Validation dossier
        if mode != 'preview' and params['format'] not in (4, 5) and not params['overwrite'] and not params['dossier']:
            QMessageBox.warning(self.dlg, "Dossier manquant", "Veuillez choisir un dossier de sortie.")
            return

        # Validation PostGIS
        if params['format'] == 4:
            if not params['pg_db'] or not params['pg_table']:
                QMessageBox.warning(self.dlg, "PostGIS", "Veuillez renseigner la base et la table PostGIS.")
                return

        # Validation GeoServer
        if params['format'] == 5:
            if not params['gs_url'] or not params['gs_workspace'] or not params['gs_datastore']:
                QMessageBox.warning(self.dlg, "GeoServer", "Veuillez renseigner l'URL, le workspace et le datastore GeoServer.")
                return

        # Sauvegarder les paramètres
        self.dlg.save_settings()

        # Conserver la reference "avant" pour le zoom comparatif
        self.derniere_couche_avant = params['source_orig']

        # UI
        self.dlg.btnExecuter.setEnabled(False)
        self.dlg.btnAnnuler.setEnabled(True)
        self.dlg.progressBar.setValue(0)
        self.dlg.textLog.clear()
        self.dlg.reset_stats()
        self.dlg.btnRapport.setEnabled(False)
        self.dlg.btnCSV.setEnabled(False)
        self.dlg.btnJournal.setEnabled(False)

        # Worker
        self.worker = EraseWorker(params)
        self.worker.log_signal.connect(self.dlg.log)
        self.worker.progress_signal.connect(self.dlg.progressBar.setValue)
        self.worker.stats_signal.connect(self.dlg.set_stats)
        self.worker.graph_signal.connect(self.on_graph_received)
        self.worker.finished_signal.connect(self.on_worker_finished)
        self.worker.error_signal.connect(self.on_worker_error)
        self.worker.start()

    def on_graph_received(self, png_bytes):
        """Affiche le graphique matplotlib reçu du worker."""
        try:
            pixmap = QPixmap()
            pixmap.loadFromData(png_bytes)
            self.dlg.set_graph(pixmap)
        except Exception as e:
            self.dlg.log(f"⚠ Impossible d'afficher le graphique : {e}")

    def annuler_traitement(self):
        if self.worker and self.worker.isRunning():
            self.dlg.log("⏹ Annulation demandée…")
            self.worker.stop()
            self.worker = None
        self.dlg.btnExecuter.setEnabled(True)
        self.dlg.btnAnnuler.setEnabled(False)
        self.dlg.progressBar.setValue(0)

    def on_worker_error(self, message):
        self.dlg.log(f"❌ ERREUR : {message}")
        QMessageBox.critical(self.dlg, "Erreur", message)
        self.dlg.btnExecuter.setEnabled(True)
        self.dlg.btnAnnuler.setEnabled(False)
        self.worker = None

    def on_worker_finished(self, success, message, fichiers_crees, rapport_html, csv_content, table_batch_csv, journal_content, info_historique):
        self.dlg.btnExecuter.setEnabled(True)
        self.dlg.btnAnnuler.setEnabled(False)

        if not success:
            self.worker = None
            return

        params = self.worker.params if self.worker else {}
        self.worker = None

        # Stocker les rapports
        self.dernier_rapport_html = rapport_html
        self.dernier_csv = csv_content
        self.dernier_table_batch = table_batch_csv
        self.dernier_journal = journal_content

        # Ajouter les fichiers créés au projet
        derniere_couche_ajoutee = None
        if params.get('ajouter_couche') and fichiers_crees:
            for chemin in fichiers_crees:
                couche_ajoutee = self._ajouter_au_projet(chemin, params)
                if couche_ajoutee is not None:
                    derniere_couche_ajoutee = couche_ajoutee

        # Charger le résultat pour le zoom comparatif, même si "ajouter au projet" est décoché
        if derniere_couche_ajoutee is not None:
            self.derniere_couche_apres = derniere_couche_ajoutee
        elif fichiers_crees:
            premier_chemin = fichiers_crees[0]
            if isinstance(premier_chemin, str) and os.path.exists(premier_chemin):
                temp = QgsVectorLayer(premier_chemin, "resultat_apres", "ogr")
                if temp.isValid():
                    self.derniere_couche_apres = temp
        self.dlg.btnZoomComparatif.setEnabled(
            self.derniere_couche_avant is not None and self.derniere_couche_apres is not None
        )

        # Historique
        if params.get('historique') and info_historique:
            date_str = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
            self.dlg.ajouter_entree_historique(
                date_str,
                info_historique.get('mode', '—'),
                info_historique.get('algo', '—'),
                info_historique.get('source', '—'),
                info_historique.get('decoupe', '—'),
                info_historique.get('resultat', '—'),
                info_historique.get('nb_entites', '—'),
            )

        # Sauvegarder les rapports
        dossier = params.get('dossier') or (os.path.dirname(fichiers_crees[0]) if fichiers_crees and isinstance(fichiers_crees[0], str) and os.path.exists(os.path.dirname(fichiers_crees[0]) or ".") else ".")

        if rapport_html:
            self.dlg.btnRapport.setEnabled(True)
            chemin_rapport = os.path.join(dossier, "rapport_edea_erasetools.html")
            try:
                with open(chemin_rapport, 'w', encoding='utf-8') as f:
                    f.write(rapport_html)
                self.dlg.log(f"✓ Rapport HTML : {chemin_rapport}")
            except Exception as e:
                self.dlg.log(f"⚠ Rapport HTML non sauvegardé : {e}")

        if csv_content:
            self.dlg.btnCSV.setEnabled(True)
            chemin_csv = os.path.join(dossier, "statistiques_edea_erasetools.csv")
            try:
                with open(chemin_csv, 'w', encoding='utf-8') as f:
                    f.write(csv_content)
                self.dlg.log(f"✓ Statistiques CSV : {chemin_csv}")
            except Exception as e:
                self.dlg.log(f"⚠ CSV non sauvegardé : {e}")

        if table_batch_csv:
            chemin_table = os.path.join(dossier, "table_batch_edea_erasetools.csv")
            try:
                with open(chemin_table, 'w', encoding='utf-8') as f:
                    f.write(table_batch_csv)
                self.dlg.log(f"✓ Table batch CSV : {chemin_table}")
            except Exception as e:
                self.dlg.log(f"⚠ Table batch non sauvegardée : {e}")

        if journal_content:
            self.dlg.btnJournal.setEnabled(True)
            chemin_journal = os.path.join(dossier, "journal_edea_erasetools.txt")
            try:
                with open(chemin_journal, 'w', encoding='utf-8') as f:
                    f.write(journal_content)
                self.dlg.log(f"✓ Journal : {chemin_journal}")
            except Exception as e:
                self.dlg.log(f"⚠ Journal non sauvegardé : {e}")

        QMessageBox.information(self.dlg, "Succès", message)

    def ouvrir_rapport(self):
        if self.dernier_rapport_html:
            chemin, _ = QFileDialog.getSaveFileName(
                self.dlg, "Enregistrer le rapport HTML", "rapport_edea_erasetools.html", "HTML (*.html)")
            if chemin:
                with open(chemin, 'w', encoding='utf-8') as f:
                    f.write(self.dernier_rapport_html)
                QMessageBox.information(self.dlg, "Rapport", f"Enregistré : {chemin}")

    def ouvrir_csv(self):
        if self.dernier_csv:
            chemin, _ = QFileDialog.getSaveFileName(
                self.dlg, "Enregistrer le CSV", "statistiques_edea_erasetools.csv", "CSV (*.csv)")
            if chemin:
                with open(chemin, 'w', encoding='utf-8') as f:
                    f.write(self.dernier_csv)
                QMessageBox.information(self.dlg, "CSV", f"Enregistré : {chemin}")

    def ouvrir_journal(self):
        if self.dernier_journal:
            chemin, _ = QFileDialog.getSaveFileName(
                self.dlg, "Enregistrer le journal", "journal_edea_erasetools.txt", "Texte (*.txt)")
            if chemin:
                with open(chemin, 'w', encoding='utf-8') as f:
                    f.write(self.dernier_journal)
                QMessageBox.information(self.dlg, "Journal", f"Enregistré : {chemin}")

    def supprimer_couches_crees(self):
        if not self.couches_crees:
            QMessageBox.information(self.iface.mainWindow(), "Aucune couche",
                                    "Aucune couche n'a été créée par le plugin.")
            return
        reply = QMessageBox.question(
            self.iface.mainWindow(), "Confirmer",
            f"Supprimer {len(self.couches_crees)} couche(s) créée(s) ?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            for layer_id in self.couches_crees:
                layer = QgsProject.instance().mapLayer(layer_id)
                if layer:
                    QgsProject.instance().removeMapLayer(layer)
            self.couches_crees.clear()
            self.iface.mapCanvas().refresh()
            QMessageBox.information(self.iface.mainWindow(), "Terminé", "Couches supprimées.")

    # ------------------------------------------------------------------
    # HELPERS
    # ------------------------------------------------------------------

    def _ajouter_au_projet(self, chemin, params, silent=False):
        if not isinstance(chemin, str) or chemin.startswith("PostGIS:") or chemin.startswith("GeoServer:"):
            if not silent:
                self.dlg.log(f"ℹ Sortie distante non chargée dans le projet : {chemin}")
            return None

        nom = os.path.splitext(os.path.basename(chemin))[0]
        ext = os.path.splitext(chemin)[1].lower()

        if ext == '.gpkg':
            uri = f"{chemin}|layername={nom}"
            couche = QgsVectorLayer(uri, nom, "ogr")
        else:
            couche = QgsVectorLayer(chemin, nom, "ogr")

        if couche.isValid():
            QgsProject.instance().addMapLayer(couche)
            self.couches_crees.append(couche.id())

            if params.get('symbologie') and not params.get('mode') == 'preview':
                self._appliquer_symbologie(couche, params.get('mode_inverse', False), "supprime" in nom.lower())

            if not silent:
                self.dlg.log(f"✓ Ajouté au projet : {nom}")
            return couche
        else:
            if not silent:
                self.dlg.log(f"⚠ Impossible de charger : {nom}")
            return None

    def _appliquer_symbologie(self, couche, mode_inverse=False, is_supprime=False):
        try:
            symbol = QgsSymbol.defaultSymbol(couche.geometryType())
            if symbol:
                if is_supprime:
                    symbol.setColor(QColor('#F44336'))
                elif mode_inverse:
                    symbol.setColor(QColor('#FF9800'))
                else:
                    symbol.setColor(QColor('#4CAF50'))
                symbol.setWidth(1.5)
                renderer = QgsSingleSymbolRenderer(symbol)
                couche.setRenderer(renderer)
                couche.triggerRepaint()
        except Exception:
            pass

    def _layer_source_path(self, layer):
        source = layer.source()
        if "|" in source: source = source.split("|")[0]
        if os.path.isfile(source): return source
        return None
