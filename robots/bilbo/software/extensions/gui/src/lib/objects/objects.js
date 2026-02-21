import {Callbacks, getColor, splitPath} from "../helpers.js";
import {ContextMenu, ContextMenuItem} from "./contextmenu.js";
import {activeGUI} from "../globals.js"
import {EventEmitter} from "events";

const isNumber = (v) => typeof v === "number" && !Number.isNaN(v);
const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
// const isGUIObject = (v) =>
//     v && typeof v === "object" && typeof v.attach === "function" && v.container instanceof HTMLElement;

function isGUIObject(v) {
    return v != null && v instanceof GUI_Object;
}

/* ================================================================================================================== */
export class GUI_Object extends EventEmitter {
    /** @type {string} */ id;
    /** @type {Callbacks} */ callbacks;

    constructor(id, payload = {}) {
        super();
        this.id = id;
        this.callbacks = new Callbacks();
        this.callbacks.add('event');
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    callFunction(function_name, args, spread_args = true) {
        const fn = this[function_name];
        if (typeof fn !== 'function') {
            console.warn(`Function '${function_name}' not found or not callable.`);
            return null;
        }
        if (Array.isArray(args) && spread_args) return fn.apply(this, args);
        return fn.call(this, args);
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    onMessage(message) {
        switch (message.type) {
            case 'function': {
                this.callFunction(message.function_name, message.args, message.spread_args);
                break;
            }
        }
    }
}

/* ================================================================================================================== */
export class GUI_Container extends GUI_Object {
    /** @type {HTMLElement|null} */ el = null;      // outer shell
    /** @type {HTMLElement|null} */ content = null; // inner content
    /** @type {Object} */ config = null;
    /** @type {GUI_Object|null} */ object = null;

    constructor(id, data = {}) {
        super(id, data);
        const defaults = {
            // sizing
            width_mode: "fill",   // 'fill' | 'fixed' | 'auto'
            width: 100,
            height_mode: "fill",  // 'fill' | 'fixed' | 'auto'
            height: 100,
            min_height: 0,
            max_height: null,
            min_width: 0,
            max_width: null,

            // inner alignment & overflow
            vertical_align: "top",      // 'top' | 'center' | 'bottom'
            horizontal_align: "center", // 'left' | 'center' | 'right'
            overflow_y: "auto",
            overflow_x: "auto",
            padding: 0,

            // visuals
            background_color: [0, 0, 0, 0],     // transparent by default
            border_color: [255, 255, 255, 0.12],
            border_width: 1,
            border_style: "solid",
            border_radius: 6,

            // optional role/class
            className: "",
            role: "",
            ariaLabel: "",
        };
        this.config = {...defaults, ...(data.config || {})};
        this.initialize();

        if (data.object) {
            this.buildObjectFromPayload(data.object);
        }
    }

    async buildObjectFromPayload(payload) {
        console.log("Container: buildObjectFromPayload", payload);
        const id = payload.id;
        const type = payload.type;

        const {OBJECT_MAPPING} = await import('./mapping.js');

        const object_class = OBJECT_MAPPING[type];
        if (!object_class) {
            console.warn(`Container: buildObjectFromPayload: unknown object type ${type}`);
            return;
        }
        const new_object = new object_class(id, payload);
        this.addObject(new_object);
    }

    addObject(object) {
        object.attach(this.content);
        object.callbacks.get('event').register(this.onObjectEvent.bind(this));
        this.object = object;
    }

    onObjectEvent(event) {
        this.callbacks.get('event').call(event);
    }

    initialize() {
        const root = document.createElement("div");
        root.className = "gui-container";
        if (this.config.className) root.classList.add(this.config.className);
        if (this.config.role) root.setAttribute("role", this.config.role);
        if (this.config.ariaLabel) root.setAttribute("aria-label", this.config.ariaLabel);

        const content = document.createElement("div");
        content.className = "gui-container__content";
        root.appendChild(content);

        this.el = root;
        this.content = content;

        this._applyConfigToStyles();
    }

    attach(parent) {
        if (!(parent instanceof HTMLElement)) return console.warn(`${this.id}: attach() parent must be HTMLElement`);
        if (!this.el) this.initialize();
        parent.appendChild(this.el);
    }

    mountElement(node) {
        if (!this.el) this.initialize();
        if (node instanceof HTMLElement) this.content.appendChild(node);
    }

    mountObject(widget) {
        if (!this.el) this.initialize();
        if (isGUIObject(widget)) widget.attach(this.content);
    }

    updateConfig(partial = {}) {
        this.config = {...this.config, ...partial};
        if (!this.el) this.initialize();
        this._applyConfigToStyles();
    }

    _applyConfigToStyles() {
        const c = this.config, root = this.el, content = this.content;
        if (!root || !content) return;

        // visuals
        root.style.setProperty("--gc-border-width", `${c.border_width}px`);
        root.style.setProperty("--gc-border-color", getColor(c.border_color) || "transparent");
        root.style.setProperty("--gc-background", getColor(c.background_color) || "transparent");
        root.style.setProperty("--gc-border-style", c.border_style || "solid");
        root.style.setProperty("--gc-radius", `${c.border_radius}px`);

        // width
        if (c.width_mode === "fill") {
            root.style.width = "100%";
            root.style.flexGrow = "1";
            root.style.flexShrink = "1";
            root.style.flexBasis = "auto";
        } else if (c.width_mode === "auto") {
            root.style.width = "auto";
            root.style.flexGrow = "0";
            root.style.flexShrink = "1";
            root.style.flexBasis = "auto";
        } else {
            root.style.width = `${c.width}px`;
            root.style.flexGrow = "0";
            root.style.flexShrink = "0";
            root.style.flexBasis = `${c.width}px`;
        }

        // height
        if (c.height_mode === "fill") {
            root.style.height = "100%";
            root.style.flexGrow = "1";
            root.style.flexShrink = "1";
            root.style.flexBasis = "0";
        } else if (c.height_mode === "auto") {
            root.style.height = "auto";
            root.style.flexGrow = "0";
            root.style.flexShrink = "0";
            root.style.flexBasis = "auto";
        } else {
            root.style.height = `${c.height}px`;
            root.style.flexGrow = "0";
            root.style.flexShrink = "0";
            root.style.flexBasis = `${c.height}px`;
        }

        // constraints
        root.style.minHeight = isNumber(c.min_height) ? `${c.min_height}px` : "";
        root.style.maxHeight = isNumber(c.max_height) ? `${c.max_height}px` : "";
        root.style.minWidth = isNumber(c.min_width) ? `${c.min_width}px` : "";
        root.style.maxWidth = isNumber(c.max_width) ? `${c.max_width}px` : "";

        // inner content (alignment & overflow)
        content.style.display = "flex";
        content.style.flexDirection = "column";
        content.style.padding = `${c.padding}px`;
        content.style.boxSizing = "border-box";
        content.style.overflowY = c.overflow_y || "visible";
        content.style.overflowX = c.overflow_x || "visible";
        content.style.width = "100%";
        content.style.height = "100%";
        content.style.justifyContent = c.vertical_align === "center" ? "center" : (c.vertical_align === "bottom" ? "flex-end" : "flex-start");
        content.style.alignItems = c.horizontal_align === "left" ? "flex-start" : (c.horizontal_align === "right" ? "flex-end" : "center");
    }

    getObjectByPath(path) {
        let [first, remainder] = splitPath(path);

        const fullKey = `${this.id}/${first}`;

        if (!this.object) {
            return null;
        }


        if (fullKey === this.object.id) {
            if (!remainder) {
                return this.object;
            } else {
                return this.object.getObjectByPath(remainder);
            }
        }

        console.warn("XXX")
        console.log(fullKey);
        console.log(this.object.id);
        return null;

    }
}

/* ================================================================================================================== */
export class GUI_Container_Stack extends GUI_Object {
    /** @type {HTMLElement|null} */ el = null;
    /** @type {HTMLElement|null} */ content = null;

    /** @type {object} */ containers = {};

    constructor(id, data = {}) {
        super(id, data);
        const defaults = {
            direction: "vertical", // 'vertical' | 'horizontal'
            spacing: 4,
            padding: 4,
            background_color: [0, 0, 0, 0],
            border_color: [255, 0, 0, 0.8],
            border_width: 0,
            border_style: "solid",
            border_radius: 6,

            // stack sizing
            width_mode: "fill",
            height_mode: "auto",
            width: 100,
            height: 100,

            className: "",
            role: "",
            ariaLabel: "",
        };
        this.config = {...defaults, ...(data.config || {})};
        this.initialize();

        if (data.containers) {
            this.buildContainersFromPayload(data.containers);
        }
    }

    buildContainersFromPayload(payload) {
        for (const [key, value] of Object.entries(payload)) {
            const type = value.type;
            if (type === "container") {
                const new_container = new GUI_Container(value.id, value);
                this.add(new_container);
            } else if (type === 'collapsible_container') {
                const new_container = new CollapsibleContainer(value.id, value);
                this.add(new_container);
            }
        }
    }

    initialize() {
        const root = document.createElement("div");
        root.className = "gui-stack";
        if (this.config.className) root.classList.add(this.config.className);
        if (this.config.role) root.setAttribute("role", this.config.role);
        if (this.config.ariaLabel) root.setAttribute("aria-label", this.config.ariaLabel);

        this.el = root;
        this.content = root;
        this._applyConfigToStyles();
    }

    attach(parent) {
        if (!(parent instanceof HTMLElement)) return console.warn(`${this.id}: attach() parent must be HTMLElement`);
        if (!this.el) this.initialize();
        parent.appendChild(this.el);
    }

    /** child: HTMLElement | GUI_Container | CollapsibleContainer | GUI_Object */
    add(child, opts = {}) {
        if (!this.el) this.initialize();
        const host = this.content;
        let node = null;

        if (child instanceof GUI_Container || child instanceof CollapsibleContainer) {
            if (!child.el) child.initialize();
            node = child.el;

            child.callbacks.get('event').register(this.onChildEvent.bind(this));

            this.containers[child.id] = child;

        } else if (isGUIObject(child)) {
            // wrap so we can apply per-item flex
            const wrap = document.createElement("div");
            wrap.className = "gui-stack__item";
            wrap.style.display = "flex";
            wrap.style.flexDirection = "column";
            host.appendChild(wrap);
            child.attach(wrap);
            node = wrap;

            child.callbacks.get('event').register(this.onChildEvent.bind(this));

        } else if (child instanceof HTMLElement) {
            node = child;
        } else {
            console.warn(`${this.id}: add() unsupported child`, child);
            return null;
        }

        this._applyChildFlex(node, opts);
        if (node.parentNode !== host) host.appendChild(node);
        return node;
    }

    onChildEvent(event) {
        this.callbacks.get('event').call(event);
    }

    clear() {
        if (this.content) this.content.textContent = "";
    }

    updateConfig(partial = {}) {
        this.config = {...this.config, ...partial};
        if (!this.el) this.initialize();
        this._applyConfigToStyles();
    }

    _applyConfigToStyles() {
        const s = this.config, root = this.el;
        if (!root) return;

        root.style.display = "flex";
        root.style.flexDirection = s.direction === "horizontal" ? "row" : "column";
        root.style.gap = `${s.spacing}px`;
        root.style.padding = `${s.padding}px`;
        root.style.boxSizing = "border-box";

        root.style.setProperty("--gs-border-width", `${s.border_width}px`);
        root.style.setProperty("--gs-border-color", getColor(s.border_color) || "transparent");
        root.style.setProperty("--gs-background", getColor(s.background_color) || "transparent");
        root.style.setProperty("--gs-border-style", s.border_style || "solid");
        root.style.setProperty("--gs-radius", `${s.border_radius}px`);

        // sizing of the stack itself
        if (s.width_mode === "fill") {
            root.style.width = "100%";
            root.style.flexGrow = "1";
            root.style.flexShrink = "1";
            root.style.flexBasis = "auto";
        } else if (s.width_mode === "auto") {
            root.style.width = "auto";
            root.style.flexGrow = "0";
            root.style.flexShrink = "1";
            root.style.flexBasis = "auto";
        } else {
            root.style.width = `${s.width}px`;
            root.style.flexGrow = "0";
            root.style.flexShrink = "0";
            root.style.flexBasis = `${s.width}px`;
        }

        if (s.height_mode === "fill") {
            root.style.height = "100%";
            root.style.flexGrow = "1";
            root.style.flexShrink = "1";
            root.style.flexBasis = "0";
        } else if (s.height_mode === "auto") {
            root.style.height = "auto";
            root.style.flexGrow = "0";
            root.style.flexShrink = "0";
            root.style.flexBasis = "auto";
        } else {
            root.style.height = `${s.height}px`;
            root.style.flexGrow = "0";
            root.style.flexShrink = "0";
            root.style.flexBasis = `${s.height}px`;
        }
    }

    _applyChildFlex(node, {grow, shrink, basis} = {}) {
        if (grow != null) node.style.flexGrow = String(grow);
        if (shrink != null) node.style.flexShrink = String(shrink);
        if (basis != null) node.style.flexBasis = (typeof basis === "number" ? `${basis}px` : basis);
    }

    getObjectByPath(path) {
        let [first, remainder] = splitPath(path);

        const fullKey = `${this.id}/${first}`;

        // Check the containers
        const container = this.containers[fullKey];

        if (container) {
            if (!remainder) {
                return container;
            } else {
                return container.getObjectByPath(remainder);
            }
        }
    }
}

export class CollapsibleContainer extends GUI_Object {
    /** @type {HTMLElement|null} */ el = null;
    /** @type {HTMLElement|null} */ head = null;
    /** @type {HTMLElement|null} */ chevron = null;
    /** @type {HTMLElement|null} */ titleEl = null;
    /** @type {HTMLElement|null} */ body = null;
    /** @type {GUI_Object|null} */ object = null;
    _open = true;
    _animMs = 160;

    constructor(id, data = {}) {
        super(id, data);

        const defaults = {
            // titlebar
            title: id,
            start_collapsed: false,
            headbar_height: 28,
            headbar_background_color: [1, 1, 1, 0.1],
            headbar_border_width: 1,
            headbar_border_color: [255, 255, 255, 0.12],
            headbar_radius: 6,
            transition_ms: 160,

            // container sizing (same API as GUI_Container)
            width_mode: "fill",
            width: 100,
            height_mode: "auto", // collapsibles typically size to content
            height: 100,
            min_height: 0,
            max_height: null,
            min_width: 0,
            max_width: null,

            vertical_align: "top",
            horizontal_align: "left",
            overflow_y: "auto",
            overflow_x: "auto",
            padding: 4,

            // outer visuals (matches GUI_Container look)
            background_color: [0, 0, 0, 0],
            border_color: [255, 255, 255, 0.12],
            border_width: 1,
            border_style: "solid",
            border_radius: 6,

            className: "",
            role: "",
            ariaLabel: "",
        };

        this.config = {...defaults, ...(data.config || {})};
        this._open = !this.config.start_collapsed;
        this._animMs = this.config.transition_ms;

        this.initialize();

        if (data.object) {
            this.buildObjectFromPayload(data.object);
        }
    }

    async buildObjectFromPayload(payload) {
        console.log("Container: buildObjectFromPayload", payload);
        const id = payload.id;
        const type = payload.type;

        const {OBJECT_MAPPING} = await import('./mapping.js');

        const object_class = OBJECT_MAPPING[type];
        if (!object_class) {
            console.warn(`Container: buildObjectFromPayload: unknown object type ${type}`);
            return;
        }
        const new_object = new object_class(id, payload);
        this.addObject(new_object);
    }

    addObject(object) {
        if (!this.el) this.initialize();

        if (isGUIObject(object)) {
            object.attach(this.body);
            object.callbacks.get('event').register(this.onChildEvent.bind(this));
        } else {
            console.warn(`${this.id}: addObject() unsupported object`, object);
        }
        this.object = object;
    }

    getObjectByPath(path) {
        let [first, remainder] = splitPath(path);
        const fullKey = `${this.id}/${first}`;

        if (!this.object) return null;

        if (fullKey === this.object.id) {
            if (!remainder) {
                return this.object;
            } else {
                return this.object.getObjectByPath(remainder);
            }
        }
    }

    onChildEvent(event) {
        this.callbacks.get('event').call(event);
    }

    initialize() {
        const root = document.createElement("div");
        root.className = "collapsible";
        if (this.config.className) root.classList.add(this.config.className);
        if (this.config.role) root.setAttribute("role", this.config.role);
        if (this.config.ariaLabel) root.setAttribute("aria-label", this.config.ariaLabel);

        // Titlebar
        const head = document.createElement("button");
        head.type = "button";
        head.className = "collapsible__head";
        head.setAttribute("aria-expanded", this._open ? "true" : "false");
        head.setAttribute("aria-controls", `${this.id}__body`);
        head.style.height = `${this.config.headbar_height}px`;
        head.style.background = getColor(this.config.headbar_background_color);
        head.style.border = `${this.config.headbar_border_width}px solid ${getColor(this.config.headbar_border_color)}`;
        head.style.borderRadius = `${this.config.headbar_radius}px`;
        head.style.userSelect = "none";

        const chev = document.createElement("span");
        chev.className = "collapsible__chevron";
        head.appendChild(chev);

        const title = document.createElement("span");
        title.className = "collapsible__title";
        title.textContent = this.config.title || this.id;
        head.appendChild(title);

        // Body (direct, no wrapper)
        const body = document.createElement("div");
        body.className = "collapsible__body";
        body.id = `${this.id}__body`;
        body.style.padding = `${this.config.padding}px`;

        root.appendChild(head);
        root.appendChild(body);

        this.el = root;
        this.head = head;
        this.chevron = chev;
        this.titleEl = title;
        this.body = body;

        this._applyContainerStyles();
        this._renderChevron();
        this._setOpenImmediate(this._open);

        // Interactions
        head.addEventListener("click", () => this.toggle());
        head.addEventListener("keydown", (e) => {
            if (e.key === " " || e.key === "Enter") {
                e.preventDefault();
                this.toggle();
            }
        });
    }

    attach(parent) {
        if (!(parent instanceof HTMLElement)) return console.warn(`${this.id}: attach() parent must be HTMLElement`);
        if (!this.el) this.initialize();
        parent.appendChild(this.el);
    }

    mountElement(node) {
        if (!this.el) this.initialize();
        if (node instanceof HTMLElement) this.body.appendChild(node);
    }

    mountObject(widget) {
        if (!this.el) this.initialize();
        if (isGUIObject(widget)) widget.attach(this.body);
    }

    setTitle(text) {
        this.config.title = text;
        if (this.titleEl) this.titleEl.textContent = String(text ?? "");
    }

    open({animate = true} = {}) {
        this._setOpen(true, animate);
    }

    close({animate = true} = {}) {
        this._setOpen(false, animate);
    }

    toggle({animate = true} = {}) {
        this._setOpen(!this._open, animate);
    }

    updateConfig(partial = {}) {
        this.config = {...this.config, ...partial};
        if (Object.prototype.hasOwnProperty.call(partial, "title")) this.setTitle(this.config.title);
        if (!this.el) this.initialize();
        this._applyContainerStyles();
    }

    destroy() {
        if (this.el?.parentNode) this.el.parentNode.removeChild(this.el);
        this.el = this.head = this.chevron = this.titleEl = this.body = null;
    }

    /* ------------------------------------------- internals --------------------------------------------------------- */
    _applyContainerStyles() {
        const c = this.config, root = this.el, body = this.body;
        if (!root || !body) return;

        // visuals (match GUI_Container style)
        root.style.setProperty("--gc-border-width", `${c.border_width}px`);
        root.style.setProperty("--gc-border-color", getColor(c.border_color) || "transparent");
        root.style.setProperty("--gc-background", getColor(c.background_color) || "transparent");
        root.style.setProperty("--gc-border-style", c.border_style || "solid");
        root.style.setProperty("--gc-radius", `${c.border_radius}px`);
        root.classList.add("gui-container"); // reuse same base border/background rules

        // layout container: flex column (head + body)
        root.style.display = "flex";
        root.style.flexDirection = "column";
        root.style.minHeight = "0";

        // constraints
        root.style.minHeight = isNumber(c.min_height) ? `${c.min_height}px` : "";
        root.style.maxHeight = isNumber(c.max_height) ? `${c.max_height}px` : "";
        root.style.minWidth = isNumber(c.min_width) ? `${c.min_width}px` : "";
        root.style.maxWidth = isNumber(c.max_width) ? `${c.max_width}px` : "";

        // body alignment & scroll behavior
        body.style.display = "flex";
        body.style.flexDirection = "column";
        body.style.boxSizing = "border-box";
        body.style.overflowY = c.overflow_y || "visible";
        body.style.overflowX = c.overflow_x || "visible";
        body.style.width = "100%";
        body.style.minHeight = "0";
        body.style.justifyContent =
            c.vertical_align === "center" ? "center" :
                (c.vertical_align === "bottom" ? "flex-end" : "flex-start");
        body.style.alignItems =
            c.horizontal_align === "left" ? "flex-start" :
                (c.horizontal_align === "right" ? "flex-end" : "center");

        // apply sizing for current state
        this._applySizingForState(this._open);
    }

    // Apply outer sizing depending on open/closed state
    _applySizingForState(open) {
        const c = this.config;
        const root = this.el;
        if (!root) return;

        // width
        if (c.width_mode === "fill") {
            root.style.width = "100%";
            root.style.flexGrow = "1";
            root.style.flexShrink = "1";
            root.style.flexBasis = "auto";
        } else if (c.width_mode === "auto") {
            root.style.width = "auto";
            root.style.flexGrow = "0";
            root.style.flexShrink = "1";
            root.style.flexBasis = "auto";
        } else { // fixed
            root.style.width = `${c.width}px`;
            root.style.flexGrow = "0";
            root.style.flexShrink = "0";
            root.style.flexBasis = `${c.width}px`;
        }

        if (open) {
            // height (apply configured behavior only when open)
            if (c.height_mode === "fill") {
                root.style.height = "100%";
                root.style.flexGrow = "1";
                root.style.flexShrink = "1";
                root.style.flexBasis = "0";
                this.body.style.flex = "1 1 auto";   // fill remaining
                this.body.style.display = "flex";
            } else if (c.height_mode === "auto") {
                root.style.height = "auto";
                root.style.flexGrow = "0";
                root.style.flexShrink = "0";
                root.style.flexBasis = "auto";
                this.body.style.flex = "0 1 auto";   // size to content
                this.body.style.display = "flex";
            } else { // fixed
                root.style.height = `${c.height}px`;
                root.style.flexGrow = "0";
                root.style.flexShrink = "0";
                root.style.flexBasis = `${c.height}px`;
                this.body.style.flex = "1 1 auto";   // take remaining space in fixed box
                this.body.style.display = "flex";
            }
        } else {
            // CLOSED: ignore configured fixed/fill height — collapse to header only
            root.style.height = "auto";       // <-- release height
            root.style.flexBasis = "auto";    // <-- release basis so it shrinks
            root.style.flexGrow = "0";
            root.style.flexShrink = "0";

            this.body.style.display = "none";
            this.body.style.flex = "0 0 auto";
        }
    }

    _renderChevron() {
        if (!this.chevron) return;
        this.chevron.setAttribute("aria-hidden", "true");
        this.chevron.classList.toggle("is-open", this._open);
    }

    _setOpenImmediate(open) {
        this._open = open;
        this.head?.setAttribute("aria-expanded", open ? "true" : "false");
        this._renderChevron();
        this._applySizingForState(open);
    }

    _setOpen(open /*, animate = true */) {
        if (open === this._open) return;
        this._setOpenImmediate(open);
    }
}

/* ------------------------------------------------------------------------------------------------------------------ */
export class Widget extends GUI_Object {

    /** @type {HTMLElement|null} */ container = null;
    /** @type {HTMLElement|null} */ parent_container = null;
    /** @type {HTMLElement|null} */ element = null;
    /** @type {Object} */ configuration = null;
    /** @type {HTMLElement|null} */ overlay = null;
    /** @type {ContextMenu} */ contextMenu = null;

    /** Tooltip state */
    /** @type {HTMLElement|null} */ tooltipEl = null;
    /** @type {number|null} */ tooltipShowTimer = null;
    /** @type {number|null} */ tooltipHideTimer = null;
    _onTooltipMouseEnter = null;
    _onTooltipMouseLeave = null;
    _onTooltipFocus = null;
    _onTooltipBlur = null;
    _onWindowReflow = null;


    /* === CONSTRUCTOR ============================================================================================== */
    constructor(id, data = {}) {
        super(id, data);
        const default_config = {
            padding_top: 0, padding_bottom: 0, padding_left: 0, padding_right: 0, border_width: 1,
            border: true, disabled: false,
            show_context_menu: true,
            description: 'No description provided.',
            tooltip: null,
            hover_tooltip_delay: 200,
            tooltip_position: '', // 'top' | 'bottom'
            tooltip_gap: 8,          // px distance to anchor
            dim: false,
        };

        const default_data = {context_menu: {}};

        this.data = {...default_data, ...data};
        this.configuration = {...default_config, ...(data.config || {})};

        this.container = document.createElement('div');
        this.container.classList.add('gridItem');

        // Always ensure a positioning context for overlays that *are* inside the container.
        if (getComputedStyle(this.container).position === 'static') {
            this.container.style.position = 'relative';
        }

        this.buildContextMenu();
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    /** @abstract */
    initializeElement() {


    }

    /* -------------------------------------------------------------------------------------------------------------- */
    configureElement(element) {
        if (element && element instanceof HTMLElement) {
            this.element = element;
            if (this.element.parentNode !== this.container) {
                this.container.appendChild(this.element);
            }
        } else {
            console.warn(`${this.id}: Provided element is not a valid HTMLElement`, element);
        }

        if (!this.configuration.border) {
            this.element.style.border = 'none';
        }
        this.element.style.setProperty('--border-width', this.configuration.border_width + 'px');

        this.enable({enable: !this.configuration.disabled});
        this.dim(this.configuration.dim);
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    /** @abstract */
    resize() {
        // throw new Error('resize() must be implemented by subclass');
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    attach(parent_container, grid_position = null, grid_size = null) {
        if (!(parent_container instanceof HTMLElement)) {
            console.warn(`${this.id}: Parent container is not a valid HTMLElement`);
            return;
        }
        this.parent_container = parent_container;

        if (grid_position && grid_size) {
            this.container.style.gridColumnStart = String(grid_position[1]);
            this.container.style.gridColumnEnd = `span ${grid_size[0]}`;
            this.container.style.gridRowStart = String(grid_position[0]);
            this.container.style.gridRowEnd = `span ${grid_size[1]}`;
        }

        this.parent_container.appendChild(this.container);
        this.setupHoverTooltip();
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    static fromData(id, data) {
        return new this(id, data);
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    /** @abstract */ update(data) {
        throw new Error('update() must be implemented by subclass');
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    /** @abstract */ updateConfig(data) {
        throw new Error('updateConfig() must be implemented by subclass');
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    onMessage(message) {
        super.onMessage(message);
        switch (message.type) {
            case 'update_config': {
                this.updateConfig(message.config);
                break;
            }
            case 'update': {
                this.update(message.data);
                break;
            }
            case 'add': {
                this.handleAdd(message.data);
                break;
            }
            case 'remove': {
                this.handleRemove(message.data);
                break;
            }
        }
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    destroy() {
        this.cleanupHoverTooltip();
        if (this.element && this.element.parentNode) {
            this.element.parentNode.removeChild(this.element);
        }
        this.element = null;

        // Remove listeners
        if (this.resize_observer) {
            this.resize_observer.disconnect();
            this.resize_observer = null;
        }
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    assignListeners(element) {
        if (!element) return;
        element.addEventListener("contextmenu", (ev) => {
            ev.preventDefault();
            ev.stopPropagation();
            if (this.configuration.show_context_menu) {
                document.querySelectorAll(".context-menu")
                    .forEach(menuEl => (menuEl.style.display = "none"));
                this.contextMenu.show({x: ev.clientX, y: ev.clientY});
            }
        });

        // this.resize_observer = new ResizeObserver(() => {
        //     this.resize();
        // });
        //
        // this.resize_observer.observe(this.container);

        this.resize_observer = new ResizeObserver(() => {
            const rect = this.container.getBoundingClientRect();
            const visible = rect.width > 0 && rect.height > 0 &&
                this.container.offsetParent !== null; // not display:none

            if (visible && !this._firstShowFired) {
                this._firstShowFired = true;
                this.onFirstShow();
            }

            this.resize();
        });

        this.resize_observer.observe(this.container);
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    /** Subclasses can override this */
    onFirstShow() {
        this.callbacks.get('event').call({event: 'first_built', id: this.id});
        this.resize();
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    accept(accept = true) {
        const el = this.element;
        if (!el) return;
        el.classList.add(accept ? 'accepted' : 'error');
        el.addEventListener('animationend', () => el.classList.remove(accept ? 'accepted' : 'error'), {once: true});
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    enable({enable = true, disable_opacity = 0.2, show_lock = true} = {}) {
        if (enable) {
            if (this.overlay) {
                this.overlay.style.display = 'none';
                if (this.lockIcon) this.lockIcon.style.display = 'none';
            }
            this.element?.classList.remove('disabled');
        } else {
            if (!this.overlay) {
                this.overlay = document.createElement('div');
                this.overlay.classList.add('gui-disable-overlay');
                Object.assign(this.overlay.style, {
                    position: 'absolute',
                    inset: '0',
                    background: 'rgba(0, 0, 0, 0)',
                    pointerEvents: 'all',
                    zIndex: '999'
                });
                this.container.style.position = 'relative';
                this.container.appendChild(this.overlay);

                this.lockIcon = document.createElement('div');
                this.lockIcon.classList.add('lock-icon');
                this.lockIcon.textContent = '🔒';
                Object.assign(this.lockIcon.style, {
                    position: 'absolute',
                    top: '2px',
                    right: '2px',
                    fontSize: '10px',
                    pointerEvents: 'none',
                    opacity: '0.5'
                });
                this.overlay.appendChild(this.lockIcon);
            } else {
                this.overlay.style.display = 'block';
                this.overlay.style.background = 'rgba(255, 255, 255, 0)';
            }
            if (this.lockIcon) this.lockIcon.style.display = show_lock ? 'block' : 'none';

            this.element?.classList.add('disabled');
            this.element?.style.setProperty('--disable-opacity', disable_opacity);
        }
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    disable({disable_opacity = 0.2, show_lock = true} = {}) {
        this.enable({enable: false, disable_opacity, show_lock});
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    dim(dim = true) {
        if (dim) {
            this.container.classList.add('dim');
        } else {
            this.container.classList.remove('dim');
        }
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    buildContextMenu() {
        const context_menu_data = this.data.context_menu;
        this.contextMenu = new ContextMenu(this.id, this, context_menu_data.config, context_menu_data.items);
        this.contextMenu.callbacks.get('click').register(this.onContextMenuEvent.bind(this));
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    onContextMenuEvent(item, event = null) {
        if (item instanceof ContextMenuItem) {
            this.callbacks.get('event').call({
                event: 'context_menu',
                id: this.id,
                data: {item_id: item.id, event}
            });
        }
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    addItemToContextMenu(item) {
        this.contextMenu.addItem(item);
    }

    update_context_menu(payload) {
        this.contextMenu.update(payload.config, payload.items);
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    showInfo() {
        activeGUI.terminal.print(`${this.id}: ${this.configuration.description}`);
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    /** Set/replace tooltip text at runtime. Pass null/empty to remove. */
    setTooltip(text) {
        this.configuration.tooltip = (typeof text === 'string' ? text : null);
        // If we cleared the text while visible, hide.
        if (!this.configuration.tooltip) this.hideHoverTooltip();
        // Keep element; text updates on show.
        if (this.tooltipEl) this.tooltipEl.textContent = this.configuration.tooltip || '';

        if (this.parent_container) {
            this.setupHoverTooltip();
        }

    }

    /* -------------------------------------------------------------------------------------------------------------- */
    /** Update the tooltip position preference at runtime ('top' | 'bottom'). */
    setTooltipPosition(position) {
        this.configuration.tooltip_position = (position === 'bottom') ? 'bottom' : 'top';

    }

    /* -------------------------------------------------------------------------------------------------------------- */
    /** Create a tooltip element in document.body and attach listeners. */
    setupHoverTooltip() {
        this.cleanupHoverTooltip();

        const text = this.configuration.tooltip;
        if (!(typeof text === 'string' && text.trim().length > 0)) return;

        // Create the tooltip element in BODY (portal) to avoid clipping from overflow: hidden parents.
        const tooltip = document.createElement('div');
        tooltip.className = 'gui-tooltip';
        tooltip.setAttribute('role', 'tooltip');
        tooltip.setAttribute('data-visible', 'false');
        tooltip.textContent = text;
        document.body.appendChild(tooltip);
        this.tooltipEl = tooltip;

        // Hover/focus handlers – attach to the *container* so overlay won't block them.
        this._onTooltipMouseEnter = () => {
            clearTimeout(this.tooltipHideTimer);
            clearTimeout(this.tooltipShowTimer);
            this.tooltipShowTimer = window.setTimeout(() => this.showHoverTooltip(), this.configuration.hover_tooltip_delay || 0);
        };
        this._onTooltipMouseLeave = () => {
            clearTimeout(this.tooltipShowTimer);
            clearTimeout(this.tooltipHideTimer);
            this.tooltipHideTimer = window.setTimeout(() => this.hideHoverTooltip(), 50);
        };
        this._onTooltipFocus = this._onTooltipMouseEnter;
        this._onTooltipBlur = this._onTooltipMouseLeave;

        this.container.addEventListener('mouseenter', this._onTooltipMouseEnter);
        this.container.addEventListener('mouseleave', this._onTooltipMouseLeave);
        if (this.element) {
            this.element.addEventListener('focus', this._onTooltipFocus, true);
            this.element.addEventListener('blur', this._onTooltipBlur, true);
            // A11y association
            const tooltipId = `${this.id}-tooltip`;
            this.tooltipEl.id = tooltipId;
            const existingId = this.element.getAttribute('id');
            if (existingId) this.element.setAttribute('aria-describedby', tooltipId);
        }

        // Reposition on viewport changes/scroll
        this._onWindowReflow = () => this.positionHoverTooltip();
        window.addEventListener('resize', this._onWindowReflow);
        window.addEventListener('scroll', this._onWindowReflow, true);
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    /** Remove tooltip element and listeners */
    cleanupHoverTooltip() {
        clearTimeout(this.tooltipShowTimer);
        clearTimeout(this.tooltipHideTimer);

        if (this.container) {
            if (this._onTooltipMouseEnter) this.container.removeEventListener('mouseenter', this._onTooltipMouseEnter);
            if (this._onTooltipMouseLeave) this.container.removeEventListener('mouseleave', this._onTooltipMouseLeave);
        }
        if (this.element) {
            if (this._onTooltipFocus) this.element.removeEventListener('focus', this._onTooltipFocus, true);
            if (this._onTooltipBlur) this.element.removeEventListener('blur', this._onTooltipBlur, true);
        }
        if (this._onWindowReflow) {
            window.removeEventListener('resize', this._onWindowReflow);
            window.removeEventListener('scroll', this._onWindowReflow, true);
            this._onWindowReflow = null;
        }
        if (this.tooltipEl && this.tooltipEl.parentNode) {
            this.tooltipEl.parentNode.removeChild(this.tooltipEl);
        }

        this.tooltipEl = null;
        this._onTooltipMouseEnter = null;
        this._onTooltipMouseLeave = null;
        this._onTooltipFocus = null;
        this._onTooltipBlur = null;
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    showHoverTooltip() {
        if (!this.tooltipEl) return;

        // Update text in case it changed at runtime
        const text = this.configuration.tooltip;
        if (!(typeof text === 'string' && text.trim().length > 0)) {
            this.hideHoverTooltip();
            return;
        }
        this.tooltipEl.textContent = text;

        // Position before revealing (opacity animates in)
        this.positionHoverTooltip();
        this.tooltipEl.setAttribute('data-visible', 'true');
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    hideHoverTooltip() {
        if (!this.tooltipEl) return;
        this.tooltipEl.setAttribute('data-visible', 'false');
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    /**
     * Position the floating tooltip (in document.body) relative to the *container* (or element).
     * Uses viewport coordinates (position: fixed) and flips to stay on-screen.
     */
    positionHoverTooltip() {
        if (!this.tooltipEl || (!this.element && !this.container)) return;

        // Anchor: prefer the main element, fallback to container
        const anchorEl = this.element || this.container;
        const rect = anchorEl.getBoundingClientRect();

        const gap = Number(this.configuration.tooltip_gap) || 8;
        const desired = (this.configuration.tooltip_position === 'bottom') ? 'bottom' : 'top';

        // Measure tooltip size (visible or not, we can still read its size since it's not display:none)
        const tt = this.tooltipEl;
        const ttRect = tt.getBoundingClientRect();
        const ttW = ttRect.width || tt.offsetWidth || 0;
        const ttH = ttRect.height || tt.offsetHeight || 0;

        // Horizontal center, clamped to viewport with padding
        const padding = 8;
        let x = rect.left + rect.width / 2;
        x = Math.max(padding + ttW / 2, Math.min(x, window.innerWidth - padding - ttW / 2));

        // Compute candidate y for both placements
        const yTop = rect.top - gap - ttH;       // above
        const yBottom = rect.bottom + gap;       // below

        // Choose placement (respect preference but flip if needed)
        let placement = desired;
        if (desired === 'top' && yTop < padding) {
            placement = 'bottom';
        } else if (desired === 'bottom' && (yBottom + ttH > window.innerHeight - padding)) {
            placement = 'top';
        }

        // Apply classes for arrow orientation
        tt.classList.toggle('gui-tooltip--top', placement === 'top');
        tt.classList.toggle('gui-tooltip--bottom', placement === 'bottom');

        // Final Y
        const y = (placement === 'top') ? Math.max(padding, yTop) : Math.min(window.innerHeight - padding - ttH, yBottom);

        // Set fixed coordinates; keep translateX(-50%) so we can clamp x by shifting left property
        tt.style.left = `${x}px`;
        tt.style.top = `${y}px`;
        tt.style.transform = 'translateX(-50%)';
    }
}


/* ------------------------------------------------------------------------------------------------------------------ */
export class ContainerWrapperWidget extends Widget {
    constructor(id, payload = {}) {
        super(id, payload);

        this.element = this.initializeElement();
        this.configureElement(this.element);
        this.assignListeners(this.element);
        //
        this.gui_container = new GUI_Container(payload.container.id, payload.container);
        this.gui_container.attach(this.element);

        this.gui_container.callbacks.get('event').register(this.onContainerEvent.bind(this));

        // Here I want to add some debug testing of the containers
        // this.buildTestStack();
        // this.buildTestStack2();
    }

    getObjectByPath(path) {
        let [first, remainder] = splitPath(path);

        const fullKey = `${this.id}/${first}`;

        if (fullKey === this.gui_container.id) {
            if (!remainder) {
                return this.gui_container;
            } else {
                return this.gui_container.getObjectByPath(remainder);
            }
        } else {
            console.warn(`${this.id}: getObjectByPath: ${path} not found`);
            console.log(`Full key: ${fullKey}`);
            console.log(`Container ID: ${this.gui_container.id}`);
        }

        return null;
    }

    initializeElement() {
        const element = document.createElement('div');
        // element.classList.add('widget', 'gridItem', 'container-wrapper');
        element.classList.add('container-wrapper');
        return element;
    }

    resize() {
    }

    update(data) {
        return undefined;
    }

    updateConfig(data) {
        return undefined;
    }

    onContainerEvent(event) {
        this.callbacks.get('event').call(event);
    }

    buildTestStack() {
        // === Outer vertical stack in the wrapper =====================================
        const stack = new GUI_Container_Stack("test-stack", {
            config: {
                direction: "vertical",
                spacing: 8,
                padding: 6,
                height_mode: "auto",
                width_mode: "fill",
                background_color: [0, 0, 0, 0],
                border_color: [255, 255, 255, 0.08],
                border_width: 0
            }
        });
        stack.attach(this.element);

        // 1) Fixed height top bar
        const fixedTop = new GUI_Container("fixed-top", {
            config: {
                height_mode: "fixed",
                height: 50,
                padding: 6,
                background_color: [0, 1, 0, 0.25],
                border_color: [0, 255, 0, 0.25]
            }
        });
        fixedTop.mountElement(this._makeLabel("Fixed (50px)"));
        stack.add(fixedTop, {grow: 0});

        // 2) Collapsible section that will host a vertical stack
        const outerColl = new CollapsibleContainer("coll-outer", {
            config: {
                title: "Outer Collapsible (contains a vertical stack)",
                start_collapsed: false,
                padding: 4,
                headbar_height: 28,
                headbar_background_color: "rgba(255,255,255,.06)",
                headbar_border: "1px solid rgba(255,255,255,.12)",
                background_color: [0, 0, 1, 0.12],
                border_color: [120, 160, 255, 0.35],
                height_mode: "auto" // important: auto, not fill
            }
        });

        // --- Inner vertical stack inside the outer collapsible -----------------------
        const innerStack = new GUI_Container_Stack("inner-stack", {
            config: {
                direction: "vertical",
                spacing: 6,
                padding: 4,
                width_mode: "fill",
                height_mode: "auto",
                background_color: [0, 0, 0, 0],
                border_color: [255, 255, 255, 0.10],
                border_width: 0
            }
        });

        // Attach the inner stack element into the collapsible body
        outerColl.mountElement(innerStack.el);

        // 2.a) Nested collapsible A
        const collA = new CollapsibleContainer("coll-A", {
            config: {
                title: "Nested A",
                start_collapsed: false,
                padding: 8,
                background_color: [1, 0, 0, 0.12],
                border_color: [255, 255, 255, 0.18],
                height_mode: "fixed",
                height: 300,
            }
        });
        collA.mountElement(this._makeParagraph([
            "I am nested collapsible A.",
            "I size to my content.",
            "Click my header to toggle."
        ]));
        innerStack.add(collA);

        // 2.b) Fixed-size section in between
        const midFixed = new GUI_Container("mid-fixed", {
            config: {
                height_mode: "fixed",
                height: 70,
                padding: 6,
                background_color: [0.9, 0.6, 0.1, 0.25],
                border_color: [255, 200, 120, 0.35]
            }
        });
        midFixed.mountElement(this._makeLabel("Fixed middle section (70px)"));
        innerStack.add(midFixed, {grow: 0});

        // 2.c) Nested collapsible B
        const collB = new CollapsibleContainer("coll-B", {
            config: {
                title: "Nested B",
                start_collapsed: true,
                padding: 8,
                background_color: [0, 0, 0, 0.12],
                border_color: [255, 255, 255, 0.18],
                height_mode: "auto"
            }
        });
        collB.mountElement(this._makeParagraph([
            "I am nested collapsible B.",
            "I start collapsed.",
            "Open me to see more lines…",
            "Line 4 just to show growth."
        ]));
        innerStack.add(collB);

        // Add the outer collapsible (with the inner stack inside) to the main stack
        stack.add(outerColl, {grow: 0});

        // 3) Bottom fixed section
        const fixedBottom = new GUI_Container("fixed-bottom", {
            config: {
                height_mode: "fixed",
                height: 80,
                padding: 6,
                background_color: [1, 0, 0, 0.25],
                border_color: [255, 120, 120, 0.35]
            }
        });
        fixedBottom.mountElement(this._makeLabel("Fixed (80px)"));
        stack.add(fixedBottom, {grow: 0});

        // Optional: a fill panel to see flex behavior
        // const filler = new GUI_Container("filler", { config: { height_mode: "fill", background_color: [0,0,0,0.08], padding: 8 }});
        // filler.initialize();
        // filler.mountElement(this._makeLabel("Fill panel (takes remaining space)"));
        // stack.add(filler, { grow: 1 });
    }

    async buildTestStack2() {
        const stack = new GUI_Container_Stack("test-stack", {
            config: {
                direction: "vertical",
                spacing: 8,
                padding: 6,
                height_mode: "auto",
                width_mode: "fill",
                background_color: [0, 0, 0, 0],
                border_color: [255, 255, 255, 0.08],
                border_width: 0
            }
        });
        stack.attach(this.element);

        // 1) Fixed height top bar
        const fixed1 = new GUI_Container("fixed-top", {
            config: {
                height_mode: "fixed",
                height: 100,
                padding: 6,
                background_color: [0, 1, 0, 0.25],
                border_color: [0, 255, 0, 0.25]
            }
        });
        fixed1.mountElement(this._makeLabel("Fixed (100px)"));
        stack.add(fixed1, {grow: 0});

        const fixed2 = new CollapsibleContainer("collapsible_1", {
            config: {
                height_mode: "auto",
                height: 200,
                padding: 6,
                background_color: [0, 0, 1, 0.1],
                overflow_y: "auto",
                // border_color: [0, 255, 0, 0.25]
            }
        });
        stack.add(fixed2);

        const {WidgetGroup} = await import('./group.js');

        const group = new WidgetGroup("group-1", {config: {fit: false, show_scrollbar: true}});
        // group.attach(fixed2.body);
        fixed2.mountObject(group);

    }

    _makeLabel(text) {
        const div = document.createElement("div");
        div.textContent = text;
        div.style.fontSize = "12px";
        div.style.padding = "4px";
        return div;
    }

    _makeParagraph(lines) {
        const div = document.createElement("div");
        div.style.fontSize = "12px";
        div.style.lineHeight = "1.4";
        div.innerHTML = lines.map(l => `${l}`).join("<br>");
        return div;
    }

}