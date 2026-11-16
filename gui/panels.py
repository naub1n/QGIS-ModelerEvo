"""Side panels: inputs, algorithms, model properties, variables."""

from qgis.core import Qgis, QgsApplication, QgsExpressionContext, QgsExpressionContextScope, QgsMessageLog
from qgis.PyQt.QtCore import QByteArray, QMimeData, QModelIndex, Qt, pyqtSignal
from qgis.PyQt.QtGui import QDrag
from qgis.PyQt.QtWidgets import QApplication
from qgis.PyQt.QtWidgets import (
    QAbstractItemView,
    QFormLayout,
    QLineEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..core.model_utils import CATEGORY_LABELS, category
from ..i18n import tr
from .icons import gear_icon, input_type_icon
from .scene import ALG_MIME, PARAM_MIME

try:
    from qgis.gui import QgsFilterLineEdit
except ImportError:  # pragma: no cover
    QgsFilterLineEdit = QLineEdit

_ROLE = Qt.ItemDataRole.UserRole


def _search_box(placeholder):
    edit = QgsFilterLineEdit()
    edit.setPlaceholderText(placeholder)
    try:
        edit.setShowSearchIcon(True)
    except AttributeError:
        pass
    return edit


def _exposed_to_modeler(ptype):
    flag = getattr(getattr(Qgis, "ProcessingParameterTypeFlag", None), "ExposeToModeler", None)
    if flag is None:
        from qgis.core import QgsProcessingParameterType
        flag = getattr(QgsProcessingParameterType, "ExposeToModeler", None)
    if flag is None:
        return True
    try:
        return bool(ptype.flags() & flag)
    except TypeError:
        return True


class _MimeTree(QTreeWidget):
    mime_type = PARAM_MIME

    def __init__(self):
        super().__init__()
        self.setHeaderHidden(True)
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)
        self.setIndentation(14)

    def mimeData(self, items):  # noqa: N802
        md = QMimeData()
        ids = [i.data(0, _ROLE) for i in items if i.data(0, _ROLE)]
        if ids:
            md.setData(self.mime_type, QByteArray(ids[0].encode("utf-8")))
        return md


class InputsPanel(QWidget):
    """List of the input types, grouped by category, with their icon."""

    activated = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.search = _search_box(tr("Search inputs…"))
        self.tree = _MimeTree()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.addWidget(self.search)
        lay.addWidget(self.tree)
        self.populate()
        self.search.textChanged.connect(self._filter)
        self.tree.itemDoubleClicked.connect(self._double_clicked)

    def populate(self):
        self.tree.clear()
        groups = {}
        types = [t for t in QgsApplication.processingRegistry().parameterTypes() if _exposed_to_modeler(t)]
        for t in sorted(types, key=lambda t: t.name().lower()):
            cat = category(t.id())
            if cat not in groups:
                g = QTreeWidgetItem([CATEGORY_LABELS[cat]])
                g.setFlags(Qt.ItemFlag.ItemIsEnabled)
                f = g.font(0)
                f.setBold(True)
                g.setFont(0, f)
                groups[cat] = g
            it = QTreeWidgetItem([t.name()])
            it.setIcon(0, input_type_icon(t.id()))
            it.setToolTip(0, t.description())
            it.setData(0, _ROLE, t.id())
            it.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsDragEnabled)
            groups[cat].addChild(it)
        order = list(CATEGORY_LABELS)
        for cat in sorted(groups, key=order.index):
            self.tree.addTopLevelItem(groups[cat])
            groups[cat].setExpanded(True)

    def _filter(self, text):
        text = text.lower().strip()
        for i in range(self.tree.topLevelItemCount()):
            g = self.tree.topLevelItem(i)
            visible = 0
            for j in range(g.childCount()):
                c = g.child(j)
                show = not text or text in c.text(0).lower() or text in (c.toolTip(0) or "").lower()
                c.setHidden(not show)
                visible += show
            g.setHidden(visible == 0)

    def _double_clicked(self, item, _col):
        type_id = item.data(0, _ROLE)
        if type_id:
            self.activated.emit(type_id)


