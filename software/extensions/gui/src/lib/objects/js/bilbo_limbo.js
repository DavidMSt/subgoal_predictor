import {Widget} from "../objects.js";
import {getColor} from "../../helpers.js";

export class BilboLimboWidget extends Widget {

    constructor(id, data = {}) {
        super(id, data);

        this.bilbos = {};
        this.rectangles = {};
        this.circles = {};
        this.paths = {};
        this.labels = {left: null, right: null};

        this.sceneConfig = {
            x_range: [-1.0, 1.0],
            floor_height: 0.04,
            floor_color: [0.88, 0.88, 0.88],
            floor_edge_color: [0.4, 0.4, 0.4],
            background_color: [0.15, 0.15, 0.2],
            padding: 0.05,
            show_grid: false,
            grid_spacing: 0.1,
            ...(this.configuration || {}),
        };

        // Load initial scene from configuration payload
        if (this.configuration) {
            this._loadScene(this.configuration);
        }

        this.element = this._initElement();
        this.configureElement(this.element);
        this.assignListeners(this.element);
    }

    /* ============================================================================================================== */
    /*  DOM setup                                                                                                     */
    /* ============================================================================================================== */

    _initElement() {
        const el = document.createElement('div');
        el.classList.add('widget', 'bilbo-limbo-widget');

        this.canvas = document.createElement('canvas');
        el.appendChild(this.canvas);

        this.ctx = this.canvas.getContext('2d');
        return el;
    }

    /* ============================================================================================================== */
    /*  Coordinate transform                                                                                          */
    /* ============================================================================================================== */

    _computeTransform() {
        const dpr = window.devicePixelRatio || 1;
        const cw = this.canvas.width;
        const ch = this.canvas.height;

        const cfg = this.sceneConfig;
        const pad = cfg.padding;
        const xRange = cfg.x_range;
        const floorH = cfg.floor_height;

        const worldW = xRange[1] - xRange[0];
        const maxH = this._getMaxContentHeight();
        // Full world height: floor slab + content above floor + padding top only
        const worldH = floorH + maxH + pad;

        // Equal aspect ratio — fit whichever dimension is tighter
        const scale = Math.min(cw / worldW, ch / worldH);

        // Horizontal: center the x_range
        const usedW = worldW * scale;
        const offsetX = (cw - usedW) / 2;

        // Vertical: anchor floor flush to the bottom of the canvas.
        const floorBottomPx = ch;

        return {
            dpr,
            cw, ch,
            scale,
            toCanvasX: (wx) => offsetX + (wx - xRange[0]) * scale,
            // y=0 (floor surface) → floorBottomPx - floorH*scale
            // y=-floorH (floor bottom) → floorBottomPx
            toCanvasY: (wy) => floorBottomPx - (wy + floorH) * scale,
            toCanvasLen: (wl) => wl * scale,
            worldW, worldH,
            xRange,
            floorH,
        };
    }

    _getMaxContentHeight() {
        let maxH = 0.15; // minimum so empty scenes still look reasonable
        for (const b of Object.values(this.bilbos)) {
            const cfg = b.config;
            const h = cfg.wheel_radius + cfg.body_height;
            if (h > maxH) maxH = h;
        }
        for (const r of Object.values(this.rectangles)) {
            const top = r.y + r.height;
            if (top > maxH) maxH = top;
        }
        for (const c of Object.values(this.circles)) {
            const top = c.y + c.radius;
            if (top > maxH) maxH = top;
        }
        for (const p of Object.values(this.paths)) {
            if (p.y) {
                for (const py of p.y) {
                    if (py > maxH) maxH = py;
                }
            }
        }
        return maxH;
    }

    /* ============================================================================================================== */
    /*  Drawing                                                                                                       */
    /* ============================================================================================================== */

