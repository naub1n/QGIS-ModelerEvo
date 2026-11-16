"""Modeler icons and colors."""

import math
import os

from qgis.core import QgsApplication
from qgis.PyQt.QtCore import QPointF, QRectF, Qt
from qgis.PyQt.QtGui import (
    QBrush,
    QColor,
    QFont,
    QIcon,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPolygonF,
    QTextOption,
)

from ..core.model_utils import category
from ..i18n import tr

PLUGIN_ICON = os.path.join(os.path.dirname(os.path.dirname(__file__)), "icons", "icon.svg")

NODE_COLORS = {
    "input": "#2e9e5b",      # green
    "algorithm": "#2f6fde",  # blue
    "model": "#7b4fd6",      # purple
    "output": "#f08c00",     # orange
    "missing": "#d64545",
    "inactive": "#9aa3ad",
}

# Connection point colors (same color code as the original modeler)
CATEGORY_COLORS = {
    "boolean": "#43a047",   # green
    "enum": "#8e44ad",      # purple
    "numeric": "#1e88e5",   # blue
    "text": "#5c6bc0",      # slate blue
    "vector": "#a1944f",    # khaki
    "raster": "#16a99a",    # turquoise
    "file": "#4b4f56",      # dark grey
    "other": "#9aa0a6",     # medium grey
}

ACCENT = "#ff8f00"

# QGIS theme icon for each input type (fallback: drawn badge)
_THEME_ICONS = {
    "vector": "/mIconVector.svg",
    "source": "/mIconPolygonLayer.svg",
    "raster": "/mIconRaster.svg",
    "mesh": "/mIconMeshLayer.svg",
    "pointcloud": "/mIconPointCloudLayer.svg",
    "vectortile": "/mIconVectorTileLayer.svg",
    "maplayer": "/mIconLayerTree.svg",
    "number": "/mIconFieldFloat.svg",
    "distance": "/mActionMeasure.svg",
    "area": "/mActionMeasureArea.svg",
    "duration": "/mIconFieldTime.svg",
    "boolean": "/mIconFieldBool.svg",
    "string": "/mIconFieldText.svg",
    "datetime": "/mIconFieldDateTime.svg",
    "crs": "/mIconProjectionEnabled.svg",
    "point": "/mActionCapturePoint.svg",
    "geometry": "/mActionAddPolygon.svg",
    "file": "/mIconFile.svg",
    "folder": "/mIconFolder.svg",
    "field": "/mSourceFields.svg",
    "expression": "/mIconExpression.svg",
    "layout": "/mIconLayout.svg",
    "layoutitem": "/mLayoutItem.svg",
    "maptheme": "/mActionShowAllLayers.svg",
    "providerconnection": "/mIconConnect.svg",
    "databaseschema": "/mIconDbSchema.svg",
    "databasetable": "/mIconTableLayer.svg",
    "authconfig": "/locked.svg",
    "annotation": "/mIconAnnotationLayer.svg",
    "coordinateoperation": "/mActionReprojectLayer.svg",
}

# QGIS theme icon for each output type (fallback: drawn badge)
_OUTPUT_ICONS = {
    "outputVector": "/mIconVector.svg",
    "outputRaster": "/mIconRaster.svg",
    "outputLayer": "/mIconLayerTree.svg",
    "outputMultilayer": "/mActionShowAllLayers.svg",
    "outputPointCloud": "/mIconPointCloudLayer.svg",
    "outputVectorTile": "/mIconVectorTileLayer.svg",
    "outputMesh": "/mIconMeshLayer.svg",
    "outputFile": "/mIconFile.svg",
    "outputFolder": "/mIconFolder.svg",
    "outputHtml": "/mActionHelpContents.svg",
    "outputString": "/mIconFieldText.svg",
    "outputNumber": "/mIconFieldFloat.svg",
    "outputBoolean": "/mIconFieldBool.svg",
    "outputConditionalBranch": "/mActionFilter2.svg",
}

_OUTPUT_ABBREVIATIONS = {
    "outputVariant": "{}", "outputHtml": "</>", "outputConditionalBranch": "?",
    "outputMultilayer": "ML", "outputPointCloud": "PC", "outputVectorTile": "VT",
}

