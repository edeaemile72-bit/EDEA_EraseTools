# EDEA_EraseTools — Plugin QGIS 3

## Version 6.0

Plugin professionnel généraliste pour supprimer la partie d'une **couche source**
(points, lignes ou polygones — tout type de géométrie) située à l'intérieur d'une
**couche de découpe** (également tout type de géométrie), via une opération
*difference* / *erase*.

Anciennement « Erase Réseau ARRD » (v5.0, limité aux réseaux linéaires et aux
polygones ARRD) — la v6.0 généralise entièrement le plugin : plus aucune
restriction de type de couche, ni dans l'interface, ni dans la logique de
traitement.

## Nouveautés v6.0

- **Généralisation complète** : fonctionne avec n'importe quel type de couche
  vectorielle en entrée (points, lignes, polygones), aussi bien pour la couche
  source que pour la couche de découpe.
- **Historique des actions** : chaque traitement exécuté est enregistré (date,
  mode, algorithme, couches, résultat, nombre d'entités) dans un nouvel onglet
  *Historique*, exportable en CSV.
- **Zoom comparatif** : fenêtre dédiée avec deux cartes synchronisées
  (avant / après) pour visualiser immédiatement l'effet du traitement.
- **Export GeoServer** : publication directe du résultat vers un GeoServer via
  son API REST (upload d'un shapefile zippé dans un datastore existant).
- **Validation des chevauchements** : détection optionnelle des recouvrements
  entre entités de la couche de découpe avant traitement (nombre de paires en
  chevauchement + surface concernée).

## Fonctionnalités

### Interface par onglets
- **Source** : couches (tout type), filtres, buffer, sélection interactive, validation des chevauchements
- **Traitement** : modes, formats (incluant PostGIS et GeoServer), actions
- **Options** : options avancées, métadonnées, historique, sauvegarde
- **Statistiques** : résumé numérique générique + graphiques matplotlib
- **Historique** : journal des traitements exécutés, exportable

### Traitement asynchrone
- Thread séparé — QGIS reste réactif
- Bouton **Annuler** pour interrompre

### Modes de traitement
- **Simple** : un seul fichier
- **Par lot** : un fichier par entité de la couche de découpe
- **Prévisualisation** : couche temporaire sans écriture

### Sélection interactive
- Utiliser les entités **sélectionnées sur la carte** comme couche de découpe
- Bouton "Sélectionner la couche sur la carte"

### Buffer optionnel
- Élargit la couche source avant traitement (distance + segments)

### Mode inversé (CLIP)
- Conserve l'intérieur au lieu de l'extérieur

### Différence symétrique
- Conserve les deux parties (conservée + supprimée) séparément

### Export multi-format
- ESRI Shapefile (.shp)
- GeoPackage (.gpkg)
- GeoJSON (.geojson)
- KML (.kml)
- **PostGIS** (PostgreSQL/PostGIS direct)
- **GeoServer** (API REST — upload direct dans un datastore)

### Couche "partie supprimée"
- Crée automatiquement une couche de ce qui a été enlevé

### Statistiques et graphiques
- Mesure avant / après / supprimée (adaptée au type de géométrie : longueur pour
  les lignes, surface pour les polygones, nombre d'entités pour les points)
- Pourcentage conservé
- Mesure de la couche de découpe
- **Graphique matplotlib** (barres + camembert) dans l'onglet Statistiques

### Rapports
- **Rapport HTML** stylisé
- **Export CSV** des statistiques
- **Table de correspondance batch** (CSV)
- **Journal détaillé** exportable en texte

### Validation topologique
- Vérifie les coupures créées par le traitement (couches linéaires)
- Compte les points isolés

### Validation des chevauchements
- Détecte les recouvrements entre entités de la couche de découpe

### Métadonnées INSPIRE
- Ajout automatique de métadonnées aux couches créées

### Symbologie automatique
- Vert = conservé, Rouge = supprimé, Orange = clip

### Vérification SCR
- Alerte si les couches ont des SCR différents

### Historique et zoom comparatif
- Historique persistant des traitements (QSettings), exportable en CSV
- Comparaison visuelle avant/après dans une fenêtre à deux cartes synchronisées

### Sauvegarde des paramètres
- QSettings — préférences conservées entre sessions

### Aide contextuelle
- Bouton ❓ Aide avec documentation intégrée

### Gestion des couches
- Action menu **Supprimer les couches créées**

### Intégration Processing
- Algorithme dans `Vector overlay > EDEA_EraseTools`
- Paramètres : buffer, filtres, mode inversé, différence symétrique, fusion, SCR, réparation

## Installation

**Depuis le dépôt officiel QGIS** (une fois le plugin publié) :
1. QGIS > Extensions > Installer/Gérer les extensions
2. Rechercher « EDEA_EraseTools »
3. Cliquer sur Installer

**Depuis un fichier ZIP** (installation manuelle) :
1. Télécharger `EDEA_EraseTools.zip` depuis le [dépôt GitHub](https://github.com/edeaemile72-bit/EDEA_EraseTools)
2. QGIS > Extensions > Installer/Gérer les extensions > Installer depuis un ZIP
3. Sélectionner le fichier téléchargé, puis activer le plugin

## Utilisation

1. Charger les couches dans le projet
2. Ouvrir le plugin (barre d'outils ou menu Extensions)
3. Configurer les options dans les onglets
4. Cliquer sur **Exécuter**
5. Consulter les statistiques, le graphique, les rapports, l'historique et le zoom comparatif

## Structure

```
EDEA_EraseTools/
├── metadata.txt
├── __init__.py
├── edea_erasetools.py         # Plugin principal + algorithme Processing
├── edea_erasetools_dialog.py
├── edea_erasetools_dialog_base.ui
├── worker.py                  # Thread asynchrone
├── comparaison_dialog.py      # Fenêtre de zoom comparatif avant/après
├── icon.png
└── resources.qrc / resources.py
```

## Auteur

**Dr EDEA O. Emile**
Dépôt du projet : https://github.com/edeaemile72-bit/EDEA_EraseTools

## Licence

Ce plugin est distribué sous licence **GNU General Public License v2.0 ou ultérieure**
(GPL v2+), compatible avec la licence de QGIS. Voir le fichier [LICENSE](LICENSE)
pour le texte complet.

## Signaler un problème / suggérer une amélioration

Utiliser la section *Issues* du dépôt GitHub :
https://github.com/edeaemile72-bit/EDEA_EraseTools/issues
