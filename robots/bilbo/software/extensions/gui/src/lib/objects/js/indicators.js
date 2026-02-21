import {Widget} from "../objects.js";
import {getColor, getFittingFontSizeSingleContainer} from "../../helpers.js";


// === CircleIndicator ================================================================================================
export class CircleIndicator extends Widget {
    constructor(id, config = {}) {
        super(id, config);

        const defaults = {
            background_color: [0, 0, 0, 1],
            color: [1, 1, 1, 0.8],
            visible: true,
            diameter: 80,            // % of container’s smaller dimension
            blinking: false,
            blinking_frequency: 1,   // Hz
        };
        this.configuration = {...defaults, ...this.configuration};

        this.element = this.initializeElement(id);

        this.configureElement(this.element);

        // recalc on window resize:
        window.addEventListener("resize", () =>
            this.configureElement(this.element)
        );
    }

    initializeElement(id) {
        const el = document.createElement("div");
        el.id = id;
        el.classList.add("widget", "circleIndicator");

        // the actual circle
        this.shapeEl = document.createElement("div");
        this.shapeEl.classList.add("circle-shape");
        el.appendChild(this.shapeEl);

        return el;
    }

    configureElement(element) {
        super.configureElement(element);
        const config = this.configuration;
        // ── Visibility & Background ───────────────────────────────────────────────
        this.element.style.display = config.visible ? "" : "none";
        this.element.style.backgroundColor = getColor(config.background_color);

        // ── Compute diameter ───────────────────────────────────────────────────────
        const rect = this.element.getBoundingClientRect();
        const size = Math.min(rect.width, rect.height);
        const diameter = size * (config.size / 100);

        // ── Style the circle ─────────────────────────────────────────────────────
        const c = this.shapeEl;
        c.style.width = `${diameter}px`;
        c.style.height = `${diameter}px`;
        c.style.borderRadius = "50%";
        c.style.backgroundColor = getColor(config.color);

        // ── Blinking ──────────────────────────────────────────────────────────────
        if (config.blinking) {
            const period = 1 / config.blinking_frequency;
            c.style.animation = `circle-blink ${period}s ease-in-out infinite`;
        } else {
            c.style.animation = "";
        }
    }

    assignListeners(element) {
        super.assignListeners(element);
    }

    getElement() {
        return this.element;
    }

    update() {
        // no dynamic data updates
    }

    singleBlink(time = 200) {
        const el = this.element;

        el.classList.remove("pulse"); // reset if already running
        void el.offsetWidth;          // force reflow (important)
        el.classList.add("pulse");

        setTimeout(() => {
            el.classList.remove("pulse");
        }, time);
    }


    updateConfig(data) {
        this.configuration = {...this.configuration, ...data};
        this.configureElement(this.element);
    }

    resize() {
    }
}

// === LoadingIndicator ================================================================================================
export class LoadingIndicator extends Widget {
    constructor(id, config = {}) {
        super(id, config);

        const defaults = {
            background_color: [0, 0, 0, 0],
            color: [0.2, 0.2, 0.2, 1],
            thickness: 20,   // % of diameter
            size: 80,        // % of container’s smaller dimension
            speed: 1.0,      // revolutions per second
            spinning: true,
            visible: true,
        };
        this.configuration = {...defaults, ...this.configuration};

        this.element = this.initializeElement(id);
        // on resize we need to re‑compute sizes:
        window.addEventListener("resize", () =>
            this.configureElement(this.element)
        );
        this.configureElement(this.element);
    }

    initializeElement(id) {
        const el = document.createElement("div");
        el.id = id;
        el.classList.add("widget", "loadingIndicator");
        this.spinnerEl = document.createElement("div");
        this.spinnerEl.classList.add("loading-spinner");
        el.appendChild(this.spinnerEl);
        return el;
    }

    configureElement(el) {
        super.configureElement(el);
        const cfg = this.configuration;

        // show/hide & background
        el.style.display = cfg.visible ? "" : "none";
        el.style.backgroundColor = getColor(cfg.background_color);

        // figure out diameter & border thickness in px
        const rect = el.getBoundingClientRect();
        const size = Math.min(rect.width, rect.height);
        const diameter = (size * cfg.size) / 100;
        const thickness = (diameter * cfg.thickness) / 100;
        const spinnerColor = getColor(cfg.color);

        // classic hollow‑ring spinner:
        Object.assign(this.spinnerEl.style, {
            width: `${diameter}px`,
            height: `${diameter}px`,
            boxSizing: "border-box",
            border: `${thickness}px solid ${spinnerColor}`,
            borderTopColor: "transparent",         // carve out the “gap”
            borderRadius: "50%",
            background: "none",
            animation: cfg.spinning
                ? `loading-spin ${1 / cfg.speed}s linear infinite`
                : "",
        });
    }

