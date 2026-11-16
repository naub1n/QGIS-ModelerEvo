# ModelerEvo — QGIS plugin

Modernized version of the Processing graphical modeler. Models keep the `.model3` format and stay
100% compatible with the original modeler. The node specifications (section of the same name) must
be followed.

- QGIS plugin 3.34 → 4.x, Qt6 compatible (`qgis.PyQt` only, no direct PyQt import)
- Languages:
  - user interface: texts written **in English** in the code, French translation provided (see
    "Translations")
  - code comments, docstrings, this `CLAUDE.md` and `README.md`: **English**
  - `README_FR.md`: French version of `README.md`, **kept in sync** with it (`README.md` links to it)
- Version 0.1.0, experimental (see `metadata.txt`)
- Plugin name: **ModelerEvo** (never translate it); "Evo" badge; folder `modeler_evo`
- License GPL-3.0-or-later (`LICENSE`, `license` field of `metadata.txt`)
- GitHub repository: https://github.com/naub1n/QGIS-ModelerEvo; for each new version, update
  `version` and `changelog` in `metadata.txt`
- Users install the plugin from the versioned ZIP published in the GitHub releases (root folder
  `modeler_evo/`, without `.claude/`, `tools/` or `.gitignore`)
- Publishing a version:
  1. update `version` and `changelog` in `metadata.txt`, check the translations
     (`python3 tools/update_translations.py --check`), commit
  2. add an annotated tag `v<version>` (same as `version` in `metadata.txt`) on that commit:
     `git tag -a v<version> -m "ModelerEvo <version>"`
  3. build the ZIP **from the tag**:
     `git archive --prefix=modeler_evo/ -o modeler_evo-<version>.zip v<version> -- . ':!.claude' ':!.gitignore' ':!tools'`
  4. push branch and tag (`git push origin main v<version>`), then create the GitHub release on that
     tag with the ZIP attached (`gh release create v<version> modeler_evo-<version>.zip`)
  5. never move a tag that has already been pushed

## Maintaining this file

- **Whenever the plugin changes, update this `CLAUDE.md` if needed**: new feature, file
  added/renamed/removed, change of structure, convention or behavior
- Update the relevant section (Structure, Features, Dark theme, Translations, Conventions) rather than
  adding a history; remove what is no longer true
- Do this update in the same change as the code
- The "Node specifications" section is the requirements document: only change it at the user's request

## Node specifications (must be followed)

Common to all canvas nodes:

- Resizable
- The node name ("Description" in QGIS) is at the top of the node
- A subtitle under the name shows the node type: input type for an input, algorithm name for an
  algorithm, model name for a model
- Inputs and outputs are shown under the subtitle, in the node body
- Connection points allow connecting two nodes according to their inputs and outputs
- A solid arrow shows a direct relation between two parameters; a dashed arrow an indirect relation
  (parameter used in an expression)
- The node description ("Help" in QGIS) is shown on mouse hover
- Double-clicking the node opens its settings dialog

By type:

- **Inputs**: green node; an icon specific to each input type, next to the name
- **Algorithms**: blue node; gear wheel icon next to the name
- **Outputs**: shown as nodes as soon as they are defined in the algorithm properties; orange node;
  icon of the output type next to the name

Settings dialog, 3 tabs:

- **Properties**: node-specific properties, identical behavior to the original modeler
- **Comments**: creates a comment box in the canvas, identical behavior to the original modeler
- **Help**: node-specific help, included in the model window when the model is opened

## Structure

