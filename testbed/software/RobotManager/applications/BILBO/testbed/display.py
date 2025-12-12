#!/usr/bin/env python3
"""
UDP client wrapper for the TestbedDisplay server.

This provides a Python class with (almost) the same API as the display,
but instead of drawing anything it just sends JSON commands via UDP.

Usage example:

    from testbed_display_client import TestbedDisplayClient

    client = TestbedDisplayClient()  # defaults to display.lan:12346

    client.set_background_color((0, 0, 64))
    client.set_title("Hello", color=(255, 215, 0), alignment="center", size=120)
    client.set_text("Main text here", size=160, color=(255, 255, 255), alignment="center")
    client.set_icon("🚀", size=160)
    client.start_clock(mode="overlay", color=(0, 255, 255))  # or mode="replace_text"

    client.set_text_color((255, 0, 0))
    client.set_title_color((0, 255, 0))
    client.set_clock_color((255, 255, 0))

    # At some later point:
    client.stop_clock()
    client.clear()
    client.quit()
"""

import json
import socket
import time
from typing import Any, Dict, Optional, Tuple, Union


ColorType = Union[Tuple[int, int, int], list, dict]

DEFAULT_HOST = "display.lan"
DEFAULT_LISTEN_PORT = 12346

# Keep these defaults in sync with display where it makes sense
DEFAULT_BACKGROUND_COLOR = (0, 0, 0)   # black
DEFAULT_TEXT_COLOR = (255, 255, 255)   # white
DEFAULT_TITLE_COLOR = (200, 200, 200)  # light gray
DEFAULT_CLOCK_COLOR = DEFAULT_TITLE_COLOR

# Per your request: bigger defaults on the sender side
DEFAULT_TEXT_SIZE = 235
DEFAULT_TITLE_SIZE = 140
DEFAULT_ICON_SIZE = 200


