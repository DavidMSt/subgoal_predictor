// import Chart from "chart.js/auto";
// import 'chartjs-adapter-moment';
// import streamingPlugin from 'chartjs-plugin-streaming';
// import './rt_plot.css';
// import {getColor, interpolateColors} from "../../helpers.js";
// import {Widget} from "../../objects/objects.js";
//
//
// // =====================================================================================================================
// const forceMajorTicks = {
//     id: 'forceMajorTicks',
//
//     afterBuildTicks(chart, args, options) {
//         const scale = args.scale;
//         // only Y axes
//         if (scale.axis !== 'y') return;
//
//         const ticks = scale.ticks;
//
//         // --- ensure zero is major ---
//         let zero = ticks.find(t => t.value === 0);
//         if (zero) {
//             if (!zero.major) {
//                 zero.major = true;
//             }
//         } else {
//             ticks.push({value: 0, label: '0', major: true});
//         }
//
//         // if we injected zero, re-sort so ordering stays numeric
//         ticks.sort((a, b) => a.value - b.value);
//
//         // --- force the first and last tick to be major ---
//         if (ticks.length) {
//             ticks[0].major = true;
//             ticks[ticks.length - 1].major = true;
//         }
//     }
// };
//
// const backgroundcolor_plugin = {
//     id: 'customCanvasBackgroundColor',
//     beforeDraw: (chart, args, options) => {
//         const ctx = chart.ctx;
//         ctx.save();
//         ctx.globalCompositeOperation = 'destination-over';
//         ctx.fillStyle = options.color || '#99ffff';
//         ctx.fillRect(0, 0, chart.width, chart.height);
//         ctx.restore();
//     }
// };
//
// const defaultLegendClick = Chart.defaults.plugins.legend.onClick;
// const defaultGenerateLabels = Chart.defaults.plugins.legend.labels.generateLabels;
// Chart.register(streamingPlugin);
//
// // =====================================================================================================================
// class RT_Plot_Y_Axis {
//
//     /** @type {object} */ chart_config;
//
//     constructor(id, config = {}) {
//         this.id = id;
//
//         const default_config = {
//             name: id,
//             color: [0.8, 0.8, 0.8, 1],
//             grid_color: [0.5, 0.5, 0.5, 0.5],
//             visible: true,
//             side: 'left',  // Options: 'left', 'right'
//             show_label: true,
//             label: id,
//             font_size: 10,
//             precision: 2,
//             grid: true,
//             highlight_zero: true,
//             min: null,
//             max: null,
//         }
//
//         this.config = {...default_config, ...config};
//     }
//
//     get_chart_config() {
//         const cfg = this.config;
//         const chart_config = {
//             type: 'linear',
//             position: cfg.side,
//             title: {
//                 display: cfg.show_label,
//                 text: cfg.label
//             },
//             beginAtZero: true,
//             ticks: {
//                 color: getColor(cfg.color),
//                 // autoSkip: false,
//                 major: {enabled: true},
//                 font: {
//                     size: cfg.font_size,
//                 },
//                 callback: (value) => value.toFixed(cfg.precision)
//             },
//             grid: {
//                 display: cfg.grid,
//                 drawOnChartArea: cfg.grid,
//                 // borderColor: getColor(this.plot_config.y_grid_color),
//                 borderColor: interpolateColors(cfg.color, cfg.grid_color, 0.5),
//                 lineWidth: ctx => cfg.highlight_zero && ctx.tick.value === 0 ? 2 : 1,
//                 color: ctx => {
//                     const isZero = cfg.highlight_zero && ctx.tick.value === 0;
//                     // parse your existing borderColor to RGBA components:
//                     const [r, g, b] = cfg.grid_color
//                         .slice(0, 3)
//                         .map(c => Math.round(c * 255));
//                     const alpha = isZero ? 1 : 0.4;
//                     return `rgba(${r}, ${g}, ${b}, ${alpha})`;
//                 }
//             },
//         };
//         if (cfg.min !== null && cfg.min !== undefined) chart_config.min = cfg.min;
//         if (cfg.max !== null && cfg.max !== undefined) chart_config.max = cfg.max;
//
//         return chart_config;
//     }
//
//
// }
//
// class RT_Plot_TimeSeries {
//
//     /** @type {RT_Plot_Y_Axis} */ y_axis = null;
//     /** @type {Array} */ data = null;
//
//
//     constructor(id, config = {}) {
//         this.id = id;
//
//         const default_config = {
//             color: [0.8, 0.8, 0.8, 1],
//             fill_color: [0.8, 0.8, 0.8, 0.2],
//             fill: false,
//             name: id,
//             unit: null,
//             tension: 0.1,
//             visible: true,
//             precision: 2,
//         }
//
//         this.config = {...default_config, ...config};
//         this.data = {};
//
//         this.chart_series = null;
//
//     }
//
//     get_config() {
//
//         return {
//             label: this.config.name,
//             unit: this.config.unit,
//             seriesId: this.id,
//             yAxisID: this.y_axis.id,
//             fill: this.config.fill,
//             borderColor: getColor(this.config.color),
//             backgroundColor: getColor(this.config.fill_color),
//             hidden: this.config.visible,
//
//             data: [],
//         };
//
//     }
//
//     update(data) {
//         const t = data.time * 1000;
//         const y = data.value;
//         this.data.push({x: t, y: y});
//         if (this.data.length > 1000) {
//             this.data.shift();
//         }
//     }
//
//     get_data() {
//         return this.data;
//     }
//
//     get_last_value() {
//         if (this.data.length === 0) return null;
//         return this.data[this.data.length - 1];
//     }
//
//     clear() {
//         this.data = [];
//     }
//
//
// }
//
//
// class RT_Plot {
//
//     /** @type {object} */ y_axes = {};
//     /** @type {object} */ timeseries = {};
//
//     constructor(id, container, payload = {}) {
//         this.id = id;
//         this.container = container;
//
//         const default_config = {
//             window_time: 10,
//             pre_delay: 0.1,
//             update_time: 0.1,
//             background_color: [1, 1, 1, 0],
//             time_ticks_color: [0.5, 0.5, 0.5],
//             y_grid_color: [0.5, 0.5, 0.5, 0.5],
//             force_major_ticks: false,
//             time_display_format: 'HH:mm:ss',
//             time_step_display: null,
//             highlight_zero: true,
//             y_axis_font_size: 10,
//             y_axis_show_label: false,
//             show_title: true,
//             title_position: 'top',  // Options: 'top', 'left', 'bottom', 'right''
//             title_font_size: 11,
//             title_color: [0.8, 0.8, 0.8],
//
//             show_legend: true,
//             legend_position: 'bottom',  // Options: 'top', 'left', 'bottom', 'right', 'chartArea'
//             legend_align: 'start',  // Options: 'start', 'center', 'end'
//             legend_fullsize: false,
//             legend_font_size: 7,
//             legend_label_type: 'point', // Options: 'box', 'point'
//             legend_label_size: 5,
//
//             use_queue: false,
//             use_local_time: true, // Use local time for x-axis, otherwise use server time
//         }
//
//         this.config = {...default_config, ...payload.config};
//         this.timeseries = {};
//         this.y_axes = {};
//
//         this.createPlotCanvas();
//
//         this.configure_plot(payload);
//
//
//         // Add a resize observer to the plot container
//         const ro = new ResizeObserver(() => this.plot.resize());
//         ro.observe(this.container);
//
//
//         // this._queue = {}; // TODO: Not used
//         // this._lastValue = {};
//
//         if (this.config.server_mode === 'standalone') {
//             const websocket_url = `ws://${this.config.host}:${this.config.port}`;
//             this._connect(websocket_url);
//         }
//
//
//     }
//
//     /* -------------------------------------------------------------------------------------------------------------- */
//     createPlotCanvas() {
//         const canvas = document.createElement('canvas');
//         canvas.style.width = '100%';
//         canvas.style.height = '100%';
//         canvas.style.display = 'block';
//         canvas.style.background = 'rgba(255, 255, 255, 0)';
//         this.container.appendChild(canvas);
//         this.canvas = canvas;
//         this.ctx = this.canvas.getContext('2d');
//     }
//
//     /* -------------------------------------------------------------------------------------------------------------- */
//     configure_plot(payload) {
//         const config = this.config;
//         const x_axis_config = payload.x_axis || {};
//         const y_axes = payload.y_axes || {};
//         const timeseries = payload.datasets || {};
//
//
//         this.chartPlugins = [backgroundcolor_plugin];
//         if (config.force_major_ticks) {
//             this.chartPlugins.push(forceMajorTicks);
//         }
//
//         // Loop over the y-axes and create them
//         for (const [id, y_axis_config] of Object.entries(y_axes)) {
//             this.addYAxis(id, y_axis_config);
//         }
//
//         // Loop over the timeseries and create them
//         for (const [id, timeseries_config] of Object.entries(timeseries)) {
//             this.addTimeSeries(id, timeseries_config);
//         }
//
//
//         // Create the datasets
//         const datasets = this._get_datasets();
//
//         // Create the plot
//         this.plot = new Chart(this.ctx, {
//             type: 'line',
//         })
//
//     }
//
//     /* -------------------------------------------------------------------------------------------------------------- */
//     get_chart_config() {
//         const chart_config = {
//             type: 'line',
//             data: null,
//
//             options: {
//                 responsive: true,
//                 maintainAspectRatio: false,
//                 animation: false,
//                 normalized: true,
//                 scales: {
//                     x: this.get_x_axis_config(),
//                     ...this.get_y_axes_configs()
//                 },
//                 elements: {point: {radius: 0}},
//                 plugins: {
//                     decimation: {
//                         enabled: true,
//                         algorithm: 'lttb',      // “largest triangle” algorithm
//                         samples: 500         // keep at most 500 points on‐screen
//                     },
//                     customCanvasBackgroundColor: {color: getColor(this.config.background_color)},
//                     legend: {
//                         display: this.config.show_legend,
//                         position: this.config.legend_position,
//                         align: this.config.legend_align,
//                         fullSize: this.config.legend_fullsize,
//                         font: {
//                             size: this.config.legend_font_size
//                         },
//                         labels: {
//                             font: {family: 'monospace'},
//                             usePointStyle: this.config.legend_label_type === 'point',
//                             boxWidth: this.config.legend_label_size,
//                             boxHeight: this.config.legend_label_size,
//                             padding: 3,
//                             generateLabels: chart => {
//                                 const items = defaultGenerateLabels(chart);
//                                 items.forEach(item => {
//                                     const ds = chart.data.datasets[item.datasetIndex];
//                                     const last = ds.data.length ? ds.data[ds.data.length - 1].y : 0;
//                                     const value = last.toFixed(ds.precision).padStart(6, ' ');
//                                     const suffix = ds.unit && !this.plot_config.y_axis_show_label
//                                         ? ` (${ds.unit})`
//                                         : '';
//                                     item.text = `${ds.label}${suffix} ${value}`;
//                                 });
//                                 return items;
//                             },
//                         },
//                         onClick: defaultLegendClick,
//                     },
//                     title: {
//                         display: this.config.show_title,
//                         position: this.config.title_position,
//                         text: this.config.title || '',
//                         color: getColor(this.config.title_color),
//                         font: {
//                             size: this.config.title_font_size
//                         },
//                         padding: {
//                             top: 2,
//                             bottom: 2
//                         }
//                     }
//                 },
//             },
//             plugins: this.chartPlugins
//         }
//     }
//
//     /* -------------------------------------------------------------------------------------------------------------- */
//     get_x_axis_config() {
//         const x_axis_config = {
//             type: 'realtime',
//             realtime: {
//                 duration: Math.floor(this.config.window_time * 1000),
//                 refresh: Math.floor(this.config.update_time * 1000),
//                 delay: Math.floor(this.config.pre_delay * 1000),
//                 onRefresh: () => this._on_refresh(),
//             },
//             time: {
//                 displayFormats: {
//                     second: this.config.time_display_format,
//                     minute: this.config.time_display_format,
//                     hour: this.config.time_display_format,
//                 },
//                 tooltipFormat: this.config.time_display_format,
//                 unit: 'second',
//                 stepSize: this.config.time_step_display
//             },
//             ticks: {color: getColor(this.config.time_ticks_color)},
//             grid: {color: getColor(this.config.time_ticks_color)}
//         }
//     }
//
//     /* -------------------------------------------------------------------------------------------------------------- */
//     _on_refresh() {
//         this.plot.data.datasets.forEach(ds => {
//             const timeseries_id = ds.seriesId;
//
//             const timeseries = this.timeseries[timeseries_id];
//             if (!timeseries) {
//                 console.warn(`Timeseries ${timeseries_id} not found`);
//                 return;
//             }
//
//             if (this.config.use_queue) {
//                 ds.data.push(...timeseries.get_data());
//                 timeseries.clear();
//             } else {
//                 const value = timeseries.get_last_value();
//                 if (value !== null) {
//                     ds.data.push(value);
//                 }
//             }
//
//         })
//     }
//
//     /* -------------------------------------------------------------------------------------------------------------- */
//     addTimeSeries(id, config = {}) {
//         const y_axis_id = config.y_axis.id;
//         if (!y_axis_id) {
//             console.warn(`No y-axis specified for timeseries ${id}`);
//             return;
//         }
//
//         let y_axis;
//         // Check if y-axis exists
//         if (!this.y_axes[y_axis_id]) {
//             // Create a new y-axis
//             y_axis = this.addYAxis(config.y_axis.id, config.y_axis);
//         } else {
//             y_axis = this.y_axes[y_axis_id];
//         }
//
//     }
//
//     /* -------------------------------------------------------------------------------------------------------------- */
//     removeTimeSeries(id) {
//
//     }
//
//     /* -------------------------------------------------------------------------------------------------------------- */
//     addYAxis(id, config = {}) {
//         const y_axis = new RT_Plot_Y_Axis(id, config);
//         this.y_axes[id] = y_axis;
//         return y_axis;
//     }
//
//     /* -------------------------------------------------------------------------------------------------------------- */
//     removeYAxis(id) {
//
//     }
//
//     /* -------------------------------------------------------------------------------------------------------------- */
//     changeTimeAxisLength(length) {
//
//     }
//
//     /* -------------------------------------------------------------------------------------------------------------- */
//     clearData() {
//
//     }
//
//     /* -------------------------------------------------------------------------------------------------------------- */
//     getTimeSeries(id) {
//         return this.timeseries[id];
//     }
//
//     /* -------------------------------------------------------------------------------------------------------------- */
//     updateTimeSeriesConfig(id, config) {
//
//     }
//
//     /* -------------------------------------------------------------------------------------------------------------- */
//     updateYAxisConfig(id, config) {
//
//     }
//
//     /* -------------------------------------------------------------------------------------------------------------- */
//     updateXAxisConfig(config) {
//
//     }
//
//     /* -------------------------------------------------------------------------------------------------------------- */
//     handleMessage(message) {
//         switch (message.type) {
//             case 'update':
//                 break;
//             case 'init':
//                 break;
//             case 'clear':
//                 break;
//             case 'add_series':
//                 break;
//             case 'remove_series':
//                 break;
//             case 'add_y_axis':
//                 break;
//             case 'remove_y_axis':
//                 break;
//             case 'update_series':
//                 break;
//             case 'update_y_axis':
//                 break;
//             case 'update_x_axis':
//                 break;
//         }
//     }
//
//     /* -------------------------------------------------------------------------------------------------------------- */
//     _get_datasets() {
//         const datasets = [];
//         for (const [id, timeseries] of Object.entries(this.timeseries)) {
//             const dataset = timeseries.get_config()
//         }
//     }
//
//     /* -------------------------------------------------------------------------------------------------------------- */
//     update(data) {
//
//     }
//
//     /* -------------------------------------------------------------------------------------------------------------- */
//     _connect(ws_url) {
//         this.socket = new WebSocket(ws_url);
//         this.socket.addEventListener('open', () => {
//             console.log('WebSocket connected');
//         });
//         this.socket.addEventListener('message', (ev) => this._onWebsocketMessage(ev));
//         this.socket.addEventListener('close', () => {
//             this._lastValue = {};
//             console.log('WebSocket closed, retrying in 3s');
//             setTimeout(() => this._connect(ws_url), 3000);
//         });
//         this.socket.addEventListener('error', (err) => {
//             console.error('WebSocket error', err);
//             this.socket.close();
//         });
//     }
//
// }
//
//
// export class RT_Plot_Widget extends Widget {
//     constructor(id, payload = {}) {
//         super(id, payload);
//
//         const default_config = {
//             host: 'localhost',
//             port: 8080,
//             server_mode: 'standalone', // Options: 'standalone', 'external'
//         }
//
//         this.configuration = {...this.configuration, ...default_config, ...payload.config};
//
//
//         this.element = this.initializeElement();
//         this.configureElement(this.element);
//         this.assignListeners(this.element);
//
//         this.plot = new RT_Plot(`${this.id}_plot`, this.element, payload.plot || {});
//     }
//
//     initializeElement() {
//         const element = document.createElement("div");
//         element.id = 'plot_container';
//         element.classList.add('widget', 'plot-wrapper');
//         return element;
//     }
//
//     resize() {
//
//     }
//
//     update(data) {
//         this.plot.update(data);
//     }
//
//     updateConfig(data) {
//         return undefined;
//     }
// }


