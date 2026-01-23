import dataclasses
import enum
import threading
import time
from typing import List, Optional, Any, Callable, Union

from core.utils.callbacks import callback_definition, CallbackContainer
from core.utils.dataclass_utils import update_dataclass_from_dict
from core.utils.dict import update_dict
from core.utils.exit import register_exit_callback
from core.utils.time import IntervalTimer
from extensions.gui.src.lib.objects.objects import Widget


class ServerMode(str, enum.Enum):
    STANDALONE = "standalone"  # you will push directly via send_to_plot
    EXTERNAL = "external"  # same behavior here; enum kept for API symmetry


class UpdateMode(str, enum.Enum):
    CONTINUOUS = "continuous"  # backend thread aggregates latest values and pushes 'update' periodically
    EXTERNAL = "external"  # you manually call backend.update_once(...) when new data arrives


@callback_definition
class Y_Axis_Callbacks:
    update: CallbackContainer


@dataclasses.dataclass
class Y_Axis:
    id: str
    label: str = ""
    side: str = "left"
    precision: int = 2
    grid: bool = True
    show_label: bool = True
    visible: bool = True
    color: List[float] = dataclasses.field(default_factory=lambda: [0.8, 0.8, 0.8, 1.0])
    grid_color: List[float] = dataclasses.field(default_factory=lambda: [0.5, 0.5, 0.5, 0.4])
    min: Optional[float] = None
    max: Optional[float] = None
    highlight_zero: bool = True
    font_size: int = 10

    def __post_init__(self):
        self.callbacks = Y_Axis_Callbacks()

    def get_config(self):
        return {
            "name": self.id,
            "label": self.label or self.id,
            "side": self.side,
            "precision": self.precision,
            "grid": self.grid,
            "show_label": self.show_label,
            "visible": self.visible,
            "color": self.color,
            "grid_color": self.grid_color,
            "min": self.min,
            "max": self.max,
            "highlight_zero": self.highlight_zero,
            "font_size": self.font_size,
        }

    # ------------------------------------------------------------------------------------------------------------------
    def update(self, **patch: Any) -> None:
        """
        Update axis fields from keyword args.
        """
        for k, v in patch.items():
            if hasattr(self, k):
                setattr(self, k, v)

        self.callbacks.update.call(config=self.get_config())

    # ------------------------------------------------------------------------------------------------------------------
    def set_visibility(self, visible: bool):
        self.visible = visible
        self.callbacks.update.call(self.get_config())

    # ------------------------------------------------------------------------------------------------------------------
    def hide(self):
        self.set_visibility(False)

    # ------------------------------------------------------------------------------------------------------------------
    def show(self):
        self.set_visibility(True)
    # ------------------------------------------------------------------------------------------------------------------


# === X AXIS ===========================================================================================================
@callback_definition
class A_Axis_Callbacks:
    update: CallbackContainer


@dataclasses.dataclass
class X_Axis:
    window_time: float = 10
    pre_delay: float = 0.1
    display_format: str = "HH:mm:ss"
    step_display: Any = None

    # ------------------------------------------------------------------------------------------------------------------
    def __post_init__(self):
        self.callbacks = A_Axis_Callbacks()

    # ------------------------------------------------------------------------------------------------------------------
    def get_config(self) -> dict:
        return {
            "window_time": self.window_time,
            "pre_delay": self.pre_delay,
            "display_format": self.display_format,
            "step_display": self.step_display,
        }


# === TIME SERIES ======================================================================================================
@callback_definition
class TimeSeries_Callbacks:
    update: CallbackContainer
    update_value: CallbackContainer


