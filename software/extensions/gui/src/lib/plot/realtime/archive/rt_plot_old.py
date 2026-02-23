from __future__ import annotations

import enum
import threading
import time

from core.utils.callbacks import callback_definition, CallbackContainer
from core.utils.exit import register_exit_callback
from core.utils.logging_utils import Logger
from core.utils.websockets import WebsocketServer


# ======================================================================================================================
@callback_definition
class TimeSeriesCallbacks:
    update: CallbackContainer


# ======================================================================================================================
class JSPlotTimeSeries:
    id: str
    name: str
    unit: str
    min: float
    max: float
    precision: int
    fill: bool
    fill_color: list
    width: int

    tension: float

    dimension: int
    value: float

    color: list

    visible: bool

    callbacks: TimeSeriesCallbacks

    def __init__(self,
                 timeseries_id: str,
                 name: str = None,
                 dimension: int = 1,
                 precision: int = 2,
                 unit: str = None,
                 min: float = None,
                 max: float = None,
                 color: list = None,
                 fill: bool = False,
                 fill_color: list = None,
                 width: int = 1,
                 visible: bool = True,
                 y_axis_side: str = 'left',
                 y_axis_grid: bool = True,
                 y_axis_label: str = None,
                 tension: float = 0):

        self.timeseries_id = timeseries_id
        self.name = name if name is not None else timeseries_id
        self.unit = unit
        self.min = min
        self.max = max
        self.dimension = dimension
        self.visible = visible
        self.precision = precision
        self.y_axis_side = y_axis_side
        self.y_axis_grid = y_axis_grid
        self.y_axis_label = y_axis_label
        self.tension = tension

        if dimension != 1:
            raise NotImplementedError("Dimension != 1 not yet implemented")

        self.value = 0

        if color is None:
            color = [0, 0, 0]

        self.color = color

        self.fill = fill

        if fill_color is None:
            fill_color = [0, 0, 0, 0.1]

        self.fill_color = fill_color
        self.width = width

        self.callbacks = TimeSeriesCallbacks()

    # ------------------------------------------------------------------------------------------------------------------
    def setValue(self, value: float):
        self.value = value
        self.callbacks.update.call(self)

    # ------------------------------------------------------------------------------------------------------------------
    def getConfig(self):
        return {
            'timeseries_id': self.timeseries_id,
            'name': self.name,
            'unit': self.unit,
            'min': self.min,
            'max': self.max,
            'dimension': self.dimension,
            'color': self.color,
            'visible': self.visible,
            'precision': self.precision,
            'fill': self.fill,
            'fill_color': self.fill_color,
            'width': self.width,
            'y_axis_side': self.y_axis_side,
            'y_axis_grid': self.y_axis_grid,
            'y_axis_label': self.y_axis_label,
            'tension': self.tension
        }

    # ------------------------------------------------------------------------------------------------------------------
    def getData(self):
        return {
            'timeseries_id': self.timeseries_id,
            'value': self.value,
        }


# ======================================================================================================================
@callback_definition
class JSPlotCallbacks:
    update: CallbackContainer
    timeseries_add: CallbackContainer
    timeseries_remove: CallbackContainer
    clear: CallbackContainer
    close: CallbackContainer


# ==================================================================================================================== #
class ServerMode(enum.StrEnum):
    STANDALONE = 'standalone'
    EXTERNAL = 'external'


class UpdateMode(enum.StrEnum):
    CONTINUOUS = 'continuous'
    EXTERNAL = 'external'


