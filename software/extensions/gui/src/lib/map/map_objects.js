/* === MAP OBJECT =================================================================================================== */
import {getColor, setOpacity, splitPath} from "../helpers.js";


const DIM_OPACITY = 0.3;

// --- Trails tuning defaults (can be overridden per-object via config) ----------
const TRAIL_SIZE_SCALE = 0.1;  // relative to object body size (in world units)
const TRAIL_MIN_DIST = 0.02;  // meters (min distance moved to record a history point)
const TRAIL_MIN_DT = 60;    // ms (min time elapsed to record a history point)
const TRAIL_HALF_LIFE_MS = 20000;   // ms (brightness halves every half-life)
const TRAIL_MAX_ALPHA = 0.75;   // cap for peak alpha of the freshest trail dot

class MapObject {
    /** @type {string} */ id;
    /** @type {object} */ config;
    /** @type {object} */ parent = null;
    history = [];

    constructor(id, payload = {}) {

        const defaults = {
            name: id,
            color: [0.8, 0.8, 0.8, 1],
            visible: true,
            show_name: false,
            show_coordinates: false,
            show_trail: false,
            layer: 1,
            tooltip: null,
            highlight: false,
            dim: false,

            // --- Optional trail controls (override defaults above if desired) ---
            trail_min_dist: undefined,      // meters
            trail_min_dt: undefined,      // ms
            trail_half_life_ms: undefined,  // ms
            trail_max_len: undefined,      // number of points in history
            trail_max_alpha: undefined,     // 0..1
            trail_size_scale: undefined,    // scale factor for dot radius vs body radius
        }

        this.id = id;
        this.config = {...defaults, ...(payload.config || {})};
        this.data = payload.data || {};

    }

    get effectiveVisible() {
        if (this.parent instanceof MapObjectGroup) {
            return !!this.config.visible && !!this.parent.effectiveVisible;
        } else {
            return !!this.config.visible;
        }

    }

    get effectiveDim() {
        if (this.parent instanceof MapObjectGroup) {
            return !!this.config.dim || !!this.parent.effectiveDim;
        } else {
            return !!this.config.dim;
        }
    }

    /** @abstract */
    draw() {
        throw new Error("Method 'draw' must be implemented.");
    }

    /**
     * Distance/time-gated history recording with timestamps.
     * Stores entries of shape: { x, y, t } where t=performance.now()
     */
    _maybePushHistory(x, y, now = performance.now()) {
        const minDist = (this.config.trail_min_dist ?? TRAIL_MIN_DIST);
        const minDt = (this.config.trail_min_dt ?? TRAIL_MIN_DT);

        const n = this.history.length;

        if (n === 0) {
            this.history.push({x, y, t: now});
            return;
        }

        const last = this.history[n - 1];
        const dx = x - last.x, dy = y - last.y;
        const dist = Math.hypot(dx, dy);
        const dt = now - (last.t ?? now);

        if (dist >= minDist || dt >= minDt) {
            this.history.push({x, y, t: now});
            // Cap length if requested
            const maxLen = Math.max(0, this.config.trail_max_len || 0);
            if (maxLen > 0 && this.history.length > maxLen) {
                this.history.splice(0, this.history.length - maxLen);
            }
        }
    }

    /**
     * Age-faded trail renderer (works for Point/Agent/VisionAgent).
     * Alpha depends on time since sample, not number of overlaps.
     */
    drawTrails() {
        // Only draw if: visible, trails enabled, and this type supports trails
        if (!this.effectiveVisible) return;
        if (!this.config?.show_trail) return;

        // Trails are only for Point, Agent, VisionAgent (per your note)
        const typeOk =
            this instanceof Point ||
            this instanceof Agent ||
            this instanceof VisionAgent;
        if (!typeOk) return;

        if (!this.history || this.history.length === 0) return;

        const map = this.getMap?.();
        const ctx = map?.context;
        if (!map || !ctx) return;

        const now = performance.now();
        const halfLife = this.config.trail_half_life_ms ?? TRAIL_HALF_LIFE_MS;
        const k = Math.log(2) / Math.max(1, halfLife); // exponential decay constant

        // --- radius: use object's "body size" baseline (same semantics as before)
        const scale = map.scale || 1;
        const size = +this.config?.size || 0.05; // fallback if missing
        const sizeMode = String(this.config?.size_mode || 'meter')
            .toLowerCase()
            .replace(/s$/, ''); // normalize
        let rWorld = sizeMode === 'pixel' ? size / scale : size;

        // Trail dot smaller, with a visible minimum (~2 px)
        let dotWorld = Math.max(0, rWorld * (this.config.trail_size_scale ?? TRAIL_SIZE_SCALE));
        const MIN_DOT_PX = 2;
        const minDotWorld = MIN_DOT_PX / scale;
        dotWorld = Math.max(dotWorld, minDotWorld);

        const baseCol = getColor(this.config.color);
        const maxA = Math.max(0, Math.min(1, this.config.trail_max_alpha ?? TRAIL_MAX_ALPHA));

        ctx.save();
        for (const p of this.history) {
            const age = now - (p.t ?? now);
            const aAge = Math.exp(-k * Math.max(0, age)); // 1 -> 0 over time
            let fill = setOpacity(baseCol, aAge * maxA);  // cap max alpha
            if (this.effectiveDim) {
                fill = setOpacity(fill, DIM_OPACITY, true);
            }

            ctx.fillStyle = fill;
            ctx.beginPath();
            ctx.arc(p.x, p.y, dotWorld, 0, Math.PI * 2);
            ctx.fill();
        }
        ctx.restore();
    }

    clearHistory() {
        this.history = [];
    }

    setVisibility(visible) {
        this.config.visible = visible;
    }

    highlight(highlight = true) {
        this.config.highlight = highlight;
    }

    dim(dim) {
        this.config.dim = dim;
    }

    updateConfig(config) {
        this.config = {...this.config, ...config};
    }

    update(data) {
        this.data = {...this.data, ...data};
    }

    static buildFromPayload() {
    }

    centerOn() {
        // Nothing to do here for now, will use map.centerOn(object) later
    }

    /** @abstract */
    getLabelPosition() {
        throw new Error("Method 'getLabelPosition' must be implemented.");
    }

    /** @abstract */
    getInfo() {
        throw new Error("Method 'getInfo' must be implemented.");
    }

    getMap() {
        if (this.parent) {
            return this.parent.getMap();
        }
        return null;
    }

    remove(remove_from_parent = true) {
        const parent = this.parent;
        this.parent = null;

        if (!remove_from_parent || !parent) return;

        if (parent instanceof MapObjectGroup) {
            if (parent.objects[this.id]) delete parent.objects[this.id];
        } else if (parent && parent.objects && parent.objects[this.id]) {
            // parent is Map
            delete parent.objects[this.id];
        }

        const map = parent?.getMap?.();
        if (map) map.drawMap();
    }


}

/* === MAP OBJECT GROUP ============================================================================================= */
export class MapObjectGroup {

    /** @type {string} */ id;
    /** @type {object} */ config;
    /** @type {object} */ objects = {};
    /** @type {object} */ groups = {};
    /** @type {object} */ parent = null;

    /* == CONSTRUCTOR =============================================================================================== */
    constructor(id, payload = {}) {

        const defaults = {
            show_in_table: true,
            visible: true,
            dim: false,
        }

        this.id = id;
        this.config = {...defaults, ...(payload.config || {})};

        this.buildObjectsFromPayload(payload.objects || {});
        this.buildGroupsFromPayload(payload.groups || {});
    }

    getObjectByPath(path) {

        const [firstSegment, remainder] = splitPath(path);
        if (!firstSegment) {
            console.warn(`[Page ID: ${this.id}] No first segment in path "${path}"`);
            return null;
        }

        // Build the full‐UID key for the direct child:
        const childKey = `${this.id}/${firstSegment}`;

        // Look up the widget or group in this.objects, which is keyed by full UID
        const child = this.objects[childKey];
        if (child) {
            return child;
        }

        // Check if its a group
        const group = this.groups[childKey];
        if (group) {
            if (!remainder) {
                return group;
            } else {
                return group.getObjectByPath(remainder);
            }

        }

        console.log(this.groups);
        console.warn(`[Group ID: ${this.id}] No child with path "${path}"`);

        return null;
    }

    get effectiveVisible() {
        if (this.parent instanceof MapObjectGroup) {
            return !!this.config.visible && !!this.parent.effectiveVisible;

        } else {
            return !!this.config.visible;
        }
    }

