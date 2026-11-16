"""Point d'entrée du plugin ModelerEvo."""

try:  # Qt6
    from qgis.PyQt.QtGui import QAction
except ImportError:  # Qt5
    from qgis.PyQt.QtWidgets import QAction
from qgis.core import QgsApplication
from qgis.PyQt.QtWidgets import QMenu

from .gui.icons import plugin_icon

MENU = "ModelerEvo"


class ModelerEvoPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.actions = []
        self.processing_menu = None
        self.context_actions = []
        self.context_key = "modelerevo"

    def initGui(self):  # noqa: N802
        self.action_new = QAction(plugin_icon(), "ModelerEvo…", self.iface.mainWindow())
        self.action_new.setToolTip("Ouvrir ModelerEvo (nouveau modèle)")
        self.action_new.triggered.connect(self.new_model)
        self.action_open = QAction(plugin_icon(), "Ouvrir un modèle dans ModelerEvo…",
                                   self.iface.mainWindow())
        self.action_open.triggered.connect(self.open_model)
        self.actions = [self.action_new, self.action_open]

        for a in self.actions:
            self.iface.addPluginToMenu(MENU, a)
        self.iface.addToolBarIcon(self.action_new)

        self._register_toolbox_action()

        # Également dans le menu Traitement, à côté du modeleur d'origine
        self.processing_menu = self._find_processing_menu()
        if self.processing_menu is not None:
            self.processing_menu.addAction(self.action_new)

    @staticmethod
    def _model_path(algorithm_name):
        """Chemin du .model3 d'un modèle de la boîte à outils (None si ce n'est pas un modèle fichier)."""
        alg = QgsApplication.processingRegistry().createAlgorithmById(f"model:{algorithm_name}")
        if alg is None:
            return None
        return getattr(alg, "sourceFilePath", lambda: "")() or None

    def _register_toolbox_action(self):
        """Ajoute « Éditer avec ModelerEvo… » au menu contextuel des modèles de la boîte à outils."""
        plugin = self
        try:  # QGIS >= 4.4 : API C++ du registre GUI de Processing
            from qgis.gui import QgsGui, QgsProcessingToolboxContextAction
            registry = QgsGui.processingGuiRegistry()
            register = registry.registerProviderToolboxContextAction
        except (ImportError, AttributeError):
            self._register_legacy_toolbox_action()
            return

        class EditWithEvoAction(QgsProcessingToolboxContextAction):
            def __init__(self):
                super().__init__("Éditer avec ModelerEvo…")

            def icon(self):
                return plugin_icon()

            def isCompatibleWithAlgorithm(self, providerId, algorithmName):  # noqa: N802
                return providerId == "model" and plugin._model_path(algorithmName) is not None

            def trigger(self, context):
                path = plugin._model_path(context.algorithmName())
                if path:
                    plugin._window().open_model(path)

        register(self.context_key, EditWithEvoAction())
        self._new_api = True

    def _register_legacy_toolbox_action(self):
        """QGIS 3.x : liste de ContextAction de processing.gui.ProviderActions."""
        try:
            from processing.gui.ContextAction import ContextAction
            from processing.gui.ProviderActions import ProviderContextMenuActions
        except ImportError:  # Processing indisponible
            return
        plugin = self

        class EditWithEvoAction(ContextAction):
            def __init__(self):
                super().__init__()
                self.name = "Éditer avec ModelerEvo…"

            def icon(self):
                return plugin_icon()

            def isEnabled(self):  # noqa: N802
                alg = self.itemData
                return (alg is not None and alg.provider() is not None
                        and alg.provider().id() == "model"
                        and bool(getattr(alg, "sourceFilePath", lambda: "")()))

            def execute(self):
                plugin._window().open_model(self.itemData.sourceFilePath())

        self.context_actions = [EditWithEvoAction()]
        ProviderContextMenuActions.registerProviderContextMenuActions(self.context_actions)

    def _unregister_toolbox_action(self):
        if getattr(self, "_new_api", False):
            from qgis.gui import QgsGui
            QgsGui.processingGuiRegistry().deregisterProviderToolboxContextActions(self.context_key)
            self._new_api = False
            return
        if not self.context_actions:
            return
        try:
            from processing.gui.ProviderActions import ProviderContextMenuActions
            ProviderContextMenuActions.deregisterProviderContextMenuActions(self.context_actions)
        except (ImportError, ValueError):
            pass
        self.context_actions = []

    def _find_processing_menu(self):
        menubar = self.iface.mainWindow().menuBar()
        for action in menubar.actions():
            menu = action.menu()
            if isinstance(menu, QMenu) and menu.objectName() in ("processing", "mProcessingMenu",
                                                                  "mProcessing"):
                return menu
        return None

    def unload(self):
        self._unregister_toolbox_action()
        from .gui.main_window import ModelerWindow
        for w in list(ModelerWindow.instances):
            w.close()
        for a in self.actions:
            self.iface.removePluginMenu(MENU, a)
        self.iface.removeToolBarIcon(self.action_new)
        if self.processing_menu is not None:
            self.processing_menu.removeAction(self.action_new)
        self.actions = []

    def _window(self):
        from .gui.main_window import ModelerWindow
        w = ModelerWindow(parent=self.iface.mainWindow())
        w.show()
        w.raise_()
        return w

    def new_model(self):
        self._window()

    def open_model(self):
        w = self._window()
        w.open_model()