# ======================================================================================================================
class JS_Plot_Realtime:
    timeseries: dict[str, JSPlotTimeSeries]
    websocket_server: WebsocketServer

    plot_config: dict
    callbacks: JSPlotCallbacks

    Ts: float
    _thread: threading.Thread
    _exit: bool

    def __init__(self, name: str,
                 server_mode: ServerMode = ServerMode.STANDALONE,
                 update_mode: UpdateMode = UpdateMode.CONTINUOUS,
                 standalone_host: str = 'localhost',
                 standalone_port: int = 8092,
                 Ts=0.02,
                 plot_config: dict = None,
                 **kwargs):

        default_plot_config = {
            'window_time': 10,  # s
            'pre_delay': 0.2,  # s
            'update_time': 0.1,  # s
            'background_color': [1, 1, 1, 1],  # rgba
            'time_ticks_color': [0.5, 0.5, 0.5],  # rgba
            'time_display_format': 'HH:mm:ss',
            'force_major_ticks': True,
            'show_title': True,
            'title': name,

            'show_legend': True,
        }

        self.plot_config = {**default_plot_config, **(plot_config or {})}
        self.plot_config.update(kwargs)

        self.Ts = Ts
        self.server_mode = server_mode
        self.update_mode = update_mode

        self.standalone_host = standalone_host
        self.standalone_port = standalone_port

        self.timeseries = {}

        self.logger = Logger(f"Plot {name}", 'DEBUG')
        self.callbacks = JSPlotCallbacks()

        if self.server_mode == 'standalone':
            self.server = WebsocketServer(host=standalone_host, port=standalone_port)
            self.server.callbacks.new_client.register(self._on_new_client)
            self.server.callbacks.client_disconnected.register(self._on_client_disconnected)
            self.server.start()

        if self.update_mode == 'continuous':
            self._thread = threading.Thread(target=self._task)
            self._exit = False
            self._thread.start()

        register_exit_callback(self.close)

    # ------------------------------------------------------------------------------------------------------------------
    def addTimeseries(self, timeseries: JSPlotTimeSeries):
        if timeseries.timeseries_id in self.timeseries:
            raise ValueError(f"Timeseries with id {timeseries.timeseries_id} already exists")

        self.timeseries[timeseries.timeseries_id] = timeseries

        message = {
            'type': 'add',
            'data': timeseries.getConfig(),
        }

        if self.server_mode == 'standalone':
            self.server.send(message)

        self.callbacks.timeseries_add.call(message)

        timeseries.callbacks.update.register(self._on_timeseries_update)

    # ------------------------------------------------------------------------------------------------------------------
    def removeTimeseries(self, timeseries: JSPlotTimeSeries):
        if timeseries.timeseries_id in self.timeseries:
            del self.timeseries[timeseries.timeseries_id]

        message = {
            'type': 'remove',
            'data': timeseries.timeseries_id,
        }

        if self.server_mode == 'standalone':
            self.server.send(message)

        self.callbacks.timeseries_remove.call(message)

    # ------------------------------------------------------------------------------------------------------------------
    def getData(self):
        data = {k: v.getData() for k, v in self.timeseries.items()}
        return data

    # ------------------------------------------------------------------------------------------------------------------
    def getTimeseriesConfig(self):
        return {k: v.getConfig() for k, v in self.timeseries.items()}

    # ------------------------------------------------------------------------------------------------------------------
    def clear(self):
        message = {
            'type': 'clear',
        }

        if self.server_mode == 'standalone':
            self.server.send(message)

        self.callbacks.clear.call(message)

    # ------------------------------------------------------------------------------------------------------------------
    def close(self):

        message = {
            'type': 'close',
        }

        if self.server_mode == 'standalone':
            self.server.send(message)
            time.sleep(0.1)
            self.server.stop()

        if self.update_mode == 'continuous':
            if self._thread is not None and self._thread.is_alive():
                self._exit = True
                self._thread.join()

        self.callbacks.close.call(message)

    # ------------------------------------------------------------------------------------------------------------------
    def _task(self):
        while not self._exit:
            message = {
                'type': 'update',
                'data': {
                    'time': time.time(),
                    'timeseries': self.getData(),
                }
            }

            if self.server_mode == 'standalone':
                self.server.send(message)

            self.callbacks.update.call(message)
            time.sleep(self.Ts)

    # ------------------------------------------------------------------------------------------------------------------
    def _on_new_client(self, client):

        self.logger.debug(f"New client connected: {client}")
        message = {
            'type': 'init',
            'config': self.plot_config,
            'timeseries': self.getTimeseriesConfig(),
        }

        self.server.sendToClient(client, message)

    # ------------------------------------------------------------------------------------------------------------------
    def _on_client_disconnected(self, client):
        self.logger.debug(f"Client disconnected: {client}")

    # ------------------------------------------------------------------------------------------------------------------
    def _on_timeseries_update(self, timeseries: JSPlotTimeSeries):
        if self.update_mode == UpdateMode.EXTERNAL:
            message = {
                'type': 'update',
                'time': time.time(),
                'data': self.getData(),
            }
            self.callbacks.update.call(message)