// rt_plot.js
//
// A modular, easy-to-use real-time (streaming) plotting wrapper around Chart.js + chartjs-plugin-streaming.
// The design supports:
//   • Multiple time series sharing the same Y-axis (or different Y-axes)
//   • Dynamic add/remove of series and Y-axes
//   • Live updates to X-axis, Y-axes, and per-series configs
//   • Two ingestion modes: "queue" (push every sample) and "last-value" (push most recent only)
//
// Notes:
//   • This replaces tight coupling in the old implementation with small focused classes.
//   • RT_Plot_Y_Axis encapsulates a Y-axis; RT_Plot_TimeSeries encapsulates one series.
//   • RT_Plot coordinates them and owns the Chart.js instance.
//   • RT_Plot_Widget is kept as your external interface (unchanged in spirit) and delegates to RT_Plot.
//
// Dependencies:
//   - chart.js/auto
//   - chartjs-adapter-moment
//   - chartjs-plugin-streaming
//   - ./rt_plot.css (styling, e.g. settings button if you use it externally)
//   - ../../helpers.js providing getColor(rgbaArray) and interpolateColors(a, b, t)
//   - ../../objects/objects.js providing Widget (unchanged per your request)
//

import Chart from "chart.js/auto";
import 'chartjs-adapter-moment';
import streamingPlugin from 'chartjs-plugin-streaming';
import '../rt_plot.css';
import {getColor, interpolateColors} from "../../../helpers.js";
import {Widget} from "../../../objects/objects.js";

