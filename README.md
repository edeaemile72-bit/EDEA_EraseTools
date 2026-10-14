# EDEA_EraseTools — Plugin QGIS 3

## Version 6.6

### Nouveautés v6.6

- **Export Excel des statistiques** : une nouvelle option de l'onglet
  « Regrouper / Agréger » enregistre la table agrégée dans un classeur
  Excel (`*_statistiques.xlsx`) — en-tête stylisée (fond vert, texte blanc),
  volet figé sur la première ligne et largeurs de colonnes ajustées
  automatiquement. Nécessite le module `openpyxl` (généralement présent avec
  QGIS ; sinon : `python -m pip install openpyxl` depuis l'OSGeo4W Shell).

---

## Version 6.5

### Nouveautés v6.5

- **Export PDF des statistiques** : une nouvelle option de l'onglet
  « Regrouper / Agréger » enregistre le récapitulatif d'agrégation en PDF
  (`*_statistiques.pdf`). Le PDF reprend le contenu du rapport HTML
  (métadonnées, fonctions utilisées, résultats par groupe) et est généré
  via Qt (`QTextDocument` + `QPrinter`), sans dépendance externe.

---

## Version 6.4

### Nouveautés v6.4

- **Constructeur d'expressions intégré** : un bouton « ε » à côté des champs
  « Filtre avant agrégation » et « Regrouper par » ouvre le constructeur
  d'expressions natif de QGIS (avec la couche en contexte).
- **Rapport HTML récapitulatif** : option générant un rapport HTML stylisé
  (date, couche source, regroupement, filtre, fonctions utilisées et tableau
  des résultats par groupe), enregistré à côté de la sortie
  (`*_rapport.html`).
- **Calcul de géométrie après agrégation** : option ajoutant les colonnes
  géométriques à la couche agrégée — aire/périmètre (polygones), longueur
  (lignes) ou X/Y (points), en calcul **ellipsoïdal** (valeurs en m / m²).

---

## Version 6.3

### Nouveautés v6.3

- **Filtrage des entités avant agrégation** : un champ « Filtre avant
  agrégation » (expression attributaire QGIS, ex. `"population" > 100 AND
  "pays" = 'Pays A'`) permet de ne regrouper et agréger que les entités
  retenues. Disponible dans l'onglet « Regrouper / Agréger » et comme
  paramètre « Filtre » de l'algorithme Processing. Laissé vide, toutes les
  entités sont prises en compte.

---

## Version 6.2

### Nouveautés v6.2

- **Onglet intégré « Regrouper / Agréger »** : l'outil d'agrégation est
  désormais accessible directement dans la fenêtre principale du plugin (plus
  besoin de passer par la boîte à outils Processing). On y choisit la couche,
  le champ (ou l'expression) de regroupement, puis on remplit un tableau
  *une ligne par champ* (fonction d'agrégation, délimiteur, nom de sortie).
- **Export automatique des statistiques (CSV)** : une case à cocher permet
  d'enregistrer automatiquement la table attributaire agrégée (= les
  statistiques, une ligne par groupe) dans un fichier CSV
  (`*_statistiques.csv`) à la fin du traitement.
- **Jeu de démonstration** : `demo_provinces.geojson` (5 provinces → 2 pays)
  et `test_demo_qgis.py` pour tester l'outil et vérifier les résultats.

---

## Version 6.1

### Nouveautés v6.1 — Regrouper et agréger (dissolve + statistiques)

Nouvel outil **« EDEA Regrouper et agréger »**, disponible à la fois comme
algorithme *Processing* (**Boîte à outils → EDEA_EraseTools → Vector general →
EDEA Regrouper et agréger**) et comme entrée de menu
(**Vecteur → EDEA_EraseTools → ∑ Regrouper et agréger**).

Il **regroupe les entités ayant la même valeur pour un champ** (ou une
expression de regroupement), **fusionne leurs géométries** (collecte en
multi-parties) et **calcule des statistiques sur les autres champs** :

- `minimum`, `maximum`, `somme`, `nombre`
- `moyenne`, `médiane`, `écart type`
- `première valeur`, `dernière valeur`
- `concaténation` et **`concaténation sans doublon` (uniquification)** —
  concatène toutes les valeurs d'un champ sans aucun doublon.

Le choix de la fonction se fait champ par champ dans le tableau d'agrégats natif
de QGIS (une ligne par champ : fonction, délimiteur, nom et type de sortie).

**Exemple** : à partir d'une couche polygonale de provinces, avec un champ
*pays* et un champ *population*, on produit une couche de pays où la population
de chaque pays est la **somme** de la population de ses provinces.

> Astuce : laissez le champ de regroupement à `NULL` pour fusionner **toutes**
> les entités en une seule ; saisissez un nom de champ (ex. `"pays"`) ou une
> expression pour regrouper par valeur.
>
> Cet outil nécessite **QGIS ≥ 3.24** (tableau d'agrégats). Sur les versions
> plus anciennes, le reste du plugin reste pleinement fonctionnel.

---

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
