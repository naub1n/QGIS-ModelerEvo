"""Canvas graphic items: nodes, links, comments, group boxes."""

import html
import math

from qgis.core import QgsProcessingModelAlgorithm
from qgis.PyQt.QtCore import QLineF, QPointF, QRectF, QSizeF, Qt
from qgis.PyQt.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontMetricsF,
    QPainter,
    QPainterPath,
    QPainterPathStroker,
    QPen,
    QPolygonF,
    QTextOption,
)
from qgis.PyQt.QtWidgets import QGraphicsItem, QGraphicsLineItem, QGraphicsPathItem

from ..core import model_utils as mu
from ..i18n import tr
from .icons import ACCENT, CATEGORY_COLORS, NODE_COLORS, EVO_COLOR, EVO_TEXT, gear_icon, input_type_icon, model_icon, output_icon, output_type_icon

GRID = 20
ROW_H = 22
HEADER_H = 50
SOCKET_R = 5.5
SOCKET_HIT = 10
GRIP = 14
MIN_W = 190
DEFAULT_W = 250
RADIUS = 10

_F = QGraphicsItem.GraphicsItemFlag
_C = QGraphicsItem.GraphicsItemChange
_AL = Qt.AlignmentFlag


def _font(px, bold=False, italic=False):
    f = QFont()
    f.setPixelSize(px)
    f.setBold(bold)
    f.setItalic(italic)
    return f


def _draw_text(p, rect, text, align, font, color, elide=True):
    p.setFont(font)
    p.setPen(QPen(QColor(color)))
    if elide:
        text = QFontMetricsF(font).elidedText(text, Qt.TextElideMode.ElideRight, max(0.0, rect.width()))
    opt = QTextOption(align)
    opt.setWrapMode(QTextOption.WrapMode.NoWrap)
    p.drawText(rect, text, opt)


def draw_evo_badge(p, rect):
    """The "Evo" badge: flags a feature that is not compatible with the original modeler."""
    p.save()
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(EVO_COLOR))
    p.drawRoundedRect(rect, 8, 8)
    _draw_text(p, rect, "Evo", _AL.AlignCenter, _font(10, bold=True), "#ffffff", elide=False)
    p.restore()


def _single_line(text):
    return " ".join(str(text).split())


class Row:
    __slots__ = ("side", "name", "label", "value", "category", "filled", "extra", "advanced")

    def __init__(self, side, name, label, value="", cat="other", filled=True, extra=None,
                 advanced=False):
        self.side = side
        self.name = name
        self.label = label
        self.value = value
        self.category = cat
        self.filled = filled
        self.extra = extra
        self.advanced = advanced


# ==========================================================================
# Node
# ==========================================================================