/* ================================================================================================================== */
/* Plugins                                                                                                            */
/* ================================================================================================================== */

/**
 * Force major ticks on Y axes for 0, first, and last tick.
 * Helpful for emphasizing zero lines and ends of ranges.
 */
const forceMajorTicks = {
    id: 'forceMajorTicks',
    afterBuildTicks(chart, args) {
        const scale = args.scale;
        if (scale.axis !== 'y') return;
        const ticks = scale.ticks;

        // Ensure 0 is a major tick
        let zero = ticks.find(t => t.value === 0);
        if (zero) {
            zero.major = true;
        } else {
            ticks.push({value: 0, label: '0', major: true});
        }

        // Keep numeric order if we injected new tick
        ticks.sort((a, b) => a.value - b.value);

        // First and last
        if (ticks.length) {
            ticks[0].major = true;
            ticks[ticks.length - 1].major = true;
        }
    }
};

/**
 * Paints a custom background color below the chart.
 */
const backgroundcolor_plugin = {
    id: 'customCanvasBackgroundColor',
    beforeDraw: (chart, _args, options) => {
        const ctx = chart.ctx;
        ctx.save();
        ctx.globalCompositeOperation = 'destination-over';
        ctx.fillStyle = options.color || '#00000000';
        ctx.fillRect(0, 0, chart.width, chart.height);
        ctx.restore();
    }
};

