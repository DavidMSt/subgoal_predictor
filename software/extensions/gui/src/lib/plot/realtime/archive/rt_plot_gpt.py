# rt_plot.py
"""
Realtime Plot Backend (Python)
==============================

This module implements a lightweight Python backend that mirrors the features
exposed by the modular JS plot (Chart.js + streaming). It does NOT open a real
WebSocket; instead, it calls a dummy transport function you can replace with your
own network layer later.

Key ideas:
- Mirror the JS "handleMessage" API:
  - 'init'            payload: { config, y_axes, datasets }
  - 'update'          payload: { time?, timeseries: { id: value, ... } | [ {timeseries_id, value}, ... ] }
  - 'clear'           payload: {}
  - 'add_series'      payload: { id, config }
  - 'remove_series'   payload: { id }
  - 'add_y_axis'      payload: { id, config }
  - 'remove_y_axis'   payload: { id }
  - 'update_series'   payload: { id, config }
  - 'update_y_axis'   payload: { id, config }
  - 'update_x_axis'   payload: { ...partial plot config... }

- Two layers:
  1) RTPlotBackend: owns timeseries & y-axes, builds messages, pushes them through transport.
  2) PlotWidget: a tiny facade that's convenient to embed in your app.

Replace `send_to_plot()` to wire up your WebSocket transport.
"""

from __future__ import annotations

import enum
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


# ----------------------------------------------------------------------------------------------------------------------
# Transport (DUMMY) — replace with your WebSocket or any IPC of your choice
# ----------------------------------------------------------------------------------------------------------------------

def send_to_plot(message_type: str, payload: dict) -> None:
    """
    Dummy transport for messages to the frontend plot.

    Replace this function's body with your WebSocket send routine, e.g.:
        ws.send(json.dumps({ "type": message_type, **payload }))
    or your server's broadcast method.

    Args:
        message_type: One of the message types listed above.
        payload:      JSON-serializable dict.
    """
    # NOTE: Replace this with your actual sending logic.
    # For now we just print for visibility.
    print(f"[PLOT TX] type={message_type} payload_keys={list(payload.keys())}")


# ----------------------------------------------------------------------------------------------------------------------
# Enums
# ----------------------------------------------------------------------------------------------------------------------

class ServerMode(str, enum.Enum):
    STANDALONE = "standalone"  # you will push directly via send_to_plot
    EXTERNAL = "external"  # same behavior here; enum kept for API symmetry


class UpdateMode(str, enum.Enum):
    CONTINUOUS = "continuous"  # backend thread aggregates latest values and pushes 'update' periodically
    EXTERNAL = "external"  # you manually call backend.update_once(...) when new data arrives


# ----------------------------------------------------------------------------------------------------------------------
# Data classes for Y-Axis and Time Series
# ----------------------------------------------------------------------------------------------------------------------

def _rgba_or_default(value: Optional[List[float]], default: List[float]) -> List[float]:
    if not value:
        return list(default)
    return list(value)


@dataclass
class YAxis:
    """
    Backend representation of a Y-axis. Mirrors the fields used by the JS plot.

    Important fields:
        id:         unique id for the scale (used by datasets.yAxisID in Chart.js)
        label:      title of the axis
        side:       'left' | 'right'
        precision:  tick label precision
        grid:       show grid lines
        show_label: whether to display label
        visible:    toggles tick/grid visibility
        color:      RGBA in [0..1] list
        grid_color: RGBA in [0..1] list
        min/max:    numeric or None
        highlight_zero: thicker line at y=0
        font_size:  tick font size
    """
    id: str
    label: str = ""
    side: str = "left"
    precision: int = 2
    grid: bool = True
    show_label: bool = True
    visible: bool = True
    color: List[float] = field(default_factory=lambda: [0.8, 0.8, 0.8, 1.0])
    grid_color: List[float] = field(default_factory=lambda: [0.5, 0.5, 0.5, 0.4])
    min: Optional[float] = None
    max: Optional[float] = None
    highlight_zero: bool = True
    font_size: int = 10

    def to_js_config(self) -> dict:
        """
        Serialize to the Y-axis config expected by the JS plot.
        """
        return {
            "name": self.id,
            "label": self.label or self.id,
            "side": self.side,
            "precision": self.precision,
            "grid": self.grid,
            "show_label": self.show_label,
            "visible": self.visible,
            "color": _rgba_or_default(self.color, [0.8, 0.8, 0.8, 1.0]),
            "grid_color": _rgba_or_default(self.grid_color, [0.5, 0.5, 0.5, 0.4]),
            "min": self.min,
            "max": self.max,
            "highlight_zero": self.highlight_zero,
            "font_size": self.font_size,
        }

    def update(self, **patch: Any) -> None:
        """
        Update axis fields from keyword args.
        """
        for k, v in patch.items():
            if hasattr(self, k):
                setattr(self, k, v)


