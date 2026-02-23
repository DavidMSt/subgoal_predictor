import Chart from "chart.js/auto";
import {getColor, splitPath} from '../../helpers.js';
import {Widget} from "../../objects/objects.js";
import './lineplot.css';
/* ------------------------------------------------------------------------------------------------------------------ */
const default_x_axis_config = {
    id: 'x', type: 'linear', unit: '',
    min: 'auto', max: 'auto', step_size: 1,
    color: [0.7, 0.7, 0.7, 1],
    label: '',
    label_font_size: 12,
    label_font_family: 'Roboto, sans-serif',
    label_font_color: null,
    auto_skip: true,
    ticks_mode: 'auto',
    ticks: [],
    major_ticks: [],
    major_ticks_width: 1,
    major_ticks_color: 'grid',
    major_ticks_force_label: true
};
const default_y_axis_config = {
    id: 'y', type: 'linear', unit: '',
    color: [0.7, 0.7, 0.7, 1],
    label: '',
    label_font_size: 12,
    label_font_family: 'Roboto, sans-serif',
    label_font_color: null,
    position: 'left',
    min: 'auto', max: 'auto', step_size: 1,
    auto_skip: true,
    ticks_mode: 'auto',
    ticks: [],
    major_ticks: [],
    major_ticks_width: 2,
    major_ticks_color: 'grid',
    major_ticks_force_label: true
};
const default_series_config = {
    id: 's', unit: '', y_axis: 'y', tension: 0,
    color: [0, 0, 1, 1], width: 1,
    line_style: 'solid', marker: 'none',
    marker_fill: true, marker_size: 5,
    fill: false, fill_color: [0, 0, 1, 0.2],
    visible: true, show_in_legend: true
};
const default_plot_config = {
    background_color: [0, 0, 0, 0],
    plot_background_color: [1, 1, 1, 1],
    show_grid: true,
    grid_color: [0.5, 0.5, 0.5, 1],
    grid_width: 1,
    grid_line_style: 'solid',
    show_legend: true,
    legend_position: 'bottom',
    legend_font_size: 8,
    legend_font_family: 'Roboto, sans-serif',
    legend_font_color: [0, 0, 0, 1],
    show_title: true,
    title: '',
    title_font_size: 12,
    title_font_family: 'Roboto, sans-serif',
    title_font_color: [0, 0, 0, 1],
    border_color: [0, 1, 0, 1],
    border_width: 1,
    x_axis: {},
    y_axes: {},  // object of objects, each with id as key and y-axis config as value
};

/* ------------------------------------------------------------------------------------------------------------------ */
export class LinePlot_X_Axis {
    constructor(id = 'x', config = {}) {
        this.id = id;
        this.config = {...default_x_axis_config, ...config, id};
        this._plot = null;
    }

    addTick(v) {
        this.config.ticks.push(v);
        this.config.ticks_mode = 'custom';
        this._plot.update();
    }

    removeTick(v) {
        this.config.ticks = this.config.ticks.filter(x => x !== v);
        this._plot.update();
    }
}

/* ------------------------------------------------------------------------------------------------------------------ */
export class LinePlot_Y_Axis {
    constructor(id, config = {}) {
        this.id = id;
        this.config = {...default_y_axis_config, ...config, id};
        this._plot = null;
        this.series = {};
    }
}

/* ------------------------------------------------------------------------------------------------------------------ */
export class LinePlot_Series {
    constructor(id, config = {}) {
        this.id = id;
        this.config = {...default_series_config, ...config, id};
        this._plot = null;
    }

    addValue(x, y) {
        const ds = this._plot.chart.data.datasets.find(d => d.id === this.id);
        ds.data.push({x, y});
        this._plot.chart.update('none');
    }

    // === Interface wrapper ===
    addValue_interface(x, y) {  // <--- INTERFACE
        return this.addValue(x, y);
    }

    setValues(values) {
        for (let value of values) {
            // normalizes [[x,y], ...] or {x,y}
            const x = Array.isArray(value) ? value[0] : value.x;
            const y = Array.isArray(value) ? value[1] : value.y;
            this.addValue(x, y);
        }
    }