const defaultLegendClick = Chart.defaults.plugins.legend.onClick;
const defaultGenerateLabels = Chart.defaults.plugins.legend.labels.generateLabels;

Chart.register(streamingPlugin);

/* ================================================================================================================== */
/* Small Classes                                                                                                      */

/* ================================================================================================================== */

/**
 * RT_Plot_Y_Axis
 * Encapsulates a single Y-axis definition and converts to Chart.js scale config.
 */
export class RT_Plot_Y_Axis {
    /**
     * @param {string} id - Unique axis id (referenced by datasets via yAxisID).
     * @param {object} config - Axis config (see defaults below).
     */
    constructor(id, config = {}) {
        this.id = id;

        /** Default Y-axis config */
        const defaults = {
            name: id,
            color: [0.8, 0.8, 0.8, 1],
            grid_color: [0.5, 0.5, 0.5, 0.5],
            visible: true,
            side: 'left',           // 'left' | 'right'
            show_label: true,
            label: id,
            font_size: 10,
            precision: 2,
            grid: true,
            highlight_zero: true,
            min: null,
            max: null
        };

        this.config = {...defaults, ...config};
    }

    /**
     * Merge config changes into this axis.
     * @param {object} patch
     */
    updateConfig(patch = {}) {
        this.config = {...this.config, ...patch};
    }

    /**
     * Build the Chart.js scale configuration for this axis.
     */
    toChartScaleConfig() {
        const cfg = this.config;
        const c = {
            type: 'linear',
            position: cfg.side,
            display: cfg.visible,
            title: {
                display: cfg.show_label,
                text: cfg.label
            },
            beginAtZero: true,
            ticks: {
                color: getColor(cfg.color),
                major: {enabled: true},
                font: {size: cfg.font_size},
                callback: (value) => {
                    // Value is a number; numerical tick formatter
                    try {
                        return Number(value).toFixed(cfg.precision);
                    } catch {
                        return value;
                    }
                }
            },
            grid: {
                display: cfg.grid,
                drawOnChartArea: cfg.grid,
                borderColor: interpolateColors(cfg.color, cfg.grid_color, 0.5),
                lineWidth: ctx => (cfg.highlight_zero && ctx.tick?.value === 0 ? 2 : 1),
                color: ctx => {
                    const isZero = cfg.highlight_zero && ctx.tick?.value === 0;
                    const [r, g, b] = cfg.grid_color.slice(0, 3).map(v => Math.round(v * 255));
                    const alpha = isZero ? 1 : (cfg.grid_color[3] ?? 0.4);
                    return `rgba(${r}, ${g}, ${b}, ${alpha})`;
                }
            }
        };
        if (cfg.min !== null && cfg.min !== undefined) c.min = cfg.min;
        if (cfg.max !== null && cfg.max !== undefined) c.max = cfg.max;
        return c;
    }
}

/**
 * RT_Plot_TimeSeries
 * Encapsulates a single streaming dataset (line).
 */
export class RT_Plot_TimeSeries {
    /**
     * @param {string} id - Unique series id.
     * @param {object} config - Series config (see defaults below).
     */
    constructor(id, config = {}) {
        this.id = id;

        /** Default series config */
        const defaults = {
            name: id,
            color: [0.2, 0.6, 0.9, 1],
            width: 2,
            tension: 0.1,
            fill: false,
            fill_color: [0.2, 0.6, 0.9, 0.15],
            unit: null,
            precision: 2,
            visible: true,
            // Axis assignment: either pass y_axis: 'axisId'
            // or y_axis: { id: 'axisId', ...axisConfig }
            y_axis: null
        };

        this.config = {...defaults, ...config};

        // Internal data buffer (used only when use_queue === true)
        this._queue = [];
        // Last value storage for "last-value" mode
        this._last = null;

        // Chart.js dataset reference (filled by RT_Plot on attach)
        this._dataset = null;
    }

    /**
     * Update the series configuration.
     * @param {object} patch
     */
    updateConfig(patch = {}) {
        this.config = {...this.config, ...patch};
    }

    /**
     * Push a new datapoint.
     * Accepts either:
     *   - { time: secondsEpoch, value: number }
     *   - { x: msEpoch, y: number }  // Chart.js style
     * The plot will convert to Chart.js object and either queue or set as last-value.
     * @param {object} sample
     * @param {boolean} useQueue - whether to queue or keep only last
     * @param {boolean} useLocalTime - take local time if "time" isn't provided
     */
    ingest(sample, useQueue, useLocalTime) {
        let point;

        if ('x' in sample && 'y' in sample) {
            point = {x: sample.x, y: sample.y};
        } else {
            // { time: secondsEpoch, value }
            const t = ('time' in sample)
                ? Math.floor(sample.time * 1000)
                : (useLocalTime ? Date.now() : Date.now());
            point = {x: t, y: sample.value};
        }

        if (useQueue) {
            this._queue.push(point);
            if (this._queue.length > 5000) this._queue.shift(); // safety bound
        } else {
            this._last = point;
        }
    }

    /**
     * Pop all queued samples (for "queue" mode).
     */
    drainQueue() {
        const q = this._queue;
        this._queue = [];
        return q;
    }

    /**
     * Get last value and clear it (for "last-value" mode).
     */
    popLast() {
        const v = this._last;
        this._last = null;
        return v;
    }

    /**
     * Build a Chart.js dataset config for this series.
     * @param {string} yAxisId - bound axis id
     */
    toChartDataset(yAxisId) {
        const c = this.config;
        return {
            label: c.name,
            unit: c.unit,
            seriesId: this.id,
            yAxisID: yAxisId,
            borderColor: getColor(c.color),
            backgroundColor: getColor(c.fill_color),
            borderWidth: c.width,
            tension: c.tension,
            fill: !!c.fill,
            hidden: !c.visible,
            data: [],
            // carry precision for legend label generation
            precision: c.precision
        };
    }
}

