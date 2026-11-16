"""Fenêtre principale de ModelerEvo."""

import os

from qgis.core import (
    Qgis,
    QgsApplication,
    QgsProcessing,
    QgsProcessingModelAlgorithm,
    QgsProcessingModelGroupBox,
    QgsProcessingModelOutput,
    QgsProcessingModelParameter,
    QgsProject,
    QgsRasterLayer,
    QgsVectorLayer,
)
from qgis.gui import QgsColorButton, QgsMessageBar
from qgis.PyQt.QtCore import QPointF, QRectF, QSettings, QSize, QSizeF, Qt
from qgis.PyQt.QtGui import QColor, QImage, QKeySequence, QPainter
from qgis.PyQt.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QDockWidget,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QToolBar,
    QUndoView,
    QVBoxLayout,
    QWidget,
)

try:  # Qt6
    from qgis.PyQt.QtGui import QAction, QUndoCommand, QUndoStack
except ImportError:  # Qt5
    from qgis.PyQt.QtWidgets import QAction, QUndoCommand, QUndoStack

from ..core import model_utils as mu
from ..i18n import tr
from . import node_dialog
from .help_dialog import ModelHelpDialog
from .icons import output_type_icon, plugin_icon, theme_icon
from .items import DEFAULT_W, HEADER_H, ROW_H, CommentItem, GroupBoxItem, NodeItem
from .panels import AlgorithmsPanel, InputsPanel, PropertiesPanel, VariablesPanel
from .scene import ModelScene, ModelView

_LEVEL = getattr(Qgis, "MessageLevel", Qgis)
SETTINGS_PREFIX = "modeler_evo/"


class SnapshotCommand(QUndoCommand):
    """Commande d'annulation : état complet du modèle avant / après."""

    def __init__(self, window, text, before, after):
        super().__init__(text)
        self.window, self.before, self.after = window, before, after
        self._first = True

    def redo(self):
        if self._first:
            self._first = False
            return
        self.window.restore(self.after)

    def undo(self):
        self.window.restore(self.before)


