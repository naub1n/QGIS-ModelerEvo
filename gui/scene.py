"""Scène du modeleur : construit les éléments à partir du modèle Processing."""

from qgis.PyQt.QtCore import QSettings, QPointF, QRectF, QSizeF, Qt, QTimer
from qgis.PyQt.QtGui import QColor, QPainterPath, QPen
from qgis.PyQt.QtWidgets import QGraphicsPathItem, QGraphicsScene, QGraphicsView

from ..core import model_utils as mu
from .icons import ACCENT, CATEGORY_COLORS
from .theme import DARK, LIGHT
from .items import GRID, CommentItem, EdgeItem, GroupBoxItem, NodeItem

DIRECT_KINDS = ("ModelParameter", "ChildOutput")


class ModelScene(QGraphicsScene):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.snapping = False
        self.show_comments = True
        self.exporting = False
        self.dark = QSettings().value("modeler_evo/dark", False, type=bool)
        self.group_moving = False
        self.child_status = {}
        self.drag_targets = set()
        self.inputs = {}
        self.children = {}
        self.outputs = {}
        self.comments = []
        self.groups = []
        self.edges = []
        self._drag = None
        self.z_order = {}  # (type, clé) -> z : l'ordre d'empilement survit aux reconstructions
        self._z_top = 10
        self.setSceneRect(QRectF(-4000, -4000, 8000, 8000))

    @property
    def model(self):
        return self.window.model

    # ------------------------------------------------------------ premier plan
    def bring_to_front(self, node):
        k = (node.kind, node.key)
        if self.z_order.get(k) == self._z_top and node.zValue() == self._z_top:
            return
        self._z_top += 1
        self.z_order[k] = self._z_top
        node.setZValue(self._z_top)

    def focus_node(self, kind, key):
        """Place le noeud au premier plan et le sélectionne (après un ajout)."""
        node = {"input": self.inputs, "child": self.children, "output": self.outputs}[kind].get(key)
        if node is None:
            return
        self.clearSelection()
        self.bring_to_front(node)
        node.setSelected(True)

    def free_position(self, anchor, width, height, extra_right=0.0, margin=30.0):
        """Centre d'un emplacement inoccupé, le plus proche de `anchor` (pas de 40 px)."""
        busy = [i.sceneBoundingRect().adjusted(-margin, -margin, margin, margin)
                for i in list(self.inputs.values()) + list(self.children.values())
                + list(self.outputs.values()) + self.comments if i.isVisible()]
        step = 40
        ax = round(anchor.x() / step) * step
        ay = round(anchor.y() / step) * step
        for ring in range(0, 80):
            for dx in range(-ring, ring + 1):
                for dy in range(-ring, ring + 1):
                    if max(abs(dx), abs(dy)) != ring:
                        continue
                    c = QPointF(ax + dx * step, ay + dy * step)
                    cand = QRectF(c.x() - width / 2, c.y() - height / 2, width + extra_right, height)
                    if not any(cand.intersects(b) for b in busy):
                        return c
        return QPointF(anchor)

    # ------------------------------------------------------------ construction
    def rebuild(self):
        selected = {(getattr(i, "kind", "group"), getattr(i, "key", getattr(i, "uuid", None)))
                    for i in self.selectedItems()}
        self._drag = None
        self.drag_targets = set()
        self.clear()
        self.inputs, self.children, self.outputs = {}, {}, {}
        self.comments, self.groups, self.edges = [], [], []
        m = self.model

        for box in m.groupBoxes():
            item = GroupBoxItem(self, box)
            self.addItem(item)
            self.groups.append(item)
        for name in m.parameterComponents().keys():
            if m.parameterDefinition(name) is None:
                continue
            node = NodeItem(self, "input", name)
            self.addItem(node)
            self.inputs[name] = node
        for cid in m.childAlgorithms().keys():
            node = NodeItem(self, "child", cid)
            self.addItem(node)
            self.children[cid] = node
        for cid, child in m.childAlgorithms().items():
            for oname in child.modelOutputs():
                node = NodeItem(self, "output", (cid, oname))
                self.addItem(node)
                self.outputs[(cid, oname)] = node
        for node in (list(self.inputs.values()) + list(self.children.values())
                     + list(self.outputs.values())):
            if node.component().comment().description():
                c = CommentItem(self, node)
                self.addItem(c)
                c.setVisible(self.show_comments)
                self.comments.append(c)
        self._build_edges()
        self._build_output_edges()

        for item in (list(self.inputs.values()) + list(self.children.values())
                     + list(self.outputs.values()) + self.groups):
            ident = (getattr(item, "kind", "group"), getattr(item, "key", getattr(item, "uuid", None)))
            if ident in selected:
                item.setSelected(True)
        bounds = self.itemsBoundingRect().adjusted(-3000, -3000, 3000, 3000)
        self.setSceneRect(bounds.united(QRectF(-4000, -4000, 8000, 8000)))

    def _source_socket(self, key):
        if key[0] == "param":
            node = self.inputs.get(key[1])
            return (node, key[1]) if node else (None, None)
        node = self.children.get(key[1])
        if node and node.row("out", key[2]):
            return node, key[2]
        return None, None

    def _source_color(self, node, name):
        row = node.row("out", name) if name else None
        return CATEGORY_COLORS.get(row.category if row else "other")

    def _add_edge(self, src, src_name, dst, dst_name, style, color, tooltip):
        edge = EdgeItem(src, src_name, dst, dst_name, style, color, tooltip)
        self.addItem(edge)
        self.edges.append(edge)

    def _build_edges(self):
        m = self.model
        vmap = mu.variable_map(m)
        # Relations entre entrées (ex. champ -> couche parente)
        for name, node in self.inputs.items():
            p = m.parameterDefinition(name)
            for dep in (p.dependsOnOtherParameters() or []):
                src = self.inputs.get(dep)
                if src:
                    self._add_edge(src, dep, node, None, "parent", "#9aa3ad",
                                   f"« {p.description()} » dépend de « {src.title} »")
        for cid, node in self.children.items():
            child = m.childAlgorithm(cid)
            visible = {r.name for r in node.rows if r.side == "in"}
            seen = set()
            for pname, srcs in child.parameterSources().items():
                if pname not in visible:
                    continue
                for s in srcs:
                    key = mu.source_key(s)
                    if key:
                        src, sname = self._source_socket(key)
                        if src:
                            self._add_edge(src, sname, node, pname, "direct",
                                           self._source_color(src, sname),
                                           f"{src.title} → {node.title} ({node.row('in', pname).label})")
                    for ref in mu.expression_references(m, s, vmap):
                        if (ref, pname) in seen:
                            continue
                        seen.add((ref, pname))
                        src, sname = self._source_socket(ref)
                        if src and src is not node:
                            self._add_edge(src, sname, node, pname, "expression",
                                           self._source_color(src, sname),
                                           f"Utilisé dans une expression : {src.title} → "
                                           f"{node.title} ({node.row('in', pname).label})")
            for dep in mu.child_dependency_ids(child):
                src = self.children.get(dep)
                if src:
                    self._add_edge(src, None, node, None, "dependency", "#7b8794",
                                   f"Dépendance : {src.title} s'exécute avant {node.title}")

    def _build_output_edges(self):
        """Flèche de chaque sortie d'algorithme vers son noeud de sortie (orange)."""
        m = self.model
        for (cid, oname), onode in self.outputs.items():
            cnode = self.children.get(cid)
            mo = m.childAlgorithm(cid).modelOutputs().get(oname)
            if cnode is None or mo is None:
                continue
            src_name = mo.childOutputName()
            if cnode.row("out", src_name):
                self._add_edge(cnode, src_name, onode, None, "direct",
                               self._source_color(cnode, src_name),
                               f"{cnode.title} → sortie « {onode.title} »")

    def update_node_links(self, node):
        for edge in node.edges:
            edge.update_path()
        if node.comment_item:
            node.comment_item.update_link()

    def set_show_comments(self, show):
        self.show_comments = show
        for c in self.comments:
            c.setVisible(show)

    # ------------------------------------------------------------ requêtes différées
    def request(self, action, kind, key, *args):
        """Les actions qui reconstruisent la scène sont différées pour ne pas
        détruire un élément pendant le traitement de son propre évènement."""
        QTimer.singleShot(0, lambda: self.window.handle_request(action, kind, key, *args))

    # ------------------------------------------------------------ géométrie -> modèle
    def commit_layout(self, text):
        m = self.model
        before = m.toVariant()
        changed = False
        comments = {(c.node.kind, c.node.key): c for c in self.comments}

        def apply(comp, node):
            nonlocal changed
            if comp.position() != node.pos() or comp.size() != node.size():
                comp.setPosition(node.pos())
                comp.setSize(node.size())
                changed = True
            c = comments.get((node.kind, node.key))
            if c is not None:
                com = comp.comment()
                if com.position() != c.pos() or com.size() != c.size():
                    com.setPosition(c.pos())
                    com.setSize(c.size())
                    changed = True

        for name, node in self.inputs.items():
            comp = m.parameterComponent(name)
            apply(comp, node)
            m.setParameterComponent(comp)
        for cid, node in self.children.items():
            child = m.childAlgorithm(cid)
            apply(child, node)
            m.setChildAlgorithm(child)
        for (cid, oname), node in self.outputs.items():
            child = m.childAlgorithm(cid)
            if oname not in child.modelOutputs():
                continue
            apply(child.modelOutput(oname), node)  # référence dans `child`, qui reste vivant
            m.setChildAlgorithm(child)
        boxes = {b.uuid(): b for b in m.groupBoxes()}
        for g in self.groups:
            box = boxes.get(g.uuid)
            if box is not None and (box.position() != g.pos() or box.size() != g.size()):
                box.setPosition(g.pos())
                box.setSize(QSizeF(g.size()))
                m.addGroupBox(box)
                changed = True
        if changed:
            self.window.push_snapshot(text, before)

    # ------------------------------------------------------------ connexions à la souris
    def _node_at(self, pos):
        for it in self.items(pos):
            if isinstance(it, NodeItem):
                return it
        return None

    def _socket_at(self, pos):
        for it in self.items(QRectF(pos - QPointF(12, 12), QSizeF(24, 24))):
            if isinstance(it, NodeItem):
                hit = it.socket_at(pos)
                if hit:
                    return it, hit
        return None, None

    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            node, hit = self._socket_at(ev.scenePos())
            if node is not None:
                self._begin_link(node, hit[0], hit[1], ev.scenePos())
                ev.accept()
                return
        super().mousePressEvent(ev)

    def _begin_link(self, node, side, name, pos):
        m = self.model
        cache = {}
        drag = {"cache": cache, "detach": None}
        if side == "out":
            drag["mode"] = "forward"
            drag["key"] = node.source_key_for_output(name)
            drag["anchor"] = (node, name)
        else:
            srcs = m.childAlgorithm(node.key).parameterSources().get(name, [])
            keys = [k for k in (mu.source_key(s) for s in srcs) if k]
            if keys:
                key = keys[-1]
                src, sname = self._source_socket(key)
                drag.update(mode="forward", key=key, anchor=(src, sname),
                            detach=(node.key, name, key))
                if src is None:
                    return
            else:
                drag.update(mode="reverse", target=(node.key, name), anchor=(node, name))

        # points d'accroche compatibles mis en évidence
        targets = set()
        if drag["mode"] == "forward":
            for cid, cnode in self.children.items():
                alg = m.childAlgorithm(cid).algorithm()
                if alg is None:
                    continue
                for row in cnode.rows:
                    if row.side != "in":
                        continue
                    p = alg.parameterDefinition(row.name)
                    if p is not None and mu.is_compatible(m, cid, p, drag["key"], cache):
                        targets.add(("in", "child", cid, row.name))
        else:
            cid, pname = drag["target"]
            p = m.childAlgorithm(cid).algorithm().parameterDefinition(pname)
            for n in list(self.inputs.values()) + list(self.children.values()):
                for row in n.rows:
                    if row.side == "out" and mu.is_compatible(
                            m, cid, p, n.source_key_for_output(row.name), cache):
                        targets.add(("out", n.kind, n.key, row.name))
        self.drag_targets = targets
        temp = QGraphicsPathItem()
        pen = QPen(QColor(ACCENT), 2, Qt.PenStyle.DashLine)
        temp.setPen(pen)
        temp.setZValue(100)
        self.addItem(temp)
        drag["temp"] = temp
        self._drag = drag
        self._update_drag(pos)
        for n in list(self.inputs.values()) + list(self.children.values()):
            n.update()

    def _update_drag(self, pos):
        d = self._drag
        node, name = d["anchor"]
        side = "out" if d["mode"] == "forward" else "in"
        a = node.socket_pos(side, name)
        tnode, hit = self._socket_at(pos)
        b = pos
        if tnode is not None and (hit[0], tnode.kind, tnode.key, hit[1]) in self.drag_targets:
            b = tnode.socket_pos(hit[0], hit[1])
        if side == "in":
            a, b = b, a
        dx = max(50.0, abs(b.x() - a.x()) * 0.5)
        path = QPainterPath(a)
        path.cubicTo(a + QPointF(dx, 0), b - QPointF(dx, 0), b)
        d["temp"].setPath(path)

    def mouseMoveEvent(self, ev):
        if self._drag:
            self._update_drag(ev.scenePos())
            ev.accept()
            return
        super().mouseMoveEvent(ev)

    def mouseReleaseEvent(self, ev):
        if not self._drag:
            super().mouseReleaseEvent(ev)
            return
        d, self._drag = self._drag, None
        self.removeItem(d["temp"])
        targets, self.drag_targets = self.drag_targets, set()
        for n in list(self.inputs.values()) + list(self.children.values()):
            n.update()
        tnode, hit = self._socket_at(ev.scenePos())
        valid = tnode is not None and (hit[0], tnode.kind, tnode.key, hit[1]) in targets
        ev.accept()
        if d["mode"] == "forward":
            if valid:
                if d["detach"] and d["detach"][:2] == (tnode.key, hit[1]):
                    return
                QTimer.singleShot(0, lambda: self.window.connect_link(
                    d["key"], tnode.key, hit[1], d["detach"]))
            elif d["detach"]:
                QTimer.singleShot(0, lambda: self.window.disconnect_link(*d["detach"]))
        elif valid:
            key = tnode.source_key_for_output(hit[1])
            QTimer.singleShot(0, lambda: self.window.connect_link(key, *d["target"], None))

    # ------------------------------------------------------------ menu du canevas
    def contextMenuEvent(self, ev):
        super().contextMenuEvent(ev)
        if not ev.isAccepted():
            self.window.canvas_context_menu(ev.scenePos(), ev.screenPos())

    # ------------------------------------------------------------ fond
    def palette(self):
        """Palette courante (l'export image reste toujours clair)."""
        return DARK if self.dark and not self.exporting else LIGHT

    def set_dark(self, on):
        self.dark = bool(on)
        QSettings().setValue("modeler_evo/dark", self.dark)
        self.update()
        for v in self.views():
            v.viewport().update()

    def drawBackground(self, painter, rect):
        painter.fillRect(rect, QColor("#ffffff" if self.exporting else self.palette()["bg"]))
        if self.exporting:
            return
        views = self.views()
        scale = views[0].transform().m11() if views else 1.0
        if scale < 0.35:
            return
        step = GRID * (2 if scale < 0.7 else 1)
        left = int(rect.left()) - (int(rect.left()) % step)
        top = int(rect.top()) - (int(rect.top()) % step)
        pen = QPen(QColor(self.palette()["dots"]), 2.2 / scale)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        pts = []
        x = left
        while x < rect.right():
            y = top
            while y < rect.bottom():
                pts.append(QPointF(x, y))
                y += step
            x += step
        painter.drawPoints(pts)


