# ModelerEvo — plugin QGIS

Version modernisée du modeleur graphique de Processing. Les modèles restent au format `.model3`,
100 % compatibles avec le modeleur d'origine. Les spécifications des noeuds (section du même nom)
sont à respecter.

- Plugin QGIS 3.34 → 4.x, compatible Qt6 (`qgis.PyQt` uniquement, pas d'import PyQt direct)
- Interface et commentaires en français
- Version 0.1.0, expérimental (voir `metadata.txt`)
- Nom du plugin : **ModelerEvo** (ne pas le franciser) ; badge « Evo » ; dossier `modeler_evo`
- Licence GPL-3.0-or-later (`LICENSE`, champ `license` de `metadata.txt`)
- Dépôt GitHub : https://github.com/naub1n/QGIS-ModelerEvo ; à chaque nouvelle version, mettre à jour
  `version` et `changelog` dans `metadata.txt`
- Les utilisateurs installent le plugin depuis le ZIP versionné publié dans les releases GitHub (dossier
  racine `modeler_evo/`, sans `.claude/` ni `.gitignore`)
- Publier une version :
  1. mettre à jour `version` et `changelog` dans `metadata.txt`, committer
  2. poser un tag annoté `v<version>` (identique à `version` de `metadata.txt`) sur ce commit :
     `git tag -a v<version> -m "ModelerEvo <version>"`
  3. construire le ZIP **depuis le tag** :
     `git archive --prefix=modeler_evo/ -o modeler_evo-<version>.zip v<version> -- . ':!.claude' ':!.gitignore'`
  4. pousser branche et tag (`git push origin main v<version>`), puis créer la release GitHub sur ce tag
     avec le ZIP en pièce jointe (`gh release create v<version> modeler_evo-<version>.zip`)

## Maintenance de ce fichier

- **À chaque modification du plugin, mettre à jour ce fichier `CLAUDE.md` si nécessaire** : nouvelle
  fonctionnalité, fichier ajouté/renommé/supprimé, changement de structure, de convention ou de comportement
- Mettre à jour la section concernée (Structure, Fonctionnalités, Thème sombre, Conventions) plutôt que
  d'ajouter un historique ; retirer ce qui n'est plus vrai
- Faire cette mise à jour dans la même intervention que le changement de code
- La section « Spécifications des noeuds » est le cahier des charges : ne la modifier qu'à la demande
  de l'utilisateur

## Spécifications des noeuds (à respecter)

Communes à tous les noeuds du canvas :

- Redimensionnables
- Le nom du noeud (« Description » dans QGIS) est en haut du noeud
- Un sous-titre sous le nom indique le type de noeud : type d'entrée pour une entrée, nom de
  l'algorithme pour un algorithme, nom du modèle pour un modèle
- Les entrées et les sorties sont affichées sous le sous-titre, dans le corps du noeud
- Des points d'accroche permettent de connecter deux noeuds selon leurs entrées et sorties
- Une flèche pleine indique une relation directe entre deux paramètres ; une flèche en pointillés une
  relation indirecte (paramètre appelé dans une expression)
- La description (« Aide » dans QGIS) du noeud s'affiche au survol de la souris
- Un double-clic sur le noeud ouvre son menu de paramétrage

Par type :

- **Entrées** : noeud vert ; une icône spécifique à chaque type d'entrée, à côté du nom
- **Algorithmes** : noeud bleu ; icône roue crantée à côté du nom
- **Sorties** : matérialisées en noeuds dès qu'elles sont définies dans les propriétés de l'algorithme ;
  noeud orange ; icône du type de sortie à côté du nom

Menu de paramétrage, 3 onglets :

- **Propriétés** : propriétés spécifiques au noeud, fonctionnement identique au modeleur d'origine
- **Commentaires** : crée un cadre de commentaire dans le canvas, fonctionnement identique au modeleur
  d'origine
- **Aide** : aide spécifique au noeud, reprise dans la fenêtre du modèle à son ouverture

## Structure

```
plugin.py            Point d'entrée (ModelerEvoPlugin) : menu « ModelerEvo », icône de barre d'outils,
                     entrée dans le menu Traitement, entrée « Éditer avec ModelerEvo… » du menu
                     contextuel de la boîte à outils (QGIS ≥ 4.4 : `QgsProcessingToolboxContextAction` via
                     `QgsGui.processingGuiRegistry()` ; QGIS 3 : `ProviderContextMenuActions`), fermeture des fenêtres à unload()
core/model_utils.py  Logique pure sur QgsProcessingModelAlgorithm (sans Qt GUI) : types/catégories de
                     paramètres, compatibilité des connexions, sources, expressions et variables,
                     dépendances, gestion de l'aide (par modèle, paramètre, algorithme, sortie)
gui/main_window.py   ModelerWindow : actions, menus, barre d'outils, docks, undo/redo (SnapshotCommand),
                     ouverture/enregistrement, validation, exécution, exports (image, PDF, SVG, Python)
gui/scene.py         ModelScene (construit les items depuis le modèle, fond, palette) et ModelView
gui/items.py         NodeItem, EdgeItem, CommentItem, GroupBoxItem (tout le dessin QPainter)
gui/panels.py        Docks : entrées, algorithmes, propriétés, variables
gui/node_dialog.py   Dialogue de paramétrage d'un noeud (onglets Propriétés / Commentaires / Aide)
gui/help_dialog.py   Fenêtre d'aide du modèle
gui/icons.py         Icônes par type d'entrée/sortie, roue crantée, badges, couleurs (NODE_COLORS,
                     CATEGORY_COLORS, ACCENT)
gui/theme.py         Palettes clair / sombre du canvas
icons/icon.svg       Icône du plugin
metadata.txt         Métadonnées QGIS (version, changelog, licence, URLs du dépôt)
README.md            Présentation publique (GitHub) : à tenir à jour avec les fonctionnalités
LICENSE              GNU GPL v3
modeler.rst          Documentation du modeleur d'origine (référence, CC BY-SA) : locale uniquement,
                     exclue du dépôt par `.gitignore`
```

## Fonctionnalités déjà en place

- **Noeuds** redimensionnables (poignée en bas à droite), en-tête coloré (entrée verte, algorithme
  bleu, sortie orange, modèle, inactif grisé), titre + sous-titre, lignes d'entrées/sorties dans le corps,
  aimantation à la grille optionnelle, état « ok / obsolète » des algorithmes enfants
- **Points d'accroche** typés et colorés par catégorie, connexion par glisser-déposer avec mise en
  évidence des cibles compatibles
- **Flèches** : directes (plein), expressions (tirets), dépendances (pointillés), relation entre deux
  entrées / paramètres liés (`parent`, pointillés)
- **Ajout d'un noeud** (entrée, algorithme, sortie du modèle) : placé dans un emplacement inoccupé le plus
  proche du centre de la vue (`ModelScene.free_position`), puis mis au premier plan et sélectionné
  (`focus_node`). Un clic sur un noeud le met aussi au premier plan (`bring_to_front`) ; l'ordre
  d'empilement est conservé dans `ModelScene.z_order` entre les reconstructions
- **Commentaires** par noeud et **cadres de groupe** colorés (couleurs choisies par l'utilisateur,
  non touchées par le thème sombre)
- **Aide** par noeud, reprise dans la fenêtre du modèle
- **Menu de paramétrage** par double-clic, 3 onglets (Propriétés, Commentaires, Aide)
- Sorties du modèle matérialisées en noeuds orange. Clic droit sur un algorithme → **Ajouter une sortie du
  modèle** (`ModelerWindow.add_model_output`) : propose toutes les sorties non encore exposées, de tout type
- **Sorties étendues (Evo)** : le cœur de QGIS n'expose une sortie de modèle que si elle est liée à un paramètre
  de l'algorithme (`qgsprocessingmodelalgorithm.cpp`, `updateDestinationParameters`). Les sorties pures
  (nombre, texte, HTML, variant…) sont donc gérées par le plugin :
  - stockées normalement dans le `.model3` (`modelOutputs` du enfant) ; l'ancien modeleur les ignore
  - détectées par `mu.is_extended_output` / `mu.extended_outputs`
  - **pas exposées** aux autres modèles : le fournisseur Processing « ModelerEvo » (algorithmes enveloppes) a été
    supprimé de la boîte à outils, il ne servait à rien
- **Badge « Evo »** (`draw_evo_badge`, `EVO_COLOR`, `EVO_TEXT` dans `gui/icons.py`/`items.py`) : **toute
  fonctionnalité non compatible avec l'ancien modeleur doit le porter** (noeud, menu, dialogue, info-bulle).
  Actuellement : noeuds de sortie étendue (pastille + info-bulle + note dans le dialogue), entrées de menu
  préfixées « [Evo] »
- Annuler / rétablir, tout sélectionner, supprimer, zoom (avant, arrière, 100 %, ensemble, vers un groupe)
- Docks : entrées, algorithmes (recherche, glisser-déposer ; le groupe natif « Paramètres d'entrée » y est
  masqué car il double le dock Entrées — `AlgorithmsPanel._hide_inputs_group` ; le glisser natif ne démarrait
  pas, le `QDrag` est donc lancé par `_make_native_tree`), propriétés, variables ; géométrie et état
  des docks mémorisés dans `QSettings`
- Enregistrer, enregistrer sous, enregistrer dans le projet, valider, exécuter (F5), réordonner les entrées
- Exports : image, PDF, SVG, script Python (l'export dessine toujours en thème clair, sans poignées
  ni sélection : `scene.exporting = True`)

## Thème sombre

- Menu **Vue → Thème sombre** (`ModelerWindow.a_dark`, action cochable)
- Palettes dans `gui/theme.py` (`LIGHT`, `DARK`) : fond, grille, corps du noeud, contour, séparateurs,
  poignée, textes (label / avancé / valeur), point de connexion vide, ombre
- `ModelScene.palette()` renvoie la palette courante ; elle est **toujours claire pendant un export**
- `ModelScene.set_dark(on)` redessine la scène et enregistre le choix dans `QSettings`
  (clé `modeler_evo/dark`, défaut : clair)
- `NodeItem.paint` récupère `pal = self.mscene.palette()` et le passe à `_paint_row`
- Les couleurs d'en-tête (vert / bleu / orange), des flèches, des catégories et des commentaires/groupes
  ne dépendent pas du thème
- Pour ajouter une couleur dépendant du thème : l'ajouter aux deux dictionnaires de `theme.py`,
  puis la lire via `pal["..."]` plutôt que d'écrire une couleur en dur dans `items.py`

## Conventions et pièges

- QGIS 4 : `processing.gui.AlgorithmDialog` n'existe plus ; l'exécution passe par
  `processing.gui.algorithm_widget.AlgorithmWidget` ou la fabrique GUI (`ModelerWindow._create_execution_dialog`,
  repli sur `AlgorithmDialog` en QGIS 3). Vérifier les sources sur GitHub (`qgis/QGIS`, branche master)
  avant d'utiliser un module Python de Processing

- PyQGIS : ne jamais chaîner sur un objet C++ temporaire dont on garde des pointeurs (ex.
  `model.create().parameterDefinitions()` a fait planter QGIS) : garder l'objet dans une variable

- Pas de dépendance hors QGIS ; `core/` ne dépend pas de l'interface graphique
- Dessin personnalisé en `paint()` : tout nouveau code de couleur doit passer par la palette
- Le dossier du plugin est un dépôt git (branche `main`) ; `.gitignore` exclut `__pycache__/`,
  les journaux et `modeler.rst`
- Thème sombre testé et fonctionnel dans QGIS