    draw() {
        const rect = this.element.getBoundingClientRect();
        if (rect.width === 0 || rect.height === 0) return;

        const dpr = window.devicePixelRatio || 1;
        this.canvas.style.width = rect.width + 'px';
        this.canvas.style.height = rect.height + 'px';
        this.canvas.width = Math.round(rect.width * dpr);
        this.canvas.height = Math.round(rect.height * dpr);

        const ctx = this.ctx;
        const T = this._computeTransform();

        // Background
        ctx.fillStyle = this._resolveColor(this.sceneConfig.background_color);
        ctx.fillRect(0, 0, T.cw, T.ch);

        // Grid
        if (this.sceneConfig.show_grid) {
            this._drawGrid(ctx, T);
        }

        // Floor
        this._drawFloor(ctx, T);

        // Rectangles (obstacles)
        for (const r of Object.values(this.rectangles)) {
            this._drawRectangle(ctx, r, T);
        }

        // Paths (trajectories)
        for (const p of Object.values(this.paths)) {
            this._drawPath(ctx, p, T);
        }

        // Circles (obstacles)
        for (const c of Object.values(this.circles)) {
            this._drawCircle(ctx, c, T);
        }

        // Robots
        for (const b of Object.values(this.bilbos)) {
            this._drawBilbo(ctx, b, T);
        }

        // Labels (on top of everything)
        this._drawLabels(ctx, T);
    }

    _drawFloor(ctx, T) {
        const cfg = this.sceneConfig;
        const floorH = cfg.floor_height;

        // Floor slab: from y = -floorH to y = 0
        const x0 = T.toCanvasX(cfg.x_range[0]);
        const y0 = T.toCanvasY(0);
        const w = T.toCanvasLen(cfg.x_range[1] - cfg.x_range[0]);
        const h = T.toCanvasLen(floorH);

        ctx.fillStyle = this._resolveColor(cfg.floor_color);
        ctx.fillRect(x0, y0, w, h);

        // Floor edge line at y=0
        ctx.strokeStyle = this._resolveColor(cfg.floor_edge_color);
        ctx.lineWidth = 2 * T.dpr;
        ctx.beginPath();
        ctx.moveTo(x0, y0);
        ctx.lineTo(x0 + w, y0);
        ctx.stroke();
    }

    _drawGrid(ctx, T) {
        const cfg = this.sceneConfig;
        const spacing = cfg.grid_spacing;
        const xMin = cfg.x_range[0];
        const xMax = cfg.x_range[1];

        ctx.strokeStyle = 'rgba(255, 255, 255, 0.08)';
        ctx.lineWidth = 1 * T.dpr;

        // Vertical lines — full canvas height
        const xStart = Math.ceil(xMin / spacing) * spacing;
        for (let x = xStart; x <= xMax; x += spacing) {
            const px = T.toCanvasX(x);
            ctx.beginPath();
            ctx.moveTo(px, 0);
            ctx.lineTo(px, T.toCanvasY(0));
            ctx.stroke();
        }

        // Horizontal lines — from floor up to top of canvas
        for (let y = spacing; T.toCanvasY(y) >= 0; y += spacing) {
            const py = T.toCanvasY(y);
            ctx.beginPath();
            ctx.moveTo(T.toCanvasX(xMin), py);
            ctx.lineTo(T.toCanvasX(xMax), py);
            ctx.stroke();
        }
    }

    _drawRectangle(ctx, rect, T) {
        const px = T.toCanvasX(rect.x);
        const py = T.toCanvasY(rect.y + rect.height);
        const pw = T.toCanvasLen(rect.width);
        const ph = T.toCanvasLen(rect.height);

        ctx.globalAlpha = rect.opacity ?? 1.0;
        ctx.fillStyle = this._resolveColor(rect.color);
        ctx.fillRect(px, py, pw, ph);

        if (rect.edge_color && rect.edge_width > 0) {
            ctx.strokeStyle = this._resolveColor(rect.edge_color);
            ctx.lineWidth = rect.edge_width * T.dpr;
            ctx.strokeRect(px, py, pw, ph);
        }
        ctx.globalAlpha = 1.0;
    }