class NodeItem(QGraphicsItem):
    """Input node (kind='input'), algorithm node (kind='child') or model output
    node (kind='output', key = (algorithm id, output name))."""

    def __init__(self, mscene, kind, key):
        super().__init__()
        self.mscene = mscene
        self.kind = kind
        self.key = key
        self.setFlags(_F.ItemIsMovable | _F.ItemIsSelectable | _F.ItemSendsGeometryChanges)
        self.setAcceptHoverEvents(True)
        self.setZValue(mscene.z_order.get((kind, key), 10))
        self._w = DEFAULT_W
        self._h = 100
        self._resizing = None
        self._press_pos = None
        self._row_rects = []
        self.edges = []
        self.comment_item = None
        self._owner = None
        self.active = True
        self.missing = False
        self.node_type = "input"
        self.rows = []
        self.refresh()

    # ---------------------------------------------------------------- data
    @property
    def model(self):
        return self.mscene.model

    def component(self):
        if self.kind == "input":
            return self.model.parameterComponent(self.key)
        if self.kind == "output":
            # keep the algorithm copy alive: modelOutput() returns a reference
            cid, oname = self.key
            self._owner = self.model.childAlgorithm(cid)
            return self._owner.modelOutput(oname)
        return self.model.childAlgorithm(self.key)

    def source_key_for_output(self, name):
        if self.kind == "output":
            return None
        if self.kind == "input":
            return ("param", self.key)
        return ("child", self.key, name)

    def refresh(self):
        m = self.model
        self.rows = []
        self.evo_only = False
        if self.kind == "input":
            p = m.parameterDefinition(self.key)
            self.node_type = "input"
            self.title = p.description() if p else self.key
            self.subtitle = mu.parameter_type_name(p.type()) if p else ""
            self.icon = input_type_icon(p.type() if p else "")
            optional = p is not None and mu.param_has_flag(p, "Optional")
            value = mu.format_value(p.defaultValue(), p) if p else ""
            if optional:
                value = (value + " · " if value else "") + tr("optional")
            self.rows.append(Row("out", self.key, "@" + self.key, value,
                                 mu.category(p.type()) if p else "other"))
            help_text = mu.param_help(m, self.key) or (p.help() if p and hasattr(p, "help") else "")
            self.tooltip_html = self._tooltip(self.title, self.subtitle, help_text)
        elif self.kind == "output":
            self._refresh_output()
        else:
            child = m.childAlgorithm(self.key)
            alg = child.algorithm()
            self.active = child.isActive()
            self.missing = alg is None
            self.title = child.description() or (alg.displayName() if alg else child.algorithmId())
            if alg is None:
                self.node_type = "missing"
                self.subtitle = tr("Algorithm not found: {0}").format(child.algorithmId())
                self.icon = gear_icon()
                self.tooltip_html = self._tooltip(self.title, self.subtitle, "")
            else:
                is_model = isinstance(alg, QgsProcessingModelAlgorithm)
                self.node_type = "model" if is_model else "algorithm"
                self.subtitle = alg.displayName()
                self.icon = model_icon() if is_model else gear_icon()
                sources = child.parameterSources()
                for p in alg.parameterDefinitions():
                    if p.isDestination() or mu.param_has_flag(p, "Hidden"):
                        continue
                    srcs = sources.get(p.name(), [])
                    if srcs:
                        value = ", ".join(v for v in (mu.describe_source(m, s, p) for s in srcs) if v)
                    else:
                        value = mu.format_value(p.defaultValue(), p)
                    connected = any(mu.source_key(s) for s in srcs)
                    self.rows.append(Row(
                        "in", p.name(), p.description(), _single_line(value), mu.category(p.type()),
                        filled=connected or not mu.is_default(p, srcs),
                        advanced=mu.param_has_flag(p, "Advanced")))
                for o in alg.outputDefinitions():
                    self.rows.append(Row("out", o.name(), o.description(), "",
                                         mu.category(o.type())))
                help_text = mu.child_help(m, self.key) or alg.shortDescription() or ""
                self.tooltip_html = self._tooltip(self.title, self.subtitle, help_text)
        self.setToolTip(self.tooltip_html)

        comp = self.component()
        size = comp.size()
        self._w = size.width() if size.width() >= MIN_W else DEFAULT_W
        self._layout()
        self._h = max(self.min_height(), size.height())
        self._layout()
        pos = comp.position()
        if self.kind == "output" and pos.isNull():
            pos = self._default_output_pos()
        self.setPos(pos)
        self.update()

    def _refresh_output(self):
        """Orange node of a model output (defined in the algorithm properties)."""
        m = self.model
        cid, oname = self.key
        child = m.childAlgorithm(cid)
        mo = child.modelOutputs().get(oname)
        alg = child.algorithm()
        self.node_type = "output"
        self.active = child.isActive()
        self.missing = False
        self.title = (mo.description() if mo else "") or oname
        self.subtitle = tr("Model output")
        self.icon = output_icon()
        self.evo_only = mu.is_extended_output(child, mo)
        source = child.description() or (alg.displayName() if alg else child.algorithmId())
        odef = alg.outputDefinition(mo.childOutputName()) if (alg and mo) else None
        if odef is not None:
            source += " › " + odef.description()
            self.icon = output_type_icon(odef.type())
        self.rows.append(Row("info", "source", tr("Source"), _single_line(source), "other"))
        help_text = mu.output_help(m, cid, oname)
        self.tooltip_html = self._tooltip(self.title, self.subtitle, help_text)
        if self.evo_only:
            self.tooltip_html += f"<hr/><b style='color:{EVO_COLOR}'>Evo</b> — {html.escape(EVO_TEXT)}"
        self.setToolTip(self.tooltip_html)

    def _default_output_pos(self):
        """Default position (output without a saved position): right of the algorithm."""
        cid, oname = self.key
        child = self.model.childAlgorithm(cid)
        idx = list(child.modelOutputs().keys()).index(oname) if oname in child.modelOutputs() else 0
        cw = max(child.size().width(), DEFAULT_W)
        return child.position() + QPointF(cw / 2 + self._w / 2 + 80, idx * 90)

    @staticmethod
    def _tooltip(title, subtitle, help_text):
        body = help_text if help_text else "<i>" + html.escape(tr("No help defined (“Help” tab).")) + "</i>"
        return (f"<b>{html.escape(title)}</b><br/><span style='color:#666'>"
                f"{html.escape(subtitle)}</span><hr/>{body}")

    # ---------------------------------------------------------------- geometry
    def n_inputs(self):
        return sum(1 for r in self.rows if r.side == "in")

    def min_height(self):
        n_in = self.n_inputs()
        n_out = len(self.rows) - n_in
        extra = 8 if (n_in and n_out) else 0
        return HEADER_H + 6 + len(self.rows) * ROW_H + extra + 10

    def _layout(self):
        r = self.rect()
        y = r.top() + HEADER_H + 6
        self._row_rects = []
        n_in = self.n_inputs()
        for i, _row in enumerate(self.rows):
            if i == n_in and n_in:
                y += 8
            self._row_rects.append(QRectF(r.left(), y, r.width(), ROW_H))
            y += ROW_H

    def rect(self):
        return QRectF(-self._w / 2, -self._h / 2, self._w, self._h)

    def size(self):
        return QSizeF(self._w, self._h)

    def boundingRect(self):
        return self.rect().adjusted(-SOCKET_R - 3, -3, SOCKET_R + 3, 6)

    def _socket_local(self, side, name):
        r = self.rect()
        for row, rr in zip(self.rows, self._row_rects):
            if row.side == side and row.name == name:
                return QPointF(r.left() if side == "in" else r.right(), rr.center().y())
        return None

    def socket_pos(self, side, name):
        local = self._socket_local(side, name)
        if local is None:
            return self.header_anchor(side)
        return self.mapToScene(local)

    def header_anchor(self, side):
        r = self.rect()
        return self.mapToScene(QPointF(r.left() if side == "in" else r.right(),
                                       r.top() + HEADER_H / 2))

    def socket_at(self, scene_pos):
        local = self.mapFromScene(scene_pos)
        r = self.rect()
        for row, rr in zip(self.rows, self._row_rects):
            if row.side == "info":
                continue
            x = r.left() if row.side == "in" else r.right()
            if QLineF(local, QPointF(x, rr.center().y())).length() <= SOCKET_HIT:
                return row.side, row.name
        return None

    def row(self, side, name):
        for row in self.rows:
            if row.side == side and row.name == name:
                return row
        return None

    def _in_grip(self, local):
        r = self.rect()
        return local.x() >= r.right() - GRIP and local.y() >= r.bottom() - GRIP

    # ---------------------------------------------------------------- painting
    def paint(self, p, option, widget=None):
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self.rect()
        selected = self.isSelected() and not self.mscene.exporting
        pal = self.mscene.palette()
        status = self.mscene.child_status.get(self.key) if self.kind == "child" else None
        color = QColor(NODE_COLORS["inactive"] if not self.active else NODE_COLORS[self.node_type])
        p.setOpacity(1.0 if self.active else 0.65)

        # shadow
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(*pal["shadow"]))
        p.drawRoundedRect(r.translated(0, 3), RADIUS, RADIUS)

        # body
        body = QPainterPath()
        body.addRoundedRect(r, RADIUS, RADIUS)
        p.fillPath(body, QColor(pal["body"]))

        # header
        head = QPainterPath()
        head.addRect(QRectF(r.left(), r.top(), r.width(), HEADER_H))
        p.fillPath(body.intersected(head), color)
        if status == "outdated":
            p.fillPath(body.intersected(head), QColor(255, 143, 0, 90))

        # icon next to the name
        icon_rect = QRectF(r.left() + 10, r.top() + 11, 28, 28)
        if self.kind == "input":
            p.setBrush(QColor(255, 255, 255, 235))
            p.drawRoundedRect(icon_rect, 7, 7)
            self.icon.paint(p, icon_rect.adjusted(5, 5, -5, -5).toRect())
        elif self.node_type in ("model", "output"):
            p.setBrush(QColor(255, 255, 255, 235))
            p.drawRoundedRect(icon_rect, 7, 7)
            self.icon.paint(p, icon_rect.adjusted(5, 5, -5, -5).toRect())
        else:
            self.icon.paint(p, icon_rect.adjusted(1, 1, -1, -1).toRect())

        # name and subtitle
        right_pad = 34 if status else (52 if self.evo_only else 12)
        text_w = r.width() - 48 - right_pad
        _draw_text(p, QRectF(r.left() + 46, r.top() + 8, text_w, 18), self.title,
                   _AL.AlignLeft | _AL.AlignVCenter, _font(13, bold=True), "#ffffff")
        sub = self.subtitle if self.active else tr("{0} (deactivated)").format(self.subtitle)
        _draw_text(p, QRectF(r.left() + 46, r.top() + 27, text_w, 15), sub,
                   _AL.AlignLeft | _AL.AlignVCenter, _font(11), QColor(255, 255, 255, 215))

        if self.evo_only:
            draw_evo_badge(p, QRectF(r.right() - 46, r.top() + 8, 36, 16))

        if status in ("ok", "outdated"):
            c = QPointF(r.right() - 18, r.top() + HEADER_H / 2)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor("#ffffff"))
            p.drawEllipse(c, 9, 9)
            pen = QPen(QColor("#2e9e5b" if status == "ok" else ACCENT), 2.2)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            p.drawPolyline(QPolygonF([c + QPointF(-4, 0), c + QPointF(-1, 3.5), c + QPointF(4.5, -3.5)]))

        # connection point of an output node (fed by the arrow from the algorithm)
        if self.kind == "output":
            p.setPen(QPen(color.darker(120), 2))
            p.setBrush(QColor(pal["socket_empty"]))
            p.drawEllipse(QPointF(r.left(), r.top() + HEADER_H / 2), SOCKET_R, SOCKET_R)

        # input / output rows
        n_in = self.n_inputs()
        if n_in and n_in < len(self.rows):
            y = self._row_rects[n_in].top() - 4
            p.setPen(QPen(QColor(pal["sep"]), 1))
            p.drawLine(QPointF(r.left() + 10, y), QPointF(r.right() - 10, y))

        targets = self.mscene.drag_targets
        for row, rr in zip(self.rows, self._row_rects):
            self._paint_row(p, row, rr, r, targets, pal)

        # outline
        p.setBrush(Qt.BrushStyle.NoBrush)
        if selected:
            p.setPen(QPen(QColor("#8a4b00" if self.kind == "output" else ACCENT), 2.2))
        else:
            p.setPen(QPen(QColor(pal["outline"]), 1))
        p.drawRoundedRect(r, RADIUS, RADIUS)

        # resize handle
        if not self.mscene.exporting:
            p.setPen(QPen(QColor(pal["grip"]), 1.2))
            for k in (4, 8, 12):
                p.drawLine(QPointF(r.right() - k, r.bottom() - 3), QPointF(r.right() - 3, r.bottom() - k))

    def _paint_row(self, p, row, rr, r, targets, pal):
        cy = rr.center().y()
        cat_color = QColor(CATEGORY_COLORS.get(row.category, CATEGORY_COLORS["other"]))
        node_key = self.key
        highlighted = (row.side, self.kind, node_key, row.name) in targets
        label_color = pal["advanced"] if row.advanced else pal["label"]
        if row.side == "info":
            _draw_text(p, QRectF(r.left() + 14, rr.top(), 52, ROW_H), row.label,
                       _AL.AlignLeft | _AL.AlignVCenter, _font(12), label_color)
            _draw_text(p, QRectF(r.left() + 68, rr.top(), r.width() - 82, ROW_H), row.value,
                       _AL.AlignRight | _AL.AlignVCenter, _font(11), pal["value"])
            return
        if row.side == "in":
            x = r.left()
            label_w = (r.width() - 24) * 0.48
            _draw_text(p, QRectF(x + 14, rr.top(), label_w, ROW_H), row.label,
                       _AL.AlignLeft | _AL.AlignVCenter, _font(12, italic=row.advanced), label_color)
            _draw_text(p, QRectF(x + 18 + label_w, rr.top(), r.width() - label_w - 30, ROW_H),
                       row.value, _AL.AlignRight | _AL.AlignVCenter, _font(11), pal["value"])
        else:
            x = r.right()
            if row.extra:
                fm = QFontMetricsF(_font(11, bold=True))
                text = "⬈ " + row.extra
                w = min(fm.horizontalAdvance(text) + 12, r.width() * 0.5)
                pill = QRectF(r.left() + 10, rr.top() + 3, w, ROW_H - 6)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(255, 143, 0, 40))
                p.drawRoundedRect(pill, 8, 8)
                _draw_text(p, pill.adjusted(6, 0, -4, 0), text, _AL.AlignLeft | _AL.AlignVCenter,
                           _font(11, bold=True), "#b85f00")
                left = pill.right() + 6
            else:
                left = r.left() + 12
                if row.value:
                    _draw_text(p, QRectF(left, rr.top(), r.width() * 0.5 - 12, ROW_H), row.value,
                               _AL.AlignLeft | _AL.AlignVCenter, _font(11), pal["value"])
                    left = r.left() + r.width() * 0.5
            _draw_text(p, QRectF(left, rr.top(), x - 14 - left, ROW_H), row.label,
                       _AL.AlignRight | _AL.AlignVCenter, _font(12), label_color)

        radius = SOCKET_R + (2 if highlighted else 0)
        if highlighted:
            p.setPen(Qt.PenStyle.NoPen)
            glow = QColor(cat_color)
            glow.setAlpha(70)
            p.setBrush(glow)
            p.drawEllipse(QPointF(x, cy), radius + 4, radius + 4)
        p.setPen(QPen(cat_color, 2))
        p.setBrush(QBrush(cat_color if row.filled else QColor(pal["socket_empty"])))
        p.drawEllipse(QPointF(x, cy), radius, radius)

    # ---------------------------------------------------------------- interactions
    def itemChange(self, change, value):
        if change == _C.ItemPositionChange and self.mscene.snapping and not self._resizing \
                and not self.mscene.group_moving:
            tl = value - QPointF(self._w / 2, self._h / 2)
            tl = QPointF(round(tl.x() / GRID) * GRID, round(tl.y() / GRID) * GRID)
            return tl + QPointF(self._w / 2, self._h / 2)
        if change == _C.ItemPositionHasChanged:
            self.mscene.update_node_links(self)
        return super().itemChange(change, value)

    def hoverMoveEvent(self, ev):
        if self._in_grip(ev.pos()):
            self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        elif self.socket_at(ev.scenePos()):
            self.setCursor(Qt.CursorShape.CrossCursor)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)
        super().hoverMoveEvent(ev)

    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton and self._in_grip(ev.pos()):
            self._resizing = (self.mapToScene(self.rect().topLeft()), self.size(), ev.scenePos())
            ev.accept()
            return
        self._press_pos = QPointF(self.pos())
        self.mscene.bring_to_front(self)
        super().mousePressEvent(ev)

    def mouseMoveEvent(self, ev):
        if self._resizing:
            tl, size, start = self._resizing
            d = ev.scenePos() - start
            w = max(MIN_W, size.width() + d.x())
            h = max(self.min_height(), size.height() + d.y())
            if self.mscene.snapping:
                w = max(MIN_W, round((tl.x() + w) / GRID) * GRID - tl.x())
                h = max(self.min_height(), round((tl.y() + h) / GRID) * GRID - tl.y())
            self.prepareGeometryChange()
            self._w, self._h = w, h
            self._layout()
            self.setPos(tl + QPointF(w / 2, h / 2))
            self.mscene.update_node_links(self)
            return
        super().mouseMoveEvent(ev)

    def mouseReleaseEvent(self, ev):
        if self._resizing:
            self._resizing = None
            self.mscene.commit_layout(tr("Resize"))
            return
        super().mouseReleaseEvent(ev)
        if self._press_pos is not None and self.pos() != self._press_pos:
            self.mscene.commit_layout(tr("Move"))
        self._press_pos = None

    def mouseDoubleClickEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            self.mscene.request("edit", self.kind, self.key)
            ev.accept()

    def contextMenuEvent(self, ev):
        if not self.isSelected():
            self.mscene.clearSelection()
            self.setSelected(True)
        self.mscene.request("menu", self.kind, self.key, ev.screenPos())
        ev.accept()