@dataclasses.dataclass
class TimeSeries:
    id: str
    y_axis: str
    name: str = ""
    unit: Optional[str] = None
    color: List[float] | tuple[float] = dataclasses.field(default_factory=lambda: [0.8, 0.8, 0.8, 1.0])
    fill_color: List[float] = dataclasses.field(default_factory=lambda: [0.8, 0.8, 0.8, 0.15])
    fill: bool = False
    tension: float = 0.0
    visible: bool = True
    precision: int = 2
    width: int = 2

    # NEW — line style fields (mirror JS)
    line_dash: Optional[List[float]] = None  # e.g. [6, 4] or None for solid
    line_dash_offset: float = 0.0  # pixels
    line_cap: str = "butt"  # 'butt' | 'round' | 'square'
    line_join: str = "miter"  # 'miter' | 'bevel' | 'round'
    stepped: Union[bool, str] = False  # True | 'before' | 'after' | 'middle'

    # Runtime value (latest)
    value: float = 0.0

    def __post_init__(self):
        self.callbacks = TimeSeries_Callbacks()

    def get_config(self):
        return {
            "id": self.id,
            "name": self.name or self.id,
            "unit": self.unit,
            "color": self.color,
            "fill_color": self.fill_color,
            "fill": bool(self.fill),
            "tension": float(self.tension),
            "visible": bool(self.visible),
            "precision": int(self.precision),
            "width": int(self.width),
            "y_axis": self.y_axis.id if isinstance(self.y_axis, Y_Axis) else self.y_axis,
            # <- JS expects y_axis string id

            # NEW — pass through to Chart.js dataset
            "line_dash": self.line_dash,
            "line_dash_offset": float(self.line_dash_offset),
            "line_cap": self.line_cap,
            "line_join": self.line_join,
            "stepped": self.stepped,
        }

    def update(self, **patch: Any) -> None:
        """
        Update dataset fields.
        """
        for k, v in patch.items():
            if hasattr(self, k):
                setattr(self, k, v)

        self.callbacks.update.call(self.get_config())

    # ------------------------------------------------------------------------------------------------------------------
    def get_data(self):
        return self.value

    # ------------------------------------------------------------------------------------------------------------------
    def set_value(self, value: float):
        self.value = value
        self.callbacks.update_value.call(self.value)

    # ------------------------------------------------------------------------------------------------------------------
    def clear(self):
        raise NotImplementedError

    # ------------------------------------------------------------------------------------------------------------------
    def set_visibility(self, visible: bool):
        self.visible = visible
        self.callbacks.update.call(self.get_config())

    # ------------------------------------------------------------------------------------------------------------------
    def hide(self):
        self.set_visibility(False)

    # ------------------------------------------------------------------------------------------------------------------
    def show(self):
        self.set_visibility(True)
    # ------------------------------------------------------------------------------------------------------------------


