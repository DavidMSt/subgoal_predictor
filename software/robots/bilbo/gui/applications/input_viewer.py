from robots.bilbo.definitions import EXPERIMENT_DIR
from core.utils.exit import register_exit_callback
from core.utils.files import file_exists
from extensions.gui.src.lib.objects.python.buttons import Button
from extensions.gui.src.lib.objects.python.directory import DirectoryWidget
from extensions.gui.src.lib.objects.python.popup import Popup
from extensions.gui.src.lib.objects.python.popup_application import GUI_Popup_Application
from extensions.gui.src.lib.plot.lineplot.lineplot_widget import LinePlot, LinePlotWidget
from robots.bilbo.robot.experiment.experiment_definitions import read_input_file


# === INPUT VIEWER APPLICATION =========================================================================================
class InputViewerApplication(GUI_Popup_Application):

    # === INIT =========================================================================================================
    def __init__(self, config: dict = None):
        super().__init__('input_viewer', 'Input Viewer', config)

        self.popup = Popup(f"{self.id}_popup",
                           title='Input Viewer',
                           allow_multiple=True,
                           grid=[10, 10],
                           size=[800, 500],
                           type='window')

        self._buildPopup()

        register_exit_callback(self.close)

    # === METHODS ======================================================================================================
    def onMessage(self, message, sender=None) -> None:
        pass

    # ------------------------------------------------------------------------------------------------------------------
    def getConfiguration(self):
        config = super().getConfiguration()
        return config

    # ------------------------------------------------------------------------------------------------------------------
    def close(self, *args, **kwargs):
        self.popup.close()
        self.directory_widget.close()

    # === PRIVATE METHODS ==============================================================================================
    def _onPopupClosed(self, *args, **kwargs):
        self.logger.debug(f"Application closed: {args}, {kwargs}")

    # ------------------------------------------------------------------------------------------------------------------
    def _buildPopup(self):
        # Add the file viewer
        self.directory_widget = DirectoryWidget(widget_id='directory_widget',
                                                directory=EXPERIMENT_DIR,
                                                title='Experiment Directory',
                                                included_extensions=['bitrj'])
        self.directory_widget.callbacks.file_double_clicked.register(self._fileDoubleClicked)

        self.popup.group.addWidget(self.directory_widget, row=2, column=1, width=4, height=9)

        self.close_button = Button(widget_id='close_button', text='Close', color=[0.6, 0.2, 0.2])
        self.popup.group.addWidget(self.close_button, row=10, column=9, width=2, height=1)
        self.close_button.callbacks.click.register(self._closeButtonClicked)

        # Plot
        self.plot_widget = LinePlotWidget(widget_id='plot_widget', title='Input')
        self.popup.group.addWidget(self.plot_widget, row=2, column=5, width=6, height=7)

    # ------------------------------------------------------------------------------------------------------------------
    def _closeButtonClicked(self, sender, *args, **kwargs):
        self.close()

    # ------------------------------------------------------------------------------------------------------------------
    def _fileDoubleClicked(self, file, *args, **kwargs):
        self._plotInputFile(file)

    # ------------------------------------------------------------------------------------------------------------------
    def _plotInputFile(self, file):
        self.plot_widget.plot.clear()

        # 1. Check if the file exists
        file_path = f"{EXPERIMENT_DIR}/{file}"
        if not file_exists(file_path):
            self.logger.error(f"File does not exist: {file_path}")
            return

        # 2. Load the file
        file_data = read_input_file(file_path)

        trajectory_name = file_data.name
        time_vector = file_data.trajectory.time_vector
        inputs = file_data.trajectory.inputs

        input_left = [inputs[i].left for i in sorted(inputs)]
        input_right = [inputs[i].right for i in sorted(inputs)]

        # 3. Configure the plot
        self.plot_widget.plot.add_y_axis('torque', label='Torque [Nm]')
        left_series = self.plot_widget.plot.add_series('left',
                                                       y_axis='torque',
                                                       width=2,
                                                       color=[204 / 255, 255 / 255, 0])

        right_series = self.plot_widget.plot.add_series('right',
                                                        y_axis='torque',
                                                        width=2,
                                                        color=[48 / 255, 92 / 255, 222 / 255])

        self.plot_widget.plot.x_axis.set(min=0, max=time_vector[-1], ticks_mode='auto', label='Time [s]')

        # 4. Plot the data
        left_series.extend(zip(time_vector, input_left))
        right_series.extend(zip(time_vector, input_right))