```
__init__.py          classFactory: installs the translation (install_translator) before importing plugin.py
i18n.py              tr() ("ModelerEvo" context), loading / removal of the QTranslator for the QGIS language
i18n/                modeler_evo_<language>.ts (Qt Linguist sources) and compiled .qm (versioned, shipped)
tools/               update_translations.py: extracts the tr() calls, updates the .ts, compiles the .qm
                     (development tool, excluded from the release ZIP)
plugin.py            Entry point (ModelerEvoPlugin): "ModelerEvo" menu, toolbar icon, entry in the
                     Processing menu, "Edit with ModelerEvo…" entry in the Processing Toolbox context
                     menu (QGIS ≥ 4.4: `QgsProcessingToolboxContextAction` via
                     `QgsGui.processingGuiRegistry()`; QGIS 3: `ProviderContextMenuActions`), closes the
                     windows in unload()
core/model_utils.py  Pure logic on QgsProcessingModelAlgorithm (no Qt GUI): parameter types/categories,
                     connection compatibility, sources, expressions and variables, dependencies, help
                     management (per model, parameter, algorithm, output)
gui/main_window.py   ModelerWindow: actions, menus, toolbar, docks, undo/redo (SnapshotCommand),
                     open/save, validation, execution, exports (image, PDF, SVG, Python)
gui/scene.py         ModelScene (builds the items from the model, background, palette) and ModelView
gui/items.py         NodeItem, EdgeItem, CommentItem, GroupBoxItem (all the QPainter drawing)
gui/panels.py        Docks: inputs, algorithms, properties, variables
gui/node_dialog.py   Node settings dialog (Properties / Comments / Help tabs)
gui/help_dialog.py   Model help window
gui/icons.py         Icons per input/output type, gear wheel, badges, colors (NODE_COLORS,
                     CATEGORY_COLORS, ACCENT)
gui/theme.py         Light / dark canvas palettes
icons/icon.svg       Plugin icon
metadata.txt         QGIS metadata (version, changelog, license, repository URLs)
README.md            Public presentation (GitHub, English): keep up to date with the features
README_FR.md         French version of README.md (keep in sync)
LICENSE              GNU GPL v3
modeler.rst          Documentation of the original modeler (reference, CC BY-SA): local only,
                     excluded from the repository by `.gitignore`
```

## Features already implemented

- Resizable **nodes** (handle at the bottom right), colored header (green input, blue algorithm,
  orange output, model, greyed when inactive), title + subtitle, input/output rows in the body,
  optional snapping to grid, "ok / outdated" state of child algorithms
- Typed **connection points** colored by category, drag-and-drop connection with highlighting of the
  compatible targets
- **Arrows**: direct (solid), expressions (dashed), dependencies (dotted), relation between two
  inputs / linked parameters (`parent`, dotted)
- **Adding a node** (input, algorithm, model output): placed at the free location closest to the
  center of the view (`ModelScene.free_position`), then brought to front and selected
  (`focus_node`). Clicking a node also brings it to front (`bring_to_front`); the stacking order is
  kept in `ModelScene.z_order` across rebuilds
- **Comments** per node and colored **group boxes** (user-chosen colors, not affected by the dark
  theme)
- **Help** per node, included in the model window
- **Settings dialog** on double-click, 3 tabs (Properties, Comments, Help)
- Model outputs shown as orange nodes. Right-click on an algorithm → **Add model output**
  (`ModelerWindow.add_model_output`): offers all the outputs not yet exposed, of any type
- **Extended outputs (Evo)**: the QGIS core only exposes a model output if it is bound to a parameter
  of the algorithm (`qgsprocessingmodelalgorithm.cpp`, `updateDestinationParameters`). Pure outputs
  (number, text, HTML, variant…) are therefore handled by the plugin:
  - stored normally in the `.model3` (`modelOutputs` of the child); the original modeler ignores them
  - detected by `mu.is_extended_output` / `mu.extended_outputs`
  - **not exposed** to other models: the "ModelerEvo" Processing provider (wrapper algorithms) was
    removed from the toolbox, it was useless
- **"Evo" badge** (`draw_evo_badge`, `EVO_COLOR`, `EVO_TEXT` in `gui/icons.py`/`items.py`): **every
  feature that is not compatible with the original modeler must carry it** (node, menu, dialog,
  tooltip). Currently: extended output nodes (badge + tooltip + note in the dialog), menu entries
  prefixed with "[Evo]"