/* ================================================================================================================== */
/* RT_Plot (orchestrator)                                                                                             */

/* ================================================================================================================== */

/**
 * RT_Plot
 * Owns the Chart.js instance, manages axes/series, and provides an imperative API.
 */
export class RT_Plot {
    /**
     * @param {string} id - Plot id.
     * @param {HTMLElement} container - DOM container for the canvas.
     * @param {object} payload - Initial payload: { config, x_axis, y_axes, datasets }.
     */
    constructor(id, container, payload = {}) {
        this.id = id;
        this.container = container;

        /** Global plot defaults */
        const defaults = {
            // Streaming timing (seconds)
            window_time: 10,
            pre_delay: 0.1,
            update_time: 0.1,

            // Styling
            background_color: [1, 1, 1, 0],
            time_ticks_color: [0.5, 0.5, 0.5],
            force_major_ticks: false,
            time_display_format: 'HH:mm:ss',
            time_step_display: null,
            show_title: true,
            title: '',
            title_position: 'top',
            title_font_size: 11,
            title_color: [0.8, 0.8, 0.8],

            // Legend
            show_legend: true,
            legend_position: 'bottom',
            legend_align: 'start',
            legend_fullsize: false,
            legend_font_size: 10,
            legend_label_type: 'point', // 'point' or 'box'
            legend_label_size: 6,

            // ingestion behavior
            use_queue: false,
            use_local_time: true,

            // optional WebSocket client (not used by the Widget in external mode)
            host: 'localhost',
            port: 8080,
            server_mode: 'external' // 'standalone' (connect) | 'external' (no socket)
        };

        this.config = {...defaults, ...(payload?.config || {})};

        /** @type {Object.<string,RT_Plot_Y_Axis>} */
        this.y_axes = {};
        /** @type {Object.<string,RT_Plot_TimeSeries>} */
        this.timeseries = {};

        // Build canvas
        this._createCanvas();

        // Prepare plugins list
        this._plugins = [backgroundcolor_plugin];
        if (this.config.force_major_ticks) {
            this._plugins.push(forceMajorTicks);
        }

        // Bootstrap any incoming axes/series definitions
        const y_axes_def = payload?.y_axes || {};
        const series_def = payload?.datasets || {};
        Object.entries(y_axes_def).forEach(([aid, aCfg]) => this.addYAxis(aid, aCfg));
        Object.entries(series_def).forEach(([sid, sCfg]) => this.addTimeSeries(sid, sCfg));

        // Build the chart
        this._createChart();

        // Resize observer
        const ro = new ResizeObserver(() => this.chart?.resize());
        ro.observe(this.container);

        // Optional socket (kept for parity with old file; you can remove if unused)
        if (this.config.server_mode === 'standalone') {
            const url = `ws://${this.config.host}:${this.config.port}`;
            this._connect(url);
        }
    }

    /* -------------------------------------------- Canvas & Chart ---------------------------------------------------- */

    _createCanvas() {
        const canvas = document.createElement('canvas');
        canvas.style.width = '100%';
        canvas.style.height = '100%';
        canvas.style.display = 'block';
        canvas.style.background = 'rgba(255, 255, 255, 0)';

        this.container.appendChild(canvas);
        this.canvas = canvas;
        this.ctx = canvas.getContext('2d');
    }

    _createChart() {
        const cfg = this._buildChartConfig();
        if (this.chart) {
            this.chart.destroy();
        }
        this.chart = new Chart(this.ctx, cfg);
    }

    /**
     * Build the full Chart.js configuration object.
     */
    _buildChartConfig() {
        return {
            type: 'line',
            data: {datasets: this._collectDatasets()},
            options: {
                responsive: true,
                maintainAspectRatio: false,
                animation: false,
                normalized: true,
                scales: {
                    x: this._buildXAxisConfig(),
                    ...this._buildYAxesConfig()
                },
                elements: {
                    point: {radius: 0}
                },
                plugins: {
                    decimation: {
                        enabled: true,
                        algorithm: 'lttb',
                        samples: 500
                    },
                    customCanvasBackgroundColor: {
                        color: getColor(this.config.background_color)
                    },
                    legend: {
                        display: this.config.show_legend,
                        position: this.config.legend_position,
                        align: this.config.legend_align,
                        fullSize: this.config.legend_fullsize,
                        labels: {
                            font: {family: 'monospace', size: this.config.legend_font_size},
                            usePointStyle: this.config.legend_label_type === 'point',
                            boxWidth: this.config.legend_label_size,
                            boxHeight: this.config.legend_label_size,
                            padding: 4,
                            generateLabels: (chart) => {
                                const items = defaultGenerateLabels(chart);
                                items.forEach(item => {
                                    const ds = chart.data.datasets[item.datasetIndex];
                                    const last = ds.data.length ? ds.data[ds.data.length - 1].y : 0;
                                    const p = ds.precision ?? 2;
                                    const value = (typeof last === 'number' ? last : Number(last)).toFixed(p);
                                    const suffix = ds.unit ? ` ${ds.unit}` : '';
                                    item.text = `${ds.label}: ${value}${suffix}`;
                                });
                                return items;
                            }
                        },
                        onClick: defaultLegendClick
                    },
                    title: {
                        display: this.config.show_title,
                        position: this.config.title_position,
                        text: this.config.title || '',
                        color: getColor(this.config.title_color),
                        font: {size: this.config.title_font_size},
                        padding: {top: 2, bottom: 2}
                    }
                }
            },
            plugins: this._plugins
        };
    }

    /**
     * Build X-axis streaming config.
     */
    _buildXAxisConfig() {
        return {
            type: 'realtime',
            realtime: {
                duration: Math.floor(this.config.window_time * 1000),
                refresh: Math.floor(this.config.update_time * 1000),
                delay: Math.floor(this.config.pre_delay * 1000),
                onRefresh: () => this._onRefresh()
            },
            time: {
                displayFormats: {
                    second: this.config.time_display_format,
                    minute: this.config.time_display_format,
                    hour: this.config.time_display_format
                },
                tooltipFormat: this.config.time_display_format,
                unit: 'second',
                stepSize: this.config.time_step_display
            },
            ticks: {color: getColor(this.config.time_ticks_color)},
            grid: {color: getColor(this.config.time_ticks_color)}
        };
    }

