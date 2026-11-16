"""User interface translation.

Texts in the code are written in English and go through ``tr()``; translations are
Qt Linguist files ``i18n/modeler_evo_<language>.ts``, compiled to ``.qm`` (see
``tools/update_translations.py``). The language is the one of the QGIS user interface.
"""

import os

from qgis.PyQt.QtCore import QCoreApplication, QTranslator

CONTEXT = "ModelerEvo"
I18N_DIR = os.path.join(os.path.dirname(__file__), "i18n")

_translator = None


def tr(text):
    """Text translated into the QGIS language (``text`` is the English version)."""
    return QCoreApplication.translate(CONTEXT, text)


def qgis_language():
    """Two-letter code of the QGIS user interface language (e.g. "fr")."""
    locale = ""
    try:
        from qgis.core import QgsApplication
        locale = QgsApplication.locale()
    except Exception:  # noqa: BLE001
        pass
    if not locale:
        try:
            from qgis.core import QgsSettings
            locale = QgsSettings().value("locale/userLocale", "") or ""
        except Exception:  # noqa: BLE001
            locale = ""
    return str(locale)[:2].lower()


def install_translator():
    """Load the translation matching the QGIS language (if there is one).

    Must be called before importing the plugin modules: some labels are
    translated when their module is loaded.
    """
    global _translator
    if _translator is not None:
        return
    path = os.path.join(I18N_DIR, f"modeler_evo_{qgis_language()}.qm")
    if not os.path.exists(path):
        return
    translator = QTranslator()
    if translator.load(path):
        QCoreApplication.installTranslator(translator)
        _translator = translator


def remove_translator():
    global _translator
    if _translator is not None:
        QCoreApplication.removeTranslator(_translator)
        _translator = None