# ==========================================================================
# Links
# ==========================================================================

class EdgeItem(QGraphicsPathItem):
    """Arrow between two parameters.

    style: 'direct' (solid line), 'expression' (dashed: parameter used in an
    expression), 'dependency' (explicit dependency), 'parent' (parameter that
    depends on another parameter).
    """

    def __init__(self, src, src_name, dst, dst_name, style, color, tooltip=""):
        super().__init__()
        self.src, self.src_name, self.dst, self.dst_name = src, src_name, dst, dst_name
        self.style = style
        self.color = QColor(color)
        self._hover = False
        self._arrow = QPolygonF()
        self.setZValue(5)
        self.setAcceptHoverEvents(True)
        if tooltip:
            self.setToolTip(tooltip)
        src.edges.append(self)
        dst.edges.append(self)
        self.update_path()

    def update_path(self):
        p1 = self.src.socket_pos("out", self.src_name) if self.src_name else self.src.header_anchor("out")
        p2 = self.dst.socket_pos("in", self.dst_name) if self.dst_name else self.dst.header_anchor("in")
        end = p2 - QPointF(SOCKET_R + 1, 0)
        dx = max(50.0, abs(end.x() - p1.x()) * 0.5)
        path = QPainterPath(p1)
        path.cubicTo(p1 + QPointF(dx, 0), end - QPointF(dx, 0), end)
        self.prepareGeometryChange()
        self.setPath(path)
        back = path.pointAtPercent(0.96)
        ang = math.atan2(end.y() - back.y(), end.x() - back.x())
        size = 9
        self._arrow = QPolygonF([
            end,
            end - QPointF(size * math.cos(ang - 0.42), size * math.sin(ang - 0.42)),
            end - QPointF(size * math.cos(ang + 0.42), size * math.sin(ang + 0.42)),
        ])

    def boundingRect(self):
        return super().boundingRect().adjusted(-10, -10, 10, 10)

    def shape(self):
        stroker = QPainterPathStroker()
        stroker.setWidth(10)
        return stroker.createStroke(self.path())

    def paint(self, p, option, widget=None):
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = QColor(self.color)
        inactive = (self.src.kind == "child" and not self.src.active) or \
                   (self.dst.kind == "child" and not self.dst.active)
        if inactive:
            color.setAlpha(110)
        width = 2.0 if self.style in ("direct", "expression", "parent") else 1.4
        if self._hover:
            width += 1.2
        pen = QPen(color, width)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        if self.style == "expression":
            pen.setStyle(Qt.PenStyle.DashLine)
        elif self.style in ("dependency", "parent"):
            pen.setStyle(Qt.PenStyle.DotLine)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(self.path())
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(color)
        p.drawPolygon(self._arrow)

    def hoverEnterEvent(self, ev):
        self._hover = True
        self.update()

    def hoverLeaveEvent(self, ev):
        self._hover = False
        self.update()