@dataclass
class TimeSeries:
    """
    Backend representation of a single dataset (a time series).

    Required:
        id:      unique id for the dataset
        y_axis:  the YAxis id to attach to

    Visual config matches the JS dataset config:
        name, unit, color, fill_color, fill, tension, visible, precision, width
    """
    id: str
    y_axis: str
    name: str = ""
    unit: Optional[str] = None
    color: List[float] = field(default_factory=lambda: [0.8, 0.8, 0.8, 1.0])
    fill_color: List[float] = field(default_factory=lambda: [0.8, 0.8, 0.8, 0.15])
    fill: bool = False
    tension: float = 0.1
    visible: bool = True
    precision: int = 2
    width: int = 2

    # Runtime value (latest)
    value: float = 0.0

    def to_js_config(self) -> dict:
        """
        Serialize to the dataset config expected by the JS plot.
        """
        return {
            "name": self.name or self.id,
            "unit": self.unit,
            "color": _rgba_or_default(self.color, [0.8, 0.8, 0.8, 1.0]),
            "fill_color": _rgba_or_default(self.fill_color, [0.8, 0.8, 0.8, 0.15]),
            "fill": bool(self.fill),
            "tension": float(self.tension),
            "visible": bool(self.visible),
            "precision": int(self.precision),
            "width": int(self.width),
            "y_axis": self.y_axis,  # <- JS expects y_axis string id
        }

    def update(self, **patch: Any) -> None:
        """
        Update dataset fields.
        """
        for k, v in patch.items():
            if hasattr(self, k):
                setattr(self, k, v)


# ----------------------------------------------------------------------------------------------------------------------
# Backend
# ----------------------------------------------------------------------------------------------------------------------

