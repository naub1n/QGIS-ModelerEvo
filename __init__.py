"""ModelerEvo : version modernisée du modeleur graphique de Processing."""


def classFactory(iface):  # noqa: N802 (nom imposé par QGIS)
    from .i18n import install_translator
    install_translator()  # avant les autres imports : libellés traduits au chargement
    from .plugin import ModelerEvoPlugin
    return ModelerEvoPlugin(iface)