    getElement() {
        return this.element;
    }

    assignListeners(element) { /* none */
        super.assignListeners(element);
    }

    update() { /* none */
    }

    updateConfig(data) {
        this.configuration = {...this.configuration, ...data};
        this.configureElement(this.element);
    }
}

// === ProgressIndicator ===============================================================================================
export class ProgressIndicator extends Widget {
    constructor(id, config = {}) {
        super(id, config);

        const defaults = {
            background_color: [0, 0, 0, 0],
            color: [0.2, 0.2, 0.2, 1],
            track_outline_color: [0.8, 0.8, 0.8, 0.2],
            track_fill_color: [0.8, 0.2, 0.2, 1],
            track_visible: true,
            type: 'linear',
            thickness: 20,               // if mode='relative' → 20% of width
            thickness_mode: 'relative',  // 'relative' or 'absolute'
            value: 0.0,
            title: '',
            title_position: 'top',       // 'top' or 'left'
            title_color: [1, 1, 1, 1],
            label: '',
            label_position: 'bottom',    // 'bottom' or 'right'
            label_color: [1, 1, 1, 1],
            ticks: [],
            tick_labels: [],
            ticks_color: [0.8, 0.8, 0.8, 1],
        };
        this.configuration = {...defaults, ...this.configuration};

        this.element = this.initializeElement(id);
        this.configureElement(this.element);

        window.addEventListener('resize', () =>
            this.configureElement(this.element)
        );
    }

    initializeElement(id) {
        const el = document.createElement('div');
        el.id = id;
        el.classList.add('widget', 'pi_widget');

        el.style.setProperty('--pi-left-width', '33%');
        el.style.setProperty('--pi-center-width', '34%');
        el.style.setProperty('--pi-right-width', '33%');
        el.style.setProperty('--pi-top-height', '33%');
        el.style.setProperty('--pi-middle-height', '34%');
        el.style.setProperty('--pi-bottom-height', '33%');

        let gridAreas = '';

        if (this.configuration.title_position === 'top') {
            gridAreas += `"title title title" `;

            if (this.configuration.label_position === 'bottom') {
                gridAreas += `"bar bar bar" `;
                gridAreas += `"label label label"`;
            } else if (this.configuration.label_position === 'right') {
                gridAreas += `"bar bar bar" `;
                gridAreas += `". . ."`;
            } else {
                console.warn(`${this.id}: Invalid label position "${this.configuration.label_position}"`);
                return null;
            }

        } else if (this.configuration.title_position === 'left') {
            if (this.configuration.label_position === 'bottom') {
                gridAreas += `". . ." `;
                gridAreas += `"title bar bar" `;
                gridAreas += `". label label"`;
            } else if (this.configuration.label_position === 'right') {
                gridAreas += `". . ." `;
                gridAreas += `"title bar label" `;
                gridAreas += `". . ."`;
            } else {
                console.warn(`${this.id}: Invalid label position "${this.configuration.label_position}"`);
                return null;
            }
        } else {
            console.warn(`${this.id}: Invalid title position "${this.configuration.title_position}"`);
            return null;
        }

        el.style.setProperty('--grid-areas', gridAreas);

        // Title
        this.titleEl = document.createElement('div');
        this.titleEl.classList.add('pi_widget_title');
        this.titleEl.textContent = 'AAAA';
        el.appendChild(this.titleEl);

        // Label
        this.labelEl = document.createElement('div');
        this.labelEl.classList.add('pi_widget_label');
        this.labelEl.textContent = 'BBBB';
        el.appendChild(this.labelEl);

        // Bar container
        this.barContainer = document.createElement('div');
        this.barContainer.classList.add('pi_widget_bar_container');
        el.appendChild(this.barContainer);

        // Outline (track)
        this.barOutline = document.createElement('div');
        this.barOutline.classList.add('pi-bar-outline');
        this.barContainer.appendChild(this.barOutline);

        // Fill (progress)
        this.barFill = document.createElement('div');
        this.barFill.classList.add('pi-bar-fill');
        this.barOutline.appendChild(this.barFill);

        return el;
    }