    // === Interface wrapper ===
    setValues_interface(values) {  // <--- INTERFACE
        return this.setValues(values);
    }

    removeValue(x) {
        const ds = this._plot.chart.data.datasets.find(d => d.id === this.id);
        ds.data = ds.data.filter(p => p.x !== x);
        this._plot.chart.update('none');
    }

    // === Interface wrapper ===
    removeValue_interface(x) {  // <--- INTERFACE
        return this.removeValue(x);
    }

    show(show = true) {
        const chart = this._plot.chart;
        const idx = chart.data.datasets.findIndex(d => d.id === this.id);
        chart.setDatasetVisibility(idx, show);
        chart.update();
        this.config.visible = show;
    }

    hide() {
        this.show(false);
    }

    showInLegend(show = true) {
        const ds = this._plot.chart.data.datasets.find(d => d.id === this.id);
        ds.showInLegend = show;
        this.config.show_in_legend = show;
        this._plot.chart.update();
    }

    dim(dim = true, dim_alpha = 0.2) {
        const chart = this._plot.chart;
        const ds = chart.data.datasets.find(d => d.id === this.id);
        if (!ds) return;

        if (!this._originalColors) {
            this._originalColors = {
                borderColor: ds.borderColor,
                backgroundColor: ds.backgroundColor,
                pointBackgroundColor: ds.pointBackgroundColor,
                pointBorderColor: ds.pointBorderColor
            };
        }

        const [r, g, b, a] = this.config.color;
        const newLineAlpha = dim ? a * dim_alpha : a;
        ds.borderColor = getColor([r, g, b, newLineAlpha]);

        if (this.config.fill) {
            const [fr, fg, fb, fa] = this.config.fill_color;
            const newFillAlpha = dim ? fa * dim_alpha : fa;
            ds.backgroundColor = getColor([fr, fg, fb, newFillAlpha]);
        }

        if (ds.pointBackgroundColor !== undefined) {
            const markerAlpha = dim ? a * dim_alpha : a;
            ds.pointBackgroundColor = this.config.marker_fill
                ? getColor([r, g, b, markerAlpha])
                : 'transparent';
            ds.pointBorderColor = getColor([r, g, b, markerAlpha]);
        }

        chart.update();
    }

    highlightMarker(x, highlight = true) {
        const chart = this._plot.chart;
        const ds = chart.data.datasets.find(d => d.id === this.id);
        if (!ds) return;

        const idx = ds.data.findIndex(p => p.x === x);
        if (idx === -1) return;

        if (!this._originalPointRadii) {
            const base = Array.isArray(ds.pointRadius)
                ? ds.pointRadius.slice()
                : ds.data.map(() => ds.pointRadius || this.config.marker_size);
            this._originalPointRadii = base;
        }

        const radii = this._originalPointRadii.slice();
        if (highlight) {
            radii[idx] = this.config.marker_size * 2;
        }

        ds.pointRadius = radii;
        chart.update();
    }

    resetAppearance() {
        const chart = this._plot.chart;
        const ds = chart.data.datasets.find(d => d.id === this.id);
        if (!ds) return;

        this.dim(false);

        if (this._originalPointRadii) {
            ds.pointRadius = this._originalPointRadii.slice();
        } else {
            ds.pointRadius = this.config.marker_size;
        }

        chart.update();
    }


    executeFunction(function_name, args, spread_args = false) {
        const fn = this[function_name];
        if (typeof fn !== 'function') {
            console.warn(`Function '${function_name}' not found or not callable.`);
            return null;
        }
        if (Array.isArray(args) && spread_args) return fn.apply(this, args);
        return fn.call(this, args);
    }

}