- Undo / redo, select all, delete, zoom (in, out, 100%, full extent, to a group)
- Docks: inputs, algorithms (search, drag and drop; the native "Input parameters" group is hidden there
  because it duplicates the Inputs dock — `AlgorithmsPanel._hide_inputs_group`; the native drag did not
  start, so the `QDrag` is started by `_make_native_tree`), properties, variables; dock geometry and
  state saved in `QSettings`
- Save, save as, save in project, validate, run (F5), reorder inputs
- Exports: image, PDF, SVG, Python script (exports always draw with the light theme, without handles
  or selection: `scene.exporting = True`)

## Dark theme

- **View → Dark theme** menu (`ModelerWindow.a_dark`, checkable action)
- Palettes in `gui/theme.py` (`LIGHT`, `DARK`): background, grid, node body, outline, separators,
  handle, texts (label / advanced / value), empty connection point, shadow
- `ModelScene.palette()` returns the current palette; it is **always light during an export**
- `ModelScene.set_dark(on)` repaints the scene and saves the choice in `QSettings`
  (key `modeler_evo/dark`, default: light)
- `NodeItem.paint` gets `pal = self.mscene.palette()` and passes it to `_paint_row`
- Header colors (green / blue / orange), arrows, categories and comments/groups do not depend on the
  theme
- To add a theme-dependent color: add it to both dictionaries of `theme.py`, then read it with
  `pal["..."]` instead of hard-coding a color in `items.py`
- Tested and working in QGIS

## Translations

- Source language: **English**; translation: French (`i18n/modeler_evo_fr.ts` → `.qm`). Any other
  QGIS language shows English
- **Every text visible to the user** (labels, menus, tooltips, messages, undo history, window titles)
  goes through `tr("…")` (`from ..i18n import tr`), with a **literal** English text: no f-string or
  variable inside `tr()` (the extractor ignores them). Variable values:
  `tr("Model saved: {0}").format(path)`
- After adding / changing a text: `python3 tools/update_translations.py` (requires lrelease: package
  `qt6-l10n-tools`, binary `/usr/lib/qt6/bin/lrelease`), fill in the French translation in the `.ts`
  (remove `type="unfinished"`), run it again to compile the `.qm`, and commit both `.ts` and `.qm`.
  `--check` fails if some texts are not translated
- Module-level labels (`CATEGORY_LABELS`, `HELP_KEYS`, `EVO_TEXT`) are translated at import time:
  the translator must be installed first (done in `classFactory`)
- `metadata.txt`: `description` / `about` in English, `description[fr]` / `about[fr]` variants read
  by the plugin manager according to the QGIS language
- The "Model steps / Model outputs" headings inserted by `sync_help` into the `.model3` help are in
  the language of whoever saves the model
- Deliberately not translated: "Evo" badge / "[Evo]" prefix, the "ModelerEvo" name, technical error
  details of `_create_execution_dialog`

## Conventions and pitfalls

- QGIS 4: `processing.gui.AlgorithmDialog` no longer exists; execution goes through
  `processing.gui.algorithm_widget.AlgorithmWidget` or the GUI factory
  (`ModelerWindow._create_execution_dialog`, fallback to `AlgorithmDialog` in QGIS 3). Check the
  sources on GitHub (`qgis/QGIS`, master branch) before using a Processing Python module
- PyQGIS: never chain calls on a temporary C++ object whose pointers are kept (e.g.
  `model.create().parameterDefinitions()` crashed QGIS): keep the object in a variable
- PyQGIS: `model.parameterComponent(name)` and `model.childAlgorithm(id)` return **references** to
  the objects stored in the model, not copies. Removing the parameter / child
  (`removeModelParameter`, `removeChildAlgorithm`) destroys them: any later use crashes QGIS (this
  crashed QGIS when renaming an input). Copy first:
  `c = QgsProcessingModelParameter(); c.loadVariant(model.parameterComponent(name).toVariant())`.
  Same for `model.parameterDefinition(name)`: invalid after `removeModelParameter(name)`
- No dependency outside QGIS; `core/` does not depend on the GUI
- Custom drawing in `paint()`: any new color must go through the palette
- The plugin folder is a git repository (`main` branch); `.gitignore` excludes `__pycache__/`, logs
  and `modeler.rst`
