// rt_plot.js
/**
 * A modular, runtime-configurable realtime plotting layer on top of Chart.js + chartjs-plugin-streaming.
 * - Multiple time series can share the same Y-axis (and you can have multiple Y-axes).
 * - You can add/remove series and Y-axes dynamically.
 * - You can update X-axis, Y-axis, and series configs at any time.
 * - Supports "queue" (batch) mode and "last value" mode for streaming.
 *
 * The public surface area centers on the RT_Plot class:
 *    - addYAxis(id, cfg), removeYAxis(id)
 *    - addTimeSeries(id, cfg), removeTimeSeries(id)
 *    - updateXAxisConfig(cfg), updateYAxisConfig(id, cfg), updateTimeSeriesConfig(id, cfg)
 *    - clearData(), changeTimeAxisLength(seconds)
 *    - update(messageFromBackend)  // push data points
 *    - handleMessage(msg)          // routing for init/update/clear/add/remove/update configs
 *
 * NOTE: RT_Plot_Widget is kept as your interface wrapper.
 */

import Chart from "chart.js/auto";
import "chartjs-adapter-moment";
import streamingPlugin from "chartjs-plugin-streaming";
import "./rt_plot.css";
import {getColor, interpolateColors} from "../../helpers.js";
import {Widget} from "../../objects/objects.js";

/* ================================================================================================================== */
/* Plugins & defaults                                                                                                 */
/* ================================================================================================================== */

/**
 * Force first/last and zero ticks to be "major" on Y axes.
 */
const forceMajorTicks = {
    id: "forceMajorTicks",
    afterBuildTicks(chart, args) {
        const scale = args.scale;
        if (scale.axis !== "y") return;

        const ticks = scale.ticks;

        // Ensure an explicit major tick at 0
        let zero = ticks.find((t) => t.value === 0);
        if (zero) zero.major = true;
        else ticks.push({value: 0, label: "0", major: true});

        // Keep ticks ordered numerically
        ticks.sort((a, b) => a.value - b.value);

        // First & last major
        if (ticks.length) {
            ticks[0].major = true;
            ticks[ticks.length - 1].major = true;
        }
    },
};

/**
 * Simple background color painter for the canvas.
 */
const backgroundcolor_plugin = {
    id: "customCanvasBackgroundColor",
    beforeDraw: (chart, _args, options) => {
        const ctx = chart.ctx;
        ctx.save();
        ctx.globalCompositeOperation = "destination-over";
        ctx.fillStyle = options.color || "#00000000";
        ctx.fillRect(0, 0, chart.width, chart.height);
        ctx.restore();
    },
};

const defaultLegendClick = Chart.defaults.plugins.legend.onClick;
const defaultGenerateLabels = Chart.defaults.plugins.legend.labels.generateLabels;

// Register streaming plugin once.
Chart.register(streamingPlugin);

/* ================================================================================================================== */
/* Utility                                                                                                            */

/* ================================================================================================================== */

/**
 * Deep merge for plain objects (non-recursive for arrays/functions).
 * Simplified to the use cases here.
 */
function deepMerge(target, source) {
    if (!source) return target;
    const out = {...target};
    for (const [k, v] of Object.entries(source)) {
        if (
            v &&
            typeof v === "object" &&
            !Array.isArray(v) &&
            typeof out[k] === "object" &&
            out[k] !== null &&
            !Array.isArray(out[k])
        ) {
            out[k] = deepMerge(out[k], v);
        } else {
            out[k] = v;
        }
    }
    return out;
}

/**
 * Clamp length of an array in-place by removing from the start.
 */
function clampArray(arr, maxLen) {
    const extra = arr.length - maxLen;
    if (extra > 0) arr.splice(0, extra);
}

/* ================================================================================================================== */
/* Y Axis                                                                                                             */

/* ================================================================================================================== */