    /**
     * Build Y-axes config map for Chart.js (scales: { [axisId]: scaleConfig }).
     */
    _buildYAxesConfig() {
        const map = {};
        Object.entries(this.y_axes).forEach(([id, axis]) => {
            map[id] = axis.toChartScaleConfig();
        });
        return map;
    }

    /**
     * Collect datasets from series objects, ensuring their yAxis exists.
     */
    _collectDatasets() {
        const arr = [];
        Object.entries(this.timeseries).forEach(([sid, series]) => {
            const yAxisId = this._resolveYAxisIdForSeries(series);
            const ds = series.toChartDataset(yAxisId);
            series._dataset = ds; // keep back-reference
            arr.push(ds);
        });
        return arr;
    }

    _resolveYAxisIdForSeries(series) {
        const ya = series?.config?.y_axis;
        if (!ya) throw new Error(`Series "${series.id}" has no y_axis configured.`);
        const id = (typeof ya === 'string') ? ya : ya.id;
        if (!id) throw new Error(`Series "${series.id}" y_axis requires an "id".`);
        if (!this.y_axes[id]) {
            // auto-create empty axis if missing
            this.addYAxis(id, (typeof ya === 'object') ? ya : {});
        }
        return id;
    }

    /* ---------------------------------------------- Streaming -------------------------------------------------------- */

    /**
     * onRefresh callback from chartjs-plugin-streaming.
     * Pull queued points (or latest point) from each series and push into dataset data.
     */
    _onRefresh() {
        if (!this.chart) return;
        this.chart.data.datasets.forEach(ds => {
            const sid = ds.seriesId;
            const s = this.timeseries[sid];
            if (!s) return;

            if (this.config.use_queue) {
                const chunk = s.drainQueue();
                if (chunk.length) ds.data.push(...chunk);
            } else {
                const last = s.popLast();
                if (last) ds.data.push(last);
            }
        });
    }

    /* ---------------------------------------------- Public API: Axes ------------------------------------------------- */

    /**
     * Add or replace a Y-axis.
     * @param {string} id
     * @param {object} config
     * @returns {RT_Plot_Y_Axis}
     */
    addYAxis(id, config = {}) {
        const axis = new RT_Plot_Y_Axis(id, config);
        this.y_axes[id] = axis;

        // If chart exists, apply immediately
        if (this.chart) {
            this.chart.options.scales[id] = axis.toChartScaleConfig();
            this.chart.update('none');
        }
        return axis;
    }

    /**
     * Remove a Y-axis. Any series bound to it must be reassigned or will be hidden.
     * @param {string} id
     * @param {string|null} reassignTo - optional new axis id to move datasets to
     */
    removeYAxis(id, reassignTo = null) {
        if (!this.y_axes[id]) return;

        // Reassign/mute series
        Object.values(this.timeseries).forEach(series => {
            const sid = this._resolveYAxisIdForSeries(series);
            if (sid === id) {
                if (reassignTo && this.y_axes[reassignTo]) {
                    // reassign series config
                    series.updateConfig({y_axis: reassignTo});
                    // also update dataset if active
                    if (series._dataset) series._dataset.yAxisID = reassignTo;
                } else {
                    // hide dataset if no reassignment provided
                    if (series._dataset) series._dataset.hidden = true;
                }
            }
        });

        delete this.y_axes[id];

        if (this.chart) {
            delete this.chart.options.scales[id];
            this.chart.update('none');
        }
    }

    /**
     * Patch a Y-axis config and apply to chart.
     * @param {string} id
     * @param {object} patch
     */
    updateYAxisConfig(id, patch = {}) {
        const axis = this.y_axes[id];
        if (!axis) return;
        axis.updateConfig(patch);

        if (this.chart) {
            this.chart.options.scales[id] = axis.toChartScaleConfig();
            this.chart.update('none');
        }
    }

    /* ---------------------------------------------- Public API: Series ----------------------------------------------- */

    /**
     * Add or replace a time series.
     * @param {string} id
     * @param {object} config - must include y_axis (string id or { id, ... }).
     * @returns {RT_Plot_TimeSeries}
     */
    addTimeSeries(id, config = {}) {
        const series = new RT_Plot_TimeSeries(id, config);
        this.timeseries[id] = series;

        // Ensure axis exists (auto-create if needed)
        const yAxisId = this._resolveYAxisIdForSeries(series);

        // Add dataset to chart immediately if ready
        if (this.chart) {
            const ds = series.toChartDataset(yAxisId);
            series._dataset = ds;
            this.chart.data.datasets.push(ds);
            this.chart.update('none');
        }

        return series;
    }

    /**
     * Remove a time series.
     * @param {string} id
     */
    removeTimeSeries(id) {
        const s = this.timeseries[id];
        if (!s) return;

        // Remove from chart datasets
        if (this.chart) {
            const idx = this.chart.data.datasets.findIndex(d => d.seriesId === id);
            if (idx >= 0) {
                this.chart.data.datasets.splice(idx, 1);
            }
        }

        delete this.timeseries[id];
        this.chart?.update('none');
    }

    /**
     * Patch a time series config and apply to its dataset.
     * @param {string} id
     * @param {object} patch
     */
    updateTimeSeriesConfig(id, patch = {}) {
        const s = this.timeseries[id];
        if (!s) return;
        s.updateConfig(patch);

        if (!this.chart || !s._dataset) return;

        // y-axis reassignment?
        const newAxisId = this._resolveYAxisIdForSeries(s);
        s._dataset.yAxisID = newAxisId;

        // Visuals
        const c = s.config;
        s._dataset.label = c.name;
        s._dataset.unit = c.unit;
        s._dataset.borderColor = getColor(c.color);
        s._dataset.backgroundColor = getColor(c.fill_color);
        s._dataset.borderWidth = c.width;
        s._dataset.tension = c.tension;
        s._dataset.fill = !!c.fill;
        s._dataset.hidden = !c.visible;
        s._dataset.precision = c.precision;

        this.chart.update('none');
    }

    /**
     * Get a series by id.
     * @param {string} id
     */
    getTimeSeries(id) {
        return this.timeseries[id];
    }

    /* ---------------------------------------------- Public API: X axis & Plot ---------------------------------------- */

