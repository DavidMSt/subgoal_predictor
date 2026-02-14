import dataclasses

from core.utils.callbacks import callback_definition, CallbackContainer, Callback
from core.utils.dataclass_utils import from_dict_auto
from core.utils.files import get_absolute_path, file_exists
from core.utils.logging_utils import Logger, addLogRedirection, LOGGING_COLORS
from core.utils.mdns import MDNSAdvertiser
from core.utils.network.port_forwarder import PortForwarder
from core.utils.yaml_utils import load_yaml
from extensions.cli.cli import CLI
from extensions.gui.src.app import App
from extensions.gui.src.gui import GUI, Category, Page
from extensions.gui.src.lib.objects.python.buttons import Button
from extensions.gui.src.lib.objects.python.callout import CalloutType
from extensions.gui.src.lib.objects.python.camera import CameraWidget
from extensions.gui.src.lib.objects.python.popup import YesNoPopup
from extensions.gui.settings import PORT_JS_APP
from robots.bilbo.gui.applications.input_viewer import InputViewerApplication
from robots.bilbo.gui.app_robot_folder import BILBO_Application_App_Robot_Folder
from robots.bilbo.gui.overview_page import BILBO_GUI_OverviewPage
from robots.bilbo.gui.robot_ui import RobotUI
from robots.bilbo.manager.bilbo_joystick_control import BILBO_JoystickControl
from robots.bilbo.robot.bilbo import BILBO
from robots.bilbo.testbed.objects import TestbedBILBO, RealTestbedBILBO
from robots.bilbo.testbed.testbed_manager import TestbedManager

# mDNS settings - advertise bilbolab.local on the network
MDNS_HOSTNAME = "bilbolab"  # Will be accessible as http://bilbolab.local/gui (with port 80) or :8400/gui


# ======================================================================================================================

@dataclasses.dataclass
class BILBO_GUI_Settings:
    enable_camera: bool = False
    enable_emergency_stop: bool = False
    bottom_group_size: list = dataclasses.field(default_factory=lambda: [3, 3])
    enable_top_bar: bool = True
    allow_multiple_instances: bool = False
    show_message_rate: bool = True
    message_rate_warning: int = 200


@callback_definition
class BILBO_Application_GUI_Callbacks:
    emergency_stop: CallbackContainer