# ======================================================================================================================
class RT_Plot_Backend:
    _exit: bool = False

    # === INIT =========================================================================================================
    def __init__(self, id: str,
                 send_function: Callable,
                 update_function: Callable,
                 Ts: float = 0.05,
                 plot_config: dict | None = None,
                 x_axis_config: dict | None = None,
                 **kwargs):
        self.id = id
        self.Ts = Ts
        self.send_function = send_function
        self.update_function = update_function

        default_plot_config = {
            "background_color": [1, 1, 1, 0],
            "time_ticks_color": [0.5, 0.5, 0.5],
            "force_major_ticks": False,

            "show_title": True,
            "title_position": "top",
            "title_font_size": 11,
            "title_color": [0.8, 0.8, 0.8],
            "title": self.id,

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

        self.config = {**default_plot_config, **(plot_config or {}), **kwargs}
        self.y_axes: dict[str, Y_Axis] = {}
        self.time_series: dict[str, TimeSeries] = {}

        # Thread lock to protect concurrent access to time_series and y_axes dicts
        self._lock = threading.Lock()

        if x_axis_config is None:
            x_axis_config = {}

        self.x_axis = X_Axis(**x_axis_config)

        self._thread: Optional[threading.Thread] = None

        self.interval_timer = IntervalTimer(self.Ts, False)

        register_exit_callback(self.stop)

    # === METHODS ======================================================================================================
    def start(self):
        if self._thread is not None:
            return
        self._exit = False
        self._thread = threading.Thread(target=self._task, daemon=True)
        self._thread.start()

    # ------------------------------------------------------------------------------------------------------------------
    def stop(self, *args, **kwargs):
        self._exit = True
        if self._thread is not None and self._thread.is_alive():
            self._thread.join()

    # ------------------------------------------------------------------------------------------------------------------
    def add_y_axis(self, y_axis: str | Y_Axis, config=None) -> Y_Axis:

        if isinstance(y_axis, Y_Axis):
            update_dataclass_from_dict(y_axis, config or {})
            id = y_axis.id
        elif isinstance(y_axis, str):
            id = y_axis
            y_axis = Y_Axis(id, **(config or {}))
        else:
            raise ValueError(f"Invalid type for y_axis: {type(y_axis)}")

        with self._lock:
            if id in self.y_axes:
                raise ValueError(f"Y-axis with id '{id}' already exists.")

            self.y_axes[id] = y_axis

        self.send_function("add_y_axis", y_axis.get_config())

        y_axis.callbacks.update.register(self._update_y_axis_callback,
                                         inputs={'id': id},
                                         lambdas={'config': lambda: y_axis.get_config()},
                                         discard_inputs=True)

        return y_axis

    # ------------------------------------------------------------------------------------------------------------------
    def remove_y_axis(self, id) -> None:

        with self._lock:
            if id not in self.y_axes:
                raise ValueError(f"Y-axis with id '{id}' does not exist.")

            del self.y_axes[id]

        self.send_function("remove_y_axis", id)

    # ------------------------------------------------------------------------------------------------------------------
    def add_timeseries(self, timeseries: TimeSeries | str, config=None) -> TimeSeries:

        if isinstance(timeseries, TimeSeries):
            id = timeseries.id
            update_dataclass_from_dict(timeseries, config or {})
        elif isinstance(timeseries, str):
            id = timeseries
            timeseries = TimeSeries(id, **(config or {}))
        else:
            raise ValueError(f"Invalid type for timeseries: {type(timeseries)}")

        with self._lock:
            if id in self.time_series:
                raise ValueError(f"Timeseries with id '{id}' already exists.")

            self.time_series[id] = timeseries

        self.send_function("add_timeseries", timeseries.get_config())

        timeseries.callbacks.update.register(
            function=self._update_timeseries_callback,
            inputs={'id': id},
            lambdas={'config': lambda: timeseries.get_config()},
            discard_inputs=True,
        )

        return timeseries

    # ------------------------------------------------------------------------------------------------------------------
    def remove_timeseries(self, timeseries: TimeSeries | str) -> None:

        if isinstance(timeseries, TimeSeries):
            timeseries_id = timeseries.id
        elif isinstance(timeseries, str):
            timeseries_id = timeseries
        else:
            raise ValueError(f"Invalid type for timeseries: {type(timeseries)}")

        with self._lock:
            if timeseries_id not in self.time_series:
                return

            del self.time_series[timeseries_id]

        self.send_function("remove_timeseries", timeseries_id)

    # ------------------------------------------------------------------------------------------------------------------
    def remove_all_timeseries(self) -> None:
        with self._lock:
            ts_list = list(self.time_series.values())

        for ts in ts_list:
            self.remove_timeseries(ts)

    # ------------------------------------------------------------------------------------------------------------------
    def update_x_axis(self, config=None, **kwargs) -> None:
        if config is None:
            config = {}

        current_config = self.x_axis.get_config()

        config = update_dict(current_config, config, kwargs, allow_add=False)
        self.x_axis = X_Axis(**config)
        self.send_function("update_x_axis", self.x_axis.get_config())

    # ------------------------------------------------------------------------------------------------------------------
    def clear(self) -> None:
        self.send_function("clear", {})

    # ------------------------------------------------------------------------------------------------------------------
    def get_config(self) -> dict:
        config = {
            'x_axis': self.x_axis.get_config(),
            **self.config
        }
        return config

    # ------------------------------------------------------------------------------------------------------------------
    def get_payload(self) -> dict:
        with self._lock:
            # Create snapshots of the dicts
            y_axes_snapshot = dict(self.y_axes)
            timeseries_snapshot = dict(self.time_series)

        payload = {
            'id': self.id,
            'config': self.get_config(),
            'y_axes': {k: value.get_config() for k, value in y_axes_snapshot.items()},
            'timeseries': {k: value.get_config() for k, value in timeseries_snapshot.items()},
        }
        return payload

    # ------------------------------------------------------------------------------------------------------------------
    def get_data(self) -> dict:
        with self._lock:
            # Hold lock during iteration - safe since get_data() is fast (just returns self.value)
            data = {k: ts.get_data() for k, ts in self.time_series.items()}
        return data

    # === PRIVATE METHODS ==============================================================================================
    def _task(self) -> None:
        self.interval_timer.reset()
        while not self._exit:
            self._send_value_update()
            self.interval_timer.sleep_until_next()

    # ------------------------------------------------------------------------------------------------------------------
    def _send_value_update(self) -> None:

        timestamp = time.time()
        timeseries_data = self.get_data()
        data = {
            'time': timestamp,
            'timeseries': timeseries_data,
        }
        self.update_function(data)

    # ------------------------------------------------------------------------------------------------------------------
    def _update_y_axis_callback(self, id, config):
        self.send_function("update_y_axis", {"id": id, "config": config})

    # ------------------------------------------------------------------------------------------------------------------
    def _update_timeseries_callback(self, id, config):
        self.send_function("update_timeseries", {"id": id, "config": config})


# === WIDGET ===========================================================================================================
class RT_Plot_Widget(Widget):
    type = 'rt_plot'

    def __init__(self, widget_id: str | None = None, plot_config=None, **kwargs):
        super().__init__(widget_id, **kwargs)

        self.plot = RT_Plot_Backend(f"{widget_id}_plot",
                                    send_function=self._send_to_plot,
                                    update_function=self._update_plot,
                                    **plot_config or {},
                                    **kwargs)

    def getConfiguration(self) -> dict:
        config = super().getConfiguration()
        return config

    def getPayload(self) -> dict:
        payload = super().getPayload()
        payload['plot'] = self.plot.get_payload()
        return payload

    def onFirstBuilt(self):
        self.plot.start()

    def handleEvent(self, message, sender=None) -> None:
        pass

    def _send_to_plot(self, message_type, payload: dict):
        self.function(function_name='send_to_plot',
                      args={
                          'message_type': message_type,
                          'payload': payload,
                      },
                      )

    def _update_plot(self, update_data: dict) -> None:
        self.sendUpdate(update_data)
