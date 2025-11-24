import time
import numpy as np

from core.utils.exit import register_exit_callback
from core.utils.network.network import getHostIP
from core.utils.websockets import WebsocketServer
from gimli import UGV02
from core.utils.joystick.joystick_manager import JoystickManager, Joystick
from core.utils.logging_utils import Logger
import threading


class GIMLI_App:
    robot: UGV02

    joystick_manager: JoystickManager
    joystick: Joystick | None = None

    _exit: bool = False

    server: WebsocketServer | None = None

    def __init__(self):
        self.robot = UGV02()

        self.logger = Logger("GIMLI", "DEBUG")
        self.joystick_manager = JoystickManager(accept_unmapped_joysticks=True)
        self.joystick_manager.callbacks.new_joystick.register(self._on_new_joystick)
        self.joystick_manager.callbacks.joystick_disconnected.register(self._on_joystick_disconnected)

        self.server = None

        websocket_server_thread = threading.Thread(target=self._websocket_server_task, daemon=True)
        websocket_server_thread.start()

        self._thread = threading.Thread(target=self._task, daemon=True)
        register_exit_callback(self.close)

    # ------------------------------------------------------------------------------------------------------------------
    def init(self):
        ...

    # ------------------------------------------------------------------------------------------------------------------
    def start(self):
        self.joystick_manager.start()
        self._thread.start()

    # ------------------------------------------------------------------------------------------------------------------
    def close(self):
        self._exit = True
        if self._thread.is_alive():
            self._thread.join()

    # ------------------------------------------------------------------------------------------------------------------
    def _websocket_server_task(self):
        while self.server is None:

            host = getHostIP()
            if host is None:
                self.logger.warning("Could not get host IP")
                time.sleep(3)
                continue

            self.server = WebsocketServer(host, 8080)
            self.server.callbacks.message.register(self.on_message)
            self.server.start()

    # ------------------------------------------------------------------------------------------------------------------
    def _task(self):
        while not self._exit:
            if self.joystick is not None:
                # === Read controller inputs ===
                forward = -self.joystick.getAxis("LEFT_VERTICAL")  # Forward/backward
                turn = self.joystick.getAxis("RIGHT_HORIZONTAL")  # Turning

                # === Exponential response mapping (for finer low-speed control) ===
                def map_input(x, factor=10.0):
                    sign = np.sign(x)
                    x = abs(x)
                    return sign * (np.exp(x * np.log(factor)) - 1) / (factor - 1)

                turn = map_input(turn)

                # === Normalize so combined magnitude doesn’t exceed 1 ===
                sum_axis = abs(forward) + abs(turn)
                if sum_axis > 1:
                    forward /= sum_axis
                    turn /= sum_axis

                # === Mix forward + turn into left/right speeds ===
                speed_left = forward + turn
                speed_right = forward - turn

                self.robot.set_motor_speed_normalized(speed_left, speed_right)

            time.sleep(0.1)

    # ------------------------------------------------------------------------------------------------------------------
    def _on_new_joystick(self, joystick: Joystick):
        self.joystick = joystick
        self.logger.info("New joystick connected")

    # ------------------------------------------------------------------------------------------------------------------
    def _on_joystick_disconnected(self, joystick):
        if joystick == self.joystick:
            self.joystick = None
            self.robot.set_motor_speed_normalized(0, 0)
            self.logger.info("Joystick disconnected")

    # ------------------------------------------------------------------------------------------------------------------
    def on_message(self, client, data, *args, **kwargs):
        message_type = data.get("type")
        message_data = data.get("data")
        if message_type is None:
            self.logger.warning("Received message without type")
            return

        if message_type == "set_motor_speed":
            self.robot.set_motor_speed_normalized(message_data["left"], message_data["right"])
        else:
            self.logger.warning(f"Unknown message type: {message_type}")


if __name__ == "__main__":
    app = GIMLI_App()
    app.init()
    app.start()
    #
    # app.robot.set_motor_speed_normalized(0.5, 0.5)
    # time.sleep(2)
    # app.robot.set_motor_speed_normalized(0, 0)

    while True:
        time.sleep(1)
