"""Fonctions utilitaires autour de QgsProcessingModelAlgorithm.

Le plugin n'introduit aucun format propre : tout est stocké dans le modèle
Processing (.model3) afin de rester compatible avec le modeleur d'origine.
"""

import html
import re

from qgis.core import (
    Qgis,
    QgsApplication,
    QgsExpression,
    QgsProcessingFeatureSourceDefinition,
    QgsProcessingModelAlgorithm,
    QgsProcessingModelChildParameterSource,
    QgsProcessingOutputLayerDefinition,
    QgsProcessingParameterDefinition,
    QgsProperty,
)

from ..i18n import tr

# --------------------------------------------------------------------------
# Compatibilité des énumérations (QGIS 3.3x / QGIS 4)
# --------------------------------------------------------------------------

_SRC = getattr(Qgis, "ProcessingModelChildParameterSource", QgsProcessingModelChildParameterSource)
_PFLAG = getattr(Qgis, "ProcessingParameterFlag", None)
_SRC_NAMES = ("ModelParameter", "ChildOutput", "StaticValue", "Expression", "ExpressionText", "ModelOutput")


def source_kind(src):
    """Nom du type de source d'un paramètre d'algorithme enfant."""
    s = src.source()
    for name in _SRC_NAMES:
        value = getattr(_SRC, name, None)
        if value is not None and s == value:
            return name
    return "Unknown"


def param_has_flag(param, name):
    flag = getattr(_PFLAG, name, None) if _PFLAG is not None else None
    if flag is None:
        flag = getattr(QgsProcessingParameterDefinition, "Flag" + name, None)
    if flag is None:
        return False
    try:
        return bool(param.flags() & flag)
    except TypeError:
        return False


def registry():
    return QgsApplication.processingRegistry()


def parameter_type_name(type_id):
    ptype = registry().parameterType(type_id)
    return ptype.name() if ptype else type_id


# --------------------------------------------------------------------------
# Catégories de types (couleur des points d'accroche)
# --------------------------------------------------------------------------

_CATEGORIES = {
    "boolean": ("boolean", "outputBoolean"),
    "enum": ("enum",),
    "numeric": ("number", "distance", "area", "volume", "duration", "scale", "range", "band",
                "matrix", "outputNumber"),
    "text": ("string", "datetime", "crs", "expression", "field", "authconfig", "layout",
             "layoutitem", "maptheme", "providerconnection", "databaseschema", "databasetable",
             "coordinateoperation", "outputString", "outputHtml"),
    "vector": ("vector", "source", "sink", "vectorDestination", "geometry", "extent", "point",
               "mesh", "pointcloud", "vectortile", "pointCloudDestination",
               "vectorTileDestination", "outputVector", "outputPointCloud", "outputVectorTile",
               "annotation", "dxflayers", "tininputlayers", "meshdatasetgroups",
               "meshdatasettime", "pointcloudattribute"),
    "raster": ("raster", "rasterDestination", "outputRaster", "multibandraster"),
    "file": ("file", "folder", "fileDestination", "folderDestination", "outputFile",
             "outputFolder"),
}
_TYPE_TO_CATEGORY = {t: cat for cat, types in _CATEGORIES.items() for t in types}

CATEGORY_LABELS = {
    "boolean": tr("Boolean"),
    "enum": tr("Enumeration"),
    "numeric": tr("Numeric"),
    "text": tr("Text"),
    "vector": tr("Vector / geometry"),
    "raster": tr("Raster"),
    "file": tr("File / folder"),
    "other": tr("Other"),
}


def category(type_id):
    return _TYPE_TO_CATEGORY.get(type_id, "other")


def _categories_compatible(src_cat, src_type, dst_cat, dst_type):
    """Règles de repli si l'API de compatibilité de QGIS n'est pas disponible."""
    if src_type == "outputVariant" or dst_cat == "other":
        return True
    if src_cat == dst_cat:
        return True
    layer_like = {"vector", "raster", "file", "other"}
    if dst_type in ("maplayer", "multilayer"):
        return src_cat in layer_like
    if dst_cat in ("vector", "raster"):
        return src_cat in ("file", "other") or src_type in ("outputLayer", "outputMultilayer")
    if dst_cat == "file":
        return src_cat in ("vector", "raster", "text")
    if dst_cat == "text":
        return src_cat in ("numeric", "file", "enum", "vector", "raster") or dst_type == "crs"
    if dst_cat == "enum":
        return src_cat in ("numeric", "text")
    return False