/* ------------------------------------------------------------------------------------------------------------------ */
export class LinePlot {
    constructor(id, container, config = {}, data = {}) {
        this.id = id;
        this.container = container;
        this.config = {...default_plot_config, ...config};

        // style container
        this.container.style.background = Array.isArray(this.config.background_color)
            ? getColor(this.config.background_color)
            : this.config.background_color;
        this.container.style.border = `${this.config.border_width}px solid ${getColor(this.config.border_color)}`;


        // registries
        this.x_axis = new LinePlot_X_Axis('x', this.config.x_axis || {});
        this.x_axis._plot = this;
        this.y_axes = {};
        this.series = {};


        // canvas
        this.canvas = document.createElement('canvas');
        this.canvas.classList.add('lineplot-canvas');
        this.container.appendChild(this.canvas);
        this.ctx = this.canvas.getContext('2d');

        // plugins
        this._makeMajorTicksPlugin();
        this._makeMinMaxPlugin();
        this.initializePlot();

        // NEW: build from incoming data payload
        this._buildFromData(data);


    }

    _buildFromData(data = {}) {
        // 1) optional: x-axis overrides coming from data.x_axis
        if (data.x_axis && typeof data.x_axis === 'object') {
            this.x_axis.config = {...default_x_axis_config, ...this.x_axis.config, ...data.x_axis, id: 'x'};
            this.updateXAxis();
        }

        // 2) y-axes
        if (data.y_axes && typeof data.y_axes === 'object') {
            Object.values(data.y_axes).forEach(cfg => {
                if (!this.y_axes[cfg.id]) this.addYAxis(cfg);
            });
        }

        // 3) series with initial points
        if (Array.isArray(data.series)) {
            data.series.forEach(sdesc => {
                const cfg = sdesc.config ? {...sdesc.config, id: sdesc.id} : {...sdesc, id: sdesc.id};
                const points = sdesc.points || [];
                const s = this.addSeriesFromConfig(cfg);
                const ds = this.chart.data.datasets.find(d => d.id === s.id);
                if (ds && Array.isArray(points) && points.length) {
                    const normalized = points.map(p => Array.isArray(p) ? {x: p[0], y: p[1]} : p);
                    ds.data.push(...normalized);
                }
            });
            this.chart.update('none');
        }

        // 4) straight lines / thresholds
        if (Array.isArray(data.lines)) {
            data.lines.forEach(L => {
                const id = this.addLine(
                    L.x1, L.y1, L.x2, L.y2,
                    L.color ?? [0, 0, 0, 1],
                    L.width ?? 1,
                    L.line_style ?? 'solid',
                    L.label ?? '',
                    L.y_axis ?? null
                );
                if (L.id && id !== L.id) {
                    const ds = this.chart.data.datasets.find(d => d.id === id);
                    if (ds) ds.id = L.id;
                }
            });
        }

        if (data.x_axis && (data.x_axis.ticks || data.x_axis.ticks_mode || data.x_axis.min !== undefined || data.x_axis.max !== undefined)) {
            this.updateXAxis();
        }
    }

    _makeMajorTicksPlugin() {
        const self = this;
        const plugin = {
            id: `${this.id}-major-ticks`,
            afterBuildTicks(chart, args) {
                if (chart !== self.chart) return;
                const scale = args.scale;
                const cfg = (scale.axis === 'x')
                    ? self.x_axis.config
                    : (self.y_axes[scale.id] && self.y_axes[scale.id].config);
                if (!cfg || !Array.isArray(cfg.major_ticks)) return;
                cfg.major_ticks.forEach(val => {
                    const eps = (cfg.step_size || 1) * 1e-6;
                    let t = scale.ticks.find(t => Math.abs(t.value - val) < eps);
                    if (!t) {
                        t = {value: val, major: true};
                        scale.ticks.push(t);
                    } else {
                        t.major = true;
                    }
                });
                scale.ticks.sort((a, b) => a.value - b.value);
            }
        };
        Chart.register(plugin);
    }

    _makeMinMaxPlugin() {
        const self = this;
        const plugin = {
            id: `${this.id}-minmax`,
            beforeDataLimits(chart, args) {
                if (chart !== self.chart) return;
                const scale = args.scale;
                if (scale.axis === 'x') {
                    const cfg = self.x_axis.config;
                    if (cfg.min !== 'auto') scale.min = cfg.min;
                    if (cfg.max !== 'auto') scale.max = cfg.max;
                } else {
                    const y = self.y_axes[scale.id];
                    if (y) {
                        const cfg = y.config;
                        if (cfg.min !== 'auto') scale.min = cfg.min;
                        if (cfg.max !== 'auto') scale.max = cfg.max;
                    }
                }
            }
        };
        Chart.register(plugin);
    }