    /**
     * Update X-axis / global streaming configuration.
     * Accepts any fields from the RT_Plot defaults.
     * @param {object} patch
     */
    updateXAxisConfig(patch = {}) {
        this.config = {...this.config, ...patch};
        if (!this.chart) return;

        // Update relevant x.realtime fields
        const rt = this.chart.options.scales.x.realtime;
        rt.duration = Math.floor(this.config.window_time * 1000);
        rt.refresh = Math.floor(this.config.update_time * 1000);
        rt.delay = Math.floor(this.config.pre_delay * 1000);

        // Time display
        const x = this.chart.options.scales.x;
        x.time.displayFormats.second = this.config.time_display_format;
        x.time.displayFormats.minute = this.config.time_display_format;
        x.time.displayFormats.hour = this.config.time_display_format;
        x.time.tooltipFormat = this.config.time_display_format;
        x.time.stepSize = this.config.time_step_display;

        x.ticks.color = getColor(this.config.time_ticks_color);
        x.grid.color = getColor(this.config.time_ticks_color);

        // Title / legend / bg
        this.chart.options.plugins.title.display = this.config.show_title;
        this.chart.options.plugins.title.position = this.config.title_position;
        this.chart.options.plugins.title.text = this.config.title || '';
        this.chart.options.plugins.title.color = getColor(this.config.title_color);
        this.chart.options.plugins.title.font.size = this.config.title_font_size;

        this.chart.options.plugins.legend.display = this.config.show_legend;
        this.chart.options.plugins.legend.position = this.config.legend_position;
        this.chart.options.plugins.legend.align = this.config.legend_align;
        this.chart.options.plugins.legend.fullSize = this.config.legend_fullsize;
        this.chart.options.plugins.legend.labels.font.size = this.config.legend_font_size;
        this.chart.options.plugins.legend.labels.usePointStyle = this.config.legend_label_type === 'point';
        this.chart.options.plugins.legend.labels.boxWidth = this.config.legend_label_size;
        this.chart.options.plugins.legend.labels.boxHeight = this.config.legend_label_size;

        // Background plugin color
        this.chart.options.plugins.customCanvasBackgroundColor.color = getColor(this.config.background_color);

        this.chart.update('none');
    }

    /**
     * Convenience to change only the window length (seconds).
     * @param {number} seconds
     */
    changeTimeAxisLength(seconds) {
        this.updateXAxisConfig({window_time: seconds});
    }

    /**
     * Clear all plotted (on-chart) data without removing series.
     */
    clearData() {
        if (!this.chart) return;
        this.chart.data.datasets.forEach(ds => {
            ds.data = [];
        });
        Object.values(this.timeseries).forEach(s => {
            s._queue = [];
            s._last = null;
        });
        this.chart.update('none');
    }

    /* ---------------------------------------------- Data Ingestion --------------------------------------------------- */

    /**
     * Ingest updates.
     * Accepts multiple shapes for convenience:
     *   1) { time: secEpoch, timeseries: [ { timeseries_id, value }, ... ] }
     *   2) { time: secEpoch, timeseries: { "<id>": value, ... } }
     *   3) { series: "<id>", value, time? }  // single point
     *   4) { "<id>": value, time? }          // single key/value (discouraged but supported)
     * Times are optional if use_local_time = true.
     * @param {object} data
     */
    update(data) {
        const useQueue = this.config.use_queue;
        const useLocal = this.config.use_local_time;

        // 1/2) Batch shape
        if (data && typeof data === 'object' && ('timeseries' in data)) {
            const t = ('time' in data && data.time != null) ? data.time : undefined;
            const payload = data.timeseries;

            if (Array.isArray(payload)) {
                // Array of { timeseries_id, value }
                payload.forEach(item => {
                    const sid = item.timeseries_id || item.series || item.id;
                    if (!sid || !(sid in this.timeseries)) return;
                    const series = this.timeseries[sid];
                    series.ingest({time: t, value: item.value}, useQueue, useLocal);
                });
            } else if (payload && typeof payload === 'object') {
                // Map of { id: value, ... }
                Object.entries(payload).forEach(([sid, val]) => {
                    if (!(sid in this.timeseries)) return;
                    this.timeseries[sid].ingest({time: t, value: val}, useQueue, useLocal);
                });
            }
            return;
        }

        // 3) Single series point: { series, value, time? }
        if (data && data.series && 'value' in data) {
            const sid = data.series;
            if (this.timeseries[sid]) {
                this.timeseries[sid].ingest(
                    {time: data.time, value: data.value},
                    useQueue,
                    useLocal
                );
            }
            return;
        }

        // 4) Single { "<id>": value, time? }
        const keys = Object.keys(data || {});
        if (keys.length === 2 && keys.includes('time')) {
            // could be { time, "<id>": value }
            const t = data.time;
            const sid = keys.find(k => k !== 'time');
            const val = data[sid];
            if (sid && this.timeseries[sid]) {
                this.timeseries[sid].ingest({time: t, value: val}, useQueue, useLocal);
            }
            return;
        }
    }

    /* ---------------------------------------------- Message Bus (optional) ------------------------------------------- */

    /**
     * Optional message handler for external control, e.g. over WebSocket.
     * Supported:
     *   - { type: 'init', payload }
     *   - { type: 'clear' }
     *   - { type: 'update', data }
     *   - { type: 'add_series', id, config }
     *   - { type: 'remove_series', id }
     *   - { type: 'add_y_axis', id, config }
     *   - { type: 'remove_y_axis', id, reassignTo? }
     *   - { type: 'update_series', id, patch }
     *   - { type: 'update_y_axis', id, patch }
     *   - { type: 'update_x_axis', patch }
     */
    handleMessage(message = {}) {
        switch (message.type) {
            case 'init': {
                // Rebuild everything from payload
                const payload = message.payload || {};
                this.y_axes = {};
                this.timeseries = {};
                Object.entries(payload?.y_axes || {}).forEach(([aid, aCfg]) => this.addYAxis(aid, aCfg));
                Object.entries(payload?.datasets || {}).forEach(([sid, sCfg]) => this.addTimeSeries(sid, sCfg));
                this.updateXAxisConfig(payload?.config || {});
                // Force full rebuild to ensure clean state
                this._createChart();
                break;
            }
            case 'clear':
                this.clearData();
                break;
            case 'update':
                this.update(message.data);
                break;
            case 'add_series':
                this.addTimeSeries(message.id, message.config || {});
                break;
            case 'remove_series':
                this.removeTimeSeries(message.id);
                break;
            case 'add_y_axis':
                this.addYAxis(message.id, message.config || {});
                break;
            case 'remove_y_axis':
                this.removeYAxis(message.id, message.reassignTo || null);
                break;
            case 'update_series':
                this.updateTimeSeriesConfig(message.id, message.patch || {});
                break;
            case 'update_y_axis':
                this.updateYAxisConfig(message.id, message.patch || {});
                break;
            case 'update_x_axis':
                this.updateXAxisConfig(message.patch || {});
                break;
            default:
                console.warn('RT_Plot.handleMessage: unknown type', message.type);
        }
    }