    configureElement(el) {
        super.configureElement(el);
        const c = this.configuration;

        // title
        this.titleEl.textContent = c.title;
        this.titleEl.style.color = getColor(c.title_color);
        el.dataset.titlePosition = c.title_position;


        // Label
        this.labelEl.textContent = c.label;
        this.labelEl.style.color = getColor(c.label_color);
        el.dataset.labelPosition = c.label_position;

        // bar thickness & rounding
        const rect = this.barContainer.getBoundingClientRect();
        let thicknessPx;
        if (c.thickness_mode === 'absolute') {
            thicknessPx = c.thickness;
        } else {
            thicknessPx = (rect.width * c.thickness) / 100;
        }
        const radius = thicknessPx * 0.25;  // gentler rounding

        this.barOutline.style.height = `${thicknessPx}px`;
        this.barOutline.style.borderRadius = `${radius}px`;
        this.barOutline.style.borderWidth = '1px';
        this.barOutline.style.borderStyle = 'solid';
        this.barOutline.style.borderColor = getColor(c.track_outline_color);

        this.barFill.style.height = '100%';
        this.barFill.style.borderRadius = `${radius}px`;
        this.barFill.style.backgroundColor = getColor(c.track_fill_color);

        // fill %
        const pct = Math.max(0, Math.min(100, c.value * 100));
        this.barFill.style.width = `${pct}%`;


        this.showBar(this.configuration.track_visible);

    }

    assignListeners() { /* none */
    }

    getElement() {
        return this.element;
    }

    update(data) {
        const value = data.value || this.configuration.value;
        const label = data.label || this.configuration.label;

        // Update the value and label in the configuration
        this.configuration.value = value;
        this.configuration.label = label;

        // Change the fill width based on the new value
        const pct = Math.max(0, Math.min(100, value * 100));
        this.barFill.style.width = `${pct}%`;

        // Change the label text
        this.labelEl.textContent = label;
    }

    updateConfig(data) {
        this.configuration = {...this.configuration, ...data};
        this.configureElement(this.element);
    }

    showBar(show) {
        this.barContainer.style.display = show ? 'block' : 'none';
    }

    resize() {
    }
}


// === BatteryIndicator ==================================================================================================
export class BatteryIndicatorWidget extends Widget {
    constructor(id, payload = {}) {
        super(id, payload);
        const defaults = {
            show: 'percentage',  // 'percentage', 'voltage' or null
            label_position: 'right', // 'left', 'center', 'right'
            label_color: [1, 1, 1, 1],
            thresholds: {low: 0.2, medium: 0.7},
            value: 0.6,
            voltage: 0.1
        };
        this.configuration = {...defaults, ...this.configuration};
        this.element = this._initializeElement();
        this.configureElement(this.element);
        this.assignListeners(this.element);
    }

    _initializeElement() {
        const el = document.createElement('div');
        el.classList.add('widget', 'battery-indicator');
        // battery body
        this.bodyEl = document.createElement('div');
        this.bodyEl.classList.add('battery-body');
        // battery head
        this.headEl = document.createElement('div');
        this.headEl.classList.add('battery-head');
        el.appendChild(this.bodyEl);
        el.appendChild(this.headEl);
        // fill
        this.fillEl = document.createElement('div');
        this.fillEl.classList.add('battery-fill');
        this.bodyEl.appendChild(this.fillEl);
        // label
        this.labelEl = document.createElement('div');
        this.labelEl.classList.add('battery-label');
        el.appendChild(this.labelEl);
        return el;
    }


