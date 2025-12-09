import dataclasses
import json
import threading
import time
import logging
import serial

from core.utils.exit import register_exit_callback

DEVICE = '/dev/ttyAMA0'
# DEVICE = '/dev/ttyS0'
BAUDRATE = 115200
SERIAL_TIMEOUT = 0.05  # seconds
HEARTBEAT_INTERVAL = 2  # must be < 3s to prevent auto-stop


@dataclasses.dataclass
class UGV02Data:
    """Holds the latest telemetry and feedback data from UGV02."""
    speed_left: float = 0.0
    speed_right: float = 0.0
    roll: float = 0.0
    pitch: float = 0.0
    velocity: float = 0.0
    timestamp: float = 0.0


class UGV02:
    """Interface for controlling and monitoring the Waveshare UGV02 robot."""

    def __init__(self, port: str = DEVICE, baudrate: int = BAUDRATE):
        # --- Serial connection ---
        self.serial = serial.Serial(port, baudrate=baudrate, timeout=SERIAL_TIMEOUT)
        self.logger = logging.getLogger("UGV02")
        self.logger.setLevel(logging.INFO)
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s", "%H:%M:%S"))
        self.logger.addHandler(handler)

        self.data = UGV02Data()
        self._running = True
        self._lock = threading.Lock()

        # --- Start serial reading thread ---
        self._reader_thread = threading.Thread(target=self._read_serial_loop, daemon=True)
        self._reader_thread.start()

        # --- Initialize robot ---
        self._init_robot()

        # --- Register exit handler ---
        register_exit_callback(self.close)

    # ------------------------------------------------------------------
    # --- INIT & SHUTDOWN ----------------------------------------------
    # ------------------------------------------------------------------

    def _init_robot(self):
        """Send initialization commands to set up PID and enable streaming."""
        self.logger.info("Initializing UGV02...")
        self.set_default_pid()
        self.enable_streaming(True)
        self.logger.info("UGV02 initialized and streaming enabled.")

    def close(self, *args, **kwargs):
        """Cleanly close the serial connection."""
        self.logger.info("Shutting down UGV02...")
        self.set_motor_speed(0, 0)
        self._running = False
        time.sleep(0.1)
        if self.serial.is_open:
            self.serial.close()
        self.logger.info("UGV02 closed.")

    # ------------------------------------------------------------------
    # --- PUBLIC COMMANDS ----------------------------------------------
    # ------------------------------------------------------------------

    def set_default_pid(self):
        """Set default PID control parameters."""
        # command = {"T": 2, "P": 200, "I": 2500, "D": 0, "L": 255}
        command = {"T": 2, "P": 200, "I": 2300, "D": 20, "L": 255}

        self._send_json(command)
        self.logger.debug("Default PID set.")

    def enable_streaming(self, enable: bool = True):
        """Enable or disable continuous feedback."""
        cmd = 1 if enable else 0
        command = {"T": 131, "cmd": cmd}
        self._send_json(command)
        self.logger.debug(f"Continuous feedback {'enabled' if enable else 'disabled'}.")

    def set_motor_speed_normalized(self, left: float, right: float):
        """
        Control the left and right wheel speeds, normalized to [-1..1].
        Range: -1 .. +1
        """
        left = max(min(left, 1), -1)
        right = max(min(right, 1), -1)
        self.set_motor_speed(left * 0.5, right * 0.5)

    def set_motor_speed(self, left: float, right: float):
        """
        Control the left and right wheel speeds.
        Range: -0.5 .. +0.5
        """
        left = max(min(left, 0.5), -0.5)
        right = max(min(right, 0.5), -0.5)
        command = {"T": 1, "L": left, "R": right}
        self._send_json(command)
        with self._lock:
            self.data.speed_left = left
            self.data.speed_right = right
        self.logger.debug(f"Set motor speeds -> L:{left:.2f}, R:{right:.2f}")

    def stop(self):
        """Stop both motors immediately."""
        self.set_motor_speed(0, 0)
        self.logger.info("Motors stopped.")

    def set_oled_line(self, line: int, text: str):
        """Display text on the OLED screen (line 0–3)."""
        if not 0 <= line <= 3:
            raise ValueError("OLED line number must be 0–3.")
        command = {"T": 3, "lineNum": line, "Text": text}
        self._send_json(command)
        self.logger.debug(f"OLED[{line}] <- {text}")

    def clear_oled(self):
        """Clear all four OLED lines."""
        for i in range(4):
            self.set_oled_line(i, "")
        self.logger.debug("OLED cleared.")

    # ------------------------------------------------------------------
    # --- SERIAL READER THREAD -----------------------------------------
    # ------------------------------------------------------------------

    def _read_serial_loop(self):
        """Continuously read incoming serial data and parse JSON messages."""
        buffer = ""
        while self._running:
            try:
                chunk = self.serial.read(128).decode("utf-8", errors="ignore")
                if not chunk:
                    continue
                buffer += chunk
                # Process complete lines
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    line = line.strip()
                    if line:
                        self._handle_incoming_line(line)
            except serial.SerialException as e:
                self.logger.error(f"Serial error: {e}")
                break
            except Exception as ex:
                self.logger.warning(f"Reader loop exception: {ex}")

    # ------------------------------------------------------------------
    # --- MESSAGE HANDLING ---------------------------------------------
    # ------------------------------------------------------------------

    def _handle_incoming_line(self, line: str):
        """Handle one complete line from the serial input."""
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            self.logger.debug(f"Non-JSON data: {line}")
            return

        msg_type = message.get("T")
        if msg_type == 1001:  # Feedback message
            self._handle_feedback(message)
        else:
            self.logger.debug(f"Received message: {message}")

    def _handle_feedback(self, message: dict):
        """Parse and store chassis feedback data."""
        with self._lock:
            self.data.speed_left = message.get("L", self.data.speed_left)
            self.data.speed_right = message.get("R", self.data.speed_right)
            self.data.roll = message.get("r", self.data.roll)
            self.data.pitch = message.get("p", self.data.pitch)
            self.data.velocity = message.get("v", self.data.velocity)
            self.data.timestamp = time.time()
        # self.logger.debug(f"Feedback: {self.data}")

    # ------------------------------------------------------------------
    # --- PRIVATE SEND HELPERS -----------------------------------------
    # ------------------------------------------------------------------

    def _send_json(self, command: dict):
        """Serialize dict to JSON and send with newline."""
        try:
            line = json.dumps(command, separators=(",", ":")) + "\n"
            self._send(line)
        except Exception as ex:
            self.logger.error(f"Failed to send JSON {command}: {ex}")

    def _send(self, message: str):
        """Low-level UART send."""
        try:
            self.serial.write(message.encode("utf-8"))
            self.serial.flush()
        except Exception as ex:
            self.logger.error(f"UART write failed: {ex}")

    # ------------------------------------------------------------------
    # --- ACCESSORS ----------------------------------------------------
    # ------------------------------------------------------------------

    def get_data(self) -> UGV02Data:
        """Return a snapshot of the latest telemetry."""
        with self._lock:
            return dataclasses.replace(self.data)