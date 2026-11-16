"""ModelerEvo : version modernisée du modeleur graphique de Processing."""


def classFactory(iface):  # noqa: N802 (nom imposé par QGIS)
    from .plugin import ModelerEvoPlugin
    return ModelerEvoPlugin(iface)