    configureElement() {
        super.configureElement(this.element);
        const cfg = this.configuration;
        const pct = Math.max(0, Math.min(1, cfg.value));
        const widthPct = pct * 100;

        // — fill bar —
        let fillColor;
        if (pct <= cfg.thresholds.low) fillColor = 'darkred';
        else if (pct <= cfg.thresholds.medium) fillColor = 'darkorange';
        else fillColor = 'darkgreen';

        this.fillEl.style.width = `${widthPct}%`;
        this.fillEl.style.backgroundColor = fillColor;
        this.fillEl.style.position = 'absolute';
        this.fillEl.style.top = '0';
        this.fillEl.style.left = '0';
        this.fillEl.style.zIndex = '1';

        // — label text & base styles —
        let text = '';
        if (cfg.show === 'percentage') text = `${Math.round(widthPct)}%`;
        else if (cfg.show === 'voltage') text = `${cfg.voltage.toFixed(1)}V`;
        this.labelEl.textContent = text;
        this.labelEl.style.color = getColor(cfg.label_color);
        this.element.dataset.labelPosition = cfg.label_position;

        // — reposition the label —
        if (cfg.label_position === 'center') {
            // make sure body is the positioning context
            this.bodyEl.style.position = 'relative';

            // move label _into_ the battery-body
            this.bodyEl.appendChild(this.labelEl);

            Object.assign(this.labelEl.style, {
                position: 'absolute',
                top: '50%',
                left: '50%',
                transform: 'translate(-50%, -50%)',
                margin: '0',
                whiteSpace: 'nowrap',
                zIndex: '2',
                pointerEvents: 'none',
            });
        } else {
            // move label back to root, clear absolute styles
            this.element.appendChild(this.labelEl);
            this.labelEl.style.position = '';
            this.labelEl.style.top = '';
            this.labelEl.style.left = '';
            this.labelEl.style.transform = '';
            this.labelEl.style.zIndex = '';
            // add some margin
            if (cfg.label_position === 'left') {
                this.labelEl.style.margin = '0 8px 0 0';
            } else {  // right
                this.labelEl.style.margin = '0 0 0 8px';
            }
        }
    }

    setValue(percentage, voltage) {
        this.configuration.value = percentage;
        this.configuration.voltage = voltage;
        this.configureElement();
    }

    getElement() {
        return this.element;
    }

    assignListeners(element) {
        super.assignListeners(element);
    }

    initializeElement() {
    }

    update(data) {
    }

    updateConfig(data) {
        this.configuration = {...this.configuration, ...data};
        this.configureElement();
    }

    resize() {
    }
}

// === ConnectionIndicator ================================================================================================
export class ConnectionIndicator extends Widget {
    constructor(id, config = {}) {
        super(id, config);
        const defaults = {
            color: [0.8, 0.8, 0.8, 1],
            value: 'medium', // 'low','medium','high'
        };
        this.configuration = {...defaults, ...this.configuration};
        this.element = this._initializeElement();
        this.configureElement(this.element);
        this.assignListeners(this.element);
    }

    _initializeElement() {
        const el = document.createElement('div');
        el.classList.add('widget', 'connection-indicator');
        this.bars = [];
        for (let i = 1; i <= 3; i++) {
            const bar = document.createElement('div');
            bar.classList.add('connection-bar');
            bar.dataset.level = i;
            el.appendChild(bar);
            this.bars.push(bar);
        }
        return el;
    }

    configureElement() {
        super.configureElement(this.element);
        const cfg = this.configuration;
        const levelMap = {low: 1, medium: 2, high: 3};
        const filledCount = levelMap[cfg.value] || 0;
        const color = getColor(cfg.color);
        this.bars.forEach((bar, idx) => {
            if (idx < filledCount) {
                bar.style.backgroundColor = color;
                bar.style.borderColor = color;
                bar.style.opacity = '1';
            } else {
                bar.style.backgroundColor = 'transparent';
                bar.style.borderColor = color;
                bar.style.opacity = '1';
            }
        });
    }

    setValue(value) {
        this.configuration.value = value;
        this.configureElement();
    }

    getElement() {
        return this.element;
    }

    assignListeners(element) {
        super.assignListeners(element);
    }

    initializeElement() {
    }

    resize() {
    }

    update(data) {
        return undefined;
    }

    updateConfig(data) {
        this.configuration = {...this.configuration, ...data};
        this.configureElement();
    }
}

// === InternetIndicator ================================================================================================
export class InternetIndicator extends Widget {
    constructor(id, config = {}) {
        super(id, config);
        const defaults = {available: true, fit_to_container: true};
        this.configuration = {...defaults, ...this.configuration};
        this.element = this._initializeElement();
        this.configureElement(this.element);
        this.assignListeners(this.element);
    }

    _initializeElement() {
        const el = document.createElement('div');
        el.classList.add('widget', 'internet-indicator');
        this.iconEl = document.createElement('div');
        this.iconEl.classList.add('internet-icon');
        this.iconEl.textContent = "🌍";
        el.appendChild(this.iconEl);
        this.crossEl = document.createElement('div');
        this.crossEl.classList.add('internet-cross');
        el.appendChild(this.crossEl);
        return el;
    }

