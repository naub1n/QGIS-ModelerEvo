# ModelerEvo

🇬🇧 [English version](README.md)

Version modernisée du modeleur graphique de Processing pour QGIS.

Les modèles restent au format `.model3` et sont **100 % compatibles** avec le modeleur d'origine :
un modèle créé ou modifié avec ModelerEvo s'ouvre dans le modeleur de QGIS, et inversement.

> **Statut : expérimental (0.1.0).** Pensez à sauvegarder vos modèles avant de les modifier.

## Fonctionnalités

- **Noeuds redimensionnables** à en-tête coloré : entrées (vert), algorithmes (bleu), sorties du
  modèle (orange) ; titre, sous-titre (type d'entrée, nom de l'algorithme ou du modèle) et liste des
  entrées / sorties dans le corps du noeud
- **Icône par type** d'entrée et de sortie, roue crantée pour les algorithmes
- **Points d'accroche typés** et colorés par catégorie ; connexion par glisser-déposer avec mise en
  évidence des cibles compatibles
- **Flèches** : relation directe (trait plein), expression (tirets), dépendance (pointillés)
- **Paramétrage par double-clic** : onglets Propriétés, Commentaires et Aide
- **Commentaires** et **cadres de groupe** colorés
- **Aide par noeud**, affichée au survol et reprise dans la fenêtre d'aide du modèle
- **Sorties étendues** `[Evo]` : sorties d'algorithme non liées à un paramètre (nombre, texte, HTML…)
- Annuler / rétablir, zoom, aimantation à la grille, **thème sombre**
- Docks : entrées, algorithmes (recherche, glisser-déposer), propriétés, variables
- Validation, exécution (F5), enregistrement dans un fichier ou dans le projet
- Exports : image, PDF, SVG, script Python

### Badge « Evo »

Les fonctionnalités qui n'existent pas dans le modeleur d'origine portent le badge **Evo**. Elles sont
enregistrées dans le `.model3` sans le rendre invalide, mais l'ancien modeleur les ignore.

## Compatibilité

- QGIS 3.34 à 4.x
- Qt5 et Qt6

## Langues

L'interface suit la langue de QGIS : **anglais** (langue par défaut pour toute autre langue) et
**français**. Les traductions sont des fichiers Qt Linguist dans `i18n/`. Pour en ajouter une, par
exemple l'allemand :

```bash
python3 tools/update_translations.py --add de   # crée i18n/modeler_evo_de.ts
linguist i18n/modeler_evo_de.ts                 # traduire (ou éditer le .ts directement)
python3 tools/update_translations.py            # compile le .qm
```

## Installation

### Depuis une release (recommandé)

1. Télécharger le ZIP du plugin depuis la page des
   [releases](https://github.com/naub1n/QGIS-ModelerEvo/releases).
2. Dans QGIS : *Extensions → Installer/Gérer les extensions → Installer depuis un ZIP*.
3. Cocher les extensions expérimentales dans les paramètres du gestionnaire d'extensions, puis
   activer **ModelerEvo**.

### Depuis le code source

Cloner le dépôt dans le dossier des plugins de votre profil QGIS, sous le nom `modeler_evo` :

```bash
cd …/profiles/default/python/plugins
git clone https://github.com/naub1n/QGIS-ModelerEvo.git modeler_evo
```

## Utilisation

- Menu **Extensions → ModelerEvo**, icône de la barre d'outils, ou menu **Traitement**
- Dans la boîte à outils Processing : clic droit sur un modèle → **Éditer avec ModelerEvo…**
  (QGIS 3, et QGIS ≥ 4.4)

## Signaler un problème

Les anomalies et suggestions sont à déposer dans les
[issues](https://github.com/naub1n/QGIS-ModelerEvo/issues).

## Utilisation de l'IA

Ce plugin a été réalisé avec l'aide d'une intelligence artificielle :
[Claude Code](https://claude.com/claude-code) (Anthropic) a servi d'assistant pour écrire le code et la
documentation. La conception, les spécifications, les choix fonctionnels et les tests dans QGIS sont
le fait de l'auteur.

## Licence

Distribué sous licence [GNU GPL v3.0](LICENSE) ou ultérieure.