    _drawCircle(ctx, circle, T) {
        const px = T.toCanvasX(circle.x);
        const py = T.toCanvasY(circle.y);
        const pr = T.toCanvasLen(circle.radius);

        ctx.globalAlpha = circle.opacity ?? 1.0;
        ctx.fillStyle = this._resolveColor(circle.color);
        ctx.beginPath();
        ctx.arc(px, py, pr, 0, Math.PI * 2);
        ctx.fill();

        if (circle.edge_color && circle.edge_width > 0) {
            ctx.strokeStyle = this._resolveColor(circle.edge_color);
            ctx.lineWidth = circle.edge_width * T.dpr;
            ctx.stroke();
        }
        ctx.globalAlpha = 1.0;
    }

    _drawBilbo(ctx, bilbo, T) {
        const cfg = bilbo.config;
        const state = bilbo.state;
        const x = state.x || 0;
        const theta = state.theta || 0;

        const wheelR = cfg.wheel_radius;
        const innerR = wheelR * cfg.wheel_inner_ratio;
        const bodyW = cfg.body_width;
        const bodyH = cfg.body_height;
        const cornerR = cfg.body_corner_radius;

        // Wheel center in canvas coords
        const wcx = T.toCanvasX(x);
        const wcy = T.toCanvasY(wheelR);

        // --- Body (rotated around wheel center) ---
        ctx.save();
        ctx.translate(wcx, wcy);
        // Positive theta = forward lean. In world coords that tilts the body.
        // Canvas y is flipped, so we negate theta for correct visual rotation.
        ctx.rotate(-theta);

        const bw = T.toCanvasLen(bodyW);
        const bh = T.toCanvasLen(bodyH);
        const cr = T.toCanvasLen(cornerR);

        ctx.globalAlpha = cfg.body_opacity ?? 0.9;
        ctx.fillStyle = this._resolveColor(cfg.body_color);

        // Body rect from wheel center upward: from (0, 0) to (0, -bodyH) in rotated frame
        this._roundedRect(ctx, -bw / 2, -bh, bw, bh, cr);
        ctx.fill();

        if (cfg.body_edge_color) {
            ctx.strokeStyle = this._resolveColor(cfg.body_edge_color);
            ctx.lineWidth = 1.5 * T.dpr;
            ctx.stroke();
        }
        ctx.globalAlpha = 1.0;
        ctx.restore();

        // --- Outer tire (black circle) ---
        const pr = T.toCanvasLen(wheelR);
        ctx.fillStyle = this._resolveColor(cfg.tire_color);
        ctx.beginPath();
        ctx.arc(wcx, wcy, pr, 0, Math.PI * 2);
        ctx.fill();

        // --- Inner hub (white circle) ---
        const ir = T.toCanvasLen(innerR);
        ctx.fillStyle = this._resolveColor(cfg.wheel_color);
        ctx.beginPath();
        ctx.arc(wcx, wcy, ir, 0, Math.PI * 2);
        ctx.fill();

        // Wheel edge
        if (cfg.wheel_edge_color) {
            ctx.strokeStyle = this._resolveColor(cfg.wheel_edge_color);
            ctx.lineWidth = 1.0 * T.dpr;
            ctx.beginPath();
            ctx.arc(wcx, wcy, pr, 0, Math.PI * 2);
            ctx.stroke();
        }
    }