def _make_native_tree(parent):
    """Native Processing Toolbox tree, with dragging handled by the plugin.

    The native drag did not start (the tree collapsed without dropping anything): the
    QDrag is started here, with the algorithm id as raw UTF-8 (ALG_MIME format).
    """
    from qgis.gui import QgsProcessingToolboxTreeView

    class _Tree(QgsProcessingToolboxTreeView):
        _press = None

        def mousePressEvent(self, ev):  # noqa: N802
            self._press = ev.pos() if ev.button() == Qt.MouseButton.LeftButton else None
            super().mousePressEvent(ev)

        def mouseMoveEvent(self, ev):  # noqa: N802
            if (self._press is not None and ev.buttons() & Qt.MouseButton.LeftButton
                    and (ev.pos() - self._press).manhattanLength() >= QApplication.startDragDistance()):
                alg = self.selectedAlgorithm()
                if alg is not None:
                    self._press = None
                    mime = QMimeData()
                    mime.setData(ALG_MIME, QByteArray(alg.id().encode("utf-8")))
                    mime.setText(alg.id())
                    drag = QDrag(self)
                    drag.setMimeData(mime)
                    drag.exec(Qt.DropAction.CopyAction)
                    return
            super().mouseMoveEvent(ev)

    return _Tree(parent, QgsApplication.processingRegistry())