class RT_Plot_Y_Axis {
    /**
     * @param {string} id - Unique Y-axis id (used as Chart.js scale key).
     * @param {object} config - Axis configuration.
     *
     * Config (defaults below):
     *  - name: string (display name)
     *  - color: [r,g,b,a] (used for tick color)
     *  - grid_color: [r,g,b,a] (grid color)
     *  - visible: boolean (controls draw, here we map to grid & title)
     *  - side: 'left' | 'right'
     *  - show_label: boolean
     *  - label: string (axis title text)
     *  - font_size: number
     *  - precision: number (tick format)
     *  - grid: boolean
     *  - highlight_zero: boolean
     *  - min: number|null
     *  - max: number|null
     */
    constructor(id, config = {}) {
        this.id = id;
        const default_config = {
            name: id,
            color: [0.8, 0.8, 0.8, 1],
            grid_color: [0.5, 0.5, 0.5, 0.5],
            visible: true,
            side: "left",
            show_label: true,
            label: id,
            font_size: 10,
            precision: 2,
            grid: true,
            highlight_zero: true,
            min: null,
            max: null,
        };
        this.config = {...default_config, ...config};
    }

    /**
     * Convert axis config to a Chart.js scale config.
     */
    toChartScaleConfig() {
        const cfg = this.config;
        const cTick = getColor(cfg.color);
        const gridRGBA = cfg.grid_color.slice(0, 3).map((c) => Math.round(c * 255));

        const scale = {
            type: "linear",
            position: cfg.side,
            // Chart.js doesn't have a direct "visible" for scales; we control grid/title/ticks.
            title: {
                display: cfg.visible && cfg.show_label,
                text: cfg.label,
            },
            ticks: {
                color: cfg.visible ? cTick : "rgba(0,0,0,0)",
                major: {enabled: true},
                font: {size: cfg.font_size},
                callback: (value) => {
                    try {
                        return Number(value).toFixed(cfg.precision);
                    } catch {
                        return value;
                    }
                },
            },
            grid: {
                display: cfg.visible && cfg.grid,
                drawOnChartArea: cfg.visible && cfg.grid,
                borderColor: interpolateColors(cfg.color, cfg.grid_color, 0.5),
                lineWidth: (ctx) => (cfg.highlight_zero && ctx.tick.value === 0 ? 2 : 1),
                color: (ctx) => {
                    const isZero = cfg.highlight_zero && ctx.tick.value === 0;
                    const alpha = isZero ? 1 : 0.4;
                    return `rgba(${gridRGBA[0]}, ${gridRGBA[1]}, ${gridRGBA[2]}, ${alpha})`;
                },
            },
        };

        if (cfg.min !== null && cfg.min !== undefined) scale.min = cfg.min;
        if (cfg.max !== null && cfg.max !== undefined) scale.max = cfg.max;

        return scale;
    }

    /**
     * Update internal config (shallow merge) and return the new chart config.
     */
    updateConfig(partialCfg = {}) {
        this.config = {...this.config, ...partialCfg};
        return this.toChartScaleConfig();
    }
}

/* ================================================================================================================== */
/* Time Series                                                                                                        */

/* ================================================================================================================== */

class RT_Plot_TimeSeries {
    /**
     * @param {string} id - Unique dataset id.
     * @param {object} config - Series config.
     *
     * Config (defaults below):
     *  - name: string (legend label)
     *  - unit: string|null (used for legend suffix when y-axis label disabled)
     *  - color: [r,g,b,a]
     *  - fill_color: [r,g,b,a]
     *  - fill: boolean
     *  - tension: number (spline amount)
     *  - visible: boolean
     *  - precision: number (decimals for legend value)
     *  - width: number (lineWidth)
     *  - y_axis: string (the Y-axis id to attach to, REQUIRED)
     */
    constructor(id, config = {}) {
        this.id = id;

        const default_config = {
            name: id,
            unit: null,
            color: [0.8, 0.8, 0.8, 1],
            fill_color: [0.8, 0.8, 0.8, 0.2],
            fill: false,
            tension: 0.1,
            visible: true,
            precision: 2,
            width: 2,
            y_axis: null,
            // NEW:
            line_dash: null,            // e.g. [6,4] or null for solid
            line_dash_offset: 0,
            line_cap: 'butt',           // 'butt' | 'round' | 'square'
            line_join: 'miter',         // 'miter' | 'bevel' | 'round'
            stepped: false              // true | 'before' | 'after' | 'middle'
        };

        this.config = {...default_config, ...config};
        this.buffer = []; // local queue when plot.use_queue === true
        this._lastValue = null; // last point when not using queue
    }