    configureElement() {
        super.configureElement(this.element);
        const cfg = this.configuration;
        if (cfg.available) {
            this.iconEl.style.opacity = '1';
            this.crossEl.style.display = 'none';
        } else {
            this.iconEl.style.opacity = '0.4';
            this.crossEl.style.display = 'block';
        }
    }

    setValue(available) {
        this.configuration.available = available;
        this.configureElement();
    }

    assignListeners(element) {
        super.assignListeners(element);
    }

    getElement() {
        return this.element;
    }

    initializeElement() {
    }

    update(data) {
    }

    updateConfig(data) {
        this.configuration = {...this.configuration, ...data};
        this.configureElement();
    }

    resize() {
        if (this.configuration.fit_to_container) {
            getFittingFontSizeSingleContainer(this.iconEl, 0, 0, 100, 0);
        }
    }
}

// === InternetIndicator ================================================================================================
export class NetworkIndicator extends Widget {
    constructor(id, config = {}) {
        super(id, config);
        const defaults = {available: true};
        this.configuration = {...defaults, ...this.configuration};
        this.element = this._initializeElement();
        this.configureElement(this.element);
        this.assignListeners(this.element);
    }

    _initializeElement() {
        const el = document.createElement('div');
        el.classList.add('widget', 'network-indicator');
        this.iconEl = document.createElement('div');
        this.iconEl.classList.add('network-icon');
        el.appendChild(this.iconEl);
        this.crossEl = document.createElement('div');
        this.crossEl.classList.add('network-cross');
        el.appendChild(this.crossEl);
        return el;
    }

    configureElement() {
        super.configureElement(this.element);
        const cfg = this.configuration;
        if (cfg.available) {
            this.iconEl.style.opacity = '1';
            this.crossEl.style.display = 'none';
        } else {
            this.iconEl.style.opacity = '0.4';
            this.crossEl.style.display = 'block';
        }
    }

    setValue(available) {
        this.configuration.available = available;
        this.configureElement();
    }

    assignListeners(element) {
        super.assignListeners(element);
    }

    getElement() {
        return this.element;
    }

    initializeElement() {
    }

    update(data) {
    }

    updateConfig(data) {
        this.configuration = {...this.configuration, ...data};
        this.configureElement();
    }

    resize() {
    }
}


// === JoystickIndicator ================================================================================================
export class JoystickIndicator extends Widget {
    constructor(id, config = {}) {
        super(id, config);
        // add png_icon_path so it can be overridden if needed
        const defaults = {
            available: true,
            use_png_icon: true,
            png_icon_path: '/gamepad.png'
        };
        this.configuration = {...defaults, ...this.configuration};
        this.element = this._initializeElement();
        this.configureElement();
        this.assignListeners(this.element);
    }

    _initializeElement() {
        const el = document.createElement('div');
        el.classList.add('widget', 'highlightable', 'joystick-indicator');

        // choose between PNG or emoji
        if (this.configuration.use_png_icon) {
            this.iconEl = document.createElement('img');
            this.iconEl.src = this.configuration.png_icon_path;
            this.iconEl.alt = 'Gamepad';
            this.iconEl.classList.add('joystick-icon-image');
        } else {
            this.iconEl = document.createElement('div');
            this.iconEl.classList.add('joystick-icon');
        }
        el.appendChild(this.iconEl);

        this.crossEl = document.createElement('div');
        this.crossEl.classList.add('joystick-cross');
        el.appendChild(this.crossEl);

        return el;
    }

    configureElement() {
        super.configureElement(this.element);
        const {available} = this.configuration;
        if (available) {
            this.iconEl.style.opacity = '1';
            this.crossEl.style.display = 'none';
        } else {
            this.iconEl.style.opacity = '0.4';
            this.crossEl.style.display = 'block';
        }
    }

    setValue(available) {
        this.configuration.available = available;
        this.configureElement();
    }

    assignListeners(element) {
        super.assignListeners(element);

        // Assign click listener to the joystick icon
        this.iconEl.addEventListener('click', () => {
            // Trigger the click on the parent element
            this.callbacks.get('event').call({id: this.id, event: 'click', data: {}});
        });
    }

    getElement() {
        return this.element;
    }

    initializeElement() {
    }

    update(data) {
    }

    updateConfig(data) {
        this.configuration = {...this.configuration, ...data};
        this.configureElement();
    }

    resize() {
    }
}