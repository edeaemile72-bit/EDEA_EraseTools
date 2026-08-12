# -*- coding: utf-8 -*-
"""
Worker thread asynchrone pour EDEA_EraseTools v6.0.
Généralisé à tout type de couche vectorielle (points, lignes, polygones) :
la mesure (longueur / surface / nombre d'entités) s'adapte au type de
géométrie de chaque couche.
"""

import os
import html
import csv
import io
import shutil
import zipfile
import tempfile
import base64
import urllib.request
import urllib.error
from datetime import datetime

from qgis.PyQt.QtCore import QThread, pyqtSignal
from qgis.core import (
    QgsVectorLayer, QgsVectorFileWriter, QgsCoordinateTransformContext,
    QgsCoordinateReferenceSystem, QgsProject, QgsDistanceArea,
    QgsWkbTypes, QgsFeature, QgsFields, QgsExpression, QgsExpressionContext,
    QgsExpressionContextUtils, QgsDataSourceUri, QgsRectangle, QgsSpatialIndex,
)

import processing


class EraseWorker(QThread):
    log_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int)
    stats_signal = pyqtSignal(str, str, str, str, str, str, str)
    graph_signal = pyqtSignal(bytes)
    # success, message, fichiers_crees, rapport_html, csv_content, table_batch_csv, journal_content, info_historique
    finished_signal = pyqtSignal(bool, str, list, str, str, str, str, dict)
    error_signal = pyqtSignal(str)

    def __init__(self, params):
        super().__init__()
        self.params = params
        self._is_running = True
        self.fichiers_crees = []
        self.rapport_html = ""
        self.csv_content = ""
        self.table_batch_csv = ""
        self.journal_content = ""
        self._journal_lines = []

    def _jlog(self, msg):
        self._journal_lines.append(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")
        self.log_signal.emit(msg)

    def run(self):
        try:
            self._process()
        except Exception as e:
            self.error_signal.emit(str(e))
            self.journal_content = "\n".join(self._journal_lines)
            self.finished_signal.emit(False, str(e), [], "", "", "", self.journal_content, {})

    def stop(self):
        self._is_running = False
        self.wait(3000)

    def _check_cancelled(self):
        if not self._is_running:
            raise Exception("Traitement annulé par l'utilisateur.")

    def _progress(self, val):
        self.progress_signal.emit(val)

    def _appliquer_filtre(self, couche, expression_str):
        expr = QgsExpression(expression_str)
        if expr.hasParserError():
            raise Exception(f"Expression invalide : {expr.parserErrorString()}")
        res = processing.run("native:extractbyexpression", {
            'INPUT': couche, 'EXPRESSION': expression_str, 'OUTPUT': 'TEMPORARY_OUTPUT'
        })
        return res['OUTPUT']

    def _calculer_longueur(self, couche):
        da = QgsDistanceArea()
        da.setSourceCrs(couche.crs(), QgsProject.instance().transformContext())
        da.setEllipsoid(QgsProject.instance().ellipsoid())
        total = 0.0
        for feat in couche.getFeatures():
            if feat.hasGeometry():
                total += da.measureLength(feat.geometry())
        return total

    def _calculer_surface(self, couche):
        da = QgsDistanceArea()
        da.setSourceCrs(couche.crs(), QgsProject.instance().transformContext())
        da.setEllipsoid(QgsProject.instance().ellipsoid())
        total = 0.0
        for feat in couche.getFeatures():
            if feat.hasGeometry():
                total += da.measureArea(feat.geometry())
        return total

    def _mesurer(self, couche):
        """Mesure générique adaptée au type de géométrie de la couche :
        longueur (lignes), surface (polygones) ou nombre d'entités (points / autres).
        Retourne (valeur_numerique, texte_formate)."""
        geom_type = couche.geometryType()
        if geom_type == QgsWkbTypes.PolygonGeometry:
            valeur = self._calculer_surface(couche)
            return valeur, f"{valeur:,.2f} m²"
        elif geom_type == QgsWkbTypes.LineGeometry:
            valeur = self._calculer_longueur(couche)
            return valeur, f"{valeur:,.2f} m"
        else:
            valeur = couche.featureCount()
            return valeur, f"{valeur} entité(s)"

    def _reprojeter_si_besoin(self, couche):
        authid = self.params.get('scr')
        if not authid:
            return couche
        crs_dest = QgsCoordinateReferenceSystem(authid)
        if not crs_dest.isValid() or crs_dest == couche.crs():
            return couche
        self._jlog(f"⏳ Reprojection vers {authid}…")
        res = processing.run("native:reprojectlayer", {
            'INPUT': couche, 'TARGET_CRS': crs_dest, 'OUTPUT': 'TEMPORARY_OUTPUT'
        })
        self._jlog("✓ Reprojection effectuée")
        return res['OUTPUT']

    def _get_driver_and_ext(self):
        fmt = self.params.get('format', 0)
        formats = [
            ("ESRI Shapefile", ".shp"),
            ("GPKG", ".gpkg"),
            ("GeoJSON", ".geojson"),
            ("KML", ".kml"),
            ("PostGIS", ""),
            ("GeoServer", ""),
        ]
        return formats[fmt]

    def _ecrire_fichier(self, couche, chemin, driver="ESRI Shapefile"):
        options = QgsVectorFileWriter.SaveVectorOptions()
        options.driverName = driver
        options.fileEncoding = "UTF-8"
        options.actionOnExistingFile = QgsVectorFileWriter.CreateOrOverwriteFile
        err = QgsVectorFileWriter.writeAsVectorFormatV3(
            couche, chemin, QgsCoordinateTransformContext(), options
        )
        code_erreur = err[0] if isinstance(err, tuple) else err
        if code_erreur != QgsVectorFileWriter.NoError:
            raise Exception(f"Échec écriture ({driver}) : {err}")

    def _exporter_postgis(self, couche, params):
        uri = QgsDataSourceUri()
        uri.setConnection(
            params['pg_host'], str(params['pg_port']),
            params['pg_db'], params['pg_user'], params['pg_pass']
        )
        uri.setDataSource(params['pg_schema'], params['pg_table'], "geom")
        options = QgsVectorFileWriter.SaveVectorOptions()
        options.driverName = "PostgreSQL"
        options.layerName = params['pg_table']
        options.actionOnExistingFile = QgsVectorFileWriter.CreateOrOverwriteFile
        err = QgsVectorFileWriter.writeAsVectorFormatV3(
            couche, uri.uri(), QgsCoordinateTransformContext(), options
        )
        code_erreur = err[0] if isinstance(err, tuple) else err
        if code_erreur != QgsVectorFileWriter.NoError:
            raise Exception(f"Échec export PostGIS : {err}")
        self._jlog(f"✓ PostGIS : {params['pg_schema']}.{params['pg_table']}")

    def _exporter_geoserver(self, couche, params, nom_layer=None):
        """Publie la couche sur GeoServer via l'API REST (upload direct d'un shapefile zippé)."""
        gs_url = (params.get('gs_url') or '').rstrip('/')
        workspace = params.get('gs_workspace')
        datastore = params.get('gs_datastore')
        user = params.get('gs_user', '')
        pwd = params.get('gs_pass', '')

        if not gs_url or not workspace or not datastore:
            raise Exception("Paramètres GeoServer incomplets (URL, workspace, datastore requis).")

        nom = nom_layer or params.get('gs_layer') or couche.name()
        nom = "".join(c for c in str(nom) if c.isalnum() or c in ('_', '-')) or "couche"

        tmp_dir = tempfile.mkdtemp(prefix="edea_geoserver_")
        try:
            shp_path = os.path.join(tmp_dir, nom + ".shp")
            self._ecrire_fichier(couche, shp_path, "ESRI Shapefile")

            zip_path = os.path.join(tmp_dir, nom + ".zip")
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                base = os.path.splitext(shp_path)[0]
                for ext in [".shp", ".shx", ".dbf", ".prj", ".cpg"]:
                    f = base + ext
                    if os.path.exists(f):
                        zf.write(f, os.path.basename(f))

            endpoint = (f"{gs_url}/rest/workspaces/{workspace}/datastores/{datastore}"
                        f"/file.shp?configure=first&update=overwrite")

            with open(zip_path, 'rb') as f:
                data = f.read()

            req = urllib.request.Request(endpoint, data=data, method='PUT')
            req.add_header('Content-Type', 'application/zip')
            credentials = base64.b64encode(f"{user}:{pwd}".encode('utf-8')).decode('ascii')
            req.add_header('Authorization', f'Basic {credentials}')

            try:
                with urllib.request.urlopen(req, timeout=60) as resp:
                    code = resp.getcode()
                    self._jlog(f"✓ GeoServer : réponse HTTP {code}")
            except urllib.error.HTTPError as e:
                detail = e.read().decode('utf-8', errors='ignore')
                raise Exception(f"Échec export GeoServer (HTTP {e.code}) : {detail}")
            except urllib.error.URLError as e:
                raise Exception(f"Échec de connexion à GeoServer : {e.reason}")

            self._jlog(f"✓ GeoServer : couche « {nom} » publiée dans {workspace}:{datastore} ({gs_url})")
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def _supprimer_fichier(self, path):
        if not path:
            return
        base = os.path.splitext(path)[0]
        ext = os.path.splitext(path)[1].lower()
        if ext == '.shp':
            for e in [".shp", ".shx", ".dbf", ".prj", ".cpg", ".qpj", ".sbn", ".sbx", ".xml", ".shp.xml"]:
                f = base + e
                if os.path.exists(f): os.remove(f)
        elif ext in ('.gpkg', '.geojson', '.json', '.kml'):
            if os.path.exists(path): os.remove(path)

    def _copier_shapefile(self, src, dst):
        base_src = os.path.splitext(src)[0]
        base_dst = os.path.splitext(dst)[0]
        for e in [".shp", ".shx", ".dbf", ".prj", ".cpg", ".qpj", ".sbn", ".sbx", ".xml", ".shp.xml"]:
            f = base_src + e
            if os.path.exists(f): shutil.copyfile(f, base_dst + e)

    def _backup_path(self, original_path):
        base, ext = os.path.splitext(original_path)
        backup = f"{base}_BACKUP_avant_erase{ext}"
        counter = 1
        while os.path.exists(backup):
            backup = f"{base}_BACKUP_avant_erase_{counter}{ext}"
            counter += 1
        return backup

    def _layer_source_path(self, layer):
        source = layer.source()
        if "|" in source: source = source.split("|")[0]
        if os.path.isfile(source): return source
        return None

    def _ajouter_metadonnees(self, couche, description=""):
        try:
            md = couche.metadata()
            md.setIdentifier(str(datetime.now().timestamp()))
            md.setTitle(couche.name())
            md.setAbstract(description or "Couche générée par EDEA_EraseTools v6.0")
            md.setLanguage("fre")
            md.setCrs(couche.crs())
            couche.setMetadata(md)
        except Exception:
            pass

    def _valider_topologie(self, couche_source, couche_resultat):
        try:
            index = QgsSpatialIndex(couche_resultat.getFeatures())
            points_isoles = 0
            for feat in couche_resultat.getFeatures():
                if not feat.hasGeometry():
                    continue
                geom = feat.geometry()
                if geom.type() != QgsWkbTypes.LineGeometry:
                    continue
                if geom.isMultipart():
                    parts = geom.asMultiPolyline()
                    for part in parts:
                        if not part:
                            continue
                        for point in [part[0], part[-1]]:
                            rect = QgsRectangle(point.x() - 0.0001, point.y() - 0.0001,
                                               point.x() + 0.0001, point.y() + 0.0001)
                            ids = index.intersects(rect)
                            if len(ids) <= 1:
                                points_isoles += 1
                else:
                    part = geom.asPolyline()
                    if not part:
                        continue
                    for point in [part[0], part[-1]]:
                        rect = QgsRectangle(point.x() - 0.0001, point.y() - 0.0001,
                                           point.x() + 0.0001, point.y() + 0.0001)
                        ids = index.intersects(rect)
                        if len(ids) <= 1:
                            points_isoles += 1
            return points_isoles
        except Exception:
            return -1

    def _valider_chevauchement(self, couche):
        """Détecte les chevauchements (recouvrements) entre entités d'une même couche.
        Retourne (nb_paires_chevauchantes, surface_totale_chevauchement) ou (-1, 0.0) si non applicable."""
        try:
            if couche.geometryType() not in (QgsWkbTypes.PolygonGeometry, QgsWkbTypes.LineGeometry):
                return -1, 0.0

            features = [f for f in couche.getFeatures() if f.hasGeometry()]
            if len(features) < 2:
                return 0, 0.0

            index = QgsSpatialIndex()
            geoms = {}
            for feat in features:
                index.addFeature(feat)
                geoms[feat.id()] = feat.geometry()

            da = QgsDistanceArea()
            da.setSourceCrs(couche.crs(), QgsProject.instance().transformContext())
            da.setEllipsoid(QgsProject.instance().ellipsoid())

            nb_paires = 0
            surface_totale = 0.0
            deja_vus = set()

            for feat in features:
                self._check_cancelled()
                geom = geoms[feat.id()]
                candidats = index.intersects(geom.boundingBox())
                for cid in candidats:
                    if cid == feat.id():
                        continue
                    paire = tuple(sorted((feat.id(), cid)))
                    if paire in deja_vus:
                        continue
                    deja_vus.add(paire)
                    autre_geom = geoms.get(cid)
                    if autre_geom is None:
                        continue
                    if geom.overlaps(autre_geom):
                        nb_paires += 1
                        try:
                            inter = geom.intersection(autre_geom)
                            if inter and not inter.isEmpty():
                                surface_totale += da.measureArea(inter)
                        except Exception:
                            pass

            return nb_paires, surface_totale
        except Exception:
            return -1, 0.0

    def _generer_graphique(self, mesure_avant, mesure_apres, mesure_supprime, unite="m"):
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt
            fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(8, 3.5))
            categories = ['Avant', 'Après', 'Supprimé']
            valeurs = [mesure_avant, mesure_apres, mesure_supprime]
            couleurs = ['#1976D2', '#4CAF50', '#F44336']
            bars = ax1.bar(categories, valeurs, color=couleurs, edgecolor='black', linewidth=0.5)
            ax1.set_ylabel(f'Mesure ({unite})')
            ax1.set_title('Mesures de la couche source')
            ax1.grid(axis='y', alpha=0.3)
            for bar, val in zip(bars, valeurs):
                ax1.text(bar.get_x() + bar.get_width()/2, bar.get_height() + max(valeurs, default=1)*0.01,
                        f'{val:,.0f}', ha='center', va='bottom', fontsize=8)
            if mesure_avant > 0:
                labels = ['Conservé', 'Supprimé']
                sizes = [mesure_apres, mesure_supprime]
                colors = ['#4CAF50', '#F44336']
                ax2.pie(sizes, labels=labels, colors=colors, autopct='%1.1f%%',
                       shadow=False, startangle=90, explode=(0.02, 0.05))
                ax2.set_title('Répartition')
            plt.tight_layout()
            buf = io.BytesIO()
            plt.savefig(buf, format='png', dpi=100, bbox_inches='tight')
            plt.close(fig)
            buf.seek(0)
            return buf.getvalue()
        except Exception as e:
            self._jlog(f"⚠ Graphique non généré : {e}")
            return None

    def _generer_csv(self, nom_source, nom_decoupe, mesure_avant, mesure_apres, pourcent, mesure_decoupe, nb_entites, algo):
        date_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        lines = [
            ["Parametre", "Valeur"],
            ["Date", date_str],
            ["Algorithme", algo],
            ["Couche source", nom_source],
            ["Couche de decoupe", nom_decoupe],
            ["Mesure avant", f"{mesure_avant:.2f}"],
            ["Mesure apres", f"{mesure_apres:.2f}"],
            ["Mesure supprimee", f"{mesure_avant - mesure_apres:.2f}"],
            ["Pourcentage conserve (%)", f"{pourcent:.1f}"],
            ["Mesure couche de decoupe", f"{mesure_decoupe:.2f}"],
            ["Entites resultat", str(nb_entites)],
        ]
        output = io.StringIO()
        writer = csv.writer(output, delimiter=';', lineterminator='\n')
        writer.writerows(lines)
        return output.getvalue()

    def _generer_rapport(self, nom_source, nom_decoupe, mesure_avant_txt, mesure_apres_txt, pourcent, mesure_decoupe_txt, nb_entites, chemin, algo, batch=False):
        date_str = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Rapport EDEA_EraseTools</title>