class AlgorithmsPanel(QWidget):
    """Processing Toolbox filtered for the modeler."""

    activated = pyqtSignal(str)
    parameter_activated = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.search = _search_box(tr("Search algorithms…"))
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.addWidget(self.search)
        self.native = False
        try:
            from qgis.gui import QgsProcessingToolboxProxyModel
            self.tree = _make_native_tree(self)
            filt_owner = getattr(QgsProcessingToolboxProxyModel, "Filter", QgsProcessingToolboxProxyModel)
            flt = getattr(filt_owner, "Modeler", None) or getattr(QgsProcessingToolboxProxyModel, "FilterModeler")
            self.tree.setFilters(flt)
            self.tree.setDragEnabled(False)  # dragging handled by _make_native_tree
            self.tree.setHeaderHidden(True)  # otherwise Qt shows "1" (column number)
            self.tree.doubleClicked.connect(self._native_double_clicked)
            self.search.textChanged.connect(self.tree.setFilterString)
            self._setup_hide_inputs()
            self.native = True
        except Exception:  # noqa: BLE001 - fallback to a simple tree
            self.tree = _MimeTree()
            self.tree.mime_type = ALG_MIME
            self._populate_fallback()
            self.search.textChanged.connect(self._filter_fallback)
            self.tree.itemDoubleClicked.connect(
                lambda it, _c: it.data(0, _ROLE) and self.activated.emit(it.data(0, _ROLE)))
        lay.addWidget(self.tree)

    def _setup_hide_inputs(self):
        """Hide the "Input parameters" group (duplicate of the Inputs dock)."""
        from qgis.PyQt.QtCore import QTimer
        model = self.tree.model()
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.setInterval(0)
        self._hide_timer.timeout.connect(self._hide_inputs_group)
        self._hide_timer.timeout.connect(self._restore_expanded)
        for sig in ("rowsInserted", "rowsRemoved", "layoutChanged", "modelReset"):
            getattr(model, sig).connect(lambda *_a: self._hide_timer.start())
        # remember the expanded groups: QGIS rebuilds the tree (a provider added at startup,
        # e.g. after 3 s), which collapsed them
        self._expanded = set()
        self.tree.expanded.connect(lambda i: self._track_expanded(i, True))
        self.tree.collapsed.connect(lambda i: self._track_expanded(i, False))
        self._hide_timer.start()

    def _index_path(self, index):
        path = []
        while index.isValid():
            path.append(str(index.data() or ""))
            index = index.parent()
        return tuple(reversed(path))

    def _track_expanded(self, index, opened):
        if self.search.text().strip():  # searching expands everything: do not remember
            return
        (self._expanded.add if opened else self._expanded.discard)(self._index_path(index))

    def _restore_expanded(self):
        if self.search.text().strip() or not self._expanded:
            return
        proxy = self.tree.model()

        def walk(parent):
            for row in range(proxy.rowCount(parent)):
                idx = proxy.index(row, 0, parent)
                if proxy.rowCount(idx) and self._index_path(idx) in self._expanded:
                    if not self.tree.isExpanded(idx):
                        self.tree.expand(idx)
                    walk(idx)

        walk(QModelIndex())

    def _is_parameter_index(self, proxy, index):
        """True if the index is a parameter type (without touching the tree selection)."""
        try:
            return bool(proxy.toolboxModel().isParameter(proxy.mapToSource(index)))
        except Exception:  # noqa: BLE001
            pass
        try:  # fallback: the MIME data of a parameter type has a dedicated format
            mime = proxy.mimeData([index])
            return mime is not None and mime.hasFormat(PARAM_MIME)
        except Exception:  # noqa: BLE001
            return False

    def _hide_inputs_group(self):
        try:
            proxy = self.tree.model()
            root = QModelIndex()
            for row in range(proxy.rowCount(root)):
                top = proxy.index(row, 0, root)
                if proxy.rowCount(top) == 0:
                    continue
                if self._is_parameter_index(proxy, proxy.index(0, 0, top)):
                    self.tree.setRowHidden(row, root, True)
        except Exception as e:  # noqa: BLE001
            QgsMessageLog.logMessage(tr("Cannot hide the inputs group: {0}").format(e), "ModelerEvo")

    def _native_double_clicked(self, _index):
        alg = self.tree.selectedAlgorithm()
        if alg is not None:
            self.activated.emit(alg.id())
            return
        fn = getattr(self.tree, "selectedParameterType", None)
        if callable(fn):
            ptype = fn()
            if ptype is not None:
                self.parameter_activated.emit(ptype.id())

    def _populate_fallback(self):
        hide = getattr(getattr(Qgis, "ProcessingAlgorithmFlag", None), "HideFromModeler", None)
        reg = QgsApplication.processingRegistry()
        for provider in sorted(reg.providers(), key=lambda p: p.name().lower()):
            pitem = QTreeWidgetItem([provider.name()])
            pitem.setIcon(0, provider.icon())
            groups = {}
            for alg in sorted(provider.algorithms(), key=lambda a: a.displayName().lower()):
                if hide is not None and alg.flags() & hide:
                    continue
                g = groups.get(alg.group())
                if g is None:
                    g = groups[alg.group()] = QTreeWidgetItem(pitem, [alg.group() or "—"])
                it = QTreeWidgetItem(g, [alg.displayName()])
                it.setIcon(0, alg.icon() if not alg.icon().isNull() else gear_icon("#2f6fde"))
                it.setToolTip(0, alg.shortDescription() or alg.id())
                it.setData(0, _ROLE, alg.id())
            if groups:
                self.tree.addTopLevelItem(pitem)

    def _filter_fallback(self, text):
        text = text.lower().strip()

        def walk(item):
            if item.childCount() == 0:
                show = not text or text in item.text(0).lower() or text in (item.data(0, _ROLE) or "")
                item.setHidden(not show)
                return show
            any_visible = False
            for i in range(item.childCount()):
                any_visible |= walk(item.child(i))
            item.setHidden(not any_visible)
            if text and any_visible:
                item.setExpanded(True)
            return any_visible

        for i in range(self.tree.topLevelItemCount()):
            walk(self.tree.topLevelItem(i))


class PropertiesPanel(QWidget):
    """Model name and group."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.name = QLineEdit()
        self.name.setPlaceholderText(tr("Model name (required)"))
        self.group = QLineEdit()
        self.group.setPlaceholderText(tr("Group in the Processing Toolbox"))
        form = QFormLayout(self)
        form.addRow(tr("Name"), self.name)
        form.addRow(tr("Group"), self.group)

    def set_values(self, name, group):
        for edit, value in ((self.name, name), (self.group, group)):
            edit.blockSignals(True)
            edit.setText(value or "")
            edit.blockSignals(False)


class VariablesPanel(QWidget):
    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        from qgis.gui import QgsVariableEditorWidget
        self.editor = QgsVariableEditorWidget()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.editor)
        self.editor.scopeChanged.connect(self.changed)

    def set_variables(self, variables):
        scope = QgsExpressionContextScope(tr("Model variables"))
        for k, v in (variables or {}).items():
            scope.setVariable(k, v)
        ctx = QgsExpressionContext()
        ctx.appendScope(scope)
        self.editor.blockSignals(True)
        self.editor.setContext(ctx)
        self.editor.setEditableScopeIndex(0)
        self.editor.blockSignals(False)

    def variables(self):
        return self.editor.variablesInActiveScope()