# --------------------------------------------------------------------------
# Sources de paramètres
# --------------------------------------------------------------------------

def source_key(src):
    """Clé hashable d'une source « connectable » (entrée ou sortie d'algorithme)."""
    kind = source_kind(src)
    if kind == "ModelParameter":
        return ("param", src.parameterName())
    if kind == "ChildOutput":
        return ("child", src.outputChildId(), src.outputName())
    return None


def make_source(key):
    if key[0] == "param":
        return QgsProcessingModelChildParameterSource.fromModelParameter(key[1])
    return QgsProcessingModelChildParameterSource.fromChildOutput(key[1], key[2])


def static_source(value):
    return QgsProcessingModelChildParameterSource.fromStaticValue(value)


def _source_type_for_key(model, key):
    if key[0] == "param":
        p = model.parameterDefinition(key[1])
        return p.type() if p else None
    child = model.childAlgorithms().get(key[1])
    alg = child.algorithm() if child else None
    out = alg.outputDefinition(key[2]) if alg else None
    return out.type() if out else None


def compatible_keys(model, child_id, param):
    """Ensemble des sources connectables à ``param`` de l'enfant ``child_id``.

    Utilise l'API du modeleur d'origine (types acceptés par le type de paramètre
    et détection des dépendances circulaires). Retourne ``None`` si l'API
    n'est pas disponible.
    """
    ptype = registry().parameterType(param.type())
    if ptype is None:
        return None
    try:
        ptypes = ptype.acceptedParameterTypes()
        otypes = ptype.acceptedOutputTypes()
    except AttributeError:
        return None
    try:
        dtypes = ptype.acceptedDataTypes(param)
    except (AttributeError, TypeError):
        dtypes = []
    calls = (
        lambda: model.availableSourcesForChild(child_id, param, ptypes, otypes, dtypes),
        lambda: model.availableSourcesForChild(child_id, ptypes, otypes, dtypes),
    )
    for call in calls:
        try:
            sources = call()
        except TypeError:
            continue
        return {k for k in (source_key(s) for s in sources) if k}
    return None


def is_compatible(model, child_id, param, key, cache=None):
    if cache is not None:
        ck = (child_id, param.name())
        if ck not in cache:
            cache[ck] = compatible_keys(model, child_id, param)
        keys = cache[ck]
    else:
        keys = compatible_keys(model, child_id, param)
    if keys is not None:
        return key in keys
    # Repli heuristique
    if key[0] == "child":
        if key[1] == child_id:
            return False
        try:
            if key[1] in model.dependentChildAlgorithms(child_id):
                return False
        except Exception:  # noqa: BLE001
            pass
    src_type = _source_type_for_key(model, key)
    if src_type is None:
        return False
    return _categories_compatible(category(src_type), src_type, category(param.type()), param.type())


def accepts_multiple(param):
    if param.type() == "multilayer":
        return True
    for attr in ("allowMultiple",):
        fn = getattr(param, attr, None)
        if callable(fn):
            try:
                return bool(fn()) and param.type() not in ("enum", "field")
            except Exception:  # noqa: BLE001
                return False
    return False


# --------------------------------------------------------------------------
# Affichage des valeurs
# --------------------------------------------------------------------------

def format_value(value, param=None):
    if value is None:
        return ""
    if isinstance(value, QgsProperty):
        expr = value.expressionString()
        return ("= " + expr) if expr else format_value(value.staticValue(), param)
    if isinstance(value, QgsProcessingOutputLayerDefinition):
        return format_value(value.sink, param)
    if isinstance(value, QgsProcessingFeatureSourceDefinition):
        return format_value(value.source, param)
    if param is not None and param.type() == "enum":
        options = param.options()
        values = value if isinstance(value, (list, tuple)) else [value]
        labels = []
        for v in values:
            try:
                labels.append(options[int(v)])
            except (ValueError, TypeError, IndexError):
                labels.append(str(v))
        return ", ".join(labels)
    if isinstance(value, bool):
        return tr("Yes") if value else tr("No")
    if isinstance(value, (list, tuple)):
        return ", ".join(format_value(v) for v in value)
    text = str(value)
    if text == "TEMPORARY_OUTPUT":
        return tr("Temporary")
    return text