    /* ---------------------------------------------- Socket (optional parity) ----------------------------------------- */

    _connect(wsUrl) {
        this.socket = new WebSocket(wsUrl);
        this.socket.addEventListener('open', () => console.log('[RT_Plot] WebSocket connected'));
        this.socket.addEventListener('message', (ev) => {
            try {
                const msg = JSON.parse(ev.data);
                this.handleMessage(msg);
            } catch (e) {
                console.error('[RT_Plot] Invalid JSON', e);
            }
        });
        this.socket.addEventListener('close', () => {
            console.warn('[RT_Plot] WebSocket closed, retrying in 3s');
            setTimeout(() => this._connect(wsUrl), 3000);
        });
        this.socket.addEventListener('error', (err) => {
            console.error('[RT_Plot] WebSocket error', err);
            this.socket.close();
        });
    }
}

/* ================================================================================================================== */
/* Widget wrapper (kept as your interface to the Python backend)                                                      */

/* ================================================================================================================== */

export class RT_Plot_Widget extends Widget {
    /**
     * @param {string} id
     * @param {object} payload - { config, plot }
     */
    constructor(id, payload = {}) {
        super(id, payload);

        // Keep your original widget-level config (host/port/mode) if you use it
        const default_config = {
            host: 'localhost',
            port: 8080,
            server_mode: 'standalone' // or 'external'
        };
        this.configuration = {...this.configuration, ...default_config, ...(payload?.config || {})};

        this.element = this.initializeElement();
        this.configureElement(this.element);
        this.assignListeners(this.element);

        // Create the RT_Plot orchestrator
        this.plot = new RT_Plot(`${this.id}_plot`, this.element, payload.plot || {});

        this.test()

    }

    initializeElement() {
        const el = document.createElement('div');
        el.id = 'plot_container';
        el.classList.add('widget', 'plot-wrapper');
        return el;
    }

    resize() {
        this.plot?.chart?.resize();
    }

    /**
     * Proxy streaming updates to the plot.
     * @param {object} data
     */
    update(data) {
        this.plot.update(data);
    }

    updateConfig(_data) {
        // Keep as no-op unless you want to forward configuration blocks to this.plot
        return undefined;
    }


    test() {
        // --- Demo: 1 y-axis with 3 series on the same axis ---

// 1) Create a left-side Y axis called "main"
        this.plot.addYAxis('main', {
            label: 'Value',
            side: 'left',
            precision: 2,
            font_size: 11,
            grid: true,
            highlight_zero: true,
            min: -10,
            max: 10
        });

// 2) Add three series that all reference the "main" axis
        this.plot.addTimeSeries('sine', {
            name: 'Sine',
            y_axis: 'main',
            color: [0.20, 0.60, 0.90, 1],     // blue-ish
            fill_color: [0.20, 0.60, 0.90, 0.15],
            width: 2,
            precision: 2,
            visible: true,
            tension: 0.2
        });

        this.plot.addTimeSeries('cosine', {
            name: 'Cosine',
            y_axis: 'main',
            color: [0.20, 0.80, 0.30, 1],     // green-ish
            fill_color: [0.20, 0.80, 0.30, 0.10],
            width: 2,
            precision: 2,
            visible: true,
            tension: 0.2
        });

        // this.plot.addTimeSeries('noise', {
        //     name: 'Noise',
        //     y_axis: 'main',
        //     color: [0.95, 0.50, 0.20, 1],     // orange-ish
        //     fill_color: [0.95, 0.50, 0.20, 0.10],
        //     width: 1.5,
        //     precision: 2,
        //     visible: true,
        //     tension: 0.05
        // });

// 3) Stream synthetic data every ~100 ms
//    By default RT_Plot uses "last-value" mode (use_queue=false), so we just keep sending new values.
//    The plugin will pull the latest on each refresh.
        let t0 = performance.now();
        let n = 0;
        let noise = 0;

        const demoInterval = setInterval(() => {
            const now = performance.now();
            const dt = (now - t0) / 1000; // seconds
            t0 = now;
            n += dt;

            // simple signals
            const sineVal = Math.sin(n * 2 * Math.PI * 0.2) * 5 + 10; // 0.2 Hz around 10
            const cosineVal = Math.cos(n * 2 * Math.PI * 0.13) * 3 + 5; // 0.13 Hz around 5
            noise = (noise * 0.95) + ((Math.random() - 0.5) * 0.8);     // gentle random walk
            const noiseVal = noise;

            // You can send a batch in "map" form; time is optional because use_local_time=true by default.
            this.plot.update({
                timeseries: {
                    sine: sineVal,
                    cosine: cosineVal,
                    noise: noiseVal
                }
            });
        }, 100);

// 4) Try some runtime mutations to exercise the modular API:

// after 4s: widen the visible window to 20 s
        setTimeout(() => {
            this.plot.changeTimeAxisLength(20);
        }, 4000);

// after 7s: clamp the y-axis range (so you can see min/max updates)
//         setTimeout(() => {
//             this.plot.updateYAxisConfig('main', {min: -5, max: 20});
//         }, 7000);

// after 10s: restyle the "noise" series (turn on area fill, change width, hide/show)
//         setTimeout(() => {
//             this.plot.updateTimeSeriesConfig('noise', {
//                 fill: true,
//                 width: 2,
//                 color: [0.90, 0.30, 0.30, 1],       // reddish
//                 fill_color: [0.90, 0.30, 0.30, 0.15]
//             });
//         }, 10000);

// // after 13s: toggle cosine visibility off
//         setTimeout(() => {
//             this.plot.updateTimeSeriesConfig('cosine', {visible: false});
//         }, 13000);

// after 16s: toggle cosine back on and move it to a new (auto-created) right axis to test reassignment
//         setTimeout(() => {
//             // Reassign cosine to a right-hand axis "rightAxis"; it will be auto-created with defaults
//             this.plot.updateTimeSeriesConfig('cosine', {
//                 visible: true,
//                 y_axis: {id: 'rightAxis', side: 'right', label: 'Cosine (right)'}
//             });
//         }, 16000);

// Optional: clean up if your widget gets destroyed; keep a reference and clearInterval(demoInterval).
// -----------------------------------------------------------------------------------------------
    }
}