import {Widget} from "../objects.js";
import {getColor, shadeColor} from "../../helpers.js";
import {JSPlot} from "../../plot/realtime/archive/rt_plot_old.js";
import {LinePlot} from "../../plot/lineplot/lineplot.js";

export class RT_PlotWidget extends Widget {
    constructor(id, config = {}) {
        super(id, config);

        const default_configuration = {}

        this.configuration = {...default_configuration, ...this.configuration};

        this.element = document.createElement('div');
        this.element.id = 'plot_container';
        //Add style classes
        this.element.classList.add('widget', 'plot-wrapper');
        // this.element.className = 'plot-wrapper';

        this.plot = new JSPlot(this.element, this.configuration.config, this.configuration.plot_config);
        this.plot.initializePlot(this.configuration);
        this.configureElement(this.element);
        this.assignListeners(this.element);
    }

    sendToPlot(data) {
        this.plot.handleMessage(data)
    }

    assignListeners(element) {
        super.assignListeners(element);
    }

    configureElement(element) {
        super.configureElement(element);
    }

    getElement() {
        return this.element;
    }

    updateConfig(data) {

    }

    update(data) {
        this.plot.update(data.data);
    }

    initializeElement() {
    }

    resize() {
    }
}