    get effectiveDim() {
        if (this.parent instanceof MapObjectGroup) {
            return !!this.config.dim || !!this.parent.effectiveDim;
        } else {
            return !!this.config.dim;
        }
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    addObject(obj) {
        // Check if there already exists an object with the same id
        if (this.objects[obj.id]) {
            console.warn(`MapObjectGroup: Object with id '${obj.id}' already exists.`);
            return;
        }
        this.objects[obj.id] = obj;
        obj.parent = this;

        return obj
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    removeObject(obj) {
        // If obj is a string, try to get the object from the objects dictionary
        if (typeof obj === 'string') {
            obj = this.objects[obj];
        }
        if (!obj) {
            console.warn(`MapObjectGroup: Object with id '${obj.id}' does not exist.`);
            return;
        }
        // Check if obj is a child of this group
        if (obj.parent !== this) {
            console.warn(`MapObjectGroup: Object with id '${obj.id}' is not a child of this group.`);
            return;
        }
        obj.remove(false);
        delete this.objects[obj.id];
        obj.parent = null;
    }

    addGroup(group) {
        if (this.groups[group.id]) {
            console.warn(`MapObjectGroup: Group with id '${group.id}' already exists.`);
            return;
        }
        this.groups[group.id] = group;
        group.parent = this;
    }

    removeGroup(group) {
        if (typeof group === 'string') {
            group = this.groups[group];
        }
        if (!group) {
            console.warn(`MapObjectGroup: Group with id '${group.id}' does not exist.`);
            return;
        }

        if (this.groups[group.id]) {
            console.warn(`MapObjectGroup: Group with id '${group.id}' does not exist.`);
            return;
        }
        this.groups[group.id].remove(false);
        delete this.groups[group.id];
        group.parent = null;
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    handleAddMessage(message) {
        const type = message.payload.type;

        if (type === 'group') {
            const group = new MapObjectGroup(message.payload.id, message.payload);
            this.addGroup(group);
            return;
        }

        const object_type = MAP_OBJECT_MAPPING[type];
        if (!object_type) {
            console.warn(`Unknown object type ${type}.`);
            return;
        }
        const object = new object_type(message.payload.id, message.payload);
        this.addObject(object);
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    handleRemoveMessage(message) {

        const object = this.getMap().getObjectByUID(message.id);
        if (!object) {
            console.warn(`MapObjectGroup: Object with id '${message.payload.id}' does not exist.`);
            return;
        }

        if (object instanceof MapObjectGroup) {
            this.removeGroup(object);
        } else {
            this.removeObject(object);
        }

    }

    /* -------------------------------------------------------------------------------------------------------------- */
    setVisibility(visible) {
        this.config.visible = visible;
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    dim(dim) {
        this.config.dim = dim;
    }

    updateConfig(config) {
        console.warn("MAP OBJECT GROUP UPDATE CONFIG")
        console.log(this.id);
        this.config = {...this.config, ...config};
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    remove(remove_from_parent = true) {
        // snapshot keys first to avoid mutating while iterating
        const childObjs = Object.values(this.objects);
        const childGroups = Object.values(this.groups);

        // 1) remove all descendant objects
        for (const o of childObjs) {
            if (typeof o.remove === 'function') o.remove(false);
        }
        this.objects = {};

        // 2) remove all descendant groups (recursive)
        for (const g of childGroups) {
            if (typeof g.remove === 'function') g.remove(false);
        }
        this.groups = {};

        // 3) detach from parent if requested
        if (remove_from_parent && this.parent) {
            const parent = this.parent;
            this.parent = null;

            if (parent instanceof MapObjectGroup) {
                if (parent.groups[this.id]) delete parent.groups[this.id];
            } else if (parent && parent.groups && parent.groups[this.id]) {
                // parent is Map
                delete parent.groups[this.id];
            }

            const map = parent?.getMap?.();
            if (map) map.drawMap();
        }
    }

    getObjects() {
        // Start with a shallow copy of this group’s objects
        const result = {...this.objects};

        // Merge in all descendant objects
        for (const group of Object.values(this.groups)) {
            Object.assign(result, group.getObjects());
        }

        return result;
    }

    /** @abstract */
    static buildFromPayload(id, payload) {
        throw new Error("Method 'buildFromPayload' must be implemented.");
    }

    getMap() {
        if (this.parent) {
            return this.parent.getMap();
        }
        return null;
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    buildObjectsFromPayload(objects) {
        for (const [id, payload] of Object.entries(objects)) {
            const type = payload.type;
            const object_type = MAP_OBJECT_MAPPING[type];
            if (!object_type) {
                console.warn(`Unknown object type ${type}.`);
                continue;
            }
            const object = new object_type(payload.id, payload);
            this.addObject(object);
        }
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    buildGroupsFromPayload(groups) {
        for (const [id, payload] of Object.entries(groups)) {
            const group = new MapObjectGroup(payload.id, payload);
            this.addGroup(group);
        }
    }
}


/* === POINT ======================================================================================================== */
export class Point
    extends MapObject {

    constructor(id, payload = {}) {
        super(id, payload);

        const default_config = {
            name: id,
            size: 0.05,                        // radius; units depend on size_mode
            size_mode: 'meter',                // 'pixel' | 'meter'
            color: [255 / 255, 134 / 255, 125 / 255, 1], // RGBA 0..1
            border_width: 1,                   // in px
            border_color: [0, 0, 0, 1],        // RGBA 0..1
            shape: 'circle',                   // 'circle' | 'square' | 'triangle'
            highlight: false,                  // draw highlight ring
            highlight_margin_px: 4,            // ring gap (px) around point
            show_name: false,
            show_coordinates: false,

            // Trails
            show_trail: false,
            label_px: 12,                      // font px
            tooltip: null,
            dim: false,
            layer: 3,
        };

        const default_data = {
            x: 0,
            y: 0,
        };

        // merge
        this.config = {...this.config, ...default_config, ...(payload.config || {})};
        this.data = {...default_data, ...(payload.data || {})};

        // keep history: newest last
        this.history = [];
    }


    /* -------------------------------------------------------------------------------------------------------------- */
    /** Helper: radius in world units, respecting size_mode */
    _worldRadius(map) {
        if (this.config.size_mode === 'meter') {
            // size already in world units
            return Math.max(0, +this.config.size || 0);
        }
        // pixel mode: convert pixel radius to world units using current scale
        return (Math.max(0, +this.config.size || 0)) / (map.scale || 1);
    }

    _screenRadius(map) {
        const size = Math.max(0, +this.config.size || 0);
        return (this.config.size_mode === 'meter')
            ? size * (map.scale || 1)
            : size; // already px
    }

    /**
     * Simplified, stable placement: place label *north* (above) the point,
     * at a clearance of body radius + small gap. No N/E/S/W switching.
     */
    getLabelPosition(map, labelText, fontPx) {
        const {x, y} = this.data;
        const c = map.worldPointToCanvas(x, y);

        const rPx = this._screenRadius(map);
        const GAP = 6;
        const clear = Math.max(8, rPx + GAP);

        return {x: c.x, y: c.y - clear, align: 'center', baseline: 'bottom'};
    }

    /** Helper: border width in world units from px */
    _worldBorderWidth(map) {
        return (Math.max(0, +this.config.border_width || 0)) / (map.scale || 1);
    }

    /** Helper: draw the shape path at (x,y) with world radius r */
    _buildShapePath(x, y, r) {
        const p = new Path2D();
        const shape = (this.config.shape || 'circle').toLowerCase();
        if (shape === 'square') {
            p.rect(x - r, y - r, 2 * r, 2 * r);
        } else if (shape === 'triangle') {
            const h = r * Math.sqrt(3);
            p.moveTo(x, y + (2 / 3) * r);       // bottom
            p.lineTo(x - h / 2, y - (1 / 3) * r); // top-left
            p.lineTo(x + h / 2, y - (1 / 3) * r); // top-right
            p.closePath();
        } else {
            // circle (default)
            p.arc(x, y, r, 0, Math.PI * 2);
        }
        return p;
    }

    /** Override update to also track history when position changes */
    update(data) {
        const nx = (data?.x ?? this.data.x);
        const ny = (data?.y ?? this.data.y);
        // record previous position into history before applying the update
        if ((nx !== this.data.x) || (ny !== this.data.y)) {
            this._maybePushHistory(this.data.x, this.data.y);
        }
        super.update(data);
    }

    /** Draw labels in screen space so font size is pixel-accurate */
    _drawLabelsScreen(map, cx, cy) {
        const ctx = map.context;
        if (!ctx) return;
        const {show_name, show_coordinates, label_px} = this.config;
        if (!show_name && !show_coordinates) return;

        // Build the label text
        let label = '';
        if (show_name && this.config?.name) label += String(this.config.name);
        if (show_coordinates) {
            const fx = (v) => Number.isFinite(v) ? v.toFixed(2) : String(v);
            const coord = `[${fx(this.data.x)}, ${fx(this.data.y)}]`;
            label = label ? `${label} ${coord}` : coord;
        }
        if (!label) return;

        const pos = this.getLabelPosition(map, label, label_px || 12);

        ctx.save();
        ctx.setTransform(1, 0, 0, 1, 0, 0);
        ctx.font = `${label_px || 12}px Roboto, Arial, sans-serif`;
        ctx.textAlign = pos?.align || 'center';
        ctx.textBaseline = pos?.baseline || 'bottom';
        ctx.fillStyle = getColor(this.config.color);

        const anchor = pos || map.worldPointToCanvas(cx, cy);
        const xSnap = Math.round(anchor.x);
        const ySnap = Math.round(anchor.y);
        ctx.fillText(label, xSnap, ySnap);
        ctx.restore();
    }

    /** Draw highlight ring (a circle around the point), fixed px offset */
    _drawHighlight(map, x, y, rWorld) {
        if (!this.config.highlight) return;
        const ctx = map.context;
        if (!ctx) return;

        const marginWorld = (this.config.highlight_margin_px || 4) / (map.scale || 1);
        const ringWorldWidth = 2 / (map.scale || 1);

        ctx.save();
        ctx.lineWidth = ringWorldWidth;
        ctx.strokeStyle = getColor(this.config.color);
        ctx.beginPath();
        ctx.arc(x, y, rWorld + marginWorld, 0, Math.PI * 2);
        ctx.stroke();
        ctx.restore();
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    draw() {
        const map = this.getMap();
        if (!map || !map.context) return;
        if (!this.effectiveVisible) return;

        const ctx = map.context;
        const x = +this.data.x || 0;
        const y = +this.data.y || 0;

        // Helper to apply dim by multiplying existing alpha
        const dimIf = (css) => this.effectiveDim ? setOpacity(css, DIM_OPACITY, true) : css;

        // ---- point
        const rWorld = this._worldRadius(map);
        const shapePath = this._buildShapePath(x, y, rWorld);

        ctx.save();

        this.drawTrails();

        // fill
        const baseFill = getColor(this.config.color);
        ctx.fillStyle = dimIf(baseFill);
        ctx.fill(shapePath);

        // border (pixel-accurate)
        const bwWorld = this._worldBorderWidth(map);
        if (bwWorld > 0) {
            ctx.lineWidth = bwWorld;
            const baseStroke = getColor(this.config.border_color);
            ctx.strokeStyle = dimIf(baseStroke);
            ctx.stroke(shapePath);
        }
        ctx.restore();

        // ---- highlight ring (dim as well)
        if (this.config.highlight) {
            ctx.save();
            ctx.globalAlpha *= (this.effectiveDim ? DIM_OPACITY : 1);
            this._drawHighlight(map, x, y, rWorld);
            ctx.restore();
        } else {
            this._drawHighlight(map, x, y, rWorld);
        }

        // ---- labels in screen space (optional, dim too)
        if (this.config.show_name || this.config.show_coordinates) {
            ctx.save();
            ctx.globalAlpha *= (this.effectiveDim ? DIM_OPACITY : 1);
            this._drawLabelsScreen(map, x, y);
            ctx.restore();
        } else {
            this._drawLabelsScreen(map, x, y);
        }
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    getInfo() {
        return {
            id: this.id,
            type: 'Point',
            name: this.config?.name ?? this.id,
            position: {x: this.data.x, y: this.data.y},
            size: this.config.size,
            size_mode: this.config.size_mode,
            shape: this.config.shape,
            color: this.config.color,
            border: {
                width_px: this.config.border_width,
                color: this.config.border_color
            },
            trail_length: this.history.length,
            highlighted: !!this.config.highlight,
            dim: !!this.config.dim,
        };
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    /** Factory */
    static buildFromPayload(payload) {
        return new Point(payload.id, payload);
    }
}

/* === LINE ========================================================================================================= */
export class Line extends MapObject {
    constructor(id, payload = {}) {
        super(id, payload);

        const default_config = {
            name: id,
            visible: true,
            color: [1, 0, 0, 1],      // RGBA 0..1
            width: 2,                 // px (pixel-accurate on screen)
            style: 'solid',           // 'solid' | 'dashed' | 'dotted'
            dash_px: [6, 4],          // used when style='dashed'
            dot_px: [2, 3],           // used when style='dotted' (dot, gap)
            show_name: true,          // draw label
            label_px: 12,
            label_offset_px: 8,       // offset from the line (screen px) along normal
            layer: 2,                 // default below points (points use layer 3)
        };

        // start/end can be:
        //  1) [x, y] array in world units
        //  2) string UID (resolved via map.getObjectByUID)
        //  3) an object with {data:{x,y}} (e.g. a Point)
        const default_data = {
            start: [0, 0],
            end: [1, 1],
        };

        this.config = {...this.config, ...default_config, ...(payload.config || {})};
        this.data = {...default_data, ...(payload.data || {})};
    }

    /** Resolve a ref ([x,y] | uid string | object) to current world coords {x,y} */
    _resolveRef(ref, map) {
        if (!ref) return null;

        // [x, y]
        if (Array.isArray(ref) && ref.length >= 2) {
            const x = +ref[0];
            const y = +ref[1];
            if (Number.isFinite(x) && Number.isFinite(y)) return {x, y};
            return null;
        }

        // string UID
        if (typeof ref === 'string') {
            const obj = map?.getObjectByUID?.(ref);
            return this._resolveRef(obj, map);
        }

        // object with data.x / data.y
        if (typeof ref === 'object' && ref.data && Number.isFinite(+ref.data.x) && Number.isFinite(+ref.data.y)) {
            return {x: +ref.data.x, y: +ref.data.y};
        }

        return null;
    }

    /** Convert a dash pattern in px to world units (so it renders pixel-accurately in world space) */
    _dashPatternWorld(map, arrPx) {
        if (!arrPx || !arrPx.length) return [];
        const k = (map?.scale || 1);
        return arrPx.map(v => (v || 0) / k);
    }

    /** Compute upright angle for label (in radians), based on screen delta */
    _uprightAngle(sx0, sy0, sx1, sy1) {
        let ang = Math.atan2(sy1 - sy0, sx1 - sx0);
        // keep within [-90°, +90°] so text is never upside down
        if (ang > Math.PI / 2) ang -= Math.PI;
        if (ang < -Math.PI / 2) ang += Math.PI;
        return ang;
    }

    /** Midpoint in SCREEN px between two screen points */
    _midScreen(s0, s1) {
        return {x: 0.5 * (s0.x + s1.x), y: 0.5 * (s0.y + s1.y)};
    }

    /** Draw the label in screen space — pixel-snapped */
    _drawLabelScreen(map, s0, s1) {
        if (!this.config.show_name || !this.config.name) return;

        const ctx = map.context;
        if (!ctx) return;

        const label = String(this.config.name);
        const fontPx = this.config.label_px || 12;
        const offsetPx = this.config.label_offset_px || 8;

        // geometry in screen space
        const mid = this._midScreen(s0, s1);
        const ang = this._uprightAngle(s0.x, s0.y, s1.x, s1.y);

        // normal offset (screen px)
        const nx = -(s1.y - s0.y);
        const ny = (s1.x - s0.x);
        const nlen = Math.hypot(nx, ny) || 1;
        const ox = (nx / nlen) * offsetPx;
        const oy = (ny / nlen) * offsetPx;

        const tx = Math.round(mid.x + ox);
        const ty = Math.round(mid.y + oy);

        // draw label, rotated to be parallel with line
        ctx.save();
        ctx.setTransform(1, 0, 0, 1, 0, 0);
        ctx.translate(tx, ty);
        ctx.rotate(ang);
        ctx.font = `${fontPx}px Roboto, Arial, sans-serif`;
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillStyle = getColor(this.config.color);
        ctx.fillText(label, 0, 0);
        ctx.restore();
    }

    /* ---------- main draw ---------- */

    draw() {
        const map = this.getMap();
        if (!map || !map.context) return;
        if (!this.effectiveVisible) return;

        const ctx = map.context;

        const s = this._resolveRef(this.data.start, map);
        const e = this._resolveRef(this.data.end, map);
        if (!s || !e) return;

        const worldLineWidth = (this.config.width || 0) / (map.scale || 1);

        let dashWorld = [];
        if (this.config.style === 'dashed') {
            dashWorld = this._dashPatternWorld(map, this.config.dash_px || [6, 4]);
        } else if (this.config.style === 'dotted') {
            dashWorld = this._dashPatternWorld(map, this.config.dot_px || [2, 3]);
        }

        const dimIf = (css) => this.effectiveDim ? setOpacity(css, DIM_OPACITY, true) : css;

        ctx.save();
        ctx.lineWidth = worldLineWidth;
        ctx.strokeStyle = dimIf(getColor(this.config.color));
        ctx.setLineDash(dashWorld);

        ctx.beginPath();
        ctx.moveTo(s.x, s.y);
        ctx.lineTo(e.x, e.y);
        ctx.stroke();

        // reset dash
        ctx.setLineDash([]);

        // label in SCREEN space (dim too)
        const s0 = map.worldPointToCanvas(s.x, s.y);
        const s1 = map.worldPointToCanvas(e.x, e.y);

        if (this.config.show_name && this.config.name) {
            ctx.save();
            ctx.globalAlpha *= (this.effectiveDim ? DIM_OPACITY : 1);
            this._drawLabelScreen(map, s0, s1);
            ctx.restore();
        } else {
            this._drawLabelScreen(map, s0, s1);
        }

        ctx.restore();
    }

    getLabelPosition() {
        // Not used by the map directly for Line; label is drawn by _drawLabelScreen.
        // Returning midpoint in world units can still be handy to external callers.
        const map = this.getMap();
        const s = this._resolveRef(this.data.start, map);
        const e = this._resolveRef(this.data.end, map);
        if (!s || !e) return null;
        return {x: 0.5 * (s.x + e.x), y: 0.5 * (s.y + e.y)};
    }

    getInfo() {
        const map = this.getMap();
        const s = this._resolveRef(this.data.start, map);
        const e = this._resolveRef(this.data.end, map);
        return {
            id: this.id,
            type: 'Line',
            name: this.config?.name ?? this.id,
            start: s || null,
            end: e || null,
            style: this.config.style,
            width_px: this.config.width,
            color: this.config.color,
            show_name: !!this.config.show_name,
            layer: +this.config.layer
        };
    }

    /** Factory */
    static buildFromPayload(payload) {
        return new Line(payload.id, payload);
    }
}

/* === RECTANGLE ==================================================================================================== */
export class Rectangle extends MapObject {
    constructor(id, payload = {}) {
        super(id, payload);

        const default_config = {
            name: id,
            color: [1, 0, 0, 0.35],        // fill RGBA 0..1
            border_color: [0, 0, 0, 1],    // stroke RGBA 0..1
            border_width: 1,               // px (pixel-accurate)
            show_name: false,
            label_px: 12,
            layer: 1,                      // typically below points (3), above lines (1)
        };

        // geometry in meters (world units), centered at (x,y)
        const default_data = {
            x: 0,
            y: 0,
            width: 1,
            height: 1,
        };

        this.config = {...this.config, ...default_config, ...(payload.config || {})};
        this.data = {...default_data, ...(payload.data || {})};
    }

    _worldBorderWidth(map) {
        return (Math.max(0, +this.config.border_width || 0)) / (map.scale || 1);
    }

    /** Label placement just outside the rectangle — north side. */
    getLabelPosition(map, labelText, fontPx) {
        const {x, y, width, height} = this.data;
        const c = map.worldPointToCanvas(+x || 0, +y || 0);

        const scale = map.scale || 1;
        const halfHpx = Math.abs(height) * scale * 0.5;
        const clear = Math.max(8, halfHpx + 6); // above top edge by 6 px

        return {x: c.x, y: c.y - clear, align: 'center', baseline: 'bottom'};
    }

    _drawLabel(map) {
        if (!this.config.show_name || !this.config.name) return;
        const ctx = map.context;
        if (!ctx) return;

        const label = String(this.config.name);
        const fontPx = this.config.label_px || 12;

        const pos = this.getLabelPosition(map, label, fontPx);
        if (!pos) return;

        ctx.save();
        ctx.setTransform(1, 0, 0, 1, 0, 0);
        ctx.font = `${fontPx}px Roboto, Arial, sans-serif`;
        ctx.textAlign = pos.align;
        ctx.textBaseline = pos.baseline;
        ctx.fillStyle = getColor(this.config.color);
        const xSnap = Math.round(pos.x);
        const ySnap = Math.round(pos.y);
        ctx.fillText(label, xSnap, ySnap);
        ctx.restore();
    }

    draw() {
        const map = this.getMap();
        if (!map || !map.context) return;
        if (!this.effectiveVisible) return;

        const ctx = map.context;
        const x = +this.data.x || 0;
        const y = +this.data.y || 0;
        const w = Math.max(0, +this.data.width || 0);
        const h = Math.max(0, +this.data.height || 0);

        const left = x - w / 2;
        const top = y - h / 2;

        const dimIf = (css) => this.effectiveDim ? setOpacity(css, DIM_OPACITY, true) : css;

        ctx.save();
        // fill
        ctx.fillStyle = dimIf(getColor(this.config.color));
        ctx.fillRect(left, top, w, h);

        // border (pixel-accurate)
        const bwWorld = this._worldBorderWidth(map);
        if (bwWorld > 0) {
            ctx.lineWidth = bwWorld;
            ctx.strokeStyle = dimIf(getColor(this.config.border_color));
            ctx.strokeRect(left, top, w, h);
        }
        ctx.restore();

        // label in screen space (dim too)
        if (this.config.show_name && this.config.name) {
            ctx.save();
            ctx.globalAlpha *= (this.effectiveDim ? DIM_OPACITY : 1);
            this._drawLabel(map);
            ctx.restore();
        } else {
            this._drawLabel(map);
        }
    }

    getInfo() {
        return {
            id: this.id,
            type: 'Rectangle',
            name: this.config?.name ?? this.id,
            center: {x: this.data.x, y: this.data.y},
            size_m: {width: this.data.width, height: this.data.height},
            fill: this.config.color,
            border: {
                width_px: this.config.border_width,
                color: this.config.border_color,
            },
            layer: +this.config.layer
        };
    }

    static buildFromPayload(payload) {
        return new Rectangle(payload.id, payload);
    }
}

/* === CIRCLE ======================================================================================================= */
export class Circle extends MapObject {
    constructor(id, payload = {}) {
        super(id, payload);

        const default_config = {
            name: id,
            color: [1, 0, 0, 1],          // fill
            border_color: [0, 0, 0, 1],   // stroke
            border_width: 1,              // px
            show_name: false,
            label_px: 12,
            layer: 1,
            opacity: 1
        };

        // geometry in meters (world units), center + radius
        const default_data = {
            x: 0,
            y: 0,
            radius: 1,
        };

        this.config = {...this.config, ...default_config, ...(payload.config || {})};
        this.data = {...default_data, ...(payload.data || {})};
    }


    _worldBorderWidth(map) {
        return (Math.max(0, +this.config.border_width || 0)) / (map.scale || 1);
    }

    /** Label just outside the circle — north. */
    getLabelPosition(map, labelText, fontPx) {
        const cx = +this.data.x || 0;
        const cy = +this.data.y || 0;
        const r = Math.max(0, +this.data.radius || 0);

        // center in screen space
        const c = map.worldPointToCanvas(cx, cy);
        const scale = map.scale || 1;
        const rPx = r * scale;

        const offset = Math.max(8, rPx + 6); // outside the circle by 6px
        return {x: c.x, y: c.y - offset, align: 'center', baseline: 'bottom'};
    }

    _drawLabel(map) {
        if (!this.config.show_name || !this.config.name) return;
        const ctx = map.context;
        if (!ctx) return;

        const label = String(this.config.name);
        const fontPx = this.config.label_px || 12;

        const pos = this.getLabelPosition(map, label, fontPx);
        if (!pos) return;

        ctx.save();
        ctx.setTransform(1, 0, 0, 1, 0, 0);
        ctx.font = `${fontPx}px Roboto, Arial, sans-serif`;
        ctx.textAlign = pos.align;
        ctx.textBaseline = pos.baseline;
        ctx.fillStyle = getColor(this.config.color);
        const xSnap = Math.round(pos.x);
        const ySnap = Math.round(pos.y);
        ctx.fillText(label, xSnap, ySnap);
        ctx.restore();
    }

    draw() {
        const map = this.getMap();
        if (!map || !map.context) return;
        if (!this.effectiveVisible) return;

        const ctx = map.context;
        const x = +this.data.x || 0;
        const y = +this.data.y || 0;
        const r = Math.max(0, +this.data.radius || 0);

        // Build base colors using the object's own opacity, then multiply if dimmed
        const baseFill = setOpacity(getColor(this.config.color), Math.max(0, Math.min(1, this.config.opacity ?? 1)));
        const baseStroke = setOpacity(getColor(this.config.border_color), Math.max(0, Math.min(1, this.config.opacity ?? 1)));
        const fillCol = this.effectiveDim ? setOpacity(baseFill, DIM_OPACITY, true) : baseFill;
        const strokeCol = this.effectiveDim ? setOpacity(baseStroke, DIM_OPACITY, true) : baseStroke;

        ctx.save();
        // fill
        ctx.fillStyle = fillCol;
        ctx.beginPath();
        ctx.arc(x, y, r, 0, Math.PI * 2);
        ctx.fill();

        // border (pixel-accurate)
        const bwWorld = this._worldBorderWidth(map);
        if (bwWorld > 0) {
            ctx.lineWidth = bwWorld;
            ctx.strokeStyle = strokeCol;
            ctx.beginPath();
            ctx.arc(x, y, r, 0, Math.PI * 2);
            ctx.stroke();
        }
        ctx.restore();

        // label in screen space (dim too)
        if (this.config.show_name && this.config.name) {
            ctx.save();
            ctx.globalAlpha *= (this.effectiveDim ? DIM_OPACITY : 1);
            this._drawLabel(map);
            ctx.restore();
        } else {
            this._drawLabel(map);
        }
    }

    getInfo() {
        return {
            id: this.id,
            type: 'Circle',
            name: this.config?.name ?? this.id,
            center: {x: this.data.x, y: this.data.y},
            radius_m: this.data.radius,
            fill: this.config.color,
            border: {
                width_px: this.config.border_width,
                color: this.config.border_color,
            },
            layer: +this.config.layer || 0,
        };
    }

    static buildFromPayload(payload) {
        return new Circle(payload.id, payload);
    }
}

/* === ELLIPSE ===================================================================================================== */
export class Ellipse extends MapObject {
    constructor(id, payload = {}) {
        super(id, payload);

        const default_config = {
            name: id,
            color: [1, 0, 0, 0.35],       // fill RGBA 0..1
            border_color: [0, 0, 0, 1],   // stroke RGBA 0..1
            border_width: 1,              // px (pixel-accurate)
            show_name: false,
            label_px: 12,
            layer: 1,
            opacity: 1
        };

        // geometry in meters (world units)
        const default_data = {
            x: 0,
            y: 0,
            rx: 1,     // semi-major or just “x radius”
            ry: 0.5,   // semi-minor or “y radius”
            psi: 0     // rotation [rad], CCW from +x
        };

        this.config = {...this.config, ...default_config, ...(payload.config || {})};
        this.data = {...default_data, ...(payload.data || {})};
    }

    _worldBorderWidth(map) {
        return (Math.max(0, +this.config.border_width || 0)) / (map?.scale || 1);
    }

    /** Label placed “north” of the ellipse (in screen space) using a conservative offset. */
    getLabelPosition(map, labelText, fontPx) {
        const {x, y, rx, ry} = this.data;
        const c = map.worldPointToCanvas(+x || 0, +y || 0);
        const scale = map.scale || 1;
        // Use the larger projected radius for a safe top offset; cheap and stable.
        const rPx = Math.max(Math.abs(rx), Math.abs(ry)) * scale;
        const offset = Math.max(8, rPx + 6); // 6 px gap outside the top
        return {x: c.x, y: c.y - offset, align: 'center', baseline: 'bottom'};
    }

    _drawLabel(map) {
        if (!this.config.show_name || !this.config.name) return;
        const ctx = map.context;
        if (!ctx) return;

        const label = String(this.config.name);
        const fontPx = this.config.label_px || 12;

        const pos = this.getLabelPosition(map, label, fontPx);
        if (!pos) return;

        ctx.save();
        ctx.setTransform(1, 0, 0, 1, 0, 0);
        ctx.font = `${fontPx}px Roboto, Arial, sans-serif`;
        ctx.textAlign = pos.align;
        ctx.textBaseline = pos.baseline;
        ctx.fillStyle = getColor(this.config.color);
        ctx.fillText(label, Math.round(pos.x), Math.round(pos.y));
        ctx.restore();
    }

    draw() {
        const map = this.getMap();
        if (!map || !map.context) return;
        if (!this.effectiveVisible) return;

        const ctx = map.context;
        const x = +this.data.x || 0;
        const y = +this.data.y || 0;
        const rx = Math.max(0, +this.data.rx || 0);
        const ry = Math.max(0, +this.data.ry || 0);
        const rot = +this.data.psi || 0;

        // Compose base colors with opacity, then dim if needed
        const baseFill = setOpacity(getColor(this.config.color), Math.max(0, Math.min(1, this.config.opacity ?? 1)));
        const baseStroke = setOpacity(getColor(this.config.border_color), Math.max(0, Math.min(1, this.config.opacity ?? 1)));
        const fillCol = this.effectiveDim ? setOpacity(baseFill, DIM_OPACITY, true) : baseFill;
        const strokeCol = this.effectiveDim ? setOpacity(baseStroke, DIM_OPACITY, true) : baseStroke;

        ctx.save();

        // Fill
        ctx.fillStyle = fillCol;
        ctx.beginPath();
        ctx.ellipse(x, y, rx, ry, rot, 0, Math.PI * 2);
        ctx.fill();

        // Border (pixel-accurate)
        const bwWorld = this._worldBorderWidth(map);
        if (bwWorld > 0) {
            ctx.lineWidth = bwWorld;
            ctx.strokeStyle = strokeCol;
            ctx.beginPath();
            ctx.ellipse(x, y, rx, ry, rot, 0, Math.PI * 2);
            ctx.stroke();
        }

        ctx.restore();

        // Label (in screen space; respect dimming)
        if (this.config.show_name && this.config.name) {
            ctx.save();
            ctx.globalAlpha *= (this.effectiveDim ? DIM_OPACITY : 1);
            this._drawLabel(map);
            ctx.restore();
        } else {
            this._drawLabel(map);
        }
    }

    getInfo() {
        return {
            id: this.id,
            type: 'Ellipse',
            name: this.config?.name ?? this.id,
            center: {x: this.data.x, y: this.data.y},
            radii_m: {rx: this.data.rx, ry: this.data.ry},
            rotation_rad: this.data.psi,
            fill: this.config.color,
            border: {
                width_px: this.config.border_width,
                color: this.config.border_color
            },
            opacity: this.config.opacity,
            layer: +this.config.layer
        };
    }

    static buildFromPayload(payload) {
        return new Ellipse(payload.id, payload);
    }
}

/* === AGENT ======================================================================================================== */

/* === AGENT ======================================================================================================== */
// export class Agent extends MapObject {
//     constructor(id, payload = {}) {
//         super(id, payload);
//
//         const default_config = {
//             // body
//             size: 0.1,
//             size_mode: 'meter',            // accepts 'meter(s)' or 'pixel(s)'
//             color: [1, 0, 0, 1],
//             border_color: [0, 0, 0, 1],
//             border_width: 1,               // px
//
//             // arrow
//             arrow_length: 0.2,
//             arrow_length_mode: 'meter',
//             arrow_width: 0.02,             // used as stroke width & head sizing
//             arrow_width_mode: 'meter',
//             arrow_color: 'inherit',        // 'inherit' | RGBA array
//
//             // highlight (same semantics as Point)
//             highlight: false,
//             highlight_margin_px: 4,        // ring gap (px) around body
//
//             opacity: 1,  // NEW
//
//             // labels & trail
//             show_name: false,
//             show_coordinates: false,
//             label_px: 12,
//
//             layer: 4
//         };
//
//         const default_data = {
//             x: 0,
//             y: 0,
//             psi: 0,                        // radians (CCW from +x)
//         };
//
//         this.config = {...this.config, ...default_config, ...(payload.config || {})};
//         this.data = {...this.data, ...default_data, ...(payload.data || {})};
//
//         this.history = [];
//     }
//
//     /* ---------- helpers ---------- */
//     _normalizeMode(m) {
//         let s = String(m ?? 'meter').toLowerCase();
//         if (s.endsWith('s')) s = s.slice(0, -1); // 'meters' -> 'meter', 'pixels' -> 'pixel'
//         return (s === 'pixels') ? 'pixel' : s;
//     }
//
//     _toWorldUnits(val, mode, map) {
//         const m = this._normalizeMode(mode);
//         const v = +val || 0;
//         if (m === 'pixel') return v / (map?.scale || 1);
//         return v; // 'meter'
//     }
//
//     _toScreenPx(val, mode, map) {
//         const m = this._normalizeMode(mode);
//         const v = +val || 0;
//         if (m === 'meter') return v * (map?.scale || 1);
//         return v; // 'pixel'
//     }
//
//     _worldRadius(map) {
//         return this._toWorldUnits(this.config.size, this.config.size_mode, map);
//     }
//
//     _screenRadius(map) {
//         return this._toScreenPx(this.config.size, this.config.size_mode, map);
//     }
//
//     _worldBorderWidth(map) {
//         return (Math.max(0, +this.config.border_width || 0)) / (map?.scale || 1);
//     }
//
//     _arrowLengthWorld(map) {
//         return this._toWorldUnits(this.config.arrow_length, this.config.arrow_length_mode, map);
//     }
//
//     _arrowWidthWorld(map) {
//         return this._toWorldUnits(this.config.arrow_width, this.config.arrow_width_mode, map);
//     }
//
//     _arrowColorCSS() {
//         if (this.config.arrow_color === 'inherit' || this.config.arrow_color == null) {
//             return getColor(this.config.color);
//         }
//         return getColor(this.config.arrow_color);
//     }
//
//     /** Simple round body */
//     _drawBody(map, x, y, rWorld) {
//         const ctx = map.context;
//         ctx.save();
//         // fill
//         ctx.fillStyle = getColor(this.config.color);
//         ctx.beginPath();
//         ctx.arc(x, y, rWorld, 0, Math.PI * 2);
//         ctx.fill();
//
//         // border (pixel-accurate)
//         const bwWorld = this._worldBorderWidth(map);
//         if (bwWorld > 0) {
//             ctx.lineWidth = bwWorld;
//             ctx.strokeStyle = getColor(this.config.border_color);
//             ctx.beginPath();
//             ctx.arc(x, y, rWorld, 0, Math.PI * 2);
//             ctx.stroke();
//         }
//         ctx.restore();
//     }
//
//     /** Arrow as a stroked segment + small triangular head (all in WORLD space) */
//     _drawArrow(map, x, y, psi, Lw, Ww) {
//         if (!(Lw > 0)) return;
//         const ctx = map.context;
//         const ex = x + Math.cos(psi) * Lw;
//         const ey = y + Math.sin(psi) * Lw;
//
//         const nx = -Math.sin(psi);
//         const ny = Math.cos(psi);
//
//         const headLen = Math.max(Ww * 2, Lw * 0.15);
//         const baseX = ex - Math.cos(psi) * headLen;
//         const baseY = ey - Math.sin(psi) * headLen;
//         const half = Math.max(Ww, headLen * 0.4);
//
//         ctx.save();
//         // shaft (pixel-accurate width)
//         ctx.lineWidth = Ww;
//         ctx.strokeStyle = this._arrowColorCSS();
//         ctx.beginPath();
//         ctx.moveTo(x, y);
//         ctx.lineTo(baseX, baseY);
//         ctx.stroke();
//
//         // head (filled triangle)
//         ctx.fillStyle = this._arrowColorCSS();
//         ctx.beginPath();
//         ctx.moveTo(ex, ey);
//         ctx.lineTo(baseX + nx * half, baseY + ny * half);
//         ctx.lineTo(baseX - nx * half, baseY - ny * half);
//         ctx.closePath();
//         ctx.fill();
//         ctx.restore();
//     }
//
//     /** Highlight ring identical to Point’s behavior (fixed px margin converted to world) */
//     _drawHighlight(map, x, y, rWorld) {
//         if (!this.config.highlight) return;
//         const ctx = map.context;
//         if (!ctx) return;
//
//         const marginWorld = (this.config.highlight_margin_px || 4) / (map.scale || 1);
//         const ringWorldWidth = 2 / (map.scale || 1);
//
//         ctx.save();
//         ctx.lineWidth = ringWorldWidth;
//         ctx.strokeStyle = getColor(this.config.color);
//         ctx.beginPath();
//         ctx.arc(x, y, rWorld + marginWorld, 0, Math.PI * 2);
//         ctx.stroke();
//         ctx.restore();
//     }
//
//     // getLabelPosition(map, labelText, fontPx) {
//     //     const ctx = map.context;
//     //     if (!ctx) return null;
//     //
//     //     // --- world values
//     //     const x = +this.data.x || 0;
//     //     const y = +this.data.y || 0;
//     //     const psi = +this.data.psi || 0;
//     //
//     //     // --- screen points
//     //     const sC = map.worldPointToCanvas(x, y);
//     //
//     //     // Use the same length semantics as drawing, but ensure non-zero
//     //     const Lw = Math.max(
//     //         this._arrowLengthWorld(map),
//     //         this._worldRadius(map) * 1.1,
//     //         0.12
//     //     );
//     //     const tipWorld = {x: x + Math.cos(psi) * Lw, y: y + Math.sin(psi) * Lw};
//     //     const sTip = map.worldPointToCanvas(tipWorld.x, tipWorld.y);
//     //
//     //     // Screen-space forward unit vector u (center -> tip)
//     //     let ux = sTip.x - sC.x;
//     //     let uy = sTip.y - sC.y;
//     //     const ulen = Math.hypot(ux, uy) || 1;
//     //     ux /= ulen;
//     //     uy /= ulen;
//     //
//     //     // --- clearances in px (same idea as before, just explicit)
//     //     const rPx = this._screenRadius(map);
//     //     const ringExtraPx = this.config.highlight ? ((this.config.highlight_margin_px || 0) + 2) : 0;
//     //     const BASE_GAP = 4;
//     //     const clearPx = Math.max(4, rPx + ringExtraPx + BASE_GAP);
//     //
//     //     const px = (fontPx || this.config.label_px || 12);
//     //     const labelHalfH = Math.max(1, px * 1.25) * 0.5;
//     //
//     //     // Target anchor (behind the arrow)
//     //     const tx = sC.x - ux * (clearPx + labelHalfH);
//     //     const ty = sC.y - uy * (clearPx + labelHalfH);
//     //
//     //     // --- Jitter killer: smooth + snap
//     //     // Keep a tiny bit of state on the instance, auto-initialized.
//     //     if (!this._labelState) {
//     //         this._labelState = {ax: tx, ay: ty};
//     //     }
//     //
//     //     const prev = this._labelState;
//     //     const dx = tx - prev.ax, dy = ty - prev.ay;
//     //     const dist = Math.hypot(dx, dy);
//     //
//     //     // If the anchor jumped a lot (teleport / fast pan), snap immediately
//     //     const BIG_JUMP_PX = 30;
//     //     let ax, ay;
//     //     if (dist > BIG_JUMP_PX) {
//     //         ax = tx;
//     //         ay = ty;
//     //     } else {
//     //         // EMA smoothing — small smoothing factor is enough to kill flicker
//     //         const ALPHA = 0.35; // 0..1 (higher = snappier, lower = smoother)
//     //         ax = prev.ax + ALPHA * dx;
//     //         ay = prev.ay + ALPHA * dy;
//     //     }
//     //
//     //     // Final pixel snap AFTER smoothing
//     //     const xSnap = Math.round(ax);
//     //     const ySnap = Math.round(ay);
//     //
//     //     // Persist smoothed (unsnapped) position for next frame
//     //     this._labelState.ax = ax;
//     //     this._labelState.ay = ay;
//     //
//     //     return {x: xSnap, y: ySnap, align: 'center', baseline: 'middle'};
//     // }
//
//
//     // getLabelPosition(map, labelText, fontPx) {
//     //     const ctx = map.context;
//     //     if (!ctx) return null;
//     //
//     //     // --- world & screen basis
//     //     const x = +this.data.x || 0;
//     //     const y = +this.data.y || 0;
//     //     const psi = +this.data.psi || 0;
//     //
//     //     const sC = map.worldPointToCanvas(x, y);
//     //
//     //     // Forward (+u) points from center to arrow tip in SCREEN space
//     //     const Lw = Math.max(
//     //         this._arrowLengthWorld(map),
//     //         this._worldRadius(map) * 1.1,
//     //         0.12
//     //     );
//     //     const tip = map.worldPointToCanvas(x + Math.cos(psi) * Lw, y + Math.sin(psi) * Lw);
//     //
//     //     let ux = tip.x - sC.x, uy = tip.y - sC.y;
//     //     const ulen = Math.hypot(ux, uy) || 1;
//     //     ux /= ulen;
//     //     uy /= ulen;
//     //
//     //     // Tangent (screen space): rotate -u by +90° (stable side)
//     //     const tx = -uy, ty = ux;
//     //
//     //     // --- label metrics (px)
//     //     const px = (fontPx || this.config.label_px || 12);
//     //     ctx.save();
//     //     ctx.setTransform(1, 0, 0, 1, 0, 0);
//     //     ctx.font = `${px}px Roboto, Arial, sans-serif`;
//     //     const m = ctx.measureText(String(labelText || ''));
//     //     ctx.restore();
//     //
//     //     const w = Math.max(1, m.width || 0);
//     //     const asc = Math.max(0, m.actualBoundingBoxAscent ?? 0);
//     //     const desc = Math.max(0, m.actualBoundingBoxDescent ?? 0);
//     //     const h = (asc + desc) || Math.max(1, px * 1.25);
//     //
//     //     // --- body clearance in px (body + optional highlight + small gap)
//     //     const bodyPx = this._screenRadius(map);
//     //     const ringExtraPx = this.config.highlight ? ((this.config.highlight_margin_px || 0) + 2) : 0;
//     //     const BASE_GAP = 4;
//     //     const rClear = Math.max(4, bodyPx + ringExtraPx + BASE_GAP);
//     //
//     //     // Put the label on a ring just outside: radial distance accounts ONLY for height
//     //     // (width will be handled by tangential slide)
//     //     const dRad = rClear + h * 0.5;
//     //
//     //     // Initial anchor: "behind" the arrow on that ring
//     //     let ax = sC.x - ux * dRad;
//     //     let ay = sC.y - uy * dRad;
//     //
//     //     // --- Collision check with expanded AABB (axis-aligned text box expanded by rClear)
//     //     const halfWexp = w * 0.5 + rClear;
//     //     const halfHexp = h * 0.5 + rClear;
//     //
//     //     // Express circle center in the label's AABB frame (label center at (ax, ay))
//     //     // Since the label is drawn axis-aligned on screen, we just use screen deltas.
//     //     const dx0 = Math.abs(sC.x - ax);
//     //     const dy0 = Math.abs(sC.y - ay);
//     //
//     //     const overlapX = halfWexp - dx0; // > 0 means the center lies within expanded range on X
//     //     const overlapY = halfHexp - dy0; // > 0 means the center lies within expanded range on Y
//     //
//     //     if (overlapX > 0 && overlapY > 0) {
//     //         // We're still overlapping due to label width.
//     //         // Slide along the tangent just enough to make the center fall outside on Y.
//     //         // Minimal |tangential shift| = (halfHexp - dy0) + pad. dy0 is 0 here normally.
//     //         const PAD = 1; // tiny safety
//     //         const slide = overlapY + PAD;
//     //
//     //         ax += tx * slide;
//     //         ay += ty * slide;
//     //     }
//     //
//     //     // --- Smooth + snap
//     //     if (!this._labelState) this._labelState = {ax, ay};
//     //
//     //     const prev = this._labelState;
//     //     const ddx = ax - prev.ax, ddy = ay - prev.ay;
//     //     const dist = Math.hypot(ddx, ddy);
//     //
//     //     const BIG_JUMP_PX = 30;
//     //     const ALPHA = 0.35;
//     //
//     //     let sx, sy;
//     //     if (dist > BIG_JUMP_PX) {
//     //         sx = ax;
//     //         sy = ay;
//     //     } else {
//     //         sx = prev.ax + ALPHA * ddx;
//     //         sy = prev.ay + ALPHA * ddy;
//     //     }
//     //
//     //     // persist unsnapped
//     //     this._labelState.ax = sx;
//     //     this._labelState.ay = sy;
//     //
//     //     return {
//     //         x: Math.round(sx),
//     //         y: Math.round(sy),
//     //         align: 'center',
//     //         baseline: 'middle'
//     //     };
//     // }
//
//     getLabelPosition(map, labelText, fontPx) {
//         const ctx = map.context;
//         if (!ctx) return null;
//
//         // --- world & screen basis
//         const x = +this.data.x || 0;
//         const y = +this.data.y || 0;
//         const psi = +this.data.psi || 0;
//
//         const sC = map.worldPointToCanvas(x, y);
//
//         // Forward (+u) points from center to arrow tip in SCREEN space
//         const Lw = Math.max(
//             this._arrowLengthWorld(map),
//             this._worldRadius(map) * 1.1,
//             0.12
//         );
//         const tip = map.worldPointToCanvas(x + Math.cos(psi) * Lw, y + Math.sin(psi) * Lw);
//
//         let ux = tip.x - sC.x, uy = tip.y - sC.y;
//         const ulen = Math.hypot(ux, uy) || 1;
//         ux /= ulen;
//         uy /= ulen;
//
//         // Tangent (screen space): rotate -u by +90° (stable side)
//         const tx = -uy, ty = ux;
//
//         // --- label metrics (px)
//         const px = (fontPx || this.config.label_px || 12);
//         ctx.save();
//         ctx.setTransform(1, 0, 0, 1, 0, 0);
//         ctx.font = `${px}px Roboto, Arial, sans-serif`;
//         const m = ctx.measureText(String(labelText || ''));
//         ctx.restore();
//
//         const w = Math.max(1, m.width || 0);
//         const asc = Math.max(0, m.actualBoundingBoxAscent ?? 0);
//         const desc = Math.max(0, m.actualBoundingBoxDescent ?? 0);
//         const h = (asc + desc) || Math.max(1, px * 1.25);
//
//         // --- body clearance in px (body + optional highlight + small gap)
//         const bodyPx = this._screenRadius(map);
//         const ringExtraPx = this.config.highlight ? ((this.config.highlight_margin_px || 0) + 2) : 0;
//         const BASE_GAP = 4;
//         const rClear = Math.max(4, bodyPx + ringExtraPx + BASE_GAP);
//
//         // Put the label on a ring just outside: radial distance accounts ONLY for height
//         const dRad = rClear + h * 0.5;
//
//         // Initial anchor: "behind" the arrow on that ring
//         let ax = sC.x - ux * dRad;
//         let ay = sC.y - uy * dRad;
//
//         // --- Collision check with expanded AABB (axis-aligned text box expanded by rClear)
//         const halfWexp = w * 0.5 + rClear;
//         const halfHexp = h * 0.5 + rClear;
//
//         const dx0 = Math.abs(sC.x - ax);
//         const dy0 = Math.abs(sC.y - ay);
//
//         const overlapX = halfWexp - dx0; // > 0 means center lies within expanded range on X
//         const overlapY = halfHexp - dy0; // > 0 means center lies within expanded range on Y
//
//         if (overlapX > 0 && overlapY > 0) {
//             // We're still overlapping due to label width—slide along tangent minimally.
//             const PAD = 1; // tiny safety
//             const slide = overlapY + PAD;
//             ax += tx * slide;
//             ay += ty * slide;
//         }
//
//         // No smoothing — just pixel-snap and return
//         return {
//             x: Math.round(ax),
//             y: Math.round(ay),
//             align: 'center',
//             baseline: 'middle'
//         };
//     }
//
//     _drawLabelsScreen(map, x, y) {
//         const ctx = map.context;
//         if (!ctx) return;
//         const {show_name, show_coordinates, label_px} = this.config;
//         if (!show_name && !show_coordinates) return;
//
//         // label text similar to the old impl
//         let label = '';
//         if (show_name && this.config?.name) label += String(this.config.name);
//         if (show_coordinates) {
//             const fx = (v) => Number.isFinite(v) ? v.toFixed(2) : String(v);
//             const coord = `[${fx(this.data.x)}, ${fx(this.data.y)}]`;
//             label = label ? `${label} ${coord}` : coord;
//         }
//         if (!label) return;
//
//         const pos = this.getLabelPosition(map, label, this.config.label_px || 12);
//
//         ctx.save();
//         ctx.setTransform(1, 0, 0, 1, 0, 0);
//         ctx.font = `${this.config.label_px || 12}px Roboto, Arial, sans-serif`;
//         ctx.textAlign = pos?.align || 'center';
//         ctx.textBaseline = pos?.baseline || 'bottom';
//         ctx.fillStyle = getColor(this.config.color);
//         const anchor = pos || map.worldPointToCanvas(x, y);
//         const xSnap = Math.round(anchor.x);
//         const ySnap = Math.round(anchor.y);
//         ctx.fillText(label, xSnap, ySnap);
//         ctx.restore();
//     }
//
//     /* ---------- lifecycle ---------- */
//     update(data) {
//         const nx = (data?.x ?? this.data.x);
//         const ny = (data?.y ?? this.data.y);
//         if ((nx !== this.data.x) || (ny !== this.data.y)) {
//             this._maybePushHistory(this.data.x, this.data.y);
//         }
//         super.update(data);
//     }
//
//     draw() {
//         const map = this.getMap();
//         if (!map || !map.context) return;
//         if (!this.effectiveVisible) return;
//
//         const ctx = map.context;
//         const x = +this.data.x || 0;
//         const y = +this.data.y || 0;
//         const psi = +this.data.psi || 0;
//
//         // world/pixel conversions
//         const Lw = this._arrowLengthWorld(map);                         // arrow length measured from CENTER
//         const Ww = Math.max(this._arrowWidthWorld(map), 1 / (map.scale || 1)); // ensure ~>= 1px on screen
//         const rWorld = this._worldRadius(map);                          // body radius (world units)
//
//         // dim helper
//         const dimIf = (css) => this.effectiveDim ? setOpacity(css, DIM_OPACITY, true) : css;
//
//         this.drawTrails();
//
//         // --- Arrow (starts at the BODY RIM, keeps same tip semantics)
//         if (Lw > 0) {
//             const ux = Math.cos(psi), uy = Math.sin(psi);
//
//             // Tip stays Lw from center (length semantics unchanged)
//             const ex = x + ux * Lw;
//             const ey = y + uy * Lw;
//
//             // Start of the shaft is on the circle rim along heading
//             const sx = x + ux * rWorld;
//             const sy = y + uy * rWorld;
//
//             // Arrowhead geometry
//             const nx = -uy, ny = ux;
//             const headLen = Math.max(Ww * 2, Lw * 0.15);
//             const baseX = ex - ux * headLen;
//             const baseY = ey - uy * headLen;
//             const half = Math.max(Ww, headLen * 0.4);
//
//             const arrowColor = dimIf(this._arrowColorCSS());
//
//             ctx.save();
//
//             // Shaft: only draw if the head base lies beyond the rim along +u (avoid drawing under the circle)
//             const projAlong = (baseX - sx) * ux + (baseY - sy) * uy; // >0 means base is in front of rim
//             if (projAlong > 0) {
//                 ctx.lineWidth = Ww;
//                 ctx.strokeStyle = arrowColor;
//                 ctx.beginPath();
//                 ctx.moveTo(sx, sy);          // <-- starts at rim now
//                 ctx.lineTo(baseX, baseY);
//                 ctx.stroke();
//             }
//
//             // Head (always at the same tip)
//             ctx.fillStyle = arrowColor;
//             ctx.beginPath();
//             ctx.moveTo(ex, ey);
//             ctx.lineTo(baseX + nx * half, baseY + ny * half);
//             ctx.lineTo(baseX - nx * half, baseY - ny * half);
//             ctx.closePath();
//             ctx.fill();
//
//             ctx.restore();
//         }
//
//         // --- Body (dimmed)
//         {
//             ctx.save();
//             // fill
//             ctx.fillStyle = dimIf(getColor(this.config.color));
//             ctx.beginPath();
//             ctx.arc(x, y, rWorld, 0, Math.PI * 2);
//             ctx.fill();
//
//             // border (pixel-accurate)
//             const bwWorld = this._worldBorderWidth(map);
//             if (bwWorld > 0) {
//                 ctx.lineWidth = bwWorld;
//                 ctx.strokeStyle = dimIf(getColor(this.config.border_color));
//                 ctx.beginPath();
//                 ctx.arc(x, y, rWorld, 0, Math.PI * 2);
//                 ctx.stroke();
//             }
//             ctx.restore();
//         }
//
//         // --- Highlight ring (dim too), same as Point
//         if (this.config.highlight) {
//             ctx.save();
//             ctx.globalAlpha *= (this.effectiveDim ? DIM_OPACITY : 1);
//             this._drawHighlight(map, x, y, rWorld);
//             ctx.restore();
//         } else {
//             this._drawHighlight(map, x, y, rWorld);
//         }
//
//         // --- Labels (dimmed)
//         if (this.config.show_name || this.config.show_coordinates) {
//             ctx.save();
//             ctx.globalAlpha *= (this.effectiveDim ? DIM_OPACITY : 1);
//             this._drawLabelsScreen(map, x, y);
//             ctx.restore();
//         } else {
//             this._drawLabelsScreen(map, x, y);
//         }
//     }
//
//     getInfo() {
//         return {
//             id: this.id,
//             type: 'Agent',
//             name: this.config?.name ?? this.id,
//             position: {x: this.data.x, y: this.data.y},
//             psi_rad: this.data.psi,
//             size: this.config.size,
//             size_mode: this._normalizeMode(this.config.size_mode),
//             color: this.config.color,
//             arrow: {
//                 length: this.config.arrow_length,
//                 length_mode: this._normalizeMode(this.config.arrow_length_mode),
//                 width: this.config.arrow_width,
//                 width_mode: this._normalizeMode(this.config.arrow_width_mode),
//                 color: this.config.arrow_color
//             },
//             trail_length: this.history.length,
//             highlighted: !!this.config.highlight,
//             layer: +this.config.layer
//         };
//     }
// }


export class Agent extends MapObject {
    constructor(id, payload = {}) {
        super(id, payload);

        const default_config = {
            // body
            size: 0.1,
            size_mode: 'meter',            // accepts 'meter(s)' or 'pixel(s)'
            color: [1, 0, 0, 1],
            border_color: [0, 0, 0, 1],
            border_width: 1,               // px

            // arrow
            arrow_length: 0.2,
            arrow_length_mode: 'meter',
            arrow_width: 0.02,             // used as stroke width & head sizing
            arrow_width_mode: 'meter',
            arrow_color: 'inherit',        // 'inherit' | RGBA array

            // highlight (same semantics as Point)
            highlight: false,
            highlight_margin_px: 4,        // ring gap (px) around body

            opacity: 1,  // NEW

            // labels & trail
            show_name: false,
            show_coordinates: false,
            label_px: 12,

            layer: 4
        };

        const default_data = {
            x: 0,
            y: 0,
            psi: 0,                        // radians (CCW from +x)
        };

        this.config = {...this.config, ...default_config, ...(payload.config || {})};
        this.data = {...this.data, ...default_data, ...(payload.data || {})};

        this.history = [];
    }

    /* ---------- helpers ---------- */
    _normalizeMode(m) {
        let s = String(m ?? 'meter').toLowerCase();
        if (s.endsWith('s')) s = s.slice(0, -1); // 'meters' -> 'meter', 'pixels' -> 'pixel'
        return (s === 'pixels') ? 'pixel' : s;
    }

    _toWorldUnits(val, mode, map) {
        const m = this._normalizeMode(mode);
        const v = +val || 0;
        if (m === 'pixel') return v / (map?.scale || 1);
        return v; // 'meter'
    }

    _toScreenPx(val, mode, map) {
        const m = this._normalizeMode(mode);
        const v = +val || 0;
        if (m === 'meter') return v * (map?.scale || 1);
        return v; // 'pixel'
    }

    _worldRadius(map) {
        return this._toWorldUnits(this.config.size, this.config.size_mode, map);
    }

    _screenRadius(map) {
        return this._toScreenPx(this.config.size, this.config.size_mode, map);
    }

    _worldBorderWidth(map) {
        return (Math.max(0, +this.config.border_width || 0)) / (map?.scale || 1);
    }

    _arrowLengthWorld(map) {
        return this._toWorldUnits(this.config.arrow_length, this.config.arrow_length_mode, map);
    }

    _arrowWidthWorld(map) {
        return this._toWorldUnits(this.config.arrow_width, this.config.arrow_width_mode, map);
    }

    _arrowColorCSS() {
        if (this.config.arrow_color === 'inherit' || this.config.arrow_color == null) {
            return getColor(this.config.color);
        }
        return getColor(this.config.arrow_color);
    }

    /** Apply base opacity from config.opacity by multiplying existing alpha */
    _applyOpacity(css) {
        const o = +this.config.opacity;
        const a = Number.isFinite(o) ? Math.min(1, Math.max(0, o)) : 1;
        return (a === 1) ? css : setOpacity(css, a, true); // true => multiply existing alpha
    }

    /** Simple round body */
    _drawBody(map, x, y, rWorld) {
        const ctx = map.context;
        ctx.save();

        // fill (with base opacity, and dim if needed)
        let fillCss = getColor(this.config.color);
        if (this.effectiveDim) fillCss = setOpacity(fillCss, DIM_OPACITY, true);
        fillCss = this._applyOpacity(fillCss);

        ctx.fillStyle = fillCss;
        ctx.beginPath();
        ctx.arc(x, y, rWorld, 0, Math.PI * 2);
        ctx.fill();

        // border (pixel-accurate)
        const bwWorld = this._worldBorderWidth(map);
        if (bwWorld > 0) {
            let strokeCss = getColor(this.config.border_color);
            if (this.effectiveDim) strokeCss = setOpacity(strokeCss, DIM_OPACITY, true);
            strokeCss = this._applyOpacity(strokeCss);

            ctx.lineWidth = bwWorld;
            ctx.strokeStyle = strokeCss;
            ctx.beginPath();
            ctx.arc(x, y, rWorld, 0, Math.PI * 2);
            ctx.stroke();
        }
        ctx.restore();
    }

    /** Arrow as a stroked segment + small triangular head (all in WORLD space) */
    _drawArrow(map, x, y, psi, Lw, Ww) {
        if (!(Lw > 0)) return;
        const ctx = map.context;
        const ex = x + Math.cos(psi) * Lw;
        const ey = y + Math.sin(psi) * Lw;

        const nx = -Math.sin(psi);
        const ny = Math.cos(psi);

        const headLen = Math.max(Ww * 2, Lw * 0.15);
        const baseX = ex - Math.cos(psi) * headLen;
        const baseY = ey - Math.sin(psi) * headLen;
        const half = Math.max(Ww, headLen * 0.4);

        ctx.save();

        // colors with dim + base opacity
        let arrowCss = this._arrowColorCSS();
        if (this.effectiveDim) arrowCss = setOpacity(arrowCss, DIM_OPACITY, true);
        arrowCss = this._applyOpacity(arrowCss);

        // shaft (pixel-accurate width)
        ctx.lineWidth = Ww;
        ctx.strokeStyle = arrowCss;
        ctx.beginPath();
        ctx.moveTo(x, y);
        ctx.lineTo(baseX, baseY);
        ctx.stroke();

        // head (filled triangle)
        ctx.fillStyle = arrowCss;
        ctx.beginPath();
        ctx.moveTo(ex, ey);
        ctx.lineTo(baseX + nx * half, baseY + ny * half);
        ctx.lineTo(baseX - nx * half, baseY - ny * half);
        ctx.closePath();
        ctx.fill();
        ctx.restore();
    }

    /** Highlight ring identical to Point’s behavior (fixed px margin converted to world) */
    _drawHighlight(map, x, y, rWorld) {
        if (!this.config.highlight) return;
        const ctx = map.context;
        if (!ctx) return;

        const marginWorld = (this.config.highlight_margin_px || 4) / (map.scale || 1);
        const ringWorldWidth = 2 / (map.scale || 1);

        ctx.save();
        ctx.lineWidth = ringWorldWidth;
        ctx.strokeStyle = getColor(this.config.color);
        ctx.beginPath();
        ctx.arc(x, y, rWorld + marginWorld, 0, Math.PI * 2);
        ctx.stroke();
        ctx.restore();
    }

    getLabelPosition(map, labelText, fontPx) {
        const ctx = map.context;
        if (!ctx) return null;

        // --- world & screen basis
        const x = +this.data.x || 0;
        const y = +this.data.y || 0;
        const psi = +this.data.psi || 0;

        const sC = map.worldPointToCanvas(x, y);

        // Forward (+u) points from center to arrow tip in SCREEN space
        const Lw = Math.max(
            this._arrowLengthWorld(map),
            this._worldRadius(map) * 1.1,
            0.12
        );
        const tip = map.worldPointToCanvas(x + Math.cos(psi) * Lw, y + Math.sin(psi) * Lw);

        let ux = tip.x - sC.x, uy = tip.y - sC.y;
        const ulen = Math.hypot(ux, uy) || 1;
        ux /= ulen;
        uy /= ulen;

        // Tangent (screen space): rotate -u by +90° (stable side)
        const tx = -uy, ty = ux;

        // --- label metrics (px)
        const px = (fontPx || this.config.label_px || 12);
        ctx.save();
        ctx.setTransform(1, 0, 0, 1, 0, 0);
        ctx.font = `${px}px Roboto, Arial, sans-serif`;
        const m = ctx.measureText(String(labelText || ''));
        ctx.restore();

        const w = Math.max(1, m.width || 0);
        const asc = Math.max(0, m.actualBoundingBoxAscent ?? 0);
        const desc = Math.max(0, m.actualBoundingBoxDescent ?? 0);
        const h = (asc + desc) || Math.max(1, px * 1.25);

        // --- body clearance in px (body + optional highlight + small gap)
        const bodyPx = this._screenRadius(map);
        const ringExtraPx = this.config.highlight ? ((this.config.highlight_margin_px || 0) + 2) : 0;
        const BASE_GAP = 4;
        const rClear = Math.max(4, bodyPx + ringExtraPx + BASE_GAP);

        // Put the label on a ring just outside: radial distance accounts ONLY for height
        const dRad = rClear + h * 0.5;

        // Initial anchor: "behind" the arrow on that ring
        let ax = sC.x - ux * dRad;
        let ay = sC.y - uy * dRad;

        // --- Collision check with expanded AABB (axis-aligned text box expanded by rClear)
        const halfWexp = w * 0.5 + rClear;
        const halfHexp = h * 0.5 + rClear;

        const dx0 = Math.abs(sC.x - ax);
        const dy0 = Math.abs(sC.y - ay);

        const overlapX = halfWexp - dx0; // > 0 means center lies within expanded range on X
        const overlapY = halfHexp - dy0; // > 0 means center lies within expanded range on Y

        if (overlapX > 0 && overlapY > 0) {
            // We're still overlapping due to label width—slide along tangent minimally.
            const PAD = 1; // tiny safety
            const slide = overlapY + PAD;
            ax += tx * slide;
            ay += ty * slide;
        }

        // No smoothing — just pixel-snap and return
        return {
            x: Math.round(ax),
            y: Math.round(ay),
            align: 'center',
            baseline: 'middle'
        };
    }

    _drawLabelsScreen(map, x, y) {
        const ctx = map.context;
        if (!ctx) return;
        const {show_name, show_coordinates, label_px} = this.config;
        if (!show_name && !show_coordinates) return;

        // label text similar to the old impl
        let label = '';
        if (show_name && this.config?.name) label += String(this.config.name);
        if (show_coordinates) {
            const fx = (v) => Number.isFinite(v) ? v.toFixed(2) : String(v);
            const coord = `[${fx(this.data.x)}, ${fx(this.data.y)}]`;
            label = label ? `${label} ${coord}` : coord;
        }
        if (!label) return;

        const pos = this.getLabelPosition(map, label, this.config.label_px || 12);

        ctx.save();
        ctx.setTransform(1, 0, 0, 1, 0, 0);
        ctx.font = `${this.config.label_px || 12}px Roboto, Arial, sans-serif`;
        ctx.textAlign = pos?.align || 'center';
        ctx.textBaseline = pos?.baseline || 'bottom';
        ctx.fillStyle = getColor(this.config.color);
        const anchor = pos || map.worldPointToCanvas(x, y);
        const xSnap = Math.round(anchor.x);
        const ySnap = Math.round(anchor.y);
        ctx.fillText(label, xSnap, ySnap);
        ctx.restore();
    }

    /* ---------- lifecycle ---------- */
    update(data) {
        const nx = (data?.x ?? this.data.x);
        const ny = (data?.y ?? this.data.y);
        if ((nx !== this.data.x) || (ny !== this.data.y)) {
            this._maybePushHistory(this.data.x, this.data.y);
        }
        super.update(data);
    }

    draw() {
        const map = this.getMap();
        if (!map || !map.context) return;
        if (!this.effectiveVisible) return;

        const ctx = map.context;
        const x = +this.data.x || 0;
        const y = +this.data.y || 0;
        const psi = +this.data.psi || 0;

        // world/pixel conversions
        const Lw = this._arrowLengthWorld(map);                         // arrow length measured from CENTER
        const Ww = Math.max(this._arrowWidthWorld(map), 1 / (map.scale || 1)); // ensure ~>= 1px on screen
        const rWorld = this._worldRadius(map);                          // body radius (world units)

        // dim + base opacity helper (applies both)
        const dimIf = (css) => this._applyOpacity(this.effectiveDim ? setOpacity(css, DIM_OPACITY, true) : css);

        this.drawTrails();

        // --- Arrow (starts at the BODY RIM, keeps same tip semantics)
        if (Lw > 0) {
            const ux = Math.cos(psi), uy = Math.sin(psi);

            // Tip stays Lw from center (length semantics unchanged)
            const ex = x + ux * Lw;
            const ey = y + uy * Lw;

            // Start of the shaft is on the circle rim along heading
            const sx = x + ux * rWorld;
            const sy = y + uy * rWorld;

            // Arrowhead geometry
            const nx = -uy, ny = ux;
            const headLen = Math.max(Ww * 2, Lw * 0.15);
            const baseX = ex - ux * headLen;
            const baseY = ey - uy * headLen;
            const half = Math.max(Ww, headLen * 0.4);

            const arrowColor = dimIf(this._arrowColorCSS());

            ctx.save();

            // Shaft: only draw if the head base lies beyond the rim along +u (avoid drawing under the circle)
            const projAlong = (baseX - sx) * ux + (baseY - sy) * uy; // >0 means base is in front of rim
            if (projAlong > 0) {
                ctx.lineWidth = Ww;
                ctx.strokeStyle = arrowColor; // opacity already applied
                ctx.beginPath();
                ctx.moveTo(sx, sy);          // <-- starts at rim now
                ctx.lineTo(baseX, baseY);
                ctx.stroke();
            }

            // Head (always at the same tip)
            ctx.fillStyle = arrowColor; // opacity already applied
            ctx.beginPath();
            ctx.moveTo(ex, ey);
            ctx.lineTo(baseX + nx * half, baseY + ny * half);
            ctx.lineTo(baseX - nx * half, baseY - ny * half);
            ctx.closePath();
            ctx.fill();

            ctx.restore();
        }

        // --- Body (dimmed + base opacity)
        {
            ctx.save();
            // fill
            ctx.fillStyle = dimIf(getColor(this.config.color)); // opacity applied
            ctx.beginPath();
            ctx.arc(x, y, rWorld, 0, Math.PI * 2);
            ctx.fill();

            // border (pixel-accurate)
            const bwWorld = this._worldBorderWidth(map);
            if (bwWorld > 0) {
                ctx.lineWidth = bwWorld;
                ctx.strokeStyle = dimIf(getColor(this.config.border_color)); // opacity applied
                ctx.beginPath();
                ctx.arc(x, y, rWorld, 0, Math.PI * 2);
                ctx.stroke();
            }
            ctx.restore();
        }

        // --- Highlight ring (dim too), same as Point
        if (this.config.highlight) {
            ctx.save();
            ctx.globalAlpha *= (this.effectiveDim ? DIM_OPACITY : 1);
            this._drawHighlight(map, x, y, rWorld);
            ctx.restore();
        } else {
            this._drawHighlight(map, x, y, rWorld);
        }

        // --- Labels (dimmed)
        if (this.config.show_name || this.config.show_coordinates) {
            ctx.save();
            ctx.globalAlpha *= (this.effectiveDim ? DIM_OPACITY : 1);
            this._drawLabelsScreen(map, x, y);
            ctx.restore();
        } else {
            this._drawLabelsScreen(map, x, y);
        }
    }

    getInfo() {
        return {
            id: this.id,
            type: 'Agent',
            name: this.config?.name ?? this.id,
            position: {x: this.data.x, y: this.data.y},
            psi_rad: this.data.psi,
            size: this.config.size,
            size_mode: this._normalizeMode(this.config.size_mode),
            color: this.config.color,
            arrow: {
                length: this.config.arrow_length,
                length_mode: this._normalizeMode(this.config.arrow_length_mode),
                width: this.config.arrow_width,
                width_mode: this._normalizeMode(this.config.arrow_width_mode),
                color: this.config.arrow_color
            },
            trail_length: this.history.length,
            highlighted: !!this.config.highlight,
            layer: +this.config.layer
        };
    }
}

/* === VISION AGENT ================================================================================================= */
export class VisionAgent extends Agent {
    constructor(id, payload = {}) {

        const cfg = {
            arrow_length: 0.25,
            arrow_width: 0.03,
            ...(payload.config || {})
        };
        super(id, {...payload, config: cfg});

        const default_vision_cfg = {
            fov: Math.PI,               // radians
            vision_radius: 0.5,           // world units
            vision_opacity: 0.3         // 0..1, applied via setOpacity(color, α)
        };
        this.config = {...default_vision_cfg, ...this.config};
    }

    draw() {
        const map = this.getMap();
        if (!map || !map.context) return;
        if (!this.effectiveVisible) return;

        const ctx = map.context;
        const x = +this.data.x || 0;
        const y = +this.data.y || 0;
        const psi = +this.data.psi || 0;

        const dimIf = (css) => this.effectiveDim ? setOpacity(css, DIM_OPACITY, true) : css;

        // 1) FOV first (behind everything), apply vision_opacity then multiply if dimmed
        const R = Math.max(0, +this.config.vision_radius || 0);
        if (R > 0) {
            const fov = Math.max(0, +this.config.fov || 0);
            const a0 = psi - fov / 2;
            const a1 = psi + fov / 2;

            // base vision fill from body color with its own vision_opacity
            const baseVision = setOpacity(this.config.color, Math.max(0, Math.min(1, this.config.vision_opacity ?? 0.3)));
            const fovFill = dimIf(baseVision); // multiply if dimmed

            ctx.save();
            ctx.fillStyle = fovFill;
            ctx.beginPath();
            ctx.moveTo(x, y);
            ctx.arc(x, y, R, a0, a1);
            ctx.closePath();
            ctx.fill();
            ctx.restore();
        }

        // 2) Then normal agent rendering (our Agent.draw already dims body/arrow/labels)
        super.draw();
    }

    getInfo() {
        const base = super.getInfo();
        return {
            ...base,
            type: 'VisionAgent',
            fov_rad: this.config.fov,
            vision_radius: this.config.vision_radius,
            vision_opacity: this.config.vision_opacity
        };
    }
}

/* === COORDINATE SYSTEM ============================================================================================ */
export class CoordinateSystem extends MapObject {
    constructor(id, payload = {}) {
        super(id, payload);

        const default_config = {
            x_color: [1, 0, 0, 1],
            y_color: [0, 1, 0, 1],
            origin_color: [0.8, 0.8, 1, 1],
            length: 0.3,   // meters
            width: 0.02,   // meters (shaft width)
            opacity: 1,
            // label options
            show_name: false,
            show_coordinates: false,
            label_color: [0.9, 0.9, 0.9, 1],
            label_px: 12,
            layer: 2
        };

        const default_data = {
            x: 0,
            y: 0,
            psi: 0
        };

        this.config = {...this.config, ...default_config, ...(payload.config || {})};
        this.data = {...default_data, ...(payload.data || {})};
    }

    /* ---------- helpers ---------- */

    _axisColors() {
        const a = Math.max(0, Math.min(1, this.config.opacity ?? 1));
        return {
            x: getColor(setOpacity(this.config.x_color, a)),
            y: getColor(setOpacity(this.config.y_color, a)),
            origin: getColor(setOpacity(this.config.origin_color, a))
        };
    }

    _drawAxis(ctx, x0, y0, x1, y1, color, widthWorld) {
        const vx = x1 - x0, vy = y1 - y0;
        const L = Math.hypot(vx, vy) || 1;
        const ux = vx / L, uy = vy / L;
        const nx = -uy, ny = ux;

        const headLen = Math.max(widthWorld * 3, L * 0.12);
        const half = Math.max(widthWorld * 1.5, headLen * 0.35);

        const bx = x1 - ux * headLen;
        const by = y1 - uy * headLen;

        ctx.save();
        ctx.lineWidth = Math.max(0, +widthWorld || 0);
        ctx.strokeStyle = color;
        ctx.lineCap = 'round';
        ctx.lineJoin = 'round';

        // Shaft
        ctx.beginPath();
        ctx.moveTo(x0, y0);
        ctx.lineTo(bx, by);
        ctx.stroke();

        // Arrowhead
        ctx.fillStyle = color;
        ctx.beginPath();
        ctx.moveTo(x1, y1);
        ctx.lineTo(bx + nx * half, by + ny * half);
        ctx.lineTo(bx - nx * half, by - ny * half);
        ctx.closePath();
        ctx.fill();

        ctx.restore();
    }

    /**
     * Label position that avoids axes:
     * - Compute screen-space direction to each axis tip, sum them, and place label
     *   opposite that sum from the origin (i.e., away from both arrowheads).
     */
    getLabelPosition(map, labelText, fontPx) {
        const ctx = map.context;
        if (!ctx) return null;

        const cx = +this.data.x || 0;
        const cy = +this.data.y || 0;
        const L = Math.max(0, +this.config.length || 0);
        const W = Math.max(0, +this.config.width || 0);
        const psi = +this.data.psi || 0;

        // screen points
        const sC = map.worldPointToCanvas(cx, cy);
        const tipX = map.worldPointToCanvas(cx + Math.cos(psi) * L, cy + Math.sin(psi) * L);
        const tipY = map.worldPointToCanvas(cx - Math.sin(psi) * L, cy + Math.cos(psi) * L);

        // direction vectors to tips (screen space)
        let vx = tipX.x - sC.x, vy = tipX.y - sC.y;
        let wx = tipY.x - sC.x, wy = tipY.y - sC.y;

        // sum vector
        let sx = vx + wx, sy = vy + wy;
        const slen = Math.hypot(sx, sy) || 1;
        sx /= slen;
        sy /= slen;

        // clearance: width + small gap
        const scale = map.scale || 1;
        const widthPx = W * scale;
        const GAP = 6;
        const clearPx = Math.max(6, widthPx * 2 + GAP);

        // small bias with label size
        ctx.save();
        ctx.setTransform(1, 0, 0, 1, 0, 0);
        ctx.font = `${fontPx || 12}px Roboto, Arial, sans-serif`;
        ctx.measureText(labelText || '');
        ctx.restore();
        const labelH = Math.max(1, (fontPx || 12) * 1.25);

        // place opposite to axes sum (away from arrowheads)
        const ax = sC.x - sx * (clearPx + labelH * 0.5);
        const ay = sC.y - sy * (clearPx + labelH * 0.5);

        return {x: ax, y: ay, align: 'center', baseline: 'middle'};
    }

    _drawLabel(map) {
        const {show_name, show_coordinates, label_px} = this.config;
        if (!show_name && !show_coordinates) return;

        const ctx = map.context;
        if (!ctx) return;

        let label = '';
        if (show_name && this.config?.name) label += String(this.config.name);
        if (show_coordinates) {
            const fx = v => Number.isFinite(v) ? v.toFixed(2) : String(v);
            const coord = `[${fx(this.data.x)}, ${fx(this.data.y)}]`;
            label = label ? `${label} ${coord}` : coord;
        }
        if (!label) return;

        const pos = this.getLabelPosition(map, label, label_px || 12);

        ctx.save();
        ctx.setTransform(1, 0, 0, 1, 0, 0);
        ctx.font = `${label_px || 12}px Roboto, Arial, sans-serif`;
        ctx.textAlign = pos?.align || 'center';
        ctx.textBaseline = pos?.baseline || 'bottom';
        ctx.fillStyle = getColor(this.config.label_color);
        const anchor = pos || map.worldPointToCanvas(this.data.x, this.data.y);
        const xSnap = Math.round(anchor.x);
        const ySnap = Math.round(anchor.y);
        ctx.fillText(label, xSnap, ySnap);
        ctx.restore();
    }

    /* ---------- main draw ---------- */
    draw() {
        const map = this.getMap();
        if (!map || !map.context) return;
        if (!this.effectiveVisible) return;

        const ctx = map.context;

        const cx = +this.data.x || 0;
        const cy = +this.data.y || 0;
        const psi = +this.data.psi || 0;
        const L = Math.max(0, +this.config.length || 0);
        const W = Math.max(0, +this.config.width || 0);

        // Base colors already respect this.config.opacity via _axisColors()
        const base = this._axisColors();
        const dimIf = (css) => this.effectiveDim ? setOpacity(css, DIM_OPACITY, true) : css;

        const colX = dimIf(base.x);
        const colY = dimIf(base.y);
        const colO = dimIf(base.origin);

        const ux = Math.cos(psi), uy = Math.sin(psi);
        const vx = -Math.sin(psi), vy = Math.cos(psi);

        const x1 = cx + ux * L, y1 = cy + uy * L;
        const y1x = cx + vx * L, y1y = cy + vy * L;

        // Draw axes
        this._drawAxis(ctx, cx, cy, x1, y1, colX, W);
        this._drawAxis(ctx, cx, cy, y1x, y1y, colY, W);

        // Draw origin circle (slightly larger than line width)
        ctx.save();
        ctx.fillStyle = colO;
        const r = W * 1.3;
        ctx.beginPath();
        ctx.arc(cx, cy, r, 0, Math.PI * 2);
        ctx.fill();
        ctx.restore();

        // Label (dim label color too)
        if (this.config.show_name || this.config.show_coordinates) {
            ctx.save();
            ctx.globalAlpha *= (this.effectiveDim ? DIM_OPACITY : 1);
            this._drawLabel(map);
            ctx.restore();
        } else {
            this._drawLabel(map);
        }
    }

    getInfo() {
        return {
            id: this.id,
            type: 'CoordinateSystem',
            name: this.config?.name ?? this.id,
            center: {x: this.data.x, y: this.data.y},
            psi_rad: this.data.psi,
            length_m: this.config.length,
            width_m: this.config.width,
            opacity: this.config.opacity,
            x_color: this.config.x_color,
            y_color: this.config.y_color,
            origin_color: this.config.origin_color,
            layer: +this.config.layer
        };
    }
}

/* === FRODO ======================================================================================================== */
export class Frodo extends MapObject {
}


/* === BILBO ======================================================================================================== */
export class Bilbo extends MapObject {
}


export const MAP_OBJECT_MAPPING = {
    'point': Point,
    'agent': Agent,
    'vision_agent': VisionAgent,
    'group': MapObjectGroup,
    'line': Line,
    'coordinate_system': CoordinateSystem,
    'circle': Circle,
    'rectangle': Rectangle,
    'ellipse': Ellipse,
}