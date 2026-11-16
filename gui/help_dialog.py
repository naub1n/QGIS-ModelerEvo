"""Édition de l'aide du modèle (description, entrées, sorties, étapes, auteur…)."""

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QSplitter,
    QTextBrowser,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..core import model_utils as mu

_ROLE = Qt.ItemDataRole.UserRole


class ModelHelpDialog(QDialog):
    def __init__(self, model, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Aide du modèle")
        self.resize(980, 620)
        self.model = model
        self.values = {}
        self._current = None

        self.list = QListWidget()
        self.editor = QTextEdit()
        self.editor.setAcceptRichText(False)
        self.preview = QTextBrowser()

        def section(title):
            it = QListWidgetItem(title)
            it.setFlags(Qt.ItemFlag.NoItemFlags)
            f = it.font()
            f.setBold(True)
            it.setFont(f)
            self.list.addItem(it)

        def entry(key, label):
            it = QListWidgetItem("   " + label)
            it.setData(_ROLE, key)
            self.list.addItem(it)
            self.values[key] = mu.help_value(model, key)

        section("Modèle")
        for key, label in mu.HELP_KEYS:
            entry(key, label)
        params = [p for p in model.parameterDefinitions()
                  if not p.isDestination() and not mu.param_has_flag(p, "Hidden")]
        if params:
            section("Entrées")
            for p in params:
                entry(p.name(), p.description())
        outs = model.outputDefinitions()
        if outs:
            section("Sorties")
            for o in outs:
                entry(o.name(), o.description())
        children = model.childAlgorithms()
        if children:
            section("Étapes (onglet « Aide » des algorithmes)")
            for cid, child in sorted(children.items(), key=lambda kv: kv[1].description().lower()):
                entry(mu.STEP_PREFIX + cid, child.description())

        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.addWidget(self.list)
        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)
        rv.addWidget(QLabel("Texte (HTML accepté)"))
        rv.addWidget(self.editor, 1)
        rv.addWidget(QLabel("Aperçu de l'aide du modèle"))
        rv.addWidget(self.preview, 2)
        split = QSplitter()
        split.addWidget(left)
        split.addWidget(right)
        split.setSizes([300, 680])

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                   | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addWidget(split)
        lay.addWidget(buttons)

        self.list.currentItemChanged.connect(self._changed)
        self.editor.textChanged.connect(self._text_changed)
        self.list.setCurrentRow(1)

    def _changed(self, current, previous):
        self._current = current.data(_ROLE) if current is not None else None
        self.editor.blockSignals(True)
        self.editor.setPlainText(self.values.get(self._current, "") if self._current else "")
        self.editor.setEnabled(self._current is not None)
        self.editor.blockSignals(False)
        self._update_preview()

    def _text_changed(self):
        if self._current:
            self.values[self._current] = self.editor.toPlainText()
            self._update_preview()

    def _update_preview(self):
        try:
            from qgis.core import QgsProcessingUtils
            content = self.help_content()
            clone = self.model.create()
            clone.setHelpContent(content)
            mu.sync_help(clone)
            self.preview.setHtml(QgsProcessingUtils.formatHelpMapAsHtml(clone.helpContent(), clone))
        except Exception:  # noqa: BLE001
            self.preview.setHtml(self.values.get("ALG_DESC", ""))

    def help_content(self):
        content = dict(self.model.helpContent() or {})
        for key, text in self.values.items():
            text = text.strip()
            if text:
                content[key] = text
            else:
                content.pop(key, None)
        return content

    def apply(self):
        self.model.setHelpContent(self.help_content())
        mu.sync_help(self.model)