def describe_source(model, src, param=None):
    kind = source_kind(src)
    if kind == "ModelParameter":
        p = model.parameterDefinition(src.parameterName())
        return p.description() if p else src.parameterName()
    if kind == "ChildOutput":
        child = model.childAlgorithms().get(src.outputChildId())
        if child is None:
            return src.outputName()
        alg = child.algorithm()
        out = alg.outputDefinition(src.outputName()) if alg else None
        out_label = out.description() if out else src.outputName()
        return f"{out_label} ← {child.description()}"
    if kind == "StaticValue":
        return format_value(src.staticValue(), param)
    if kind == "Expression":
        return "= " + src.expression()
    if kind == "ExpressionText":
        return src.expressionText()
    return ""


def is_default(param, sources):
    if not sources:
        return True
    if len(sources) != 1 or source_kind(sources[0]) != "StaticValue":
        return False
    value = sources[0].staticValue()
    default = param.defaultValue()
    if value is None or value == "":
        return default is None or default == ""
    return str(value) == str(default)


# --------------------------------------------------------------------------
# Relations indirectes (paramètres utilisés dans des expressions)
# --------------------------------------------------------------------------

_TEMPLATE = re.compile(r"\[%(.*?)%\]", re.S)


def _expression_variables(text):
    try:
        names = set(QgsExpression(text).referencedVariables())
        if names:
            return names
    except Exception:  # noqa: BLE001
        pass
    return set(re.findall(r"@(\w+)", text or ""))


def safe_name(text, capitalize=False):
    try:
        return QgsProcessingModelAlgorithm.safeName(text, capitalize)
    except TypeError:
        return QgsProcessingModelAlgorithm.safeName(text)


def variable_map(model):
    """Nom de variable d'expression -> clé de source."""
    mapping = {}
    for p in model.parameterDefinitions():
        mapping[p.name().lower()] = ("param", p.name())
    for cid, child in model.childAlgorithms().items():
        alg = child.algorithm()
        if alg is None:
            continue
        bases = {cid, safe_name(child.description()), safe_name(child.description(), True)}
        for out in alg.outputDefinitions():
            for base in bases:
                if base:
                    mapping[f"{base}_{out.name()}".lower()] = ("child", cid, out.name())
                    mapping[f"{base}_{safe_name(out.name())}".lower()] = ("child", cid, out.name())
    return mapping


def _resolve_variable(mapping, name):
    name = name.lower()
    if name in mapping:
        return mapping[name]
    best = None
    for key, ref in mapping.items():
        if name.startswith(key + "_") and (best is None or len(key) > len(best[0])):
            best = (key, ref)
    return best[1] if best else None


def expression_references(model, src, mapping=None):
    kind = source_kind(src)
    names = set()
    if kind == "Expression":
        names = _expression_variables(src.expression())
    elif kind == "ExpressionText":
        for part in _TEMPLATE.findall(src.expressionText()):
            names |= _expression_variables(part)
    elif kind == "StaticValue" and isinstance(src.staticValue(), QgsProperty):
        expr = src.staticValue().expressionString()
        if expr:
            names = _expression_variables(expr)
    if not names:
        return []
    mapping = mapping if mapping is not None else variable_map(model)
    refs = []
    for n in names:
        ref = _resolve_variable(mapping, n)
        if ref and ref not in refs:
            refs.append(ref)
    return refs


def child_dependency_ids(child):
    ids = []
    for dep in child.dependencies():
        if isinstance(dep, str):
            ids.append(dep)
        else:
            ids.append(getattr(dep, "childId", ""))
    return [i for i in ids if i]


# --------------------------------------------------------------------------
# Aide (onglet « Aide » des noeuds)
# --------------------------------------------------------------------------
# - entrées : clé = nom du paramètre (format natif de QGIS : l'aide apparaît
#   dans la fenêtre d'exécution du modèle) ;
# - algorithmes : clé « MODELEREVO_STEP:<id> » ; ces aides sont insérées dans la
#   description du modèle (ALG_DESC) entre deux marqueurs pour être visibles
#   par l'utilisateur du modèle.

STEP_PREFIX = "MODELEREVO_STEP:"
OUTPUT_PREFIX = "MODELEREVO_OUTPUT:"
_MARK_START = "<!-- modeler_evo:steps -->"
_MARK_END = "<!-- /modeler_evo:steps -->"
_MARK_RE = re.compile(re.escape(_MARK_START) + r".*?" + re.escape(_MARK_END), re.S)

HELP_KEYS = (
    ("ALG_DESC", tr("Model description")),
    ("EXAMPLES", tr("Examples")),
    ("ALG_CREATOR", tr("Algorithm author")),
    ("ALG_HELP_CREATOR", tr("Help author")),
    ("ALG_VERSION", tr("Version")),
    ("SHORT_DESCRIPTION", tr("Short description")),
    ("HELP_URL", tr("Help URL")),
)


