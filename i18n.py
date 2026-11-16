"""Traduction de l'interface.

Les textes du code sont en anglais et passent par ``tr()`` ; les traductions sont des
fichiers Qt Linguist ``i18n/modeler_evo_<langue>.ts``, compilés en ``.qm`` (voir
``tools/update_translations.py``). La langue est celle de l'interface de QGIS.
"""

import os

from qgis.PyQt.QtCore import QCoreApplication, QTranslator

CONTEXT = "ModelerEvo"
I18N_DIR = os.path.join(os.path.dirname(__file__), "i18n")

_translator = None


def tr(text):
    """Texte traduit dans la langue de QGIS (``text`` est la version anglaise)."""
    return QCoreApplication.translate(CONTEXT, text)


def qgis_language():
    """Code à deux lettres de la langue de l'interface de QGIS (ex. « fr »)."""
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
    """Charge la traduction correspondant à la langue de QGIS (si elle existe).

    À appeler avant d'importer les modules du plugin : certains libellés sont
    traduits au chargement du module.
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