    _getDash(style) {
        return style === 'dashed' ? [5, 5]
            : style === 'dotted' ? [2, 2]
                : [];
    }

    initializePlot() {
        const bgPlugin = {
            id: `${this.id}-bg`,
            beforeDraw: chart => {
                if (!chart.chartArea) return;
                const {left, top, width, height} = chart.chartArea;
                chart.ctx.save();
                chart.ctx.fillStyle = getColor(this.config.plot_background_color);
                chart.ctx.fillRect(left, top, width, height);
                chart.ctx.restore();
            }
        };

        const colorResolver = (col, axisCfg) => {
            if (col === 'grid') return getColor(this.config.grid_color);
            if (col === 'axis') return getColor(axisCfg.color);
            return Array.isArray(col) ? getColor(col) : col;
        };

        const opts = {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                x: this._buildScaleConfig('x', this.x_axis.config, colorResolver),
            },
            plugins: {
                legend: {
                    display: this.config.show_legend,
                    position: this.config.legend_position,
                    labels: {
                        font: {
                            size: this.config.legend_font_size,
                            family: this.config.legend_font_family
                        },
                        color: getColor(this.config.legend_font_color),
                        filter: (item, data) => data.datasets[item.datasetIndex].showInLegend !== false
                    },
                    onClick: (e, item, legend) => {
                        const chart = legend.chart;
                        const idx = item.datasetIndex;
                        chart.setDatasetVisibility(idx, !chart.isDatasetVisible(idx));
                        chart.update();
                        const sp = this.series[chart.data.datasets[idx].id];
                        if (sp) sp.config.visible = chart.isDatasetVisible(idx);
                    }
                },
                title: {
                    display: this.config.show_title,
                    text: this.config.title,
                    font: {
                        size: this.config.title_font_size,
                        family: this.config.title_font_family
                    },
                    color: getColor(this.config.title_font_color)
                }
            },
            elements: {
                point: {radius: 0}
            }
        };

        this.chart = new Chart(this.ctx, {
            type: 'line',
            data: {datasets: []},
            options: opts,
            plugins: [bgPlugin]
        });