<style>
body{{font-family:Arial,sans-serif;margin:40px;background:#f5f5f5}}
.container{{max-width:800px;margin:0 auto;background:white;padding:30px;border-radius:8px;box-shadow:0 2px 10px rgba(0,0,0,0.1)}}
h1{{color:#2E7D32;border-bottom:3px solid #2E7D32;padding-bottom:10px}}
h2{{color:#1976D2;margin-top:30px}}
table{{width:100%;border-collapse:collapse;margin:20px 0}}
th,td{{padding:12px;text-align:left;border-bottom:1px solid #ddd}}
th{{background:#1976D2;color:white}}
tr:hover{{background:#f1f1f1}}
.metric{{font-size:1.3em;font-weight:bold;color:#2E7D32}}
.footer{{margin-top:40px;font-size:0.9em;color:#666;text-align:center}}
</style></head><body>
<div class="container">
<h1>📊 Rapport — EDEA_EraseTools v6.0</h1>
<p><strong>Date :</strong> {html.escape(date_str)}</p>
<p><strong>Algorithme :</strong> native:{html.escape(algo)}</p>
<h2>🔹 Couches source</h2>
<table><tr><th>Parametre</th><th>Valeur</th></tr>
<tr><td>Couche source</td><td>{html.escape(nom_source)}</td></tr>
<tr><td>Couche de decoupe</td><td>{html.escape(nom_decoupe)}</td></tr>
</table>
<h2>📈 Statistiques</h2>
<table><tr><th>Metrique</th><th>Valeur</th></tr>
<tr><td>Mesure avant</td><td class="metric">{mesure_avant_txt}</td></tr>
<tr><td>Mesure apres</td><td class="metric">{mesure_apres_txt}</td></tr>
<tr><td>Pourcentage conserve</td><td class="metric">{pourcent:.1f} %</td></tr>
<tr><td>Mesure couche de decoupe</td><td class="metric">{mesure_decoupe_txt}</td></tr>
<tr><td>Entites resultat</td><td class="metric">{nb_entites}</td></tr>
</table>
<h2>💾 Fichier(s) de sortie</h2>
<p>{html.escape(str(chemin))}</p>
<div class="footer"><p>Genere par <strong>EDEA_EraseTools v6.0</strong> pour QGIS 3</p></div>
</div></body></html>"""

    def _process(self):
        p = self.params
        couche_source = p['source']
        couche_decoupe = p['decoupe']
        self._jlog(f"✓ Couche source : {couche_source.name()} ({couche_source.featureCount()} entites)")
        self._jlog(f"✓ Couche de decoupe : {couche_decoupe.name()} ({couche_decoupe.featureCount()} entites)")
        self._progress(5)

        if p.get('filtre_source'):
            self._jlog(f"⏳ Filtre couche source : {p['filtre_source']}")
            couche_source = self._appliquer_filtre(couche_source, p['filtre_source'])
            self._jlog(f"✓ Couche source filtree : {couche_source.featureCount()} entites")

        if p.get('filtre_decoupe'):
            self._jlog(f"⏳ Filtre couche de decoupe : {p['filtre_decoupe']}")
            couche_decoupe = self._appliquer_filtre(couche_decoupe, p['filtre_decoupe'])
            self._jlog(f"✓ Couche de decoupe filtree : {couche_decoupe.featureCount()} entites")

        self._check_cancelled()
        self._progress(8)

        # La réparation de géométrie doit se faire tôt et sur LES DEUX couches
        # (source ET découpe), avant tout algorithme sensible aux géométries
        # invalides (dissolve, validation de chevauchement, difference/clip).
        if p.get('valider_geom', True):
            self._jlog("⏳ Verification/reparation geometries (couche source)…")
            res_fix_source = processing.run("native:fixgeometries", {
                'INPUT': couche_source, 'OUTPUT': 'TEMPORARY_OUTPUT'
            })
            couche_source = res_fix_source['OUTPUT']
            self._jlog(f"✓ Geometries source : {couche_source.featureCount()} entites")

            self._jlog("⏳ Verification/reparation geometries (couche de decoupe)…")
            res_fix_decoupe = processing.run("native:fixgeometries", {
                'INPUT': couche_decoupe, 'OUTPUT': 'TEMPORARY_OUTPUT'
            })
            couche_decoupe = res_fix_decoupe['OUTPUT']
            self._jlog(f"✓ Geometries decoupe : {couche_decoupe.featureCount()} entites")

        self._check_cancelled()
        self._progress(12)

        chevauchement_msg = "—"
        if p.get('validation_chevauchement'):
            self._jlog("⏳ Validation des chevauchements (couche de decoupe)…")
            nb_paires, surf_chevauch = self._valider_chevauchement(couche_decoupe)
            if nb_paires < 0:
                chevauchement_msg = "Non applicable"
            elif nb_paires == 0:
                chevauchement_msg = "Aucun"
                self._jlog("✓ Aucun chevauchement detecte")
            else:
                chevauchement_msg = f"{nb_paires} paire(s), {surf_chevauch:,.2f} m²"
                self._jlog(f"⚠ {nb_paires} paire(s) d'entites se chevauchent ({surf_chevauch:,.2f} m²)")
        self._chevauchement_msg = chevauchement_msg

        self._check_cancelled()
        self._progress(15)

        if p.get('buffer_actif'):
            dist = p['buffer_dist']
            segments = p['buffer_segments']
            self._jlog(f"⏳ Buffer : {dist} m, {segments} segments…")
            res_buf = processing.run("native:buffer", {
                'INPUT': couche_source, 'DISTANCE': dist, 'SEGMENTS': segments,
                'END_CAP_STYLE': 0, 'JOIN_STYLE': 0, 'MITER_LIMIT': 2, 'DISSOLVE': False,
                'OUTPUT': 'TEMPORARY_OUTPUT'
            })
            couche_source = res_buf['OUTPUT']
            self._jlog(f"✓ Buffer : {couche_source.featureCount()} entites")

        self._check_cancelled()
        self._progress(18)

        if p.get('fusionner_decoupe', True) and couche_decoupe.featureCount() > 1:
            self._jlog("⏳ Fusion couche de decoupe…")
            res_dissolve = processing.run("native:dissolve", {
                'INPUT': couche_decoupe, 'FIELD': [], 'OUTPUT': 'TEMPORARY_OUTPUT'
            })
            couche_decoupe = res_dissolve['OUTPUT']
            self._jlog(f"✓ Fusion : {couche_decoupe.featureCount()} entite")

        self._check_cancelled()
        self._progress(20)

        mesure_avant, mesure_avant_txt = self._mesurer(couche_source)
        mesure_decoupe, mesure_decoupe_txt = self._mesurer(couche_decoupe)
        self._jlog(f"📊 Mesure avant (couche source) : {mesure_avant_txt}")
        self._jlog(f"📊 Mesure couche de decoupe : {mesure_decoupe_txt}")

        if p['mode'] == 'preview':
            self._mode_preview(couche_source, couche_decoupe, mesure_avant, mesure_decoupe)
        elif p['mode'] == 'batch':
            self._mode_batch(couche_source, couche_decoupe, mesure_avant, mesure_decoupe)
        else:
            self._mode_simple(couche_source, couche_decoupe, mesure_avant, mesure_decoupe)

    def _mode_simple(self, couche_source, couche_decoupe, mesure_avant, mesure_decoupe):
        p = self.params
        self._jlog("⏳ Mode simple : operation…")
        algo = "native:clip" if p.get('mode_inverse') else "native:difference"
        nom_algo = "clip" if p.get('mode_inverse') else "difference"
        self._jlog(f"   Algorithme : native:{nom_algo}")

        res = processing.run(algo, {
            'INPUT': couche_source, 'OVERLAY': couche_decoupe, 'OUTPUT': 'TEMPORARY_OUTPUT'
        })
        self._check_cancelled()
        couche_resultat = res['OUTPUT']
        if not couche_resultat or not couche_resultat.isValid():
            raise Exception("Resultat invalide.")

        nb_result = couche_resultat.featureCount()
        self._jlog(f"✓ {nb_result} entites conservees")
        self._progress(45)

        couche_supprimee = None
        mesure_supprime = 0.0
        if p.get('diff_symetrique'):
            self._jlog("⏳ Difference symetrique…")
            res_inter = processing.run("native:intersection", {
                'INPUT': couche_source, 'OVERLAY': couche_decoupe, 'OUTPUT': 'TEMPORARY_OUTPUT'
            })
            couche_supprimee = res_inter['OUTPUT']
            mesure_supprime, mesure_supprime_txt = self._mesurer(couche_supprimee)
            self._jlog(f"✓ Supprime : {couche_supprimee.featureCount()} entites, {mesure_supprime_txt}")
        elif p.get('couche_supprimee'):
            algo_suppr = "native:difference" if p.get('mode_inverse') else "native:intersection"
            self._jlog(f"⏳ Partie supprimee ({algo_suppr})…")
            res_suppr = processing.run(algo_suppr, {
                'INPUT': couche_source, 'OVERLAY': couche_decoupe, 'OUTPUT': 'TEMPORARY_OUTPUT'
            })
            couche_supprimee = res_suppr['OUTPUT']
            mesure_supprime, mesure_supprime_txt = self._mesurer(couche_supprimee)
            self._jlog(f"✓ Supprime : {couche_supprimee.featureCount()} entites, {mesure_supprime_txt}")
        else:
            mesure_supprime_txt = "—"

        mesure_apres, mesure_apres_txt = self._mesurer(couche_resultat)
        pourcent = (mesure_apres / mesure_avant * 100) if mesure_avant > 0 else 0

        topo_msg = "—"
        if p.get('topologie'):
            self._jlog("⏳ Validation topologique…")
            points_isoles = self._valider_topologie(couche_source, couche_resultat)
            if points_isoles >= 0:
                topo_msg = f"{points_isoles} point(s) isole(s)"
                self._jlog(f"✓ Topologie : {topo_msg}")
            else:
                topo_msg = "Non verifiee"

        _, mesure_avant_txt = self._mesurer(couche_source)
        self.stats_signal.emit(
            mesure_avant_txt, mesure_apres_txt,
            f"{pourcent:.1f} %", self._mesurer(couche_decoupe)[1],
            mesure_supprime_txt, topo_msg, self._chevauchement_msg
        )

        graph_bytes = self._generer_graphique(mesure_avant, mesure_apres, mesure_supprime)
        if graph_bytes:
            self.graph_signal.emit(graph_bytes)

        couche_resultat = self._reprojeter_si_besoin(couche_resultat)
        if couche_supprimee:
            couche_supprimee = self._reprojeter_si_besoin(couche_supprimee)
        self._check_cancelled()
        self._progress(55)

        driver, ext = self._get_driver_and_ext()
        is_postgis = (driver == "PostGIS")
        is_geoserver = (driver == "GeoServer")

        if is_postgis:
            self._exporter_postgis(couche_resultat, p)
            if couche_supprimee:
                pg_params_suppr = p.copy()
                pg_params_suppr['pg_table'] = p['pg_table'] + "_supprime"
                self._exporter_postgis(couche_supprimee, pg_params_suppr)
            chemin_final = f"PostGIS: {p['pg_schema']}.{p['pg_table']}"
        elif is_geoserver:
            self._exporter_geoserver(couche_resultat, p)
            if couche_supprimee:
                gs_params_suppr = p.copy()
                gs_params_suppr['gs_layer'] = (p.get('gs_layer') or couche_resultat.name()) + "_supprime"
                self._exporter_geoserver(couche_supprimee, gs_params_suppr)
            chemin_final = f"GeoServer: {p['gs_workspace']}:{p.get('gs_layer') or couche_resultat.name()}"
        elif p.get('overwrite'):
            source_path = self._layer_source_path(p['source_orig'])
            if not source_path: raise Exception("Chemin source inconnu")
            backup = self._backup_path(source_path)
            self._copier_shapefile(source_path, backup)
            self._jlog(f"✓ Backup : {backup}")
            self._supprimer_fichier(source_path)
            self._ecrire_fichier(couche_resultat, source_path, driver)
            chemin_final = source_path
            self._jlog(f"✓ Original remplace : {source_path}")
            if couche_supprimee:
                chemin_suppr = os.path.join(os.path.dirname(source_path), os.path.splitext(os.path.basename(source_path))[0] + "_SUPPRIME" + ext)
                self._supprimer_fichier(chemin_suppr)
                self._ecrire_fichier(couche_supprimee, chemin_suppr, driver)
                self.fichiers_crees.append(chemin_suppr)
                self._jlog(f"✓ Supprime : {chemin_suppr}")
        else:
            dossier = p['dossier']
            if not dossier: raise Exception("Dossier de sortie non specifie")
            nom_base = p['source_orig'].name()
            sortie = os.path.join(dossier, f"{nom_base}_hors_decoupe{ext}")
            self._supprimer_fichier(sortie)
            self._ecrire_fichier(couche_resultat, sortie, driver)
            chemin_final = sortie
            self._jlog(f"✓ Resultat : {sortie}")
            if couche_supprimee:
                chemin_suppr = os.path.join(dossier, f"{nom_base}_SUPPRIME{ext}")
                self._supprimer_fichier(chemin_suppr)
                self._ecrire_fichier(couche_supprimee, chemin_suppr, driver)
                self.fichiers_crees.append(chemin_suppr)
                self._jlog(f"✓ Supprime : {chemin_suppr}")

        self.fichiers_crees.append(chemin_final)

        if p.get('metadonnees') and not (is_postgis or is_geoserver):
            for chemin in self.fichiers_crees:
                if os.path.exists(chemin):
                    temp = QgsVectorLayer(chemin, "temp", "ogr")
                    if temp.isValid():
                        self._ajouter_metadonnees(temp, f"Resultat de l'operation {nom_algo}")

        self._progress(80)

        if p.get('rapport_html'):
            self.rapport_html = self._generer_rapport(
                p['source_orig'].name(), p['decoupe_orig'].name(),
                mesure_avant_txt, mesure_apres_txt, pourcent, self._mesurer(couche_decoupe)[1],
                nb_result, chemin_final, nom_algo
            )
        if p.get('export_csv'):
            self.csv_content = self._generer_csv(
                p['source_orig'].name(), p['decoupe_orig'].name(),
                mesure_avant, mesure_apres, pourcent, mesure_decoupe, nb_result, nom_algo
            )

        self._progress(100)
        self._jlog("🎉 Termine avec succes !")
        self.journal_content = "\n".join(self._journal_lines)
        info_hist = {
            'mode': 'Simple', 'algo': nom_algo,
            'source': p['source_orig'].name(), 'decoupe': p['decoupe_orig'].name(),
            'resultat': chemin_final, 'nb_entites': nb_result,
        }
        self.finished_signal.emit(True, f"{nb_result} entites conservees", self.fichiers_crees,
                                   self.rapport_html, self.csv_content, "", self.journal_content, info_hist)

    def _mode_batch(self, couche_source, couche_decoupe, mesure_avant, mesure_decoupe):
        p = self.params
        self._jlog("⏳ Mode par lot…")
        dossier = p['dossier']
        driver, ext = self._get_driver_and_ext()
        is_postgis = (driver == "PostGIS")
        is_geoserver = (driver == "GeoServer")
        if not dossier and not (is_postgis or is_geoserver):
            raise Exception("Dossier de sortie non specifie")

        prefixe = p.get('prefixe', 'couche_hors_decoupe_')
        expr_batch = p.get('expr_batch', '')
        champ_id = p.get('champ_id')
        if not champ_id:
            champ_id = couche_decoupe.fields()[0].name() if couche_decoupe.fields().count() > 0 else "id"

        algo = "native:clip" if p.get('mode_inverse') else "native:difference"
        nom_algo = "clip" if p.get('mode_inverse') else "difference"

        total = couche_decoupe.featureCount()
        compteur = 0
        mesure_totale_apres = 0.0
        batch_data = []
        couches_merge = []

        for i, feat_decoupe in enumerate(couche_decoupe.getFeatures()):
            self._check_cancelled()
            if not feat_decoupe.hasGeometry():
                continue

            geom_type_str = QgsWkbTypes.geometryDisplayString(couche_decoupe.geometryType())
            mem_layer = QgsVectorLayer(f"{geom_type_str}?crs=" + couche_decoupe.crs().authid(), "temp", "memory")
            mem_layer.dataProvider().addAttributes(couche_decoupe.fields().toList())
            mem_layer.updateFields()
            mem_layer.dataProvider().addFeatures([feat_decoupe])

            try:
                res = processing.run(algo, {
                    'INPUT': couche_source, 'OVERLAY': mem_layer, 'OUTPUT': 'TEMPORARY_OUTPUT'
                })
            except Exception as e:
                self._jlog(f"⚠ Entite {i+1} ignoree : {e}")
                continue

            resultat = res['OUTPUT']
            if not resultat or resultat.featureCount() == 0:
                self._jlog(f"⚠ Entite {i+1} : aucun resultat")
                continue

            resultat = self._reprojeter_si_besoin(resultat)
            mesure_apres, mesure_apres_txt = self._mesurer(resultat)
            mesure_totale_apres += mesure_apres

            if expr_batch:
                ctx = QgsExpressionContext()
                ctx.setFeature(feat_decoupe)
                ctx.appendScopes(QgsExpressionContextUtils.globalProjectLayerScopes(couche_decoupe))
                expr = QgsExpression(expr_batch)
                val_id = expr.evaluate(ctx)
                if expr.hasEvalError():
                    val_id = str(feat_decoupe[champ_id]) if feat_decoupe[champ_id] is not None else str(i+1)
            else:
                val_id = str(feat_decoupe[champ_id]) if feat_decoupe[champ_id] is not None else str(i+1)

            val_id_safe = "".join(c for c in str(val_id) if c.isalnum() or c in ('_', '-')).strip()
            if not val_id_safe:
                val_id_safe = f"entite_{i+1}"

            nom_fichier = f"{prefixe}{val_id_safe}{ext}"

            if is_postgis:
                pg_params = p.copy()
                pg_params['pg_table'] = f"{p['pg_table']}_{val_id_safe}"
                self._exporter_postgis(resultat, pg_params)
                chemin = f"PostGIS: {pg_params['pg_schema']}.{pg_params['pg_table']}"
            elif is_geoserver:
                gs_params = p.copy()
                gs_params['gs_layer'] = f"{p.get('gs_layer') or 'couche'}_{val_id_safe}"
                self._exporter_geoserver(resultat, gs_params)
                chemin = f"GeoServer: {p['gs_workspace']}:{gs_params['gs_layer']}"
            else:
                chemin = os.path.join(dossier, nom_fichier)
                self._supprimer_fichier(chemin)
                self._ecrire_fichier(resultat, chemin, driver)

            self.fichiers_crees.append(chemin)
            compteur += 1
            batch_data.append([val_id_safe, nom_fichier, resultat.featureCount(), mesure_apres_txt])

            if p.get('merge_batch'):
                couches_merge.append(resultat)

            self._jlog(f"  ✓ {nom_fichier} ({resultat.featureCount()} entites, {mesure_apres_txt})")
            self._progress(int((i + 1) / total * 70))

        chemin_merge = None
        if p.get('merge_batch') and couches_merge:
            self._jlog("⏳ Fusion batch…")
            res_merge = processing.run("native:mergevectorlayers", {
                'LAYERS': couches_merge, 'CRS': couches_merge[0].crs(), 'OUTPUT': 'TEMPORARY_OUTPUT'
            })
            couche_merge = res_merge['OUTPUT']
            if is_postgis:
                pg_params = p.copy()
                pg_params['pg_table'] = f"{p['pg_table']}_fusion"
                self._exporter_postgis(couche_merge, pg_params)
                chemin_merge = f"PostGIS: {pg_params['pg_schema']}.{pg_params['pg_table']}"
            elif is_geoserver:
                gs_params = p.copy()
                gs_params['gs_layer'] = f"{p.get('gs_layer') or 'couche'}_fusion"
                self._exporter_geoserver(couche_merge, gs_params)
                chemin_merge = f"GeoServer: {p['gs_workspace']}:{gs_params['gs_layer']}"
            else:
                nom_merge = f"{prefixe}TOUS_FUSIONNES{ext}"
                chemin_merge = os.path.join(dossier, nom_merge)
                self._supprimer_fichier(chemin_merge)
                self._ecrire_fichier(couche_merge, chemin_merge, driver)
            self.fichiers_crees.append(chemin_merge)
            self._jlog(f"✓ Fusion : {chemin_merge}")

        pourcent = (mesure_totale_apres / mesure_avant * 100) if mesure_avant > 0 else 0
        _, mesure_avant_txt = self._mesurer(couche_source)
        self.stats_signal.emit(
            mesure_avant_txt, f"{mesure_totale_apres:,.2f}",
            f"{pourcent:.1f} %", self._mesurer(couche_decoupe)[1], "—", "—", self._chevauchement_msg
        )
        self._jlog(f"✓ {compteur}/{total} fichiers crees")

        if p.get('table_batch') and batch_data:
            output = io.StringIO()
            writer = csv.writer(output, delimiter=';', lineterminator='\n')
            writer.writerow(["ID_ENTITE", "NOM_FICHIER", "NB_ENTITES", "MESURE"])
            writer.writerows(batch_data)
            self.table_batch_csv = output.getvalue()

        if p.get('rapport_html'):
            self.rapport_html = self._generer_rapport(
                p['source_orig'].name(), p['decoupe_orig'].name(),
                mesure_avant_txt, f"{mesure_totale_apres:,.2f}", pourcent, self._mesurer(couche_decoupe)[1],
                compteur, dossier if not (is_postgis or is_geoserver) else (driver), nom_algo, batch=True
            )
        if p.get('export_csv'):
            self.csv_content = self._generer_csv(
                p['source_orig'].name(), p['decoupe_orig'].name(),
                mesure_avant, mesure_totale_apres, pourcent, mesure_decoupe, compteur, nom_algo
            )

        self._progress(100)
        self._jlog("🎉 Traitement par lot termine !")
        self.journal_content = "\n".join(self._journal_lines)
        info_hist = {
            'mode': 'Par lot', 'algo': nom_algo,
            'source': p['source_orig'].name(), 'decoupe': p['decoupe_orig'].name(),
            'resultat': f"{compteur} fichier(s)", 'nb_entites': compteur,
        }
        self.finished_signal.emit(True, f"{compteur} fichier(s) cree(s)", self.fichiers_crees,
                                   self.rapport_html, self.csv_content, self.table_batch_csv,
                                   self.journal_content, info_hist)

    def _mode_preview(self, couche_source, couche_decoupe, mesure_avant, mesure_decoupe):
        p = self.params
        self._jlog("⏳ Previsualisation…")
        algo = "native:clip" if p.get('mode_inverse') else "native:difference"
        nom_algo = "clip" if p.get('mode_inverse') else "difference"

        res = processing.run(algo, {
            'INPUT': couche_source, 'OVERLAY': couche_decoupe, 'OUTPUT': 'TEMPORARY_OUTPUT'
        })
        resultat = res['OUTPUT']
        if not resultat or not resultat.isValid():
            raise Exception("Resultat invalide.")

        resultat = self._reprojeter_si_besoin(resultat)
        mesure_apres, mesure_apres_txt = self._mesurer(resultat)
        pourcent = (mesure_apres / mesure_avant * 100) if mesure_avant > 0 else 0

        _, mesure_avant_txt = self._mesurer(couche_source)
        self.stats_signal.emit(
            mesure_avant_txt, mesure_apres_txt,
            f"{pourcent:.1f} %", self._mesurer(couche_decoupe)[1], "—", "—", self._chevauchement_msg
        )

        graph_bytes = self._generer_graphique(mesure_avant, mesure_apres, mesure_avant - mesure_apres)
        if graph_bytes:
            self.graph_signal.emit(graph_bytes)

        nom = f"PREVIEW_{p['source_orig'].name()}_{nom_algo}_{p['decoupe_orig'].name()}"
        resultat.setName(nom)
        QgsProject.instance().addMapLayer(resultat)

        self._progress(100)
        self._jlog(f"✓ Previsualisation : {nom} ({resultat.featureCount()} entites)")
        self.journal_content = "\n".join(self._journal_lines)
        info_hist = {
            'mode': 'Prévisualisation', 'algo': nom_algo,
            'source': p['source_orig'].name(), 'decoupe': p['decoupe_orig'].name(),
            'resultat': nom, 'nb_entites': resultat.featureCount(),
        }
        self.finished_signal.emit(True, f"Previsualisation : {resultat.featureCount()} entites", [],
                                   "", "", "", self.journal_content, info_hist)