# ==========================================================================
# Comments
# ==========================================================================

class CommentItem(QGraphicsItem):
    DEFAULT_COLOR = "#fff4b8"

    def __init__(self, mscene, node):
        super().__init__()
        self.mscene = mscene
        self.node = node
        node.comment_item = self
        comment = node.component().comment()
        self.text = comment.description()
        col = comment.color() if hasattr(comment, "color") else QColor()
        self.color = QColor(col) if col is not None and QColor(col).isValid() else QColor(self.DEFAULT_COLOR)
        size = comment.size()
        self._w = max(150.0, size.width())
        fm = QFontMetricsF(_font(12))
        needed = fm.boundingRect(QRectF(0, 0, self._w - 20, 10000),
                                 int(Qt.TextFlag.TextWordWrap.value) if hasattr(Qt.TextFlag.TextWordWrap, "value")
                                 else int(Qt.TextFlag.TextWordWrap), self.text).height() + 20
        self._h = max(44.0, size.height(), needed)
        pos = comment.position()
        if pos.isNull():
            pos = node.pos() + QPointF(node.size().width() * 0.5 + self._w * 0.5 + 40,
                                       -node.size().height() * 0.5 - 30)
        self.setFlags(_F.ItemIsMovable | _F.ItemIsSelectable | _F.ItemSendsGeometryChanges)
        self.setZValue(8)
        self.setToolTip(html.escape(self.text))
        self.link = QGraphicsLineItem()
        pen = QPen(QColor("#9aa3ad"), 1.2, Qt.PenStyle.DashLine)
        self.link.setPen(pen)
        self.link.setZValue(4)
        mscene.addItem(self.link)
        self.setPos(pos)
        self._press_pos = None
        self.update_link()

    def rect(self):
        return QRectF(-self._w / 2, -self._h / 2, self._w, self._h)

    def size(self):
        return QSizeF(self._w, self._h)

    def boundingRect(self):
        return self.rect().adjusted(-2, -2, 2, 5)

    def update_link(self):
        a = self.mapToScene(self.rect().center())
        nr = self.node.mapRectToScene(self.node.rect())
        b = QPointF(min(max(a.x(), nr.left()), nr.right()), min(max(a.y(), nr.top()), nr.bottom()))
        ar = self.mapRectToScene(self.rect())
        a2 = QPointF(min(max(b.x(), ar.left()), ar.right()), min(max(b.y(), ar.top()), ar.bottom()))
        self.link.setLine(QLineF(a2, b))

    def setVisible(self, visible):  # noqa: N802
        super().setVisible(visible)
        self.link.setVisible(visible)

    def paint(self, p, option, widget=None):
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self.rect()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(15, 23, 42, 25))
        p.drawRoundedRect(r.translated(0, 3), 6, 6)
        p.setBrush(self.color)
        sel = self.isSelected() and not self.mscene.exporting
        p.setPen(QPen(QColor(ACCENT), 2) if sel else QPen(self.color.darker(115), 1))
        p.drawRoundedRect(r, 6, 6)
        p.setFont(_font(12))
        p.setPen(QPen(QColor("#3d3a2a")))
        opt = QTextOption(_AL.AlignLeft | _AL.AlignTop)
        opt.setWrapMode(QTextOption.WrapMode.WordWrap)
        p.drawText(r.adjusted(10, 9, -10, -9), self.text, opt)

    def itemChange(self, change, value):
        if change == _C.ItemPositionHasChanged:
            self.update_link()
        return super().itemChange(change, value)

    def mousePressEvent(self, ev):
        self._press_pos = QPointF(self.pos())
        super().mousePressEvent(ev)

    def mouseReleaseEvent(self, ev):
        super().mouseReleaseEvent(ev)
        if self._press_pos is not None and self.pos() != self._press_pos:
            self.mscene.commit_layout(tr("Move comment"))
        self._press_pos = None

    def mouseDoubleClickEvent(self, ev):
        self.mscene.request("edit_comment", self.node.kind, self.node.key)
        ev.accept()

    def contextMenuEvent(self, ev):
        self.mscene.request("comment_menu", self.node.kind, self.node.key, ev.screenPos())
        ev.accept()