        // Add initial y-axes from config
        if (this.config.y_axes && Object.keys(this.config.y_axes).length > 0) {
            Object.values(this.config.y_axes).forEach(cfg => {
                this.addYAxis(cfg);
            });
        }
    }

    _buildScaleConfig(axisId, cfg, resolveColor) {
        const isX = axisId === 'x';
        const scaleOpts = {
            type: cfg.type,
            position: isX ? 'bottom' : cfg.position,
            beginAtZero: false,
            grid: {
                display: this.config.show_grid,
                borderDash: this._getDash(this.config.grid_line_style),
                color: ctx => {
                    const maj = ctx.tick && ctx.tick.major;
                    return maj
                        ? resolveColor(cfg.major_ticks_color, cfg)
                        : getColor(this.config.grid_color);
                },
                lineWidth: ctx => {
                    const maj = ctx.tick && ctx.tick.major;
                    return maj
                        ? cfg.major_ticks_width
                        : this.config.grid_width;
                },
                drawBorder: true,
                borderColor: getColor(cfg.color)
            },
            ticks: {
                autoSkip: cfg.auto_skip,
                stepSize: cfg.step_size,
                major: {enabled: cfg.major_ticks_force_label},
                callback: function (value) {
                    const eps = (cfg.step_size || 1) * 1e-6;
                    const inCustom = cfg.ticks_mode === 'custom'
                        && cfg.ticks.some(t => Math.abs(t - value) < eps);
                    const isMaj = this.tick && this.tick.major;
                    if (cfg.ticks_mode === 'custom' && !inCustom && !isMaj) {
                        return '';
                    }
                    return this.getLabelForValue(value);
                },
                color: getColor(cfg.color),
                font: {family: cfg.label_font_family}
            },
            title: {
                display: !!cfg.label,
                text: cfg.label,
                color: cfg.label_font_color
                    ? (Array.isArray(cfg.label_font_color)
                        ? getColor(cfg.label_font_color)
                        : cfg.label_font_color)
                    : getColor(cfg.color),
                font: {
                    size: cfg.label_font_size,
                    family: cfg.label_font_family
                }
            }
        };

        if (cfg.min !== 'auto') scaleOpts.min = cfg.min;
        if (cfg.max !== 'auto') scaleOpts.max = cfg.max;

        return scaleOpts;
    }

    addYAxis(cfg) {
        const y = new LinePlot_Y_Axis(cfg.id, cfg);
        y._plot = this;
        this.y_axes[y.id] = y;

        const scfg = this._buildScaleConfig(
            y.id,
            y.config,
            (col, axisCfg) => {
                if (col === 'grid') return getColor(this.config.grid_color);
                if (col === 'axis') return getColor(axisCfg.color);
                return Array.isArray(col) ? getColor(col) : col;
            }
        );

        this.chart.options.scales[y.id] = scfg;
        this.chart.update();
        return y;
    }

    // === Interface wrapper ===
    addYAxis_interface(cfg) {  // <--- INTERFACE
        return this.addYAxis(cfg);
    }

    removeYAxis(id) {
        delete this.y_axes[id];
        if (this.chart.options.scales[id]) {
            delete this.chart.options.scales[id];
        }
        // detach any series pointing to that axis
        this.chart.data.datasets.forEach(d => {
            if (d.yAxisID === id) d.yAxisID = 'y';
        });
        this.chart.update();
    }

    // === Interface wrapper ===
    removeYAxis_interface(id) {  // <--- INTERFACE
        return this.removeYAxis(id);
    }

    addSeriesFromConfig(cfg) {
        return this.addSeries(new LinePlot_Series(cfg.id, cfg));
    }

    // === Interface wrapper ===
    addSeries_interface(cfg) {  // <--- INTERFACE
        return this.addSeriesFromConfig(cfg);
    }

    addSeries(series) {
        series._plot = this;
        const c = series.config;
        const style = c.marker === 'circle'
            ? 'circle'
            : c.marker === 'square'
                ? 'rect'
                : undefined;

        this.chart.data.datasets.push({
            id: series.id,
            label: c.id,
            unit: c.unit,
            data: [],
            borderColor: getColor(c.color),
            borderWidth: c.width,
            tension: c.tension,
            fill: c.fill,
            backgroundColor: c.fill ? getColor(c.fill_color) : undefined,
            yAxisID: c.y_axis,
            pointStyle: style,
            pointRadius: style ? c.marker_size : 0,
            pointBackgroundColor: style
                ? (c.marker_fill ? getColor(c.color) : 'transparent')
                : undefined,
            pointBorderColor: style ? getColor(c.color) : undefined,
            pointBorderWidth: style ? c.width : undefined,
            borderDash: this._getDash(c.line_style),
            hidden: !c.visible,
            showInLegend: c.show_in_legend
        });

        this.series[series.id] = series;
        if (this.y_axes[c.y_axis]) {
            this.y_axes[c.y_axis].series[c.id] = series;
        }
        this.chart.update();
        return series;
    }

    removeSeries(id) {
        this.chart.data.datasets = this.chart.data.datasets.filter(d => d.id !== id);
        delete this.series[id];
        Object.values(this.y_axes).forEach(y => delete y.series[id]);
        this.chart.update();
    }

    // === Interface wrapper ===
    removeSeries_interface(id) {  // <--- INTERFACE
        return this.removeSeries(id);
    }

    clear(remove_y_axes = false) {
        this.chart.data.datasets = [];
        this.series = {};
        if (remove_y_axes) {
            Object.keys(this.y_axes).forEach(k => delete this.chart.options.scales[k]);
            this.y_axes = {};
        }
        this.chart.update();
    }

    update() {
        this.chart.update();
    }

    addLine(x1, y1, x2, y2, color = [0, 0, 0, 1], width = 1, line_style = 'solid', label = '', yAxisID = null, forcedId = null) {
        const id = forcedId || `line_${Date.now()}_${Math.floor(Math.random() * 1e6)}`;
        const dash = this._getDash(line_style);
        const axis = yAxisID && this.y_axes[yAxisID]
            ? yAxisID
            : Object.keys(this.y_axes)[0] || 'y';

        this.chart.data.datasets.push({
            id, label,
            data: [{x: x1, y: y1}, {x: x2, y: y2}],
            borderColor: getColor(color),
            borderWidth: width,
            fill: false,
            tension: 0,
            pointRadius: 0,
            borderDash: dash,
            yAxisID: axis,
            hidden: false,
            showInLegend: !!label,
            _isAuxLine: true   // mark so we can clear fast
        });
        this.chart.update();
        return id;
    }

    // === Interface wrapper ===
    addLine_interface(params) {  // <--- INTERFACE
        const {
            x1, y1, x2, y2,
            color = [0, 0, 0, 1],
            width = 1,
            line_style = 'solid',
            label = '',
            y_axis = null,
            id = null
        } = params || {};
        return this.addLine(x1, y1, x2, y2, color, width, line_style, label, y_axis, id);
    }

    removeLine(lineId) {
        this.chart.data.datasets = this.chart.data.datasets.filter(d => d.id !== lineId);
        this.chart.update();
    }

    // === Interface wrapper ===
    removeLine_interface(lineId) {  // <--- INTERFACE
        return this.removeLine(lineId);
    }

    clearLines() {
        this.chart.data.datasets = this.chart.data.datasets.filter(d => !d._isAuxLine);
        this.chart.update();
    }

    // === Interface wrapper ===
    clearLines_interface() {  // <--- INTERFACE
        return this.clearLines();
    }

    updateXAxis() {
        const ax = this.x_axis.config;
        const scale = this.chart.options.scales.x;
        if (ax.ticks_mode === 'custom') {
            scale.ticks.autoSkip = false;
            const all = ax.ticks.concat(ax.major_ticks || []);
            if (all.length) {
                scale.min = ax.min !== 'auto' ? ax.min : Math.min(...all);
                scale.max = ax.max !== 'auto' ? ax.max : Math.max(...all);
            }
        } else {
            scale.ticks.autoSkip = ax.auto_skip;
            if (ax.min !== 'auto') scale.min = ax.min; else delete scale.min;
            if (ax.max !== 'auto') scale.max = ax.max; else delete scale.max;
        }
        this.chart.update();
    }

    updateXAxisFromConfig(config) {
        Object.assign(this.x_axis.config, config);
        const scaleOpts = this.chart.options.scales.x;
        const tickOpts = scaleOpts.ticks ? {...scaleOpts.ticks} : {};
        const cfg = this.x_axis.config;
        tickOpts.autoSkip = (cfg.ticks_mode === 'custom') ? false : !!cfg.auto_skip;
        tickOpts.stepSize = cfg.step_size;
        tickOpts.callback = (value, index, ticks) => {
            const live = this.x_axis.config;
            const eps = (live.step_size || 1) * 1e-6;
            const isMaj = !!(ticks && ticks[index] && ticks[index].major);
            const inCustom = live.ticks_mode === 'custom'
                && Array.isArray(live.ticks)
                && live.ticks.some(t => Math.abs(t - value) < eps);
            if (live.ticks_mode === 'custom' && !inCustom && !isMaj) return '';
            const scale = this.chart.scales.x;
            return scale && scale.getLabelForValue ? scale.getLabelForValue(value) : value;
        };
        scaleOpts.ticks = tickOpts;

        if (cfg.ticks_mode === 'custom') {
            const all = [...(cfg.ticks || []), ...(cfg.major_ticks || [])];
            if (all.length) {
                if (cfg.min !== 'auto') scaleOpts.min = cfg.min; else scaleOpts.min = Math.min(...all);
                if (cfg.max !== 'auto') scaleOpts.max = cfg.max; else scaleOpts.max = Math.max(...all);
            }
        } else {
            if (cfg.min !== 'auto') scaleOpts.min = cfg.min; else delete scaleOpts.min;
            if (cfg.max !== 'auto') scaleOpts.max = cfg.max; else delete scaleOpts.max;
        }
        this.chart.update();
    }

    // === Interface wrapper ===
    updateXAxisFromConfig_interface(config) {  // <--- INTERFACE
        return this.updateXAxisFromConfig(config);
    }

    // Convenience x-axis tick bridge wrappers
    xAxisAddTick_interface(v) {  // <--- INTERFACE
        this.x_axis.addTick(v);
        this.updateXAxis();
    }

    xAxisRemoveTick_interface(v) {  // <--- INTERFACE
        this.x_axis.removeTick(v);
        this.updateXAxis();
    }

    dimAll(dim = false) {
        Object.values(this.series).forEach(s => s.dim(dim));
    }

    // === Interface wrapper ===
    dimAll_interface(dim = true) {  // <--- INTERFACE
        return this.dimAll(dim);
    }

    getSeriesById(id) {
        return this.series[id] || null;
    }


    function(path, function_name, args, spread_args = false) {
        let first_key, remainder;

        [first_key, remainder] = splitPath(path);

        if (first_key !== this.id) {
            console.warn('LinePlot: invalid path', path);
            console.log(`Expected: ${this.id}. Got: ${first_key}`)
            return;
        }
        if (!remainder) {
            this._executeFunction(function_name, args, spread_args);
            return;
        }

        // Series branch
        if (remainder in this.series) {
            const series = this.series[remainder];
            series.executeFunction(function_name, args, spread_args);
        } else {
            console.warn('LinePlot: invalid path', path);
        }

    }

    _executeFunction(function_name, args, spread_args = false) {
        const fn = this[function_name];
        if (typeof fn !== 'function') {
            console.warn(`Function '${function_name}' not found or not callable.`);
            return null;
        }
        if (Array.isArray(args) && spread_args) return fn.apply(this, args);
        return fn.call(this, args);
    }
}