    _drawPath(ctx, path, T) {
        const xs = path.x;
        const ys = path.y;
        if (!xs || !ys || xs.length < 2) return;

        ctx.globalAlpha = path.opacity ?? 1.0;
        ctx.lineWidth = (path.width ?? 2.0) * T.dpr;
        ctx.lineCap = 'round';
        ctx.lineJoin = 'round';

        if (path.dash) {
            ctx.setLineDash(path.dash.map(d => d * T.dpr));
        }

        if (path.gradient && xs.length >= 2) {
            // Draw segment by segment with interpolated colors
            const startColor = path.gradient_start_color || [0.2, 0.5, 1.0];
            const endColor = path.gradient_end_color || [1.0, 0.3, 0.2];
            const n = xs.length - 1;
            for (let i = 0; i < n; i++) {
                const t = n > 1 ? i / (n - 1) : 0;
                const r = startColor[0] + (endColor[0] - startColor[0]) * t;
                const g = startColor[1] + (endColor[1] - startColor[1]) * t;
                const b = startColor[2] + (endColor[2] - startColor[2]) * t;
                const a = (startColor[3] ?? 1) + ((endColor[3] ?? 1) - (startColor[3] ?? 1)) * t;
                ctx.strokeStyle = this._resolveColor([r, g, b, a]);
                ctx.beginPath();
                ctx.moveTo(T.toCanvasX(xs[i]), T.toCanvasY(ys[i]));
                ctx.lineTo(T.toCanvasX(xs[i + 1]), T.toCanvasY(ys[i + 1]));
                ctx.stroke();
            }
        } else {
            ctx.strokeStyle = this._resolveColor(path.color || [0.2, 0.5, 1.0]);
            ctx.beginPath();
            ctx.moveTo(T.toCanvasX(xs[0]), T.toCanvasY(ys[0]));
            for (let i = 1; i < xs.length; i++) {
                ctx.lineTo(T.toCanvasX(xs[i]), T.toCanvasY(ys[i]));
            }
            ctx.stroke();
        }

        ctx.setLineDash([]);
        ctx.globalAlpha = 1.0;
    }

    _drawLabels(ctx, T) {
        const dpr = T.dpr;
        const pad = 8 * dpr;

        for (const [side, label] of Object.entries(this.labels)) {
            if (!label || !label.text) continue;

            const fontSize = (label.font_size ?? 14) * dpr;
            const fontWeight = label.font_weight ?? 'normal';
            const fontFamily = label.font_family ?? 'sans-serif';
            ctx.font = `${fontWeight} ${fontSize}px ${fontFamily}`;
            ctx.fillStyle = this._resolveColor(label.color ?? [1, 1, 1]);
            ctx.globalAlpha = label.opacity ?? 1.0;
            ctx.textBaseline = 'top';

            if (side === 'left') {
                ctx.textAlign = 'left';
                ctx.fillText(label.text, pad, pad);
            } else {
                ctx.textAlign = 'right';
                ctx.fillText(label.text, T.cw - pad, pad);
            }
            ctx.globalAlpha = 1.0;
        }
    }

    _roundedRect(ctx, x, y, w, h, r) {
        r = Math.min(r, w / 2, h / 2);
        ctx.beginPath();
        ctx.moveTo(x + r, y);
        ctx.lineTo(x + w - r, y);
        ctx.quadraticCurveTo(x + w, y, x + w, y + r);
        ctx.lineTo(x + w, y + h - r);
        ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
        ctx.lineTo(x + r, y + h);
        ctx.quadraticCurveTo(x, y + h, x, y + h - r);
        ctx.lineTo(x, y + r);
        ctx.quadraticCurveTo(x, y, x + r, y);
        ctx.closePath();
    }

    /* ============================================================================================================== */
    /*  Color resolution                                                                                              */
    /* ============================================================================================================== */

    _resolveColor(color) {
        if (typeof color === 'string') {
            return color;
        }
        if (Array.isArray(color)) {
            return getColor(color);
        }
        return 'white';
    }

    /* ============================================================================================================== */
    /*  Scene loading from configuration (reconnect support)                                                          */
    /* ============================================================================================================== */

