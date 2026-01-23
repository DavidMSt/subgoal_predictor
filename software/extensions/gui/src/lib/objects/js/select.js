import {Widget} from "../objects.js";
import {getColor, shadeColor, interpolateColors} from "../../helpers.js";

export class MultiSelectWidget extends Widget {
    constructor(id, config = {}) {
        super(id, config);

        const defaults = {
            visible: true,
            color: "#333",        // or a single color; per-option colors can be specified in options[color]
            text_color: "#fff",
            title: "",
            options: {},          // { valueKey: { label, color? }, … }
            value: null,          // the selected valueKey
            lockable: false,
            locked: false,
            titlePosition: "top",  // 'top' or 'left'
            // titleStyle: "bold"     // 'bold' or 'normal'
        };

        this.configuration = {...defaults, ...this.configuration};
        if (!this.configuration.lockable) {
            this.configuration.locked = false;
        }

        this.element = this._initializeElement();
        this.configureElement(this.element);
        this.assignListeners(this.element);
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    /**
     * Determine the current background‐color. If the currently selected option
     * has its own .color property, use that; otherwise fall back to config.color.
     */
    _getCurrentColor() {
        const {color, options, value} = this.configuration;
        const optObj = options[value];
        if (optObj && optObj.color) {
            return optObj.color;
        }
        return color;
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    /**
     * Find the label corresponding to the current `value`.
     */
    _getCurrentLabel() {
        const {options, value} = this.configuration;
        const found = options[value];
        return found ? found.label : "";
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    /**
     * Create the root container. Inner content is built in `configureElement()`.
     */
    _initializeElement() {
        const container = document.createElement("div");
        container.id = this.id;
        container.classList.add("widget",'highlightable', "multiSelectWidget");
        return container;
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    /**
     * Apply `this.configuration` to the DOM: set styles, rebuild innerHTML, repopulate <select>.
     */
    configureElement(element) {
        super.configureElement(element);
        const c = this.configuration;
        const container = this.element;

        // ── Visibility ───────────────────────────────────────────────────────────────────────────────────────────────
        if (!c.visible) {
            container.style.display = "none";
        } else {
            container.style.display = "";
        }

        // ── Dataset flags for CSS layout or external styling ─────────────────────────────────────────────────────────
        container.dataset.titlePosition = c.title_position;
        container.dataset.lockable = c.lockable;
        container.dataset.locked = c.locked;

        // ── Colors ───────────────────────────────────────────────────────────────────────────────────────────────────
        container.style.backgroundColor = getColor(this._getCurrentColor());
        container.style.color = getColor(c.text_color);

        // ── Build inner HTML ─────────────────────────────────────────────────────────────────────────────────────────
        let html = "";
        if (c.title) {
            html += `<span class="msSelectTitle">${c.title}</span>`;
        }
        html += `
            <span class="msSelectValue">${this._getCurrentLabel()}</span>
            <select></select>
            <span class="msSelectDropdown">&#x25BC;</span>
        `;
        container.innerHTML = html;

        // ── Populate <select> with options (now `options` is an object) ───────────────────────────────────────────────
        const select = container.querySelector("select");
        // Clear any existing children (in case configureElement is called again)
        select.innerHTML = "";

        Object.entries(c.options).forEach(([optValue, optDef]) => {
            const o = document.createElement("option");
            o.value = optValue;
            o.textContent = optDef.label;
            if (optValue === c.value) {
                o.selected = true;
            }
            select.appendChild(o);
        });

        select.disabled = !!c.locked;

        // ── Stretch the <select> invisibly to capture clicks ──────────────────────────────────────────────────────────
        Object.assign(select.style, {
            position: "absolute",
            top: "0",
            left: "0",
            width: "100%",
            height: "100%",
            opacity: "0",
            cursor: "pointer",
            zIndex: "1",
        });

        // ── Style the dropdown arrow ─────────────────────────────────────────────────────────────────────────────────
        const arrow = container.querySelector(".msSelectDropdown");
        Object.assign(arrow.style, {
            position: "absolute",
            bottom: "1px",
            right: "1px",
            pointerEvents: "none",
            zIndex: "2",
        });

        // ── Apply titleStyle (font‐weight) ───────────────────────────────────────────────────────────────────────────
        // const titleEl = container.querySelector(".msSelectTitle");
        // if (titleEl) {
        //     titleEl.style.fontWeight = (c.titleStyle === "bold" ? "bold" : "normal");
        // }
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    setValue(value) {
        const c = this.configuration;
        const el = this.element;
        const select = el.querySelector("select");
        const valueEl = el.querySelector(".msSelectValue");

        if (!(value in c.options)) return; // ignore unknown values

        // Update internal state
        c.value = value;

        // Update <select>
        if (select) {
            select.value = value;
        }

        // Update visible label
        if (valueEl) {
            valueEl.textContent = this._getCurrentLabel();
        }

        // Update background color if per-option color exists
        el.style.backgroundColor = getColor(this._getCurrentColor());
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    /**
     * Expose the root element for insertion into the DOM.
     */
    getElement() {
        return this.element;
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    /**
     * Merge `data` into configuration, then re-render.
     * Reassign listeners because the inner <select> may be rebuilt.
     */
    update(data) {

    }

    /* -------------------------------------------------------------------------------------------------------------- */
    /**
     * Wire up event listeners on the <select> and the container for change, right-click (lock prevention),
     * and long-press → long-click detection.
     */
    assignListeners(container) {

        // Clear any previously attached listeners by cloning the node
        // (Prevents duplicate handlers if `update()` is called repeatedly.)
        const fresh = container.cloneNode(false);
        container.parentNode?.replaceChild(fresh, container);
        this.element = fresh;

        // Re-apply the contents (they were lost by cloneNode). Then proceed to attach listeners.
        this.configureElement(this.element);
        super.assignListeners(this.element);

        const select = this.element.querySelector("select");
        const c = this.configuration;
        const valueEl = this.element.querySelector(".msSelectValue");

        // ── On selection change ───────────────────────────────────────────────────────────────────────────────────────
        select.addEventListener("change", () => {
            c.value = select.value;
            valueEl.textContent = this._getCurrentLabel();

            this.callbacks.get('event').call({
                id: this.id,
                event: "multi_select_change",
                data: {value: c.value},
            });

            this.element.style.backgroundColor = getColor(this._getCurrentColor());
            this.element.classList.add("accepted");
            this.element.addEventListener(
                "animationend",
                () => {
                    this.element.classList.remove("accepted");
                },
                {once: true}
            );
        });

        // ── Prevent default context menu if lockable ─────────────────────────────────────────────────────────────────
        // select.addEventListener("contextmenu", (e) => {
        //     if (c.lockable) {
        //         e.preventDefault();
        //     }
        // });

        // ── Long-press detection for long-click event ──────────────────────────────────────────────────────────────
        let longPressTimer;
        const LP_THRESHOLD = 500;
        const startPress = () => {
            longPressTimer = setTimeout(() => {
                this.callbacks.get('event').call({
                    id: this.id,
                    event: "multi_select_long_click",
                    data: {},
                });
            }, LP_THRESHOLD);
        };
        const clearPress = () => {
            clearTimeout(longPressTimer);
        };

        this.element.addEventListener("mousedown", startPress);
        this.element.addEventListener("mouseup", clearPress);
        this.element.addEventListener("mouseleave", clearPress);
        this.element.addEventListener("touchstart", startPress, {passive: true});
        this.element.addEventListener("touchend", clearPress);
        this.element.addEventListener("touchcancel", clearPress);
    }

    updateConfig(data) {
        this.configuration = {...this.configuration, ...data};
        this.configureElement(this.element);
        this.assignListeners(this.element);
    }
}