/* ------------------------------------------------------------------------------------------------------------------ */
export class LinePlotWidget extends Widget {
    constructor(id, data = {}) {
        super(id, data);

        this.element = this.initializeElement();
        this.configureElement(this.element);
        this.assignListeners(this.element);

        this.waitForLayout(this.element).then(() => {
            this.plot = new LinePlot(
                this.configuration.plot_id,
                this.element,
                data.plot.config,
                data.plot.data
            );
        });


        // setTimeout(() => {
        //     this.plot = new LinePlot(this.configuration.plot_id, this.element, data.plot.config, data.plot.data);
        // }, 250);

    }

    initializeElement() {
        const element = document.createElement('div');
        element.classList.add('lineplot-widget');
        return element;
    }

    configureElement(element) {
        super.configureElement(element);
    }

    resize() {
    }

    update(data) {
        // currently unused
    }

    updateConfig(data) {
        return undefined;
    }

    onMessage(msg) {
        super.onMessage(msg);

        switch (msg.type) {
            case 'plot_function':
                this.plot.function(msg.path, msg.function_name, msg.arguments, msg.spread_args);
                break;
        }
    }

    function

    waitForLayout(el) {
        return new Promise((resolve) => {
            const isReady = () =>
                el.isConnected &&
                el.clientWidth > 0 &&
                el.clientHeight > 0 &&
                getComputedStyle(el).display !== 'none' &&
                getComputedStyle(el).visibility !== 'hidden';

            if (isReady()) return resolve();

            // Observe size & style changes that could make it visible
            const ro = new ResizeObserver(() => {
                if (isReady()) done();
            });
            ro.observe(el);

            const mo = new MutationObserver(() => {
                if (isReady()) done();
            });
            mo.observe(el, {attributes: true, attributeFilter: ['style', 'class']});

            // If your popup toggles aria-hidden or attaches/detaches, observe parent too (optional)
            const parent = el.parentElement;
            let mo2;
            if (parent) {
                mo2 = new MutationObserver(() => {
                    if (isReady()) done();
                });
                mo2.observe(parent, {attributes: true, attributeFilter: ['style', 'class', 'aria-hidden']});
            }

            function done() {
                ro.disconnect();
                mo.disconnect();
                mo2?.disconnect();
                resolve();
            }
        });
    }
}