ALG_MIME = "application/x-vnd.qgis.qgis.algorithmid"
PARAM_MIME = "application/x-vnd.qgis.qgis.parametertypeid"


class ModelView(QGraphicsView):
    def __init__(self, scene, window):
        super().__init__(scene)
        self.window = window
        from qgis.PyQt.QtGui import QPainter
        self.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing
                            | QPainter.RenderHint.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
        self.setAcceptDrops(True)
        self.setFrameShape(QGraphicsView.Shape.NoFrame)
        self._pan = None

    # zoom
    def zoom_by(self, factor):
        current = self.transform().m11()
        factor = max(0.1 / current, min(4.0 / current, factor))
        self.scale(factor, factor)

    def zoom_actual(self):
        self.resetTransform()

    def zoom_full(self):
        rect = self.scene().itemsBoundingRect()
        if rect.isEmpty():
            return
        self.fitInView(rect.adjusted(-40, -40, 40, 40), Qt.AspectRatioMode.KeepAspectRatio)
        if self.transform().m11() > 1.5:
            self.resetTransform()
            self.centerOn(rect.center())

    def wheelEvent(self, ev):
        delta = ev.angleDelta().y()
        if delta:
            self.zoom_by(1.0015 ** delta)
        ev.accept()

    # déplacement (clic molette ou espace + clic)
    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.MiddleButton:
            self._pan = ev.position() if hasattr(ev, "position") else QPointF(ev.pos())
            self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)
            ev.accept()
            return
        super().mousePressEvent(ev)

    def mouseMoveEvent(self, ev):
        if self._pan is not None:
            pos = ev.position() if hasattr(ev, "position") else QPointF(ev.pos())
            d = pos - self._pan
            self._pan = pos
            self.horizontalScrollBar().setValue(int(self.horizontalScrollBar().value() - d.x()))
            self.verticalScrollBar().setValue(int(self.verticalScrollBar().value() - d.y()))
            ev.accept()
            return
        super().mouseMoveEvent(ev)

    def mouseReleaseEvent(self, ev):
        if self._pan is not None and ev.button() == Qt.MouseButton.MiddleButton:
            self._pan = None
            self.viewport().unsetCursor()
            ev.accept()
            return
        super().mouseReleaseEvent(ev)

    # glisser-déposer depuis les panneaux
    @staticmethod
    def _accepts(mime):
        return mime.hasFormat(ALG_MIME) or mime.hasFormat(PARAM_MIME)

    @staticmethod
    def _decode_id(data):
        """Identifiant dans le MIME : QDataStream (arbre natif QGIS) ou UTF-8 brut (arbre de repli)."""
        from qgis.PyQt.QtCore import QByteArray, QDataStream, QIODevice
        raw = QByteArray(data)
        stream = QDataStream(raw, QIODevice.OpenModeFlag.ReadOnly)
        try:
            text = stream.readQString()
            if text and stream.atEnd() and stream.status() == QDataStream.Status.Ok:
                return text
        except Exception:  # noqa: BLE001
            pass
        return bytes(raw).decode("utf-8")

    def dragEnterEvent(self, ev):
        if self._accepts(ev.mimeData()):
            ev.acceptProposedAction()
        else:
            super().dragEnterEvent(ev)

    def dragMoveEvent(self, ev):
        if self._accepts(ev.mimeData()):
            ev.acceptProposedAction()
        else:
            super().dragMoveEvent(ev)

    def dropEvent(self, ev):
        mime = ev.mimeData()
        if not self._accepts(mime):
            super().dropEvent(ev)
            return
        pos = ev.position().toPoint() if hasattr(ev, "position") else ev.pos()
        scene_pos = self.mapToScene(pos)
        ev.acceptProposedAction()
        if mime.hasFormat(ALG_MIME):
            alg_id = self._decode_id(mime.data(ALG_MIME))
            QTimer.singleShot(0, lambda: self.window.add_algorithm(alg_id, scene_pos))
        else:
            type_id = self._decode_id(mime.data(PARAM_MIME))
            QTimer.singleShot(0, lambda: self.window.add_input(type_id, scene_pos))