    /**
     * Return a Chart.js dataset config for creation.
     */
    toChartDatasetConfig() {
        return {
            label: this.config.name,
            unit: this.config.unit,
            seriesId: this.id,
            yAxisID: this.config.y_axis,
            fill: !!this.config.fill,
            borderColor: getColor(this.config.color),
            backgroundColor: getColor(this.config.fill_color),
            borderWidth: this.config.width,
            tension: this.config.tension,
            hidden: !this.config.visible,
            precision: this.config.precision,
            data: [],
            // NEW:
            borderDash: this.config.line_dash || [],
            borderDashOffset: this.config.line_dash_offset || 0,
            borderCapStyle: this.config.line_cap,
            borderJoinStyle: this.config.line_join,
            stepped: this.config.stepped
        };
    }

    /**
     * Update internal config (shallow) and return a partial dataset patch.
     */
    datasetPatchFromConfig(partialCfg = {}) {
        this.config = {...this.config, ...partialCfg};
        return {
            label: this.config.name,
            unit: this.config.unit,
            yAxisID: this.config.y_axis,
            fill: !!this.config.fill,
            borderColor: getColor(this.config.color),
            backgroundColor: getColor(this.config.fill_color),
            borderWidth: this.config.width,
            tension: this.config.tension,
            hidden: !this.config.visible,
            precision: this.config.precision,
            // NEW:
            borderDash: this.config.line_dash || [],
            borderDashOffset: this.config.line_dash_offset || 0,
            borderCapStyle: this.config.line_cap,
            borderJoinStyle: this.config.line_join,
            stepped: this.config.stepped
        };
    }

    /**
     * Push an incoming point.
     * @param {number} tMillis - timestamp in milliseconds
     * @param {number} y       - value
     * @param {boolean} useQueue - true => queue mode, false => last value mode
     * @param {number} [maxBuffer=2000] - clamp queue length to avoid runaway memory
     */
    pushPoint(tMillis, y, useQueue, maxBuffer = 2000) {
        const pt = {x: tMillis, y};
        if (useQueue) {
            this.buffer.push(pt);
            if (this.buffer.length > maxBuffer) this.buffer.shift();
        } else {
            this._lastValue = pt;
        }
    }

    /**
     * Drain and return the queued points (queue mode), or return last value (last mode).
     */
    drainForRefresh(useQueue) {
        if (useQueue) {
            const out = this.buffer;
            this.buffer = [];
            return out;
        }
        return this._lastValue ? [this._lastValue] : [];
    }

    clear() {
        this.buffer = [];
        this._lastValue = null;
    }
}

/* ================================================================================================================== */
/* RT_Plot (main)                                                                                                     */

/* ================================================================================================================== */

