import dataclasses
import time
from typing import Iterable, List, Sequence, Tuple, Union, Optional

from core.utils.exit import register_exit_callback
from core.utils.websockets import WebsocketClient

WEBSOCKET_PORT = 7777
DEFAULT_HOST = "display.lan"

# Local defaults (also carried in the config we can push to the Pi)
HEIGHT_OFFSET_TO_PIXEL_0 = 0.0  # physical height (same units as 'height') at pixel 0
DISTANCE_BETWEEN_PIXELS = 17  # distance (same units) between successive pixels
DEFAULT_HEIGHT_COLOR = (50, 0, 50)
DEFAULT_NUM_PIXELS = 30
DEFAULT_MAX_BRIGHTNESS = 10  # max per-channel value after scaling (0..255)





def _as_color_triplet(
        color: Union[Sequence[int], Tuple[int, int, int]],
        max_brightness: Optional[int] = None
) -> Tuple[int, int, int]:
    """
    Convert to (r,g,b) clamped to 0..255 and (optionally) scale down uniformly so that
    no channel exceeds max_brightness, preserving the overall color ratios.

    Example:
      (200, 50, 0) with max_brightness=100 -> scale by 0.5 -> (100, 25, 0)
    """
    r, g, b = int(color[0]), int(color[1]), int(color[2])
    r = max(0, min(255, r))
    g = max(0, min(255, g))
    b = max(0, min(255, b))

    if max_brightness is None:
        return (r, g, b)

    mb = int(max_brightness)
    mb = max(0, min(255, mb))
    if mb == 0:
        return (0, 0, 0)

    peak = max(r, g, b)
    if peak <= mb:
        return (r, g, b)

    scale = mb / float(peak)
    rr = int(round(r * scale))
    gg = int(round(g * scale))
    bb = int(round(b * scale))

    # Safety (rounding could barely overshoot)
    rr = min(rr, mb)
    gg = min(gg, mb)
    bb = min(bb, mb)
    return (rr, gg, bb)

@dataclasses.dataclass
class HeightIndicatorConfig:
    height_offset_to_pixel_0: float = HEIGHT_OFFSET_TO_PIXEL_0
    distance_between_pixels: float = DISTANCE_BETWEEN_PIXELS
    height_color: Tuple[int, int, int] = dataclasses.field(default_factory=lambda: _as_color_triplet(DEFAULT_HEIGHT_COLOR))
    num_pixels: int = DEFAULT_NUM_PIXELS
    websocket_port: int = WEBSOCKET_PORT
    max_brightness: int = DEFAULT_MAX_BRIGHTNESS  # applied client-side before sending


class HeightIndicator:
    client: WebsocketClient
    connected: bool = False

    # === INIT =========================================================================================================
    def __init__(self, host: str = DEFAULT_HOST, port: int = WEBSOCKET_PORT,
                 max_brightness: int = DEFAULT_MAX_BRIGHTNESS):
        self.client = WebsocketClient(host, port)
        self.client.callbacks.connected.register(self._websocket_connected_callback)
        self.client.callbacks.disconnected.register(self._websocket_disconnected_callback)

        self.max_brightness = int(max(0, min(255, max_brightness)))

        register_exit_callback(self.close, priority=100)

    # === METHODS ======================================================================================================
    def start(self):
        self.client.connect()

    # ------------------------------------------------------------------------------------------------------------------
    def close(self):
        try:
            self.clear()
            time.sleep(2)
        finally:
            self.client.close()

    # ------------------------------------------------------------------------------------------------------------------
    def setConfig(self, config: HeightIndicatorConfig):
        """
        Send runtime configuration to the Pi.
        You can change mapping parameters, num_pixels, and height_color.

        Note: max_brightness is applied client-side before sending colors. We also
        include it in the config payload for completeness (the Pi may ignore it).
        """
        # Adopt brightness locally so subsequent sends are scaled
        self.max_brightness = int(max(0, min(255, int(config.max_brightness))))

        config_dict = dataclasses.asdict(config)
        self.send({'type': 'set_config', 'data': config_dict})

    # ------------------------------------------------------------------------------------------------------------------
    def setMaxBrightness(self, max_brightness: int):
        """Set client-side max per-channel brightness (0..255)."""
        self.max_brightness = int(max(0, min(255, int(max_brightness))))

    # ------------------------------------------------------------------------------------------------------------------
    def clear(self):
        """Turn everything off."""
        self.send({'type': 'clear'})

    # ------------------------------------------------------------------------------------------------------------------
    def setPixel(self, index: int, color: Union[Sequence[int], Tuple[int, int, int]]):
        """Set a single pixel to a color (scaled to max_brightness)."""
        r, g, b = _as_color_triplet(color, self.max_brightness)
        self.send({'type': 'set_pixel', 'data': {'index': int(index), 'color': [r, g, b]}})

    # ------------------------------------------------------------------------------------------------------------------
    def fill(self, color: Union[Sequence[int], Tuple[int, int, int]]):
        """Fill the entire strip with a color (scaled to max_brightness)."""
        r, g, b = _as_color_triplet(color, self.max_brightness)
        self.send({'type': 'set_all', 'data': {'color': [r, g, b]}})

    # ------------------------------------------------------------------------------------------------------------------
    def blink(self, color: Union[Sequence[int], Tuple[int, int, int]], num_blinks: int = 1, time_ms: int = 250):
        """Flash the whole strip a number of times (scaled to max_brightness)."""
        r, g, b = _as_color_triplet(color, self.max_brightness)
        self.send({'type': 'blink', 'data': {'color': [r, g, b], 'times': int(num_blinks), 'time_ms': int(time_ms)}})

    # ------------------------------------------------------------------------------------------------------------------
    def blinkRed(self):
        self.blink((255, 0, 0), 3, 150)

    # ------------------------------------------------------------------------------------------------------------------
    def blinkGreen(self):
        self.blink((0, 255, 0), 3, 150)

    # ------------------------------------------------------------------------------------------------------------------
    def setHeight(self, height: float):
        """
        Ask the Pi to compute and render the nearest pixel for a given physical height
        using its current mapping config.
        """
        self.send({'type': 'set_height', 'data': {'height': float(height)}})

    # ------------------------------------------------------------------------------------------------------------------
    def setHeightPixels(self, height_pixels: Iterable[int]):
        """
        Light multiple pixel indices at once using the Pi's configured height color.
        """
        indices: List[int] = [int(i) for i in height_pixels]
        self.send({'type': 'set_height_pixels', 'data': {'indices': indices}})

    # === PRIVATE METHODS ==============================================================================================
    def send(self, data: dict):
        if self.connected:
            self.client.send(data)

    # ------------------------------------------------------------------------------------------------------------------
    def _websocket_connected_callback(self, *args, **kwargs):
        self.connected = True

    # ------------------------------------------------------------------------------------------------------------------
    def _websocket_disconnected_callback(self, *args, **kwargs):
        self.connected = False


if __name__ == '__main__':
    height_indicator = HeightIndicator()
    height_indicator.start()

    while not height_indicator.connected:
        time.sleep(1)
    # Tiny demo script (safe to remove)
    height_indicator.clear()
    time.sleep(0.5)

    cfg = HeightIndicatorConfig()
    height_indicator.setConfig(cfg)

    time.sleep(1)

    height_indicator.setHeight(200)

    time.sleep(3)

    while True:
        height_indicator.blinkRed()
        time.sleep(3)
    #     height_indicator.blinkGreen()
    #     time.sleep(3)
