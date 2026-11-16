"""Node settings dialog: Properties, Comments and Help tabs.

The "Properties" and "Comments" tabs are those of the original modeler dialogs
(identical behavior); the "Help" tab is added.
"""

from qgis.core import QgsProject
from qgis.gui import QgsColorButton
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

try:
    from qgis.utils import iface
except ImportError:  # pragma: no cover
    iface = None


from ..i18n import tr  # noqa: E402
from .icons import EVO_COLOR, EVO_TEXT  # noqa: E402


def _create_context():
    try:
        from processing.tools.dataobjects import createContext
        return createContext()
    except ImportError:
        from qgis.core import QgsProcessingContext
        ctx = QgsProcessingContext()
        ctx.setProject(QgsProject.instance())
        return ctx


def create_widget_context(model):
    from qgis.gui import QgsProcessingParameterWidgetContext
    ctx = QgsProcessingParameterWidgetContext()
    ctx.setProject(QgsProject.instance())
    if iface is not None:
        ctx.setMapCanvas(iface.mapCanvas())
        try:
            ctx.setActiveLayer(iface.activeLayer())
        except AttributeError:
            pass
        try:
            ctx.setBrowserModel(iface.browserModel())
        except AttributeError:
            pass
    ctx.setModel(model)
    return ctx


def _main_tab_widget(dlg):
    """Top-level QTabWidget of the dialog (Properties / Comments)."""
    best, best_depth = None, None
    for tw in dlg.findChildren(QTabWidget):
        depth, w = 0, tw.parentWidget()
        while w is not None and w is not dlg:
            depth += 1
            w = w.parentWidget()
        if best is None or depth < best_depth:
            best, best_depth = tw, depth
    return best


def _help_editor(text):
    editor = QTextEdit()
    editor.setAcceptRichText(False)
    editor.setPlaceholderText(tr(
        "Help specific to this node (text or HTML).\n"
        "It is shown when hovering over the node and included in the model help "
        "when a user opens the model."))
    editor.setPlainText(text or "")
    return editor


def install_tabs(dlg, help_text):
    """Rename the original tabs and add the "Help" tab.

    Returns the help editor.
    """
    editor = _help_editor(help_text)
    tabs = _main_tab_widget(dlg)
    if tabs is not None:
        if tabs.count() >= 1:
            tabs.setTabText(0, tr("Properties"))
        if tabs.count() >= 2:
            tabs.setTabText(1, tr("Comments"))
        page = QWidget()
        lay = QVBoxLayout(page)
        info = QLabel(tr("This help is shown when hovering over the node and in the model window."))
        info.setWordWrap(True)
        lay.addWidget(info)
        lay.addWidget(editor)
        tabs.addTab(page, tr("Help"))
    else:
        box = QGroupBox(tr("Help"))
        QVBoxLayout(box).addWidget(editor)
        layout = dlg.layout()
        if layout is not None:
            layout.insertWidget(max(0, layout.count() - 1), box)
    dlg.resize(max(dlg.width(), 620), max(dlg.height(), 560))
    return editor


def _call(obj, name, *args):
    fn = getattr(obj, name, None)
    if callable(fn):
        try:
            return fn(*args)
        except TypeError:
            return None
    return None


def edit_parameter(parent, model, type_id, existing=None, comment="", comment_color=None,
                   help_text="", comment_tab=False):
    """Definition dialog of a model input.

    Returns (parameter, comment, color, help) or None if cancelled.
    """
    legacy_cls = None
    try:
        from processing.modeler.ModelerParameterDefinitionDialog import (
            ModelerParameterDefinitionDialog as legacy_cls,
        )
        if existing is not None:
            use_legacy = legacy_cls.use_legacy_dialog(param=existing)
        else:
            use_legacy = legacy_cls.use_legacy_dialog(paramType=type_id)
    except (ImportError, AttributeError, TypeError):
        use_legacy = False

    if use_legacy and legacy_cls is not None:
        if existing is not None:
            dlg = legacy_cls(model, param=existing)
        else:
            dlg = legacy_cls(model, type_id)
        _call(dlg, "setComments", comment)
        if comment_color is not None:
            _call(dlg, "setCommentColor", comment_color)
        editor = install_tabs(dlg, help_text)
        if comment_tab:
            _call(dlg, "switchToCommentTab")
        if not dlg.exec():
            return None
        return (dlg.param, _call(dlg, "comments") or "", _call(dlg, "commentColor"),
                editor.toPlainText().strip())

    from qgis.gui import QgsProcessingParameterDefinitionDialog
    context = _create_context()
    widget_context = create_widget_context(model)
    dlg = QgsProcessingParameterDefinitionDialog(
        type=type_id, context=context, widgetContext=widget_context,
        definition=existing, algorithm=model, parent=parent)
    _call(dlg, "setComments", comment)
    if comment_color is not None:
        _call(dlg, "setCommentColor", comment_color)
    editor = install_tabs(dlg, help_text)
    if comment_tab:
        _call(dlg, "switchToCommentTab")
    if not dlg.exec():
        return None
    param = dlg.createParameter(existing.name() if existing is not None else "")
    return (param, _call(dlg, "comments") or "", _call(dlg, "commentColor"),
            editor.toPlainText().strip())