    _loadScene(cfg) {
        if (cfg.bilbos) {
            for (const [id, data] of Object.entries(cfg.bilbos)) {
                this.bilbos[id] = {config: {...this._defaultBilboConfig(), ...data.config}, state: data.state || {x: 0, theta: 0}};
            }
        }
        if (cfg.rectangles) {
            for (const [id, data] of Object.entries(cfg.rectangles)) {
                this.rectangles[id] = {...data};
            }
        }
        if (cfg.circles) {
            for (const [id, data] of Object.entries(cfg.circles)) {
                this.circles[id] = {...data};
            }
        }
        if (cfg.paths) {
            for (const [id, data] of Object.entries(cfg.paths)) {
                this.paths[id] = {...data};
            }
        }
        if (cfg.labels) {
            if (cfg.labels.left) this.labels.left = {...cfg.labels.left};
            if (cfg.labels.right) this.labels.right = {...cfg.labels.right};
        }
    }

    _defaultBilboConfig() {
        return {
            wheel_radius: 0.06,
            wheel_inner_ratio: 0.65,
            body_height: 0.185,
            body_width: 0.085,
            body_corner_radius: 0.005,
            tire_color: 'black',
            wheel_color: 'white',
            wheel_edge_color: [0.3, 0.3, 0.3],
            body_color: [0.3, 0.5, 0.9],
            body_edge_color: 'black',
            body_opacity: 0.9,
        };
    }

    /* ============================================================================================================== */
    /*  Function handlers (called via callFunction from Python self.function())                                       */
    /* ============================================================================================================== */

    add_bilbo({bilbo_id, config, state}) {
        this.bilbos[bilbo_id] = {
            config: {...this._defaultBilboConfig(), ...config},
            state: state || {x: 0, theta: 0},
        };
        this.draw();
    }

    remove_bilbo({bilbo_id}) {
        delete this.bilbos[bilbo_id];
        this.draw();
    }

    add_rectangle({rect_id, ...data}) {
        this.rectangles[rect_id] = data;
        this.draw();
    }

    remove_rectangle({rect_id}) {
        delete this.rectangles[rect_id];
        this.draw();
    }

    update_rectangle({rect_id, ...data}) {
        if (this.rectangles[rect_id]) {
            Object.assign(this.rectangles[rect_id], data);
            this.draw();
        }
    }

    add_circle({circle_id, ...data}) {
        this.circles[circle_id] = data;
        this.draw();
    }

    remove_circle({circle_id}) {
        delete this.circles[circle_id];
        this.draw();
    }

    update_circle({circle_id, ...data}) {
        if (this.circles[circle_id]) {
            Object.assign(this.circles[circle_id], data);
            this.draw();
        }
    }

    set_x_range({x_range}) {
        this.sceneConfig.x_range = x_range;
        this.draw();
    }

    set_grid({show_grid, grid_spacing}) {
        if (show_grid !== undefined) this.sceneConfig.show_grid = show_grid;
        if (grid_spacing !== undefined) this.sceneConfig.grid_spacing = grid_spacing;
        this.draw();
    }

    add_path({path_id, ...data}) {
        this.paths[path_id] = data;
        this.draw();
    }

    remove_path({path_id}) {
        delete this.paths[path_id];
        this.draw();
    }

    update_path({path_id, ...data}) {
        if (this.paths[path_id]) {
            Object.assign(this.paths[path_id], data);
            this.draw();
        }
    }

    set_label({side, ...data}) {
        this.labels[side] = data;
        this.draw();
    }

    clear_label({side}) {
        this.labels[side] = null;
        this.draw();
    }

    /* ============================================================================================================== */
    /*  Widget interface                                                                                              */
    /* ============================================================================================================== */

    update(data) {
        if (data.bilbo_states) {
            for (const [id, state] of Object.entries(data.bilbo_states)) {
                if (this.bilbos[id]) {
                    Object.assign(this.bilbos[id].state, state);
                }
            }
        }
        this.draw();
    }

    updateConfig(data) {
        Object.assign(this.sceneConfig, data);
        this.draw();
    }

    resize() {
        this.draw();
    }
}