# ==========================================================================
# Group boxes
# ==========================================================================

class GroupBoxItem(QGraphicsItem):
    DEFAULT_COLOR = "#8fa3bf"

    def __init__(self, mscene, box):
        super().__init__()
        self.mscene = mscene
        self.uuid = box.uuid()
        self.title = box.description()
        col = box.color() if hasattr(box, "color") else QColor()
        self.color = QColor(col) if col is not None and QColor(col).isValid() else QColor(self.DEFAULT_COLOR)
        size = box.size()
        self._w = max(160.0, size.width())
        self._h = max(100.0, size.height())
        self.setFlags(_F.ItemIsMovable | _F.ItemIsSelectable | _F.ItemSendsGeometryChanges)
        self.setZValue(-10)
        self.setPos(box.position())
        self._resizing = None
        self._press_pos = None
        self._carried = []
        self._last_pos = None
        self.setAcceptHoverEvents(True)

    def rect(self):
        return QRectF(-self._w / 2, -self._h / 2, self._w, self._h)

    def size(self):
        return QSizeF(self._w, self._h)

    def boundingRect(self):
        return self.rect().adjusted(-2, -2, 2, 2)

    def paint(self, p, option, widget=None):
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self.rect()
        fill = QColor(self.color)
        fill.setAlpha(38)
        border = QColor(self.color)
        sel = self.isSelected() and not self.mscene.exporting
        p.setBrush(fill)
        p.setPen(QPen(QColor(ACCENT) if sel else border, 2 if sel else 1.4, Qt.PenStyle.SolidLine))
        p.drawRoundedRect(r, 14, 14)
        _draw_text(p, QRectF(r.left() + 14, r.top() + 8, r.width() - 28, 22), self.title,
                   _AL.AlignLeft | _AL.AlignVCenter, _font(14, bold=True), self.color.darker(150))
        if not self.mscene.exporting:
            p.setPen(QPen(border, 1.2))
            for k in (5, 10, 15):
                p.drawLine(QPointF(r.right() - k, r.bottom() - 4), QPointF(r.right() - 4, r.bottom() - k))

    def _in_grip(self, local):
        r = self.rect()
        return local.x() >= r.right() - GRIP - 4 and local.y() >= r.bottom() - GRIP - 4

    def hoverMoveEvent(self, ev):
        self.setCursor(Qt.CursorShape.SizeFDiagCursor if self._in_grip(ev.pos())
                       else Qt.CursorShape.ArrowCursor)
        super().hoverMoveEvent(ev)

    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton and self._in_grip(ev.pos()):
            self._resizing = (self.mapToScene(self.rect().topLeft()), self.size(), ev.scenePos())
            ev.accept()
            return
        self._press_pos = QPointF(self.pos())
        self._last_pos = QPointF(self.pos())
        area = self.mapRectToScene(self.rect())
        self._carried = [it for it in self.mscene.items(area, Qt.ItemSelectionMode.ContainsItemShape)
                         if isinstance(it, (NodeItem, CommentItem)) and not it.isSelected()]
        self.mscene.group_moving = True
        super().mousePressEvent(ev)

    def mouseMoveEvent(self, ev):
        if self._resizing:
            tl, size, start = self._resizing
            d = ev.scenePos() - start
            w, h = max(160.0, size.width() + d.x()), max(100.0, size.height() + d.y())
            self.prepareGeometryChange()
            self._w, self._h = w, h
            self.setPos(tl + QPointF(w / 2, h / 2))
            return
        super().mouseMoveEvent(ev)

    def itemChange(self, change, value):
        if change == _C.ItemPositionHasChanged and self._last_pos is not None:
            delta = self.pos() - self._last_pos
            self._last_pos = QPointF(self.pos())
            for it in self._carried:
                it.moveBy(delta.x(), delta.y())
        return super().itemChange(change, value)

    def mouseReleaseEvent(self, ev):
        self.mscene.group_moving = False
        if self._resizing:
            self._resizing = None
            self.mscene.commit_layout(tr("Resize group box"))
            return
        super().mouseReleaseEvent(ev)
        moved = self._press_pos is not None and self.pos() != self._press_pos
        self._press_pos = None
        self._last_pos = None
        self._carried = []
        if moved:
            self.mscene.commit_layout(tr("Move group box"))

    def mouseDoubleClickEvent(self, ev):
        self.mscene.request("edit_group", "group", self.uuid)
        ev.accept()

    def contextMenuEvent(self, ev):
        self.mscene.request("group_menu", "group", self.uuid, ev.screenPos())
        ev.accept()
