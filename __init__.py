"""ModelerEvo: modernized version of the Processing graphical modeler."""


def classFactory(iface):  # noqa: N802 (name required by QGIS)
    from .i18n import install_translator
    install_translator()  # before the other imports: some labels are translated at load time
    from .plugin import ModelerEvoPlugin
    return ModelerEvoPlugin(iface)