_ABBREVIATIONS = {
    "multilayer": "ML", "enum": "≡", "extent": "▭", "matrix": "▦", "scale": "1:", "range": "↔",
    "band": "B", "color": "◐", "volume": "m³", "aggregates": "Σ", "fieldmapping": "⇄",
    "dxflayers": "DXF", "tininputlayers": "TIN", "meshdatasetgroups": "MG",
    "meshdatasettime": "MT", "pointcloudattribute": "PA", "alignrasterlayers": "AR",
    "multibandraster": "MB",
}

_cache = {}


def _transparent_pixmap(size):
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    return pm


def gear_path(cx, cy, r_out, teeth=8):
    """Path of a gear wheel."""
    r_in = r_out * 0.76
    n = teeth * 4
    pts = []
    for i in range(n):
        a = 2 * math.pi * (i - 0.5) / n - math.pi / 2
        r = r_out if (i % 4) in (0, 1) else r_in
        pts.append(QPointF(cx + r * math.cos(a), cy + r * math.sin(a)))
    path = QPainterPath()
    path.addPolygon(QPolygonF(pts))
    path.closeSubpath()
    hole = r_out * 0.36
    path.addEllipse(QPointF(cx, cy), hole, hole)
    path.setFillRule(Qt.FillRule.OddEvenFill)
    return path


def gear_icon(color="#ffffff", size=64):
    key = ("gear", color, size)
    if key not in _cache:
        pm = _transparent_pixmap(size)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor(color)))
        p.drawPath(gear_path(size / 2, size / 2, size * 0.46))
        p.end()
        _cache[key] = QIcon(pm)
    return _cache[key]


def badge_icon(text, color, size=64):
    key = ("badge", text, color, size)
    if key not in _cache:
        pm = _transparent_pixmap(size)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor(color)))
        p.drawRoundedRect(QRectF(2, 2, size - 4, size - 4), size * 0.22, size * 0.22)
        font = QFont()
        font.setBold(True)
        font.setPixelSize(int(size * (0.5 if len(text) <= 2 else 0.36)))
        p.setFont(font)
        p.setPen(QPen(QColor("#ffffff")))
        p.drawText(QRectF(0, 0, size, size), text, QTextOption(Qt.AlignmentFlag.AlignCenter))
        p.end()
        _cache[key] = QIcon(pm)
    return _cache[key]


def _theme_icon(name):
    if not name:
        return None
    icon = QgsApplication.getThemeIcon(name)
    if icon.isNull() or icon.pixmap(16, 16).isNull():
        return None
    return icon


def input_type_icon(type_id):
    """Icon specific to each input type."""
    key = ("input", type_id)
    if key not in _cache:
        icon = _theme_icon(_THEME_ICONS.get(type_id))
        if icon is None:
            abbr = _ABBREVIATIONS.get(type_id) or (type_id[:2].upper() if type_id else "?")
            icon = badge_icon(abbr, CATEGORY_COLORS[category(type_id)])
        _cache[key] = icon
    return _cache[key]


def model_icon():
    key = ("model",)
    if key not in _cache:
        _cache[key] = _theme_icon("/processingModel.svg") or badge_icon("M", NODE_COLORS["model"])
    return _cache[key]


def output_type_icon(type_id):
    """Icon representing the type of an output (layer, file, number, text…)."""
    key = ("output-type", type_id)
    if key not in _cache:
        icon = _theme_icon(_OUTPUT_ICONS.get(type_id))
        if icon is None:
            abbr = _OUTPUT_ABBREVIATIONS.get(type_id) or \
                (type_id[len("output"):][:2].upper() if type_id else "?")
            icon = badge_icon(abbr or "?", NODE_COLORS["output"])
        _cache[key] = icon
    return _cache[key]


def output_icon():
    key = ("output",)
    if key not in _cache:
        _cache[key] = _theme_icon("/mActionFileSave.svg") or badge_icon("⬈", NODE_COLORS["output"])
    return _cache[key]


def theme_icon(name):
    return _theme_icon(name) or QIcon()


def plugin_icon():
    return QIcon(PLUGIN_ICON)


# Features specific to ModelerEvo, not compatible with the original modeler:
# always flagged with the "Evo" badge (EVO_COLOR) and this text.
EVO_COLOR = "#7e57c2"
EVO_TEXT = tr("ModelerEvo feature, not compatible with the original modeler")
