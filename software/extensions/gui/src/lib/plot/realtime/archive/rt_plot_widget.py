from typing import Any

from extensions.gui.src.lib.objects.objects import Widget
from extensions.gui.src.lib.plot.realtime.rt_plot import ServerMode, UpdateMode

used_ports = []
PORT_START = 9000


def get_next_port():
    global PORT_START
    port = PORT_START
    while port in used_ports:
        port += 1
    used_ports.append(port)
    return port


class PlotWidget(Widget):
    type = 'plot'
    plot: JS_Plot_Realtime

    # === INIT =========================================================================================================
    def __init__(self, widget_id: str, title: str = None, config=None, plot_config=None, **kwargs):
        super().__init__(widget_id)

        default_config = {
            'server_mode': ServerMode.STANDALONE,
            'update_mode': UpdateMode.CONTINUOUS,
            'host': 'localhost',
            'port': None,
            'Ts': 0.05,
        }

        default_plot_config = {
            'window_time': 10,  # s
            'pre_delay': 0.2,  # s
            'update_time': 0.1,  # s
            'background_color': [1, 1, 1, 0.02],  # rgba
            'time_ticks_color': [0.5, 0.5, 0.5, 0.5],  # rgba
            'time_display_format': 'HH:mm:ss',

            'show_title': True,
            'title': title if title is not None else id,

            'show_legend': True,
        }

        self.config = {**default_config, **(config or {})}
        self.config.update(kwargs)

        if self.config['update_mode'] == UpdateMode.EXTERNAL:
            raise NotImplementedError("External update mode is not yet supported in PlotWidget.")

        self.plot_config = {**default_plot_config, **(plot_config or {})}
        self.plot_config.update(kwargs)

        if self.config['server_mode'] == ServerMode.STANDALONE:
            if self.config['port'] in used_ports:
                raise ValueError(f"Port {self.config['port']} is already in use.")

            if self.config['port'] is None:
                self.config['port'] = get_next_port()
                print(f"Using port {self.config['port']} for plot {self.id}")

        self.plot = JS_Plot_Realtime(
            name=self.id,
            server_mode=self.config['server_mode'],
            update_mode=self.config['update_mode'],
            standalone_host=self.config['host'],
            standalone_port=self.config['port'],
            Ts=self.config['Ts'],
            plot_config=self.plot_config,
        )

        self.plot.callbacks.timeseries_add.register(self._on_timeseries_add)
        self.plot.callbacks.clear.register(self._on_clear_plot)
        self.plot.callbacks.update.register(self._on_plot_update)

    # === METHODS ======================================================================================================
    def getConfiguration(self) -> dict:
        config = {
            'type': self.type,
            'id': self.id,
            'config': self.config,
            'plot_config': {**self.plot.plot_config, **self.plot_config},
            'timeseries': self.plot.getTimeseriesConfig()
        }
        return config

    # ------------------------------------------------------------------------------------------------------------------
    def setValue(self, timeseries_id, value):
        ...

    # ------------------------------------------------------------------------------------------------------------------
    def update(self, data):
        self.sendUpdate(data)

    # ------------------------------------------------------------------------------------------------------------------
    def sendToPlot(self, data: dict):
        self.function('sendToPlot',
                      args=data)

    # ------------------------------------------------------------------------------------------------------------------
    def handleEvent(self, message, sender=None) -> Any:
        pass

    # ------------------------------------------------------------------------------------------------------------------
    def updateConfig(self, *args, **kwargs):
        pass

    # ------------------------------------------------------------------------------------------------------------------
    def init(self, *args, **kwargs):
        pass

    # ------------------------------------------------------------------------------------------------------------------
    def _on_timeseries_add(self, message):
        if self.plot.server_mode == ServerMode.EXTERNAL:
            self.sendToPlot(message)

    # ------------------------------------------------------------------------------------------------------------------
    def _on_clear_plot(self, message):
        if self.plot.server_mode == ServerMode.EXTERNAL:
            self.sendToPlot(message)

    # ------------------------------------------------------------------------------------------------------------------
    def _on_plot_update(self, message):
        if self.plot.server_mode == ServerMode.EXTERNAL:
            self.update(message)

    # ------------------------------------------------------------------------------------------------------------------
    def __del__(self):
        self.plot.close()
        if self.plot.standalone_port in used_ports:
            used_ports.remove(self.plot.standalone_port)
    # ------------------------------------------------------------------------------------------------------------------