class RTPlotBackend:
    """
    Plot backend that manages Y-axes and Time Series and sends messages to the JS plot.

    Methods you can call at runtime (mirrors JS API):
      - init_full()                   -> sends a full "init" snapshot
      - add_y_axis(id, **cfg)         -> 'add_y_axis'
      - remove_y_axis(id)             -> 'remove_y_axis'
      - update_y_axis(id, **patch)    -> 'update_y_axis'
      - add_series(id, **cfg)         -> 'add_series'
      - remove_series(id)             -> 'remove_series'
      - update_series(id, **patch)    -> 'update_series'
      - update_x_axis(**patch)        -> 'update_x_axis'
      - clear()                       -> 'clear'
      - update_once(data_map)         -> sends a single 'update' with your dict of values
      - start() / stop()              -> control the continuous update thread (if UpdateMode.CONTINUOUS)

    Config:
      - plot_config: dict with the global (X-axis/legend/title/…) options.
      - Ts: update period (seconds) for continuous mode.

    Transport:
      - Uses send_to_plot(message_type, payload); swap that with your WebSocket bridge.
    """

    def __init__(
            self,
            name: str,
            server_mode: ServerMode = ServerMode.STANDALONE,
            update_mode: UpdateMode = UpdateMode.CONTINUOUS,
            Ts: float = 0.05,
            plot_config: Optional[dict] = None,
            **kwargs: Any,
    ) -> None:
        # ---- defaults (mirrors your JS defaults) ----
        default_plot_config = {
            "window_time": 10,
            "pre_delay": 0.1,
            "update_time": 0.1,
            "background_color": [1, 1, 1, 0],
            "time_ticks_color": [0.5, 0.5, 0.5],
            "force_major_ticks": False,
            "time_display_format": "HH:mm:ss",
            "time_step_display": None,

            "show_title": True,
            "title_position": "top",
            "title_font_size": 11,
            "title_color": [0.8, 0.8, 0.8],
            "title": name,

            "show_legend": True,
            "legend_position": "bottom",
            "legend_align": "start",
            "legend_fullsize": False,
            "legend_font_size": 10,
            "legend_label_type": "point",
            "legend_label_size": 6,

            "use_queue": False,
            "use_local_time": True,
            "max_points_per_dataset": 5000,
        }

        self.plot_config: Dict[str, Any] = {**default_plot_config, **(plot_config or {})}
        self.plot_config.update(kwargs or {})

        self.name = name
        self.server_mode = server_mode
        self.update_mode = update_mode
        self.Ts = float(Ts)

        self.y_axes: Dict[str, YAxis] = {}
        self.series: Dict[str, TimeSeries] = {}

        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    # --------------- helpers ---------------

    def _send(self, message_type: str, payload: dict) -> None:
        """
        Centralized transport call in case you later want to add instrumentation.
        """
        send_to_plot(message_type, payload)

    def _snapshot_payload(self) -> dict:
        """
        Build a full snapshot payload suitable for 'init'.
        """
        y_axes_cfg = {ax_id: ax.to_js_config() for ax_id, ax in self.y_axes.items()}
        datasets_cfg = {sid: s.to_js_config() for sid, s in self.series.items()}
        return {
            "config": dict(self.plot_config),
            "y_axes": y_axes_cfg,
            "datasets": datasets_cfg,
        }

    # --------------- lifecycle ---------------

    def init_full(self) -> None:
        """
        Send a full 'init' to (re)build the plot on the frontend.
        """
        self._send("init", {"payload": self._snapshot_payload()})

    def start(self) -> None:
        """
        Start continuous mode updates (if not already running).
        """
        if self.update_mode != UpdateMode.CONTINUOUS:
            return
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._task_loop, name=f"RTPlotBackend[{self.name}]")
        self._thread.daemon = True
        self._thread.start()

    def stop(self) -> None:
        """
        Stop continuous updates.
        """
        if self._thread and self._thread.is_alive():
            self._stop_event.set()
            self._thread.join(timeout=2.0)
        self._thread = None

    # --------------- thread loop ---------------

    def _task_loop(self) -> None:
        """
        Periodically push latest values. The frontend may use local time if configured,
        so we only include 'time' when use_local_time=False (but it's safe to include anyway).
        """
        while not self._stop_event.is_set():
            self._push_update_now()
            self._stop_event.wait(self.Ts)

    def _push_update_now(self) -> None:
        """
        Gather current series values and send a single 'update'.
        """
        now_sec = time.time()
        timeseries_values = {sid: s.value for sid, s in self.series.items()}
        payload = {
            "time": now_sec,
            "timeseries": timeseries_values,  # dict format (JS supports dict or array)
        }
        self._send("update", payload)

    # --------------- public API mirroring JS ---------------

    # Y-axes
    def add_y_axis(self, axis_id: str, **cfg: Any) -> YAxis:
        ax = self.y_axes.get(axis_id)
        if ax is None:
            ax = YAxis(id=axis_id, label=cfg.pop("label", axis_id))
            ax.update(**cfg)
            self.y_axes[axis_id] = ax
            self._send("add_y_axis", {"id": axis_id, "config": ax.to_js_config()})
        else:
            # Acts like update when already exists
            ax.update(**cfg)
            self._send("update_y_axis", {"id": axis_id, "config": ax.to_js_config()})
        return ax

    def remove_y_axis(self, axis_id: str) -> None:
        if axis_id in self.y_axes:
            del self.y_axes[axis_id]
            self._send("remove_y_axis", {"id": axis_id})
            # NOTE: We do not automatically remove or reassign series; do that explicitly.

    def update_y_axis(self, axis_id: str, **patch: Any) -> None:
        ax = self.y_axes.get(axis_id)
        if not ax:
            return
        ax.update(**patch)
        self._send("update_y_axis", {"id": axis_id, "config": ax.to_js_config()})

    # Series
    def add_series(self, series_id: str, **cfg: Any) -> TimeSeries:
        """
        cfg must include 'y_axis' (string id). If the y-axis does not exist yet,
        we'll create it with defaults.
        """
        y_axis = cfg.get("y_axis") or cfg.get("yAxis") or cfg.get("y_axis_id")
        if not y_axis:
            raise ValueError("add_series requires cfg['y_axis']")

        if y_axis not in self.y_axes:
            # Create the target axis with defaults to match JS convenience behavior.
            self.add_y_axis(y_axis)

        ts = self.series.get(series_id)
        if ts is None:
            ts = TimeSeries(id=series_id, y_axis=y_axis)
            ts.update(**cfg)
            self.series[series_id] = ts
            self._send("add_series", {"id": series_id, "config": ts.to_js_config()})
        else:
            # Update if exists
            ts.update(**cfg)
            self._send("update_series", {"id": series_id, "config": ts.to_js_config()})

        return ts

    def remove_series(self, series_id: str) -> None:
        if series_id in self.series:
            del self.series[series_id]
            self._send("remove_series", {"id": series_id})

    def update_series(self, series_id: str, **patch: Any) -> None:
        ts = self.series.get(series_id)
        if not ts:
            return
        # If patch changes the y_axis, ensure it exists
        if "y_axis" in patch and patch["y_axis"] and patch["y_axis"] not in self.y_axes:
            self.add_y_axis(patch["y_axis"])
        ts.update(**patch)
        self._send("update_series", {"id": series_id, "config": ts.to_js_config()})

    # X-axis / global config
    def update_x_axis(self, **patch: Any) -> None:
        """
        Patch the plot's global config and send 'update_x_axis'.
        Common fields include window_time, update_time, pre_delay, time_display_format, time_step_display, etc.
        """
        self.plot_config.update(patch)
        self._send("update_x_axis", {"config": dict(patch)})

    # Data operations
    def clear(self) -> None:
        self._send("clear", {})

    def update_once(self, values: Dict[str, float], time_sec: Optional[float] = None) -> None:
        """
        EXTERNAL update: send one 'update' with supplied values.
        Also updates the cached "latest" values for those series.
        """
        now = time.time() if time_sec is None else float(time_sec)
        for sid, v in values.items():
            if sid in self.series:
                self.series[sid].value = float(v)
        payload = {"time": now, "timeseries": dict(values)}
        self._send("update", payload)

    # Convenience
    def set_value(self, series_id: str, value: float) -> None:
        """
        Set the latest value for a series (used by CONTINUOUS mode loop).
        """
        ts = self.series.get(series_id)
        if not ts:
            return
        ts.value = float(value)