class RT_Plot {
    /**
     * @param {string} id - Plot id (for debugging).
     * @param {HTMLElement} container - DOM container where a <canvas> will be injected.
     * @param {object} payload - Initial payload with { config, x_axis, y_axes, datasets }.
     */
    constructor(id, container, payload = {}) {
        this.id = id;
        this.container = container;

        // -------- Plot config defaults --------
        const default_config = {
            x_axis: {
                window_time: 10,
                pre_delay: 0.1,
                display_format: "HH:mm:ss",
                step_display: null,
            },

            update_time: 0.1,
            background_color: [1, 1, 1, 0],
            time_ticks_color: [0.5, 0.5, 0.5],
            force_major_ticks: false,
            show_title: true,
            title_position: "top",
            title_font_size: 11,
            title_color: [0.8, 0.8, 0.8],
            title: "",

            show_legend: true,
            legend_position: "bottom",
            legend_align: "start",
            legend_fullsize: false,
            legend_font_size: 10,
            legend_label_type: "point",
            legend_label_size: 6,

            use_queue: false,
            use_local_time: true, // else expect server timestamp in incoming packet
            max_points_per_dataset: 5000, // hard safety clamp (applied during refresh)
        };

        this.config = deepMerge(default_config, payload.config || {});
        this.y_axes = {}; // id -> RT_Plot_Y_Axis
        this.timeseries = {}; // id -> RT_Plot_TimeSeries
        this._datasetsIndex = {}; // seriesId -> dataset index in chart

        this._initCanvas();
        this._buildPlugins();
        this._initializeFromPayload(payload);

        // Resize handling
        const ro = new ResizeObserver(() => this.plot.resize());
        ro.observe(this.container);
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    /* Setup                                                                                                           */

    /* -------------------------------------------------------------------------------------------------------------- */

    _initCanvas() {
        const canvas = document.createElement("canvas");
        canvas.style.width = "100%";
        canvas.style.height = "100%";
        canvas.style.display = "block";
        canvas.style.background = "rgba(255, 255, 255, 0)";
        this.container.appendChild(canvas);
        this.canvas = canvas;
        this.ctx = this.canvas.getContext("2d");
    }

    _buildPlugins() {
        this.chartPlugins = [
            backgroundcolor_plugin,
            // Add forceMajorTicks only if requested
            ...(this.config.force_major_ticks ? [forceMajorTicks] : []),
        ];
    }

    _initializeFromPayload(payload) {
        // 1) Create axes
        const y_axes = payload.y_axes || {};
        for (const [id, axisCfg] of Object.entries(y_axes)) {
            this.addYAxis(id, axisCfg);
        }

        // 2) Create series
        const datasetsCfg = payload.timeseries || {};
        for (const [id, seriesCfg] of Object.entries(datasetsCfg)) {
            this.addTimeSeries(id, seriesCfg);
        }

        // 3) Build chart
        this._createOrRebuildChart();
    }

    _createOrRebuildChart() {
        const data = {datasets: this._composeDatasetsForChart()};
        const options = this._composeChartOptions();

        if (this.plot) {
            // Full rebuild (safer when axes changed)
            this.plot.destroy();
            this.plot = null;
        }

        this.plot = new Chart(this.ctx, {
            type: "line",
            data,
            options,
            plugins: this.chartPlugins,
        });

        // Rebuild dataset index map
        this._recomputeDatasetIndexMap();
    }

    _composeDatasetsForChart() {
        const out = [];
        for (const ts of Object.values(this.timeseries)) {
            out.push(ts.toChartDatasetConfig());
        }
        return out;
    }

    _composeChartOptions() {
        const bg = getColor(this.config.background_color);
        const timeTickColor = getColor(this.config.time_ticks_color);
        const scales = {
            x: this._xAxisScaleConfig(),
            ...this._yAxesScaleConfigs(),
        };

        return {
            responsive: true,
            maintainAspectRatio: false,
            animation: false,
            normalized: true,
            elements: {point: {radius: 0}},
            scales,
            plugins: {
                decimation: {
                    enabled: true,
                    algorithm: "lttb",
                    samples: 500,
                },
                customCanvasBackgroundColor: {color: bg},
                legend: {
                    display: this.config.show_legend,
                    position: this.config.legend_position,
                    align: this.config.legend_align,
                    fullSize: this.config.legend_fullsize,
                    labels: {
                        font: {family: "monospace", size: this.config.legend_font_size},
                        usePointStyle: this.config.legend_label_type === "point",
                        boxWidth: this.config.legend_label_size,
                        boxHeight: this.config.legend_label_size,
                        padding: 4,
                        generateLabels: (chart) => {
                            const items = defaultGenerateLabels(chart);
                            items.forEach((item) => {
                                const ds = chart.data.datasets[item.datasetIndex];
                                const last =
                                    ds.data && ds.data.length
                                        ? ds.data[ds.data.length - 1].y
                                        : undefined;
                                const precision = Number.isFinite(ds.precision)
                                    ? ds.precision
                                    : 2;
                                const val =
                                    last !== undefined
                                        ? Number(last).toFixed(precision).padStart(6, " ")
                                        : "--";
                                const suffix =
                                    ds.unit && !this._isYAxisLabelShown(ds.yAxisID)
                                        ? ` (${ds.unit})`
                                        : "";
                                item.text = `${ds.label}${suffix} ${val}`;
                            });
                            return items;
                        },
                    },
                    onClick: defaultLegendClick,
                },
                title: {
                    display: this.config.show_title,
                    position: this.config.title_position,
                    text: this.config.title || "",
                    color: getColor(this.config.title_color),
                    font: {size: this.config.title_font_size},
                    padding: {top: 2, bottom: 2},
                },
            },
        };
    }

    _xAxisScaleConfig() {
        const step = this.config.x_axis.step_display; // number or null
        return {
            type: "realtime",
            realtime: {
                duration: Math.floor(this.config.x_axis.window_time * 1000),
                refresh: Math.floor(this.config.update_time * 1000),
                delay: Math.floor(this.config.x_axis.pre_delay * 1000),
                onRefresh: () => this._onRefresh(),
            },
            time: {
                displayFormats: {
                    second: this.config.x_axis.display_format,
                    minute: this.config.x_axis.display_format,
                    hour: this.config.x_axis.display_format,
                },
                tooltipFormat: this.config.x_axis.display_format,
                // Only force seconds + stepSize when step_display is provided:
                ...(step != null && {
                    unit: "second",
                    stepSize: step, // e.g. 5
                }),
                // If step_display is null, no unit/stepSize are added → auto-scaling
            },
            ticks: {
                color: getColor(this.config.time_ticks_color),
                autoSkip: true,
                autoSkipPadding: 10,
                // maxTicksLimit: 8, // optional: further cap labels
                // maxRotation: 0, minRotation: 0, // optional: keep labels horizontal
            },
            grid: {color: getColor(this.config.time_ticks_color)},
        };
    }

    _yAxesScaleConfigs() {
        const out = {};
        for (const [id, axis] of Object.entries(this.y_axes)) {
            out[id] = axis.toChartScaleConfig();
        }
        return out;
    }

    _isYAxisLabelShown(yAxisID) {
        const ax = this.y_axes[yAxisID];
        return ax ? !!(ax.config.visible && ax.config.show_label) : false;
    }

    _recomputeDatasetIndexMap() {
        this._datasetsIndex = {};
        this.plot.data.datasets.forEach((ds, i) => {
            if (ds.seriesId) this._datasetsIndex[ds.seriesId] = i;
        });
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    /* Runtime data & refresh                                                                                          */

    /* -------------------------------------------------------------------------------------------------------------- */

    /**
     * Streaming refresh callback from chartjs-plugin-streaming.
     * Pulls new points from series buffers and appends to chart datasets.
     */
    _onRefresh() {
        const maxKeep = Math.max(500, this.config.max_points_per_dataset || 5000);

        this.plot.data.datasets.forEach((ds) => {
            const seriesId = ds.seriesId;
            const ts = this.timeseries[seriesId];
            if (!ts) return;

            const newPts = ts.drainForRefresh(this.config.use_queue);
            if (newPts.length) ds.data.push(...newPts);

            // Safety clamp in case streaming continues for very long sessions
            clampArray(ds.data, maxKeep);
        });
    }

    /**
     * Push incoming update payload into series buffers.
     * Supported formats:
     *  - { time: <sec>, timeseries: { <seriesId>: <value>, ... } }
     *  - { time: <sec>, timeseries: [ { timeseries_id: "...", value: <number> }, ... ] }
     *  - { timeseries: ... } with local time if config.use_local_time === true
     */
    update(data) {
        const tMillis = this.config.use_local_time
            ? Date.now()
            : Math.floor((data.time || 0) * 1000);

        const tsBlock = data.timeseries || {};

        if (Array.isArray(tsBlock)) {
            // Array of { timeseries_id, value }
            for (const item of tsBlock) {
                const sid = item.timeseries_id || item.seriesId || item.id;
                if (!sid || !(sid in this.timeseries)) continue;
                this.timeseries[sid].pushPoint(
                    tMillis,
                    item.value,
                    this.config.use_queue
                );
            }
        } else if (typeof tsBlock === "object") {
            // Dict of { id: value }
            for (const [sid, val] of Object.entries(tsBlock)) {
                if (!(sid in this.timeseries)) continue;
                this.timeseries[sid].pushPoint(tMillis, val, this.config.use_queue);
            }
        }
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    /* Public API: axes & series                                                                                        */

    /* -------------------------------------------------------------------------------------------------------------- */

    /**
     * Add a Y axis (or update if already exists).
     * @param {string} id
     * @param {object} config
     * @returns {RT_Plot_Y_Axis}
     */
    addYAxis(id, config = {}) {
        const axis = this.y_axes[id]
            ? this.y_axes[id]
            : new RT_Plot_Y_Axis(id, config);

        if (this.y_axes[id]) {
            axis.updateConfig(config);
        } else {
            this.y_axes[id] = axis;
        }

        // Reflect into chart scales (full rebuild safest when scale set changes)
        this._createOrRebuildChart();
        return axis;
    }

    /**
     * Remove a Y axis and detach any datasets previously targeting it.
     * Caller should reassign those series to another axis or remove them.
     */
    removeYAxis(id) {
        if (!this.y_axes[id]) return;

        // Reassign or hide any datasets pointing to this axis
        for (const ts of Object.values(this.timeseries)) {
            if (ts.config.y_axis === id) {
                // If you prefer to auto-move them, change here:
                ts.config.y_axis = null;
            }
        }

        delete this.y_axes[id];
        this._createOrRebuildChart();
    }

    /**
     * Add a time series (or update if exists).
     * @param {string} id
     * @param {object} config - Requires config.y_axis (string)
     */
    addTimeSeries(id, config = {}) {
        if (!config.y_axis && config.y_axis !== 0) {
            // Backward compatibility: allow config.y_axis.id object shape
            if (config.y_axis?.id) config.y_axis = config.y_axis.id;
        }

        if (!config.y_axis) {
            console.warn(`addTimeSeries("${id}"): missing required y_axis id`);
            return null;
        }
        if (!this.y_axes[config.y_axis]) {
            console.warn(
                `addTimeSeries("${id}"): Y axis "${config.y_axis}" not found; creating it with defaults.`
            );
            this.addYAxis(config.y_axis, {});
        }

        let ts = this.timeseries[id];
        if (!ts) {
            ts = new RT_Plot_TimeSeries(id, config);
            this.timeseries[id] = ts;

            // Add to chart datasets
            const ds = ts.toChartDatasetConfig();
            this.plot.data.datasets.push(ds);
            this._recomputeDatasetIndexMap();
            this.plot.update("none");
        } else {
            // If series exists, treat as config update
            this.updateTimeSeriesConfig(id, config);
        }

        return ts;
    }

    /**
     * Remove a series completely.
     */
    removeTimeSeries(id) {
        if (!(id in this.timeseries)) return;

        delete this.timeseries[id];

        const idx = this._datasetsIndex[id];
        if (idx !== undefined) {
            this.plot.data.datasets.splice(idx, 1);
            this._recomputeDatasetIndexMap();
            this.plot.update("none");
        }
    }

    /**
     * Update a series' config and patch its dataset.
     */
    updateTimeSeriesConfig(id, config = {}) {
        const ts = this.timeseries[id];
        if (!ts) return;

        // If a new y_axis is specified, ensure it exists.
        if (config.y_axis) {
            if (!this.y_axes[config.y_axis]) this.addYAxis(config.y_axis, {});
        }

        const patch = ts.datasetPatchFromConfig(config);
        const idx = this._datasetsIndex[id];
        if (idx !== undefined) {
            const ds = this.plot.data.datasets[idx];
            Object.assign(ds, patch);
            this.plot.update("none");
        }
    }

    /**
     * Update a Y axis config by id.
     */
    updateYAxisConfig(id, config = {}) {
        const axis = this.y_axes[id];
        if (!axis) return;

        axis.updateConfig(config);
        // Updating scales in place:
        this.plot.options.scales[id] = axis.toChartScaleConfig();
        this.plot.update("none");
    }

    /**
     * Update X axis (realtime scale) config. Supports any of the config fields; common examples:
     *   - { window_time: 30 }, { update_time: 0.05 }, { pre_delay: 0.2 }, { time_display_format: "HH:mm:ss" }
     */
    updateXAxisConfig(config = {}) {
        this.config.x_axis = deepMerge(this.config.x_axis, config);
        // Update only the x scale in place
        this.plot.options.scales.x = this._xAxisScaleConfig();
        this.plot.update("none");
    }

    /**
     * Change the realtime window length (seconds).
     */
    changeTimeAxisLength(seconds) {
        this.updateXAxisConfig({window_time: seconds});
    }

    /**
     * Get a reference to a series instance.
     */
    getTimeSeries(id) {
        return this.timeseries[id] || null;
    }

    /**
     * Clear all dataset data (chart-side) and series buffers.
     */
    clearData() {
        // Clear chart-side data
        this.plot.data.datasets.forEach((ds) => (ds.data = []));
        // Clear series buffers
        for (const ts of Object.values(this.timeseries)) ts.clear();
        this.plot.update("none");
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    /* Message handling (optional, for your backend protocol)                                                           */

    /* -------------------------------------------------------------------------------------------------------------- */

    /**
     * Generic message router to support a flexible backend protocol.
     * Recognized message shapes:
     *  - { type: 'init', payload: { config, x_axis, y_axes, datasets } }
     *  - { type: 'update', time?, timeseries: {...} | [...] }
     *  - { type: 'clear' }
     *  - { type: 'add_series', id, config }
     *  - { type: 'remove_series', id }
     *  - { type: 'add_y_axis', id, config }
     *  - { type: 'remove_y_axis', id }
     *  - { type: 'update_series', id, config }
     *  - { type: 'update_y_axis', id, config }
     *  - { type: 'update_x_axis', config }
     */
    handleMessage(message) {
        const {type, payload} = message || {};
        switch (type) {

            case "update": {
                this.update(message);
                break;
            }

            case "clear": {
                this.clearData();
                break;
            }

            case "add_timeseries": {
                this.addTimeSeries(payload.id, payload || {});
                break;
            }

            case "remove_timeseries": {
                this.removeTimeSeries(payload);
                break;
            }

            case "add_y_axis": {
                this.addYAxis(payload.id, payload.config || {});
                break;
            }

            case "remove_y_axis": {
                this.removeYAxis(payload);
                break;
            }

            case "update_timeseries": {
                this.updateTimeSeriesConfig(payload.id, payload.config || {});
                break;
            }

            case "update_y_axis": {
                this.updateYAxisConfig(payload.id, payload.config || {});
                break;
            }

            case "update_x_axis": {
                this.updateXAxisConfig(payload.config || {});
                break;
            }

            default: {
                console.warn("RT_Plot.handleMessage: unknown message type:", type);
            }
        }
    }
}

/* ================================================================================================================== */
/* RT_Plot_Widget (interface wrapper)                                                                                 */

/* ================================================================================================================== */

export class RT_Plot_Widget extends Widget {
    /**
     * Leave this class as your interface to the Python backend.
     * Minor internal wiring to use the new RT_Plot API.
     */
    constructor(id, payload = {}) {
        super(id, payload);

        const default_config = {
            host: "localhost",
            port: 8080,
            server_mode: "standalone", // 'standalone' | 'external'
        };

        this.configuration = {...this.configuration, ...default_config, ...(payload.config || {})};

        this.element = this.initializeElement();
        this.configureElement(this.element);
        this.assignListeners(this.element);

        this.plot = new RT_Plot(`${this.id}_plot`, this.element, payload.plot || {});
    }

    initializeElement() {
        const element = document.createElement("div");
        element.id = "plot_container";
        element.classList.add("widget", "plot-wrapper");
        return element;
    }

    resize() {
        // No-op: Chart is responsive; ResizeObserver is set in RT_Plot.
    }

    /**
     * Push streaming data from backend into the plot.
     * Expected shape:
     *  - { time?, timeseries: {...} | [...] }
     */
    update(data) {
        this.plot.update(data);
    }

    updateConfig(_data) {
        // Intentionally left as your extension point.
        return undefined;
    }

    send_to_plot({message_type, payload}) {
        console.warn(`Send to plot: ${message_type}`)
        this.plot.handleMessage({type: message_type, payload: payload});
    }

    /**
     * Demo / smoke test for RT_Plot_Widget.
     * Paste this method inside the RT_Plot_Widget class and call `this.test()` in the constructor.
     *
     * It showcases:
     *  1) A shared Y-axis ("trig") for sine and cosine, with continuous updates
     *  2) Adding a second Y-axis ("rand") later with a random-walk series
     *  3) Live updates to axis configs and dataset config
     *  4) Removing a series and clearing all data
     */
    test() {
        // Keep refs so we can stop intervals later if you reload widgets
        this._testIntervals = this._testIntervals || [];
        const addInterval = (id) => this._testIntervals.push(id);
        const clearIntervals = () => {
            this._testIntervals.forEach(id => clearInterval(id));
            this._testIntervals = [];
        };

        // --- 1) Create a shared Y-axis for sine/cosine and add both series ---
        // Note: colors are [r,g,b,a] in 0..1 range
        this.plot.addYAxis("trig", {
            label: "Amplitude",
            side: "left",
            precision: 3,
            color: [0.75, 0.75, 0.75, 1],
            grid_color: [0.5, 0.5, 0.5, 0.35],
            grid: true,
            highlight_zero: true,
            min: -1.25,
            max: 1.25
        });

        this.plot.addTimeSeries("sine", {
            name: "sin(x)",
            y_axis: "trig",
            color: [0.20, 0.65, 0.90, 1],
            fill_color: [0.20, 0.65, 0.90, 0.15],
            fill: false,
            tension: 0.15,
            width: 2,
            precision: 3,
            visible: true
        });

        this.plot.addTimeSeries("cosine", {
            name: "cos(x)",
            y_axis: "trig",
            color: [0.95, 0.40, 0.30, 1],
            fill_color: [0.95, 0.40, 0.30, 0.10],
            fill: false,
            tension: 0.15,
            width: 2,
            precision: 3,
            visible: true
        });

        // Stream sine/cosine values (shared timestamp via plot.update)
        let phase = 0;
        const phaseStep = 0.05;  // ~20 Hz at 50ms interval
        addInterval(setInterval(() => {
            phase += phaseStep;
            this.plot.update({
                // If plot.config.use_local_time is true, we can omit 'time'
                timeseries: {
                    sine: Math.sin(phase),
                    cosine: Math.cos(phase)
                }
            });
        }, 50));

        // --- 2) After a bit, add a 2nd Y-axis and a random-walk series on it ---
        setTimeout(() => {
            this.plot.addYAxis("rand", {
                label: "Random Walk",
                side: "right",
                precision: 2,
                color: [0.75, 0.75, 0.75, 1],
                grid_color: [0.5, 0.5, 0.5, 0.15],
                grid: false,           // keep the trig grid clean
                show_label: true,
                min: -10,
                max: 10
            });

            this.plot.addTimeSeries("noise", {
                name: "noise",
                y_axis: "rand",
                color: [0.35, 0.90, 0.50, 1],
                fill_color: [0.35, 0.90, 0.50, 0.10],
                fill: true,
                width: 2,
                precision: 2
            });

            // Random-walk streamer
            let v = 0;
            addInterval(setInterval(() => {
                // bounded random-walk-ish
                v += (Math.random() - 0.5) * 0.6;
                v = Math.max(-100, Math.min(100, v));
                this.plot.update({timeseries: {noise: v}});
            }, 75));
        }, 3000);

        // --- 3) Live config updates (axes, series, x-axis window) ---
        setTimeout(() => {
            // Tighten the trig axis and increase precision
            this.plot.updateYAxisConfig("trig", {min: -1.1, max: 1.1, precision: 4});

            // Make the cosine line filled
            this.plot.updateTimeSeriesConfig("cosine", {fill: true, fill_color: [0.95, 0.40, 0.30, 0.12]});

            // Expand the time window and slow refresh
            this.plot.updateXAxisConfig({window_time: 20, update_time: 0.12, pre_delay: 0.25});

            // // Change title and legend style
            // this.plot.handleMessage({
            //     type: "update_x_axis",
            //     config: {time_display_format: "HH:mm:ss.SS"}
            // });
            // this.plot.handleMessage({
            //     type: "init",
            //     payload: {
            //         config: {
            //             title: "RT_Plot: trig + random walk",
            //             show_title: true,
            //             legend_label_type: "point",
            //             legend_font_size: 11
            //         }
            //     }
            // });
        }, 6000);

        // --- 4) Remove a series to test dynamic removal ---
        setTimeout(() => {
            this.plot.removeTimeSeries("cosine");
        }, 9000);

        // --- 5) Clear all data (datasets remain) ---
        setTimeout(() => {
            this.plot.clearData();
        }, 12000);

        // // --- 6) Optional: stop all intervals after a while to keep things tidy ---
        // setTimeout(() => {
        //     clearIntervals();
        // }, 15000);

        // Clean up intervals if the widget gets torn down (optional hook if you have one)
        this._teardownTest = clearIntervals;
    }
}

// Export the core plot for direct use if needed.
export {RT_Plot, RT_Plot_TimeSeries, RT_Plot_Y_Axis};