def _help(model):
    return dict(model.helpContent() or {})


def raw_description(model):
    return _MARK_RE.sub("", str(_help(model).get("ALG_DESC", "") or "")).rstrip()


def help_value(model, key):
    if key == "ALG_DESC":
        return raw_description(model)
    return str(_help(model).get(key, "") or "")


def set_help_value(model, key, text):
    content = _help(model)
    if text:
        content[key] = text
    else:
        content.pop(key, None)
    model.setHelpContent(content)
    sync_help(model)


def param_help(model, name):
    return help_value(model, name)


def set_param_help(model, name, text):
    set_help_value(model, name, text)


def child_help(model, child_id):
    return help_value(model, STEP_PREFIX + child_id)


def set_child_help(model, child_id, text):
    set_help_value(model, STEP_PREFIX + child_id, text)


# --------------------------------------------------------------------------
# Sorties étendues (propres à ModelerEvo, non compatibles avec le modeleur d'origine)
# --------------------------------------------------------------------------

def is_extended_output(child, mo):
    """Sortie de modèle non liée à un paramètre (nombre, texte, HTML…) : QGIS ne l'expose pas."""
    alg = child.algorithm()
    if alg is None or mo is None:
        return False
    name = mo.childOutputName()
    return alg.parameterDefinition(name) is None and alg.outputDefinition(name) is not None


def extended_outputs(model):
    """Sorties étendues actives du modèle : liste de dict (name, child, child_output, description, type)."""
    res = []
    for cid, child in model.childAlgorithms().items():
        alg = child.algorithm()
        if alg is None or not child.isActive():
            continue
        for oname, mo in child.modelOutputs().items():
            if is_extended_output(child, mo):
                odef = alg.outputDefinition(mo.childOutputName())
                res.append({"name": re.sub(r"\W+", "_", f"{cid}_{oname}"), "child": cid,
                            "child_output": mo.childOutputName(),
                            "description": mo.description() or odef.description(), "type": odef.type()})
    return res


def output_help_key(child_id, output_name):
    return f"{OUTPUT_PREFIX}{child_id}::{output_name}"


def output_help(model, child_id, output_name):
    return help_value(model, output_help_key(child_id, output_name))


def set_output_help(model, child_id, output_name, text):
    set_help_value(model, output_help_key(child_id, output_name), text)


def rename_help_key(model, old, new):
    content = _help(model)
    if old in content:
        content[new] = content.pop(old)
        model.setHelpContent(content)


def sync_help(model):
    """Insère l'aide des étapes dans la description du modèle."""
    content = _help(model)
    children = model.childAlgorithms()
    for key in [k for k in content if k.startswith(STEP_PREFIX)]:
        if key[len(STEP_PREFIX):] not in children:
            content.pop(key)
    for key in [k for k in content if k.startswith(OUTPUT_PREFIX)]:
        cid, _sep, oname = key[len(OUTPUT_PREFIX):].partition("::")
        if cid not in children or oname not in children[cid].modelOutputs():
            content.pop(key)
    desc = _MARK_RE.sub("", str(content.get("ALG_DESC", "") or "")).rstrip()
    steps = []
    for cid, child in sorted(children.items(), key=lambda kv: kv[1].description().lower()):
        text = content.get(STEP_PREFIX + cid)
        if text:
            steps.append(f"<li><b>{html.escape(child.description())}</b> : {text}</li>")
    outs = []
    for cid, child in sorted(children.items(), key=lambda kv: kv[1].description().lower()):
        for oname, mo in child.modelOutputs().items():
            text = content.get(output_help_key(cid, oname))
            if text:
                outs.append(f"<li><b>{html.escape(mo.description() or oname)}</b> : {text}</li>")
    if steps or outs:
        block = f"{_MARK_START}"
        if steps:
            block += f"<h3>{tr('Model steps')}</h3><ul>{''.join(steps)}</ul>"
        if outs:
            block += f"<h3>{tr('Model outputs')}</h3><ul>{''.join(outs)}</ul>"
        block += _MARK_END
        desc = (desc + "\n" if desc else "") + block
    if desc:
        content["ALG_DESC"] = desc
    else:
        content.pop("ALG_DESC", None)
    model.setHelpContent(content)


def unique_parameter_name(model, description, exclude=None):
    base = safe_name(description).lower() or "parametre"
    name, i = base, 2
    while model.parameterDefinition(name) is not None and name != exclude:
        name = f"{base}{i}"
        i += 1
    return name