def edit_algorithm(parent, model, alg, child=None, help_text="", comment_tab=False):
    """Settings dialog of a model algorithm.

    Returns (QgsProcessingModelChildAlgorithm, help) or None if cancelled.
    """
    from processing.modeler.ModelerParametersDialog import ModelerParametersDialog
    if child is not None:
        dlg = ModelerParametersDialog(alg, model, child.childId(), child.configuration())
        _call(dlg, "setComments", child.comment().description())
        _call(dlg, "setCommentColor", child.comment().color())
    else:
        dlg = ModelerParametersDialog(alg, model)
    editor = install_tabs(dlg, help_text)
    if comment_tab:
        _call(dlg, "switchToCommentTab")
    if not dlg.exec():
        return None
    new_child = dlg.createAlgorithm()
    if new_child is None:
        return None
    return new_child, editor.toPlainText().strip()


def edit_output(parent, description, source, comment="", comment_color=None, help_text="",
                comment_tab=False, evo_only=False):
    """Settings dialog of a model output (Properties, Comments, Help tabs).

    Returns (description, comment, color, help) or None if cancelled.
    """
    dlg = QDialog(parent)
    dlg.setWindowTitle(tr("Model output"))
    lay = QVBoxLayout(dlg)
    tabs = QTabWidget()
    lay.addWidget(tabs)

    props = QWidget()
    form = QFormLayout(props)
    name_edit = QLineEdit(description)
    form.addRow(tr("Description"), name_edit)
    src_label = QLabel(source)
    src_label.setWordWrap(True)
    form.addRow(tr("Source"), src_label)
    if evo_only:
        note = QLabel(f"<b style='color:{EVO_COLOR}'>Evo</b> — {EVO_TEXT}.<br/>"
                      + tr("This output can only be read by ModelerEvo (the original modeler ignores it)."))
        note.setWordWrap(True)
        form.addRow(note)
    tabs.addTab(props, tr("Properties"))

    com = QWidget()
    clay = QVBoxLayout(com)
    com_edit = QTextEdit()
    com_edit.setAcceptRichText(False)
    com_edit.setPlainText(comment or "")
    clay.addWidget(com_edit)
    color_btn = QgsColorButton()
    color_btn.setAllowOpacity(True)
    if comment_color is not None and QColor(comment_color).isValid():
        color_btn.setColor(QColor(comment_color))
    else:
        color_btn.setColor(QColor("#fff4b8"))
    clay.addWidget(color_btn)
    tabs.addTab(com, tr("Comments"))

    help_page = QWidget()
    hlay = QVBoxLayout(help_page)
    hlay.addWidget(QLabel(tr("This help is shown when hovering over the node and in the model window.")))
    editor = _help_editor(help_text)
    hlay.addWidget(editor)
    tabs.addTab(help_page, tr("Help"))

    if comment_tab:
        tabs.setCurrentIndex(1)
    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                               | QDialogButtonBox.StandardButton.Cancel)
    buttons.accepted.connect(dlg.accept)
    buttons.rejected.connect(dlg.reject)
    lay.addWidget(buttons)
    dlg.resize(520, 380)
    if not dlg.exec():
        return None
    return (name_edit.text().strip() or description, com_edit.toPlainText().strip(),
            color_btn.color(), editor.toPlainText().strip())