class TestbedDisplayClient:
    """
    A thin client that mimics the display-side API and sends UDP JSON messages
    to a TestbedDisplay server.
    """

    def __init__(self, host: str = DEFAULT_HOST, port: int = DEFAULT_LISTEN_PORT):
        self.host = host
        self.port = port

        self.default_background_color = DEFAULT_BACKGROUND_COLOR
        self.default_text_size = DEFAULT_TEXT_SIZE
        self.default_title_size = DEFAULT_TITLE_SIZE
        self.default_icon_size = DEFAULT_ICON_SIZE

        # Single UDP socket reused for all sends
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    # ------------------------------------------------------------------------------------------------------------------
    # Low-level send
    # ------------------------------------------------------------------------------------------------------------------
    def _send(self, payload: Dict[str, Any]) -> None:
        data = json.dumps(payload).encode("utf-8")
        self._sock.sendto(data, (self.host, self.port))

    # ------------------------------------------------------------------------------------------------------------------
    # API methods mirroring the display side
    # ------------------------------------------------------------------------------------------------------------------
    def set_text(
        self,
        text: Optional[str],
        size: int = DEFAULT_TEXT_SIZE,
        color: ColorType = DEFAULT_TEXT_COLOR,
        alignment: str = "center",
    ) -> None:
        """
        Set main text. Vertically centered on the display, alignment controls
        left/center/right horizontally.
        """
        msg = {
            "command": "set_text",
            "text": text,
            "size": size,
            "color": self._serialize_color(color),
            "alignment": alignment,
        }
        self._send(msg)

    # ------------------------------------------------------------------------------------------------------------------
    def set_text_color(self, color: ColorType = DEFAULT_TEXT_COLOR) -> None:
        """
        Change text color without changing text content or size.
        """
        msg = {
            "command": "set_text_color",
            "color": self._serialize_color(color),
        }
        self._send(msg)

    # ------------------------------------------------------------------------------------------------------------------
    def set_title(
        self,
        text: Optional[str],
        color: ColorType = DEFAULT_TITLE_COLOR,
        alignment: str = "center",
        size: int = DEFAULT_TITLE_SIZE,
    ) -> None:
        """
        Set a title at the top edge of the display.
        """
        msg = {
            "command": "set_title",
            "text": text,
            "size": size,
            "color": self._serialize_color(color),
            "alignment": alignment,
        }
        self._send(msg)

    # ------------------------------------------------------------------------------------------------------------------
    def set_title_color(self, color: ColorType = DEFAULT_TITLE_COLOR) -> None:
        """
        Change title color without changing title text or size.
        """
        msg = {
            "command": "set_title_color",
            "color": self._serialize_color(color),
        }
        self._send(msg)

    # ------------------------------------------------------------------------------------------------------------------
    def set_icon(self, icon: Optional[str], size: int = DEFAULT_ICON_SIZE) -> None:
        """
        Set a centered icon (emoji string) on the display.
        """
        msg = {
            "command": "set_icon",
            "icon": icon,
            "size": size,
        }
        self._send(msg)

    # ------------------------------------------------------------------------------------------------------------------
    def set_image(self, image_path: Optional[str]) -> None:
        """
        Set a fullscreen image. Should be a valid path on the display's filesystem.
        """
        msg = {
            "command": "set_image",
            "image": image_path,
        }
        self._send(msg)

    # ------------------------------------------------------------------------------------------------------------------
    def clear(self) -> None:
        """
        Clear text, title, icon, image, and stop the clock.
        """
        self._send({"command": "clear"})

    # ------------------------------------------------------------------------------------------------------------------
    def start_clock(
        self,
        mode: str = "overlay",
        replace_text: Optional[bool] = None,
        color: Optional[ColorType] = None,
    ) -> None:
        """
        Start the clock from 00:00:00:000.

        mode:
          - "overlay" (default): clock at bottom center, main text stays visible
          - "replace_text": clock is centered and replaces the main text

        replace_text:
          - if provided, overrides the mode on the display side.

        color:
          - optional clock color (separate from title color).
        """
        msg: Dict[str, Any] = {
            "command": "start_clock",
            "mode": mode,
        }
        if replace_text is not None:
            msg["replace_text"] = bool(replace_text)
        if color is not None:
            msg["color"] = self._serialize_color(color)
        self._send(msg)

    # ------------------------------------------------------------------------------------------------------------------
    def stop_clock(self) -> None:
        """
        Stop the clock (time is frozen until started again).
        """
        self._send({"command": "stop_clock"})

    # ------------------------------------------------------------------------------------------------------------------
    def set_clock_color(self, color: ColorType = DEFAULT_CLOCK_COLOR) -> None:
        """
        Change clock color without changing the time or mode.
        """
        msg = {
            "command": "set_clock_color",
            "color": self._serialize_color(color),
        }
        self._send(msg)

    # ------------------------------------------------------------------------------------------------------------------
    def set_background_color(self, color: ColorType = DEFAULT_BACKGROUND_COLOR) -> None:
        """
        Set the solid background color.
        """
        msg = {
            "command": "set_background_color",
            "color": self._serialize_color(color),
        }
        self._send(msg)

    # ------------------------------------------------------------------------------------------------------------------
    def quit(self) -> None:
        """
        Ask the display to shut down gracefully.
        """
        self._send({"command": "quit"})

    # ------------------------------------------------------------------------------------------------------------------
    # Convenience: combined "direct-style" updates
    # ------------------------------------------------------------------------------------------------------------------
    def update(
        self,
        *,
        background_color: Optional[ColorType] = None,
        title: Optional[Dict[str, Any]] = None,
        text: Optional[Dict[str, Any]] = None,
        icon: Optional[Dict[str, Any]] = None,
        image: Optional[str] = None,
        clock: Optional[Dict[str, Any]] = None,
        text_color: Optional[ColorType] = None,
        title_color: Optional[ColorType] = None,
        clock_color: Optional[ColorType] = None,
        clear: bool = False,
        quit: bool = False,
    ) -> None:
        """
        Send a single combined "direct-style" update, mirroring the display's
        direct JSON format.

        Example:

            client.update(
                background_color=(32, 0, 64),
                title={"text": "Title", "size": 120, "color": (255, 255, 0), "alignment": "center"},
                text={"text": "Hello", "size": 160, "color": (255, 255, 255), "alignment": "center"},
                icon={"icon": "🚀", "size": 160},
                clock={"action": "start", "mode": "replace_text", "color": (0, 255, 255)},
                text_color=(255, 0, 0),
                clock_color=(0, 255, 0),
            )
        """
        msg: Dict[str, Any] = {}

        if background_color is not None:
            msg["background_color"] = self._serialize_color(background_color)

        if title is not None:
            t = dict(title)
            if "color" in t:
                t["color"] = self._serialize_color(t["color"])
            msg["title"] = t

        if text is not None:
            t = dict(text)
            if "color" in t:
                t["color"] = self._serialize_color(t["color"])
            msg["text"] = t

        if icon is not None:
            msg["icon"] = dict(icon)

        if image is not None:
            msg["image"] = image

        if clock is not None:
            c = dict(clock)
            if "color" in c:
                c["color"] = self._serialize_color(c["color"])
            msg["clock"] = c

        if text_color is not None:
            msg["text_color"] = self._serialize_color(text_color)
        if title_color is not None:
            msg["title_color"] = self._serialize_color(title_color)
        if clock_color is not None:
            msg["clock_color"] = self._serialize_color(clock_color)

        if clear:
            msg["clear"] = True

        if quit:
            msg["quit"] = True

        self._send(msg)

    # ------------------------------------------------------------------------------------------------------------------
    # Utility / lifecycle
    # ------------------------------------------------------------------------------------------------------------------
    def close(self) -> None:
        """
        Close the underlying UDP socket. After this, the client cannot be used
        unless re-instantiated.
        """
        try:
            self._sock.close()
        except OSError:
            pass

    def __enter__(self) -> "TestbedDisplayClient":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    # ------------------------------------------------------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------------------------------------------------------
    @staticmethod
    def _serialize_color(color: ColorType) -> Any:
        """
        Normalize color into something JSON-serializable that the display
        understands. The display accepts:

          - [r, g, b]
          - (r, g, b)
          - {"r":..., "g":..., "b":...}

        We convert tuples/dicts into simple [r, g, b] lists.
        """
        if isinstance(color, (list, tuple)) and len(color) == 3:
            return [int(color[0]), int(color[1]), int(color[2])]
        if isinstance(color, dict):
            return [
                int(color.get("r", 0)),
                int(color.get("g", 0)),
                int(color.get("b", 0)),
            ]
        # Fallback / invalid: just return as-is, the server will try to parse or fall back
        return color


# Optional: quick manual test when run as script
if __name__ == "__main__":
    client = TestbedDisplayClient()
    client.clear()
    client.set_background_color((0, 0, 0))
    client.set_title("Experiment 1: Stand Up", color=(255, 255, 255), alignment="left", size=DEFAULT_TITLE_SIZE)
    client.set_text("Hello from TestbedDisplayClient", size=DEFAULT_TEXT_SIZE, color=(255, 255, 255), alignment="center")
    # client.set_icon("🚀", size=DEFAULT_ICON_SIZE)
    client.start_clock(mode="replace_text", color=(0, 255, 255))

    time.sleep(5.05)
    # Color-only updates
    # client.set_text_color((255, 0, 0))
    # client.set_title_color((0, 255, 0))
    client.set_clock_color((255, 0, 0))