class BILBO_Application_GUI:
    gui: GUI
    app: App
    categories: dict
    robot_ui: dict[str, RobotUI]
    # robot_categories: dict[str, BILBO_Application_GUI_Robot_Category]
    robot_app_folders: dict[str, BILBO_Application_App_Robot_Folder]
    mdns_advertiser: MDNSAdvertiser | None
    port_forwarder: PortForwarder | None

    # === INIT =========================================================================================================
    def __init__(self,
                 settings,
                 host,
                 testbed_manager: TestbedManager,
                 cli: CLI = None,
                 joystick_control: BILBO_JoystickControl | None = None,
                 enable_mdns: bool = True,
                 mdns_hostname: str = MDNS_HOSTNAME,
                 mdns_use_port_80: bool = False):

        settings_file = get_absolute_path('./gui_settings.yaml')

        if file_exists(settings_file):
            settings_dict = load_yaml(settings_file)
        else:
            settings_dict = {}

        self.settings = from_dict_auto(BILBO_GUI_Settings, settings_dict)

        self.application_settings = settings
        self.callbacks = BILBO_Application_GUI_Callbacks()
        self.host = host
        self.enable_mdns = enable_mdns
        self.mdns_hostname = mdns_hostname
        self.mdns_use_port_80 = mdns_use_port_80

        self.gui = GUI(
            id='bilbo_application',
            host=host,
            run_js=True,
            options={
                'enable_emergency_stop': self.settings.enable_emergency_stop,
                'bottom_group_size': self.settings.bottom_group_size,
                'enable_top_bar': self.settings.enable_top_bar,
                'allow_multiple_instances': self.settings.allow_multiple_instances,
                'show_message_rate': self.settings.show_message_rate,
                'message_rate_warning': self.settings.message_rate_warning,
            }
        )

        self.app = App(
            app_id='bilbo_application_app',
            host=host,
            run_js_app=False,
        )

        self.testbed_manager = testbed_manager
        self.gui.cli_terminal.setCLI(cli)
        self.joystick_control = joystick_control

        # GUI Callbacks
        self.gui.callbacks.emergency_stop.register(self.callbacks.emergency_stop.call)

        self.categories = {}
        self.robot_ui = {}

        self._addCategoriesAndPages()

        self._create_bottom_group()

        self.logger = Logger('gui')

        # Reroute all logs to the CLI
        addLogRedirection(self._logRedirection, minimum_level='INFO')

        # mDNS advertiser for network discovery
        self.mdns_advertiser = None
        # Port forwarder for port 80 access (optional, requires sudo)
        self.port_forwarder = None

        # Subscribe to testbed manager events for robot connect/disconnect
        self.testbed_manager.events.new_bilbo.on(self._on_new_bilbo)
        self.testbed_manager.events.bilbo_removed.on(self._on_bilbo_removed)

    # === METHODS ======================================================================================================
    def init(self):
        ...

    # ------------------------------------------------------------------------------------------------------------------
    def start(self):
        self.gui.start()
        self.app.start()

        # Start mDNS advertisement so the GUI is discoverable on the network
        if self.enable_mdns:
            self._start_mdns()

    # ------------------------------------------------------------------------------------------------------------------
    def _start_mdns(self):
        """Start mDNS advertisement to make the GUI discoverable on the network.

        If mdns_use_port_80 is True, also starts a port forwarder on port 80 to allow
        access without specifying a port (requires running with sudo).
        """
        # Determine which port to advertise
        advertised_port = PORT_JS_APP

        if self.mdns_use_port_80:
            # Start port forwarder: port 80 -> GUI port
            self.port_forwarder = PortForwarder(listen_port=80, target_port=PORT_JS_APP, target_host=self.host)
            if self.port_forwarder.start():
                advertised_port = 80
            else:
                self.logger.error("Cannot bind to port 80 - requires sudo. Falling back to port 8400.")
                self.port_forwarder = None

        # Start mDNS advertisement
        self.mdns_advertiser = MDNSAdvertiser(
            hostname=self.mdns_hostname,
            port=advertised_port
        )
        if self.mdns_advertiser.start():
            if advertised_port == 80:
                self.logger.info(f"GUI advertised on network: http://{self.mdns_hostname}.local/gui")
            else:
                self.logger.info(f"GUI advertised on network: http://{self.mdns_hostname}.local:{advertised_port}/gui")
        else:
            self.logger.warning("mDNS advertisement failed. GUI will only be accessible via direct IP:port.")

    # ------------------------------------------------------------------------------------------------------------------
    def close(self):
        """Clean up resources including mDNS advertisement and port forwarder."""
        if self.mdns_advertiser:
            self.mdns_advertiser.stop()
        if self.port_forwarder:
            self.port_forwarder.stop()

    # ------------------------------------------------------------------------------------------------------------------
    def addRobot(self, robot: BILBO):
        self.robot_ui[robot.id] = RobotUI(robot=robot,
                                          manager=self.testbed_manager,
                                          gui=self.gui,
                                          app=self.app,
                                          application_settings=self.application_settings)

        self.gui.callout_handler.add(callout_type=CalloutType.INFO,
                                     title='Robot Connected',
                                     content=f'Robot {robot.id} connected.',
                                     timeout=5)

    # ------------------------------------------------------------------------------------------------------------------
    def removeRobot(self, robot_id: str):
        if robot_id not in self.robot_ui:
            return

        self.gui.callout_handler.add(callout_type=CalloutType.WARNING,
                                     title='Robot Disconnected',
                                     content=f'Robot {robot_id} disconnected.',
                                     timeout=5)
        self.robot_ui[robot_id].close()
        del self.robot_ui[robot_id]

    # ------------------------------------------------------------------------------------------------------------------
    def _on_new_bilbo(self, testbed_bilbo: TestbedBILBO, *args, **kwargs):
        """Handle new robot from testbed manager. Wait for initialization before building UI."""
        if not isinstance(testbed_bilbo, RealTestbedBILBO):
            return

        robot = testbed_bilbo.robot

        # Wait for first sample before building robot UI
        if not robot.core.initialized:
            robot.core.events.initialized.on(
                callback=Callback(
                    function=self.addRobot,
                    inputs={'robot': robot},
                    discard_inputs=True
                ),
                once=True,
                discard_data=True
            )
        else:
            self.addRobot(robot)

    # ------------------------------------------------------------------------------------------------------------------
    def _on_bilbo_removed(self, robot_id: str, *args, **kwargs):
        """Handle robot disconnect from testbed manager."""
        self.removeRobot(robot_id)

    # === PRIVATE METHODS ==============================================================================================
    def _addCategoriesAndPages(self):
        # Application category
        category_application = Category(id='application', name='Application', icon='🎛️')
        self.gui.addCategory(category_application)
        self.categories['application'] = {'category': category_application}

        # Pages
        # page_overview = Page(id='overview', name='Overview')
        # category_application.addPage(page_overview)
        #
        # page_robots = Page(id='robots', name='Robots')
        # category_application.addPage(page_robots)

        self.testbed_page = BILBO_GUI_OverviewPage(self.testbed_manager)
        category_application.addPage(self.testbed_page.page)

        self.categories['application']['pages'] = {
            'testbed': self.testbed_page.page,
        }

        # Robots Category
        category_robots = Category(id='robots', name='Robots', icon='🤖', number_of_pages=1, max_pages=1)
        self.gui.addCategory(category_robots)
        self.categories['robots'] = {'category': category_robots}

        robots_overview = Page(id='overview', name='Overview')
        category_robots.addPage(robots_overview)
        self.categories['robots']['pages'] = {'overview': robots_overview}

    # # ------------------------------------------------------------------------------------------------------------------
    # def _addRobotCategory(self, robot_id, robot: BILBO):
    #     self.robot_categories[robot_id] = BILBO_Application_GUI_Robot_Category(robot, self.gui)
    #     self.categories['robots']['category'].addCategory(self.robot_categories[robot_id].category)

    # ------------------------------------------------------------------------------------------------------------------
    def _removeRobotCategory(self, robot_id):
        if robot_id in self.robot_categories:
            self.categories['robots']['category'].removeCategory(self.robot_categories[robot_id].category)
            del self.robot_categories[robot_id]

    # # ------------------------------------------------------------------------------------------------------------------
    # def _addRobotFolder_App(self, robot_id, robot: BILBO):
    #     self.robot_app_folders[robot_id] = BILBO_Application_App_Robot_Folder(robot, self.app)
    #     self.app.addFolder(self.robot_app_folders[robot_id].folder)

    # ------------------------------------------------------------------------------------------------------------------
    def _removeRobotFolder_App(self, robot_id):
        if robot_id in self.robot_app_folders:
            self.app.removeFolder(self.robot_app_folders[robot_id].folder)
            del self.robot_app_folders[robot_id]

    # ------------------------------------------------------------------------------------------------------------------
    def _create_bottom_group(self):
        if self.settings.enable_camera:
            camera = CameraWidget(
                widget_id='testbed_camera',
                excluded=['iPhone', 'FaceTime'],
                priority=['Elgato 4K'],
            )
            self.gui.bottom_group.addWidget(camera, row=1, column=1, width=1, height=1)

    # ------------------------------------------------------------------------------------------------------------------
    def _openInputViewer(self, sender, *args, **kwargs):

        input_viewer_app = InputViewerApplication()
        input_viewer_app.open(self.gui, sender)

    # ------------------------------------------------------------------------------------------------------------------
    def _logRedirection(self, log_entry, log, logger, level):
        print_text = f"[{logger.name}] {log}"
        color = LOGGING_COLORS[level]
        color = [c / 255 for c in color]
        self.gui.print(print_text, color=color)
        self.app.print(print_text, color=color)