class ModelerWindow(QMainWindow):
    instances = []

    def __init__(self, model=None, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowIcon(plugin_icon())
        self.setObjectName("ModelerEvoWindow")
        self.model = model if model is not None else QgsProcessingModelAlgorithm()
        self.dirty = False
        self._before = None
        self.child_results = {}

        self.undo_stack = QUndoStack(self)
        self.undo_stack.cleanChanged.connect(self._clean_changed)

        self.scene = ModelScene(self)
        self.view = ModelView(self.scene, self)
        self.message_bar = QgsMessageBar()
        central = QWidget()
        cl = QVBoxLayout(central)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(0)
        cl.addWidget(self.message_bar)
        cl.addWidget(self.view)
        self.setCentralWidget(central)

        self._build_panels()
        self._build_actions()
        self._build_menus()
        self.setStyleSheet(STYLE)

        self.resize(1400, 860)
        s = QSettings()
        geom = s.value(SETTINGS_PREFIX + "geometry")
        if geom:
            self.restoreGeometry(geom)
        state = s.value(SETTINGS_PREFIX + "state")
        if state:
            self.restoreState(state)

        self.refresh_all()
        self.view.zoom_full() if self.model.childAlgorithms() or self.model.parameterComponents() \
            else self.view.centerOn(0, 0)
        ModelerWindow.instances.append(self)

    # ================================================================ interface
    def _dock(self, title, widget, area, name):
        dock = QDockWidget(title, self)
        dock.setObjectName(name)
        dock.setWidget(widget)
        self.addDockWidget(area, dock)
        return dock

    def _build_panels(self):
        left = Qt.DockWidgetArea.LeftDockWidgetArea
        right = Qt.DockWidgetArea.RightDockWidgetArea
        self.inputs_panel = InputsPanel()
        self.inputs_panel.activated.connect(lambda t: self.add_input(t))
        self.algs_panel = AlgorithmsPanel()
        self.algs_panel.activated.connect(lambda a: self.add_algorithm(a))
        self.algs_panel.parameter_activated.connect(lambda t: self.add_input(t))
        self.props_panel = PropertiesPanel()
        self.props_panel.name.editingFinished.connect(self._name_group_changed)
        self.props_panel.group.editingFinished.connect(self._name_group_changed)
        try:
            self.vars_panel = VariablesPanel()
            self.vars_panel.changed.connect(self._variables_changed)
        except Exception:  # noqa: BLE001
            self.vars_panel = None
        self.undo_view = QUndoView(self.undo_stack)

        self.dock_inputs = self._dock(tr("Inputs"), self.inputs_panel, left, "mevo_inputs")
        self.dock_algs = self._dock(tr("Algorithms"), self.algs_panel, left, "mevo_algorithms")
        self.tabifyDockWidget(self.dock_inputs, self.dock_algs)
        self.dock_inputs.raise_()
        self.dock_props = self._dock(tr("Model properties"), self.props_panel, right, "mevo_props")
        docks = [self.dock_props]
        if self.vars_panel is not None:
            self.dock_vars = self._dock(tr("Variables"), self.vars_panel, right, "mevo_variables")
            docks.append(self.dock_vars)
        self.dock_undo = self._dock(tr("History"), self.undo_view, right, "mevo_undo")
        docks.append(self.dock_undo)
        for d in docks[1:]:
            self.tabifyDockWidget(docks[0], d)
        self.dock_props.raise_()
        self.docks = [self.dock_inputs, self.dock_algs] + docks

    def _action(self, text, slot, icon=None, shortcut=None, checkable=False, checked=False, tip=None):
        a = QAction(text, self)
        if icon:
            a.setIcon(theme_icon(icon))
        if shortcut is not None:
            a.setShortcut(QKeySequence(shortcut))
        if checkable:
            a.setCheckable(True)
            a.setChecked(checked)
            a.toggled.connect(slot)
        else:
            a.triggered.connect(lambda _checked=False: slot())
        if tip:
            a.setToolTip(tip)
        self.addAction(a)
        return a

    def _build_actions(self):
        SK = QKeySequence.StandardKey
        A = self._action
        self.a_new = A(tr("New model"), self.new_model, "/mActionFileNew.svg", SK.New)
        self.a_open = A(tr("Open model…"), self.open_model, "/mActionFileOpen.svg", SK.Open)
        self.a_save = A(tr("Save"), self.save, "/mActionFileSave.svg", SK.Save)
        self.a_save_as = A(tr("Save as…"), self.save_as, "/mActionFileSaveAs.svg", "Ctrl+Shift+S")
        self.a_save_project = A(tr("Save in project"), self.save_in_project, "/mAddToProject.svg")
        self.a_validate = A(tr("Validate model"), self.validate, "/mIconSuccess.svg")
        self.a_run = A(tr("Run model…"), self.run_model, "/mActionStart.svg", "F5")
        self.a_reorder = A(tr("Reorder inputs…"), self.reorder_inputs)
        self.a_help = A(tr("Edit model help…"), self.edit_model_help, "/mActionEditHelpContent.svg")
        self.a_exp_img = A(tr("Export as image…"), self.export_image, "/mActionSaveMapAsImage.svg")
        self.a_exp_pdf = A(tr("Export as PDF…"), self.export_pdf, "/mActionSaveAsPDF.svg")
        self.a_exp_svg = A(tr("Export as SVG…"), self.export_svg, "/mActionSaveAsSVG.svg")
        self.a_exp_py = A(tr("Export as Python script…"), self.export_python, "/mActionSaveAsPython.svg")

        self.a_undo = self.undo_stack.createUndoAction(self, tr("Undo"))
        self.a_undo.setIcon(theme_icon("/mActionUndo.svg"))
        self.a_undo.setShortcut(QKeySequence(SK.Undo))
        self.a_redo = self.undo_stack.createRedoAction(self, tr("Redo"))
        self.a_redo.setIcon(theme_icon("/mActionRedo.svg"))
        self.a_redo.setShortcuts([QKeySequence(SK.Redo), QKeySequence("Ctrl+Y")])
        self.addAction(self.a_undo)
        self.addAction(self.a_redo)
        self.a_select_all = A(tr("Select all"), self.select_all, "/mActionSelectAll.svg", SK.SelectAll)
        self.a_delete = A(tr("Delete selection"), self.delete_selected, "/mActionDeleteSelected.svg",
                          SK.Delete)
        self.a_snap_sel = A(tr("Snap selection to grid"), self.snap_selection)
        self.a_group = A(tr("Add group box"), lambda: self.add_group_box(None), "/mActionAddBasicRectangle.svg")

        self.a_zoom_in = A(tr("Zoom in"), lambda: self.view.zoom_by(1.25), "/mActionZoomIn.svg", "Ctrl++")
        self.a_zoom_out = A(tr("Zoom out"), lambda: self.view.zoom_by(0.8), "/mActionZoomOut.svg", "Ctrl+-")
        self.a_zoom_100 = A(tr("Zoom to 100%"), self.view.zoom_actual, "/mActionZoomActual.svg", "Ctrl+1")
        self.a_zoom_full = A(tr("Zoom to full extent"), self.view.zoom_full, "/mActionZoomFullExtent.svg", "Ctrl+0")
        self.a_comments = A(tr("Show comments"), self.scene.set_show_comments, checkable=True,
                            checked=True)
        self.a_snapping = A(tr("Enable snapping"), self._set_snapping, checkable=True, checked=False)
        self.a_dark = A(tr("Dark theme"), self.scene.set_dark, checkable=True, checked=self.scene.dark)
        self.a_panels = A(tr("Show panels"), self._toggle_panels, shortcut="Ctrl+Tab",
                          checkable=True, checked=True)

    def _build_menus(self):
        mb = self.menuBar()
        m = mb.addMenu(tr("&Model"))
        for a in (self.a_new, self.a_open, None, self.a_validate, self.a_run, None, self.a_reorder,
                  None, self.a_save, self.a_save_as, self.a_save_project, None, self.a_help):
            m.addSeparator() if a is None else m.addAction(a)
        exp = m.addMenu(tr("Export"))
        for a in (self.a_exp_img, self.a_exp_pdf, self.a_exp_svg, self.a_exp_py):
            exp.addAction(a)

        e = mb.addMenu(tr("&Edit"))
        for a in (self.a_undo, self.a_redo, None, self.a_select_all, self.a_snap_sel, None,
                  self.a_delete, None, self.a_group):
            e.addSeparator() if a is None else e.addAction(a)

        v = mb.addMenu(tr("&View"))
        self.zoom_to_menu = v.addMenu(tr("Zoom to"))
        self.zoom_to_menu.aboutToShow.connect(self._fill_zoom_to)
        for a in (self.a_zoom_in, self.a_zoom_out, self.a_zoom_100, self.a_zoom_full, None,
                  self.a_comments, self.a_snapping, self.a_dark, None, self.a_panels):
            v.addSeparator() if a is None else v.addAction(a)
        panels = v.addMenu(tr("Panels"))
        for d in self.docks:
            panels.addAction(d.toggleViewAction())

        tb = QToolBar(tr("Navigation"), self)
        tb.setObjectName("mevo_toolbar")
        tb.setIconSize(QSize(22, 22))
        self.addToolBar(tb)
        for a in (self.a_open, self.a_save, self.a_save_as, self.a_save_project, None,
                  self.a_zoom_full, self.a_zoom_in, self.a_zoom_out, self.a_zoom_100, None,
                  self.a_undo, self.a_redo, None, self.a_exp_img, self.a_exp_py, None,
                  self.a_help, self.a_validate, self.a_run):
            tb.addSeparator() if a is None else tb.addAction(a)

    def _fill_zoom_to(self):
        self.zoom_to_menu.clear()
        if not self.scene.groups:
            a = self.zoom_to_menu.addAction(tr("(no group box)"))
            a.setEnabled(False)
        for g in self.scene.groups:
            self.zoom_to_menu.addAction(
                g.title or tr("Group"),
                lambda g=g: self.view.fitInView(g.sceneBoundingRect().adjusted(-30, -30, 30, 30),
                                                Qt.AspectRatioMode.KeepAspectRatio))

    def _set_snapping(self, on):
        self.scene.snapping = on

    def _toggle_panels(self, on):
        for d in self.docks:
            d.setVisible(on)

    # ================================================================ état
    def refresh_all(self):
        self.scene.rebuild()
        self.props_panel.set_values(self.model.name(), self.model.group())
        if self.vars_panel is not None:
            self.vars_panel.set_variables(self.model.variables())
        self._update_title()

    def _update_title(self):
        name = self.model.name() or tr("Untitled model")
        self.setWindowTitle(f"{'*' if self.dirty else ''}{name} — ModelerEvo")

    def _clean_changed(self, clean):
        self.dirty = not clean
        self._update_title()

    def set_dirty(self):
        self.dirty = True
        self._update_title()

    def push_snapshot(self, text, before):
        after = self.model.toVariant()
        if after == before:
            return
        self.undo_stack.push(SnapshotCommand(self, text, before, after))
        self.set_dirty()

    def begin_change(self):
        self._before = self.model.toVariant()

    def end_change(self, text, rebuild=True):
        before, self._before = self._before, None
        if before is not None:
            self.push_snapshot(text, before)
        if rebuild:
            self.refresh_all()

    def restore(self, variant):
        path = self.model.sourceFilePath()
        self.model.loadVariant(variant)
        self.model.setSourceFilePath(path)
        self.refresh_all()

    def push_message(self, text, level="info", duration=5):
        lv = {"info": _LEVEL.Info, "warning": _LEVEL.Warning, "critical": _LEVEL.Critical,
              "success": _LEVEL.Success}[level]
        self.message_bar.pushMessage("", text, lv, duration)

    def _new_position(self, width=DEFAULT_W, height=110, extra_right=0.0):
        """Emplacement inoccupé le plus proche du centre de la vue."""
        c = self.view.mapToScene(self.view.viewport().rect().center())
        return self.scene.free_position(c, width, height, extra_right)

    # ================================================================ entrées
    def add_input(self, type_id, pos=None):
        res = node_dialog.edit_parameter(self, self.model, type_id)
        if not res or res[0] is None:
            return
        param, comment, color, help_text = res
        param.setName(mu.unique_parameter_name(self.model, param.description()))
        pos = QPointF(pos) if pos is not None else self._new_position(DEFAULT_W, HEADER_H + 50)
        comp = QgsProcessingModelParameter(param.name())
        comp.setDescription(param.name())
        comp.setPosition(pos)
        comp.comment().setDescription(comment)
        if color is not None:
            comp.comment().setColor(color)
        self.begin_change()
        self.model.addModelParameter(param, comp)
        mu.set_param_help(self.model, param.name(), help_text)
        self.end_change(tr("Add input"))
        self.scene.focus_node("input", param.name())

    def edit_input(self, name, comment_tab=False):
        m = self.model
        existing = m.parameterDefinition(name)
        if existing is None:
            return
        comp = m.parameterComponent(name)
        old_description = existing.description()
        res = node_dialog.edit_parameter(
            self, m, existing.type(), existing, comp.comment().description(), comp.comment().color(),
            mu.param_help(m, name), comment_tab)
        if not res or res[0] is None:
            return
        new_param, comment, color, help_text = res
        self.begin_change()
        if new_param.description() != old_description:
            # comme le modeleur d'origine : le nom suit la description modifiée
            new_param.setName(mu.unique_parameter_name(m, new_param.description(), exclude=name))
        else:
            new_param.setName(name)
        m.removeModelParameter(name)
        comp.setParameterName(new_param.name())
        comp.setDescription(new_param.name())
        comp.comment().setDescription(comment)
        if color is not None:
            comp.comment().setColor(color)
        m.addModelParameter(new_param, comp)
        if new_param.name() != name:
            try:
                m.changeParameterName(name, new_param.name())
            except AttributeError:
                pass
            mu.rename_help_key(m, name, new_param.name())
        mu.set_param_help(m, new_param.name(), help_text)
        self.end_change(tr("Edit input"))

    # ================================================================ algorithmes
    def add_algorithm(self, alg_id, pos=None):
        alg = QgsApplication.processingRegistry().createAlgorithmById(alg_id)
        if alg is None:
            self.push_message(tr("Algorithm not found: {0}").format(alg_id), "warning")
            return
        try:
            res = node_dialog.edit_algorithm(self, self.model, alg)
        except ImportError as e:
            self.push_message(tr("The Processing plugin is required: {0}").format(e), "critical")
            return
        if not res:
            return
        child, help_text = res
        if pos is None:
            n_rows = sum(1 for p in alg.parameterDefinitions()
                         if not p.isDestination() and not mu.param_has_flag(p, "Hidden")) \
                + len(alg.outputDefinitions())
            pos = self._new_position(DEFAULT_W, HEADER_H + 26 + n_rows * ROW_H,
                                     330 + DEFAULT_W if child.modelOutputs() else 0.0)
        pos = QPointF(pos)
        child.setPosition(pos)
        try:
            y = 120.0
            for out_name in child.modelOutputs():
                child.modelOutput(out_name).setPosition(pos + QPointF(320, y))
                y += 50
        except Exception:  # noqa: BLE001
            pass
        self.begin_change()
        cid = self.model.addChildAlgorithm(child)
        mu.set_child_help(self.model, cid, help_text)
        self.end_change(tr("Add algorithm"))
        self.scene.focus_node("child", cid)
        self._report_child_validity(cid)

    def edit_algorithm(self, cid, comment_tab=False):
        m = self.model
        child = m.childAlgorithm(cid)
        alg = child.algorithm()
        if alg is None:
            self.push_message(tr("Algorithm “{0}” is not available.").format(child.algorithmId()), "warning")
            return
        res = node_dialog.edit_algorithm(self, m, alg, child, mu.child_help(m, cid), comment_tab)
        if not res:
            return
        new_child, help_text = res
        new_child.setChildId(cid)
        new_child.copyNonDefinitionPropertiesFromModel(m)
        # La fenêtre d'origine ne connaît que les sorties de type destination : on conserve
        # celles qu'elle ne gère pas (nombre, texte, HTML…) ajoutées avec le clic droit.
        dest = {p.name() for p in alg.parameterDefinitions() if p.isDestination()}
        kept = {n: o for n, o in child.modelOutputs().items()
                if o.childOutputName() not in dest and n not in new_child.modelOutputs()}
        if kept:
            outs = dict(new_child.modelOutputs())
            outs.update(kept)
            new_child.setModelOutputs(outs)
        self.begin_change()
        m.setChildAlgorithm(new_child)
        mu.set_child_help(m, cid, help_text)
        self.end_change(tr("Edit algorithm"))
        self._report_child_validity(cid)

    # ================================================================ sorties du modèle
    def edit_output(self, key, comment_tab=False):
        cid, oname = key
        m = self.model
        child = m.childAlgorithm(cid)
        mo = child.modelOutputs().get(oname)
        if mo is None:
            return
        alg = child.algorithm()
        odef = alg.outputDefinition(mo.childOutputName()) if alg else None
        source = (child.description() or child.algorithmId()) + (
            " › " + odef.description() if odef is not None else "")
        com = mo.comment()
        res = node_dialog.edit_output(self, mo.description() or oname, source, com.description(),
                                      com.color() if hasattr(com, "color") else None,
                                      mu.output_help(m, cid, oname), comment_tab,
                                      evo_only=mu.is_extended_output(child, mo))
        if not res:
            return
        desc, text, color, help_text = res
        self.begin_change()
        child = m.childAlgorithm(cid)
        out = child.modelOutput(oname)
        out.setDescription(desc)
        out.comment().setDescription(text)
        if hasattr(out.comment(), "setColor"):
            out.comment().setColor(color)
        m.setChildAlgorithm(child)
        mu.set_output_help(m, cid, oname, help_text)
        self.end_change(tr("Edit output"))

    def add_model_output(self, cid, out_name):
        """Expose une sortie d'algorithme (de n'importe quel type) comme sortie du modèle."""
        child = self.model.childAlgorithm(cid)
        alg = child.algorithm()
        odef = alg.outputDefinition(out_name) if alg else None
        if odef is None or out_name in child.modelOutputs():
            return
        desc = odef.description() or out_name
        mo = QgsProcessingModelOutput(out_name, desc)
        mo.setChildId(cid)
        mo.setChildOutputName(out_name)
        idx = len(child.modelOutputs())
        mo.setPosition(self.scene.free_position(
            child.position() + QPointF(DEFAULT_W + 80, 40 * idx), DEFAULT_W, HEADER_H + 40))
        self.begin_change()
        outs = dict(child.modelOutputs())
        outs[out_name] = mo
        child.setModelOutputs(outs)
        self.model.setChildAlgorithm(child)
        self.end_change(tr("Add model output"))
        self.scene.focus_node("output", (cid, out_name))
        if out_name not in self.model.childAlgorithm(cid).modelOutputs():
            self.push_message(tr("This output could not be added to the model."), "warning")

    def _remove_output(self, key):
        cid, oname = key
        child = self.model.childAlgorithm(cid) if cid in self.model.childAlgorithms() else None
        if child is None or oname not in child.modelOutputs():
            return
        child.removeModelOutput(oname)
        self.model.setChildAlgorithm(child)
        mu.sync_help(self.model)

    def _report_child_validity(self, cid):
        try:
            ok, errors = self.model.validateChildAlgorithm(cid)
        except Exception:  # noqa: BLE001
            return
        if not ok:
            self.push_message(tr("Invalid parameters: {0}").format("; ".join(errors)), "warning", 8)

    def set_active(self, cid, active):
        self.begin_change()
        if active:
            self.model.activateChildAlgorithm(cid)
        else:
            self.model.deactivateChildAlgorithm(cid)
        self.end_change(tr("Activate algorithm") if active else tr("Deactivate algorithm"))

    # ================================================================ connexions
    def connect_link(self, src_key, cid, pname, detach=None):
        m = self.model
        child = m.childAlgorithm(cid)
        alg = child.algorithm()
        param = alg.parameterDefinition(pname) if alg else None
        if param is None:
            return
        srcs = list(child.parameterSources().get(pname, []))
        if detach is not None:
            child_src = m.childAlgorithm(detach[0])
            dsrcs = [s for s in child_src.parameterSources().get(detach[1], [])
                     if mu.source_key(s) != detach[2]]
            if detach[0] != cid:
                self.begin_change()
                if not dsrcs:
                    p2 = child_src.algorithm().parameterDefinition(detach[1])
                    dsrcs = [mu.static_source(p2.defaultValue() if p2 else None)]
                child_src.addParameterSources(detach[1], dsrcs)
                m.setChildAlgorithm(child_src)
                child = m.childAlgorithm(cid)
                srcs = list(child.parameterSources().get(pname, []))
            else:
                srcs = dsrcs
        if self._before is None:
            self.begin_change()
        new = mu.make_source(src_key)
        if mu.accepts_multiple(param):
            srcs = [s for s in srcs if mu.source_key(s) and mu.source_key(s) != src_key] + [new]
        else:
            srcs = [new]
        child.addParameterSources(pname, srcs)
        m.setChildAlgorithm(child)
        self.end_change(tr("Connect"))

    def disconnect_link(self, cid, pname, key):
        m = self.model
        child = m.childAlgorithm(cid)
        alg = child.algorithm()
        param = alg.parameterDefinition(pname) if alg else None
        srcs = [s for s in child.parameterSources().get(pname, []) if mu.source_key(s) != key]
        if not srcs:
            srcs = [mu.static_source(param.defaultValue() if param else None)]
        self.begin_change()
        child.addParameterSources(pname, srcs)
        m.setChildAlgorithm(child)
        self.end_change(tr("Disconnect"))

    # ================================================================ suppression
    def _remove_input(self, name):
        if self.model.childAlgorithmsDependOnParameter(name):
            self.push_message(tr("Cannot delete “{0}”: algorithms depend on it.").format(name),
                              "warning")
            return False
        self.model.removeModelParameter(name)
        mu.set_param_help(self.model, name, "")
        return True

    def _remove_child(self, cid):
        if not self.model.removeChildAlgorithm(cid):
            deps = self.model.dependentChildAlgorithms(cid)
            names = ", ".join(self.model.childAlgorithm(d).description() for d in deps)
            self.push_message(tr("Cannot delete this algorithm: {0} depend(s) on it.").format(names),
                              "warning")
            return False
        mu.sync_help(self.model)
        return True

    def _set_comment(self, kind, key, text):
        if kind == "input":
            comp = self.model.parameterComponent(key)
            comp.comment().setDescription(text)
            self.model.setParameterComponent(comp)
        elif kind == "output":
            cid, oname = key
            child = self.model.childAlgorithm(cid)
            if oname in child.modelOutputs():
                child.modelOutput(oname).comment().setDescription(text)
                self.model.setChildAlgorithm(child)
        else:
            child = self.model.childAlgorithm(key)
            child.comment().setDescription(text)
            self.model.setChildAlgorithm(child)

    def remove(self, kind, key):
        self.begin_change()
        if kind == "input":
            self._remove_input(key)
        elif kind == "child":
            self._remove_child(key)
        elif kind == "output":
            self._remove_output(key)
        elif kind == "group":
            self.model.removeGroupBox(key)
        self.end_change(tr("Delete"))

    def delete_selected(self):
        items = self.scene.selectedItems()
        if not items:
            return
        self.begin_change()
        # les algorithmes en aval d'abord pour lever les dépendances
        children = [i.key for i in items if isinstance(i, NodeItem) and i.kind == "child"]
        pending = list(children)
        for _ in range(len(pending) + 1):
            for cid in list(pending):
                if self.model.removeChildAlgorithm(cid):
                    pending.remove(cid)
        if pending:
            self.push_message(tr("Some algorithms were not deleted: other algorithms depend on them."),
                              "warning")
        mu.sync_help(self.model)
        for i in items:
            if isinstance(i, NodeItem) and i.kind == "output":
                self._remove_output(i.key)
            elif isinstance(i, NodeItem) and i.kind == "input":
                self._remove_input(i.key)
            elif isinstance(i, GroupBoxItem):
                self.model.removeGroupBox(i.uuid)
            elif isinstance(i, CommentItem) and not i.node.isSelected():
                self._set_comment(i.node.kind, i.node.key, "")
        self.end_change(tr("Delete selection"))

    # ================================================================ cadres de groupe
    def add_group_box(self, pos):
        box = QgsProcessingModelGroupBox(tr("Group"))
        sel = [i for i in self.scene.selectedItems() if isinstance(i, NodeItem)]
        if sel and pos is None:
            rect = QRectF()
            for i in sel:
                rect = rect.united(i.sceneBoundingRect())
            rect = rect.adjusted(-30, -50, 30, 30)
            box.setPosition(rect.center())
            box.setSize(QSizeF(rect.size()))
        else:
            box.setPosition(QPointF(pos) if pos is not None else self._new_position())
            box.setSize(QSizeF(420, 300))
        self.begin_change()
        self.model.addGroupBox(box)
        self.end_change(tr("Add group box"))

    def edit_group_box(self, uuid):
        box = next((b for b in self.model.groupBoxes() if b.uuid() == uuid), None)
        if box is None:
            return
        dlg = QDialog(self)
        dlg.setWindowTitle(tr("Group box"))
        title = QLineEdit(box.description())
        color = QgsColorButton()
        try:
            c = box.color()
            if c.isValid():
                color.setColor(c)
            else:
                color.setColor(QColor(GroupBoxItem.DEFAULT_COLOR))
        except AttributeError:
            color.setEnabled(False)
        form = QFormLayout(dlg)
        form.addRow(tr("Title"), title)
        form.addRow(tr("Color"), color)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        form.addRow(bb)
        if not dlg.exec():
            return
        box.setDescription(title.text())
        if color.isEnabled():
            box.setColor(color.color())
        self.begin_change()
        self.model.addGroupBox(box)
        self.end_change(tr("Edit group box"))

    # ================================================================ requêtes de la scène
    def handle_request(self, action, kind, key, *args):
        editors = {"input": self.edit_input, "output": self.edit_output, "child": self.edit_algorithm}
        if action == "edit":
            editors[kind](key)
        elif action == "edit_comment":
            editors[kind](key, True)
        elif action == "menu":
            self.node_context_menu(kind, key, args[0])
        elif action == "comment_menu":
            menu = QMenu(self)
            menu.addAction(tr("Edit comment…"), lambda: self.handle_request("edit_comment", kind, key))
            menu.addAction(tr("Delete comment"), lambda: self._delete_comment(kind, key))
            menu.exec(args[0])
        elif action == "edit_group":
            self.edit_group_box(key)
        elif action == "group_menu":
            menu = QMenu(self)
            menu.addAction(tr("Edit…"), lambda: self.edit_group_box(key))
            menu.addAction(tr("Delete"), lambda: self.remove("group", key))
            menu.exec(args[0])

    def _delete_comment(self, kind, key):
        self.begin_change()
        self._set_comment(kind, key, "")
        self.end_change(tr("Delete comment"))

    def node_context_menu(self, kind, key, screen_pos):
        menu = QMenu(self)
        if kind == "input":
            menu.addAction(theme_icon("/mActionToggleEditing.svg"), tr("Edit…"), lambda: self.edit_input(key))
            menu.addAction(tr("Comment…"), lambda: self.edit_input(key, True))
        elif kind == "output":
            menu.addAction(theme_icon("/mActionToggleEditing.svg"), tr("Edit…"),
                           lambda: self.edit_output(key))
            menu.addAction(tr("Comment…"), lambda: self.edit_output(key, True))
        else:
            child = self.model.childAlgorithm(key)
            menu.addAction(theme_icon("/mActionToggleEditing.svg"), tr("Edit…"),
                           lambda: self.edit_algorithm(key))
            menu.addAction(tr("Comment…"), lambda: self.edit_algorithm(key, True))
            alg = child.algorithm()
            if alg is not None:
                free = [o for o in alg.outputDefinitions() if o.name() not in child.modelOutputs()]
                sub = menu.addMenu(theme_icon("/mActionFileSave.svg"), tr("Add model output"))
                sub.setEnabled(bool(free))
                for o in free:
                    label = f"{o.description() or o.name()}  ({o.type()})"
                    if alg.parameterDefinition(o.name()) is None:
                        label = "[Evo] " + label  # sortie étendue : non compatible avec l'ancien modeleur
                    sub.addAction(output_type_icon(o.type()), label,
                                  lambda n=o.name(): self.add_model_output(key, n))
            menu.addSeparator()
            if child.isActive():
                menu.addAction(tr("Deactivate"), lambda: self.set_active(key, False))
            else:
                menu.addAction(tr("Activate"), lambda: self.set_active(key, True))
            if key in self.child_results:
                menu.addAction(theme_icon("/mActionShowSelectedLayers.svg"), tr("View output layers"),
                               lambda: self.view_output_layers(key))
        menu.addSeparator()
        menu.addAction(theme_icon("/mActionDeleteSelected.svg"), tr("Delete"), lambda: self.remove(kind, key))
        menu.exec(screen_pos)

    def canvas_context_menu(self, scene_pos, screen_pos):
        menu = QMenu(self)
        menu.addAction(tr("Add group box here"), lambda: self.add_group_box(scene_pos))
        menu.addAction(tr("Zoom to full extent"), self.view.zoom_full)
        menu.exec(screen_pos)

    # ================================================================ édition
    def select_all(self):
        for i in self.scene.items():
            if i.flags() & i.GraphicsItemFlag.ItemIsSelectable:
                i.setSelected(True)

    def snap_selection(self):
        from .items import GRID
        for i in self.scene.selectedItems():
            if isinstance(i, (NodeItem, GroupBoxItem, CommentItem)):
                tl = i.mapToScene(i.rect().topLeft())
                d = QPointF(round(tl.x() / GRID) * GRID - tl.x(), round(tl.y() / GRID) * GRID - tl.y())
                i.setPos(i.pos() + d)
        self.scene.commit_layout(tr("Snap to grid"))

    def _name_group_changed(self):
        name, group = self.props_panel.name.text(), self.props_panel.group.text()
        if name == self.model.name() and group == self.model.group():
            return
        self.begin_change()
        self.model.setName(name)
        self.model.setGroup(group)
        self.end_change(tr("Edit name / group"), rebuild=False)
        self._update_title()

    def _variables_changed(self):
        self.begin_change()
        self.model.setVariables(self.vars_panel.variables())
        self.end_change(tr("Edit variables"), rebuild=False)

    def edit_model_help(self):
        dlg = ModelHelpDialog(self.model, self)
        if dlg.exec():
            self.begin_change()
            dlg.apply()
            self.end_change(tr("Edit model help"))

    def reorder_inputs(self):
        dlg = QDialog(self)
        dlg.setWindowTitle(tr("Reorder model inputs"))
        lst = QListWidget()
        lst.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        try:
            params = [self.model.parameterDefinition(c.parameterName())
                      for c in self.model.orderedParameters()]
        except AttributeError:
            params = list(self.model.parameterDefinitions())
        for p in params:
            if p is None or p.isDestination():
                continue
            it = QListWidgetItem(p.description())
            it.setData(Qt.ItemDataRole.UserRole, p.name())
            lst.addItem(it)

        def move(delta):
            row = lst.currentRow()
            if row < 0 or not (0 <= row + delta < lst.count()):
                return
            it = lst.takeItem(row)
            lst.insertItem(row + delta, it)
            lst.setCurrentRow(row + delta)

        up, down = QPushButton(tr("Move up")), QPushButton(tr("Move down"))
        up.clicked.connect(lambda: move(-1))
        down.clicked.connect(lambda: move(1))
        side = QVBoxLayout()
        side.addWidget(up)
        side.addWidget(down)
        side.addStretch()
        row = QHBoxLayout()
        row.addWidget(lst)
        row.addLayout(side)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        lay = QVBoxLayout(dlg)
        lay.addLayout(row)
        lay.addWidget(bb)
        if dlg.exec():
            order = [lst.item(i).data(Qt.ItemDataRole.UserRole) for i in range(lst.count())]
            self.begin_change()
            self.model.setParameterOrder(order)
            self.end_change(tr("Reorder inputs"), rebuild=False)

    # ================================================================ fichiers
    def _models_folder(self):
        try:
            from processing.modeler.ModelerUtils import ModelerUtils
            return ModelerUtils.modelsFolders()[0]
        except Exception:  # noqa: BLE001
            return os.path.expanduser("~")

    def _confirm_discard(self):
        if not self.dirty:
            return True
        btn = QMessageBox.question(
            self, tr("Model modified"), tr("The model has been modified. Save the changes?"),
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel)
        if btn == QMessageBox.StandardButton.Save:
            return self.save()
        return btn == QMessageBox.StandardButton.Discard

    def set_model(self, model):
        self.model = model
        self.child_results = {}
        self.scene.child_status = {}
        self.undo_stack.clear()
        self.dirty = False
        self.refresh_all()
        self.view.zoom_full()

    def new_model(self):
        if self._confirm_discard():
            self.set_model(QgsProcessingModelAlgorithm())

    def open_model(self, path=None):
        if not self._confirm_discard():
            return
        if not path:
            path, _ = QFileDialog.getOpenFileName(self, tr("Open model"), self._models_folder(),
                                                  tr("Processing models") + " (*.model3 *.MODEL3)")
        if not path:
            return
        model = QgsProcessingModelAlgorithm()
        if not model.fromFile(path):
            QMessageBox.critical(self, tr("Open model"), tr("Cannot read the model:\n{0}").format(path))
            return
        model.setSourceFilePath(path)
        self.set_model(model)

    def _prepare_save(self):
        self._name_group_changed()
        if not self.model.name():
            QMessageBox.warning(self, tr("Save"), tr("Please enter a model name "
                                   "(“Model properties” panel)."))
            self.dock_props.show()
            self.dock_props.raise_()
            self.props_panel.name.setFocus()
            return False
        mu.sync_help(self.model)
        return True

    def save(self):
        return self._save(self.model.sourceFilePath())

    def save_as(self):
        return self._save(None)

    def _save(self, path):
        if not self._prepare_save():
            return False
        if not path:
            default = os.path.join(self._models_folder(), mu.safe_name(self.model.name()) + ".model3")
            path, _ = QFileDialog.getSaveFileName(self, tr("Save model"), default,
                                                  tr("Processing models") + " (*.model3 *.MODEL3)")
            if not path:
                return False
            if not path.lower().endswith(".model3"):
                path += ".model3"
        self.model.setSourceFilePath(path)
        if not self.model.toFile(path):
            QMessageBox.critical(self, tr("Save"), tr("Cannot write the file:\n{0}").format(path))
            return False
        provider = QgsApplication.processingRegistry().providerById("model")
        if provider is not None:
            provider.refreshAlgorithms()
        self.undo_stack.setClean()
        self.dirty = False
        self._update_title()
        self.push_message(tr("Model saved: {0}").format(path), "success")
        return True

    def save_in_project(self):
        if not self._prepare_save():
            return
        provider = QgsApplication.processingRegistry().providerById("project")
        if provider is None or not hasattr(provider, "add_model"):
            self.push_message(tr("The “project models” provider is not available."), "warning")
            return
        self.model.setSourceFilePath("")
        provider.add_model(self.model)
        self.undo_stack.setClean()
        self.dirty = False
        self._update_title()
        self.push_message(tr("Model saved in the project. Remember to save the project."), "success")

    # ================================================================ validation / exécution
    def validate(self):
        try:
            ok, issues = self.model.validate()
        except AttributeError:
            ok, issues = True, []
        if ok:
            self.push_message(tr("The model is valid."), "success")
        else:
            QMessageBox.warning(self, tr("Validate model"),
                                tr("The model is not valid:") + "\n\n• " + "\n• ".join(issues))

    def _create_execution_dialog(self, alg):
        """Fenêtre d'exécution d'un algorithme (QGIS 4 : widget Processing ; QGIS 3 : AlgorithmDialog).

        Retourne (fenêtre, None) ou (None, message d'erreur détaillé).
        """
        errors = []
        try:  # QGIS 4 : processing.gui.algorithm_widget.AlgorithmWidget
            from qgis.gui import QgsProcessingAlgorithmWidgetBase
            from processing.gui.algorithm_widget import AlgorithmWidget
            base = QgsProcessingAlgorithmWidgetBase
            try:
                flags = base.WidgetFlags(base.WidgetFlag.NoDocking)
            except TypeError:
                flags = base.WidgetFlag.NoDocking
            return AlgorithmWidget(alg, False, self, flags), None
        except Exception as e:  # noqa: BLE001
            errors.append(f"algorithm_widget : {type(e).__name__}: {e}")
        try:  # QGIS 4 : fabrique GUI
            from qgis.gui import QgsGui
            factory = QgsGui.processingGuiRegistry().dialogFactory()
            if factory is not None:
                return factory.createWidget(alg, False, self), None
            errors.append("no processing dialog factory")
        except Exception as e:  # noqa: BLE001
            errors.append(f"dialog factory: {type(e).__name__}: {e}")
        try:  # QGIS 3.x
            from processing.gui.AlgorithmDialog import AlgorithmDialog
            return AlgorithmDialog(alg, parent=self), None
        except Exception as e:  # noqa: BLE001
            errors.append(f"AlgorithmDialog : {type(e).__name__}: {e}")
        return None, " | ".join(errors)

    def run_model(self):
        if not self.model.childAlgorithms():
            self.push_message(tr("The model does not contain any algorithm."), "warning")
            return
        mu.sync_help(self.model)
        alg = self.model.create()
        dlg, err = self._create_execution_dialog(alg)
        if dlg is None:
            self.push_message(tr("Cannot open the execution dialog: {0}").format(err), "critical", 15)
            return
        level = getattr(getattr(Qgis, "ProcessingLogLevel", None), "ModelDebug", None)
        if level is not None:
            try:
                dlg.setLogLevel(level)
            except Exception:  # noqa: BLE001
                pass
        try:
            dlg.setParameters(self.model.designerParameterValues())
        except Exception:  # noqa: BLE001
            pass

        def finished(successful=True, results=None, *_args):
            child = {}
            try:
                child = dict(dlg.results().get("CHILD_RESULTS", {}) or {})
            except Exception:  # noqa: BLE001
                pass
            if not child:
                try:
                    res = dlg.processingContext().modelResult()
                    child = {k: v.outputs() for k, v in res.childResults().items()}
                except Exception:  # noqa: BLE001
                    child = {}
            self.child_results = child
            self.scene.child_status = {k: "ok" for k in child}
            self.scene.update()

        try:
            dlg.algorithmFinished.connect(finished)
        except AttributeError:
            pass
        dlg.exec()
        try:
            if dlg.wasExecuted():
                self.model.setDesignerParameterValues(dlg.createProcessingParameters())
        except Exception:  # noqa: BLE001
            pass

    def view_output_layers(self, cid):
        outputs = self.child_results.get(cid, {}) or {}
        child = self.model.childAlgorithm(cid)
        added = 0
        for name, value in outputs.items():
            if not isinstance(value, str) or not value:
                continue
            label = f"{child.description()} — {name}"
            layer = QgsVectorLayer(value, label, "ogr")
            if not layer.isValid():
                layer = QgsRasterLayer(value, label)
            if layer.isValid():
                QgsProject.instance().addMapLayer(layer)
                added += 1
        self.push_message(tr("{0} layer(s) added to the project.").format(added) if added
                          else tr("No output layer available."), "info")

    # ================================================================ exports
    def _render(self, painter, target=None):
        self.scene.exporting = True
        selected = self.scene.selectedItems()
        self.scene.clearSelection()
        source = self.scene.itemsBoundingRect().adjusted(-20, -20, 20, 20)
        self.scene.render(painter, target if target is not None else QRectF(), source)
        for i in selected:
            i.setSelected(True)
        self.scene.exporting = False

    def _export_path(self, title, filt, ext):
        default = os.path.join(self._models_folder(), (mu.safe_name(self.model.name()) or "model") + ext)
        path, _ = QFileDialog.getSaveFileName(self, title, default, filt)
        if path and not path.lower().endswith(ext):
            path += ext
        return path

    def export_image(self):
        path = self._export_path(tr("Export as image"), "PNG (*.png)", ".png")
        if not path:
            return
        rect = self.scene.itemsBoundingRect().adjusted(-20, -20, 20, 20)
        scale = 2
        img = QImage(int(rect.width() * scale), int(rect.height() * scale), QImage.Format.Format_ARGB32)
        img.fill(QColor("#ffffff"))
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._render(p, QRectF(0, 0, img.width(), img.height()))
        p.end()
        img.save(path)
        self.push_message(tr("Image exported: {0}").format(path), "success")

    def export_pdf(self):
        path = self._export_path(tr("Export as PDF"), "PDF (*.pdf)", ".pdf")
        if not path:
            return
        from qgis.PyQt.QtCore import QMarginsF
        from qgis.PyQt.QtGui import QPageLayout, QPageSize, QPdfWriter
        rect = self.scene.itemsBoundingRect().adjusted(-20, -20, 20, 20)
        writer = QPdfWriter(path)
        writer.setResolution(96)
        writer.setPageLayout(QPageLayout(QPageSize(QSizeF(rect.width(), rect.height()),
                                                   QPageSize.Unit.Point),
                                         QPageLayout.Orientation.Portrait, QMarginsF(0, 0, 0, 0)))
        p = QPainter(writer)
        self._render(p)
        p.end()
        self.push_message(tr("PDF exported: {0}").format(path), "success")

    def export_svg(self):
        path = self._export_path(tr("Export as SVG"), "SVG (*.svg)", ".svg")
        if not path:
            return
        from qgis.PyQt.QtSvg import QSvgGenerator
        rect = self.scene.itemsBoundingRect().adjusted(-20, -20, 20, 20)
        gen = QSvgGenerator()
        gen.setFileName(path)
        gen.setSize(rect.size().toSize())
        gen.setViewBox(QRectF(0, 0, rect.width(), rect.height()))
        gen.setTitle(self.model.name() or tr("Model"))
        p = QPainter(gen)
        self._render(p, QRectF(0, 0, rect.width(), rect.height()))
        p.end()
        self.push_message(tr("SVG exported: {0}").format(path), "success")

    def export_python(self):
        mu.sync_help(self.model)
        out_type = None
        for owner in (getattr(QgsProcessing, "PythonOutputType", None), QgsProcessing,
                      getattr(Qgis, "ProcessingPythonOutputType", None)):
            if owner is not None and hasattr(owner, "PythonQgsProcessingAlgorithmSubclass"):
                out_type = owner.PythonQgsProcessingAlgorithmSubclass
                break
        if out_type is None:
            self.push_message(tr("Python export is not available in this QGIS version."), "warning")
            return
        code = "\n".join(self.model.asPythonCode(out_type, 4))
        path = self._export_path(tr("Export as Python script"), "Python (*.py)", ".py")
        if not path:
            return
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(code)
        self.push_message(tr("Script exported: {0}").format(path), "success")

    # ================================================================ fermeture
    def closeEvent(self, ev):  # noqa: N802
        if not self._confirm_discard():
            ev.ignore()
            return
        s = QSettings()
        s.setValue(SETTINGS_PREFIX + "geometry", self.saveGeometry())
        s.setValue(SETTINGS_PREFIX + "state", self.saveState())
        if self in ModelerWindow.instances:
            ModelerWindow.instances.remove(self)
        super().closeEvent(ev)


STYLE = """
QDockWidget::title { padding: 6px 8px; font-weight: 600; }
QToolBar { spacing: 4px; padding: 3px; }
QTreeView, QTreeWidget, QListWidget { border: none; }
"""
