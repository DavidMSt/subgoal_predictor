// === SLIDER WIDGET ===================================================================================================
import {Widget} from "../objects.js";
import {getColor, shadeColor, interpolateColors} from "../../helpers.js";

export class SliderWidget extends Widget {
    constructor(id, config = {}) {
        super(id, config);

        const default_configuration = {
            title: '',
            visible: true,
            color: [0.3, 0.3, 0.3],
            text_color: [1, 1, 1],
            min_value: 0,
            max_value: 10,
            value: 0,
            increment: 1,
            direction: 'horizontal',
            continuousUpdates: false,
            maxContinuousUpdatesPerSecond: 20,
            ticks: null,
            snapToTicks: false,
            automaticReset: null,

        }

        this.configuration = {...default_configuration, ...this.configuration};

        this.element = this._initializeElement();

        this.configureElement(this.element);

        this.assignListeners(this.element);

    }

    _initializeElement() {
        const el = document.createElement('div');
        el.id = this.id;
        el.classList.add('widget', 'highlightable', 'sliderWidget');
        return el;
    }

    configureElement(element) {
        super.configureElement(element);

        // ── Visibility ───────────────────────────────────────────────────────────────────────────────────────────────
        if (!this.configuration.visible) {
            this.element.style.display = 'none';
        } else {
            this.element.style.display = '';
        }

        // ── Colors ───────────────────────────────────────────────────────────────────────────────────────────────────
        this.element.style.backgroundColor = getColor(this.configuration.color);
        this.element.style.color = getColor(this.configuration.text_color);

        // ── Compute increment/decimals/valueType ─────────────────────────────────────────────────────────────────────
        const inc = parseFloat(this.configuration.increment);
        const decimals = Math.max(0, (inc.toString().split('.')[1] || '').length);
        const valueType = inc % 1 === 0 ? 'int' : 'float';

        // ── Set data-* attributes for later use in event handlers ───────────────────────────────────────────────────
        // We store min, max, increment, decimals, etc. in data-attributes, so the drag logic can read them.
        this.element.dataset.min = this.configuration.min_value;
        this.element.dataset.max = this.configuration.max_value;
        this.element.dataset.increment = inc;
        this.element.dataset.decimals = decimals;
        this.element.dataset.valueType = valueType;
        this.element.dataset.direction = this.configuration.direction;
        this.element.dataset.continuousUpdates = String(this.configuration.continuousUpdates);
        this.element.dataset.limitToTicks = String(this.configuration.snapToTicks);
        this.element.dataset.ticks = JSON.stringify(this.configuration.ticks || []);
        if (this.configuration.automaticReset != null) {
            this.element.dataset.automaticReset = this.configuration.automaticReset;
        }
        // ── Compute fill percentage based on current value ───────────────────────────────────────────────────────────
        const rawPct = ((this.configuration.value - this.configuration.min_value) / (this.configuration.max_value - this.configuration.min_value)) * 100;
        const pct = Math.min(100, Math.max(0, rawPct));
        // ── HTML ─────────────────────────────────────────────────────────────────────────────────────────────────────
        this.element.innerHTML = `
            <span class="sliderTitle">${this.configuration.title || ''}</span>
            <div class="sliderFill" style="${this.configuration.direction === 'vertical' ? `height:${pct}%; width:100%; bottom:0; top:auto;` : `width:${pct}%; height:100%;`}"></div>
            <span class="sliderValue">${Number(this.configuration.value).toFixed(decimals)}</span>
              ${this.configuration.continuousUpdates ? '<div class="continuousIcon">🔄</div>' : ''}
            `;

        // ticks
        if (this.configuration.ticks && this.configuration.ticks.length) {
            this.configuration.ticks.forEach(v => {
                const tick = document.createElement('div');
                tick.className = 'sliderTick';
                const tPct = ((v - this.configuration.min_value) / (this.configuration.max_value - this.configuration.min_value)) * 100;
                if (this.configuration.direction === 'vertical') {
                    tick.style.top = `${100 - tPct}%`;
                    tick.style.width = '100%';
                } else {
                    tick.style.left = `${tPct}%`;
                    tick.style.height = '100%';
                }
                this.element.appendChild(tick);
            });
        }
    }

    getElement() {
        return this.element;
    }

    updateConfig(data) {
        this.configuration = {...this.configuration, ...data};
        this.configureElement(this.configuration);
    }

    update(data) {
        this.setValue(data);
    }


    assignListeners(el) {
        super.assignListeners(el);
        let dragging = false,
            trackLength,
            direction = el.dataset.direction,
            rect;

        // ── Throttle state ─────────────────────────────────────────────────────────
        const maxRate = this.configuration.maxContinuousUpdatesPerSecond;
        const interval = 1000 / maxRate;           // ms between allowed sends
        let lastSent = 0;                          // timestamp of last send
        let trailingTimer = null;                  // timer for trailing send
        let trailingValue = null;                  // last value seen

        // helper to actually send an event
        const sendEvent = (value) => {
            if (value === null || value === undefined || Number.isNaN(value)) {
                return;
            }
            this.callbacks.get('event').call({
                id: this.id,
                event: 'slider_change',
                data: {value}
            });
        };

        // throttle + trailing
        const maybeSend = (value) => {
            const now = Date.now();
            const since = now - lastSent;
            if (since >= interval) {
                // allowed to send immediately
                sendEvent(value);
                lastSent = now;
            } else {
                // schedule a trailing send
                trailingValue = value;
                if (!trailingTimer) {
                    trailingTimer = setTimeout(() => {
                        sendEvent(trailingValue);
                        lastSent = Date.now();
                        trailingTimer = null;
                    }, interval - since);
                }
            }
        };

        // ── Raw pointer → value logic (unchanged) ────────────────────────────────────
        const updateFromPointer = e => {
            const min = parseFloat(el.dataset.min);
            const max = parseFloat(el.dataset.max);
            const inc = parseFloat(el.dataset.increment);
            const decimals = parseInt(el.dataset.decimals, 10);
            const valueType = el.dataset.valueType;
            const fill = el.querySelector('.sliderFill');

            // compute raw position → percentage
            const pos = direction === 'vertical'
                ? (rect.bottom - e.clientY)
                : (e.clientX - rect.left);
            const rawPct = Math.max(0, Math.min(1, pos / trackLength));
            let raw = min + rawPct * (max - min);

            // snapping logic
            if (el.dataset.limitToTicks === 'true') {
                const ticks = JSON.parse(el.dataset.ticks);
                if (ticks.length) {
                    raw = ticks.reduce(
                        (p, c) => Math.abs(c - raw) < Math.abs(p - raw) ? c : p,
                        ticks[0]
                    );
                }
            } else {
                raw = Math.round(raw / inc) * inc;
                if (valueType === 'int') raw = Math.round(raw);
                else raw = parseFloat(raw.toFixed(decimals));
            }

            // update DOM
            el.dataset.currentValue = raw;
            el.querySelector('.sliderValue').textContent =
                valueType === 'int' ? raw.toFixed(0) : raw.toFixed(decimals);

            const snappedPct = (raw - min) / (max - min);
            if (direction === 'vertical') fill.style.height = (snappedPct * 100) + '%';
            else fill.style.width = (snappedPct * 100) + '%';

            return raw;
        };

        // ── Event handlers ──────────────────────────────────────────────────────────
        el.addEventListener('pointerdown', e => {
            if (e.button !== 0) return;
            if (el.dataset.continuousUpdates === 'true') el.classList.add('dragging');
            e.preventDefault();
            rect = el.getBoundingClientRect();
            trackLength = direction === 'vertical' ? rect.height : rect.width;
            dragging = true;
            el.setPointerCapture(e.pointerId);

            const v = updateFromPointer(e);
            if (el.dataset.continuousUpdates === 'true') maybeSend(v);
        });

        el.addEventListener('pointermove', e => {
            if (!dragging) return;
            const v = updateFromPointer(e);
            if (el.dataset.continuousUpdates === 'true') maybeSend(v);
        });

        el.addEventListener('pointerup', e => {
            if (e.button !== 0) return;
            dragging = false;
            el.releasePointerCapture(e.pointerId);

            // 1) always send the true final value
            const finalValue = parseFloat(el.dataset.currentValue);
            sendEvent(finalValue);

            // 2) automaticReset (if configured)
            if (el.dataset.automaticReset != null) {
                el.dataset.currentValue = el.dataset.automaticReset;
                sendEvent(el.dataset.automaticReset);
                this.update(parseFloat(el.dataset.automaticReset));
            }

            // 3) “accepted” animation for non‐continuous
            if (el.dataset.continuousUpdates !== 'true') {
                el.classList.add('accepted');
                el.addEventListener('animationend', () => {
                    el.classList.remove('accepted');
                }, {once: true});
            }

            // 4) clear any pending trailing send
            if (trailingTimer) {
                clearTimeout(trailingTimer);
                trailingTimer = null;
            }

            el.classList.remove('dragging');
        });
    }


    setValue(value) {
        const el = this.element;

        const min = parseFloat(el.dataset.min);
        const max = parseFloat(el.dataset.max);
        const inc = parseFloat(el.dataset.increment);
        const decimals = parseInt(el.dataset.decimals, 10);
        const valueType = el.dataset.valueType;
        const direction = el.dataset.direction;

        // Clamp value
        let clamped = Math.max(min, Math.min(max, value));

        // Snap to increment
        clamped = Math.round(clamped / inc) * inc;
        if (valueType === 'int') clamped = Math.round(clamped);
        else clamped = parseFloat(clamped.toFixed(decimals));

        // Update internal config and dataset
        this.configuration.value = clamped;
        el.dataset.currentValue = clamped;

        // Update UI
        const pct = ((clamped - min) / (max - min)) * 100;
        const fill = el.querySelector('.sliderFill');
        const valueLabel = el.querySelector('.sliderValue');
        if (fill) {
            if (direction === 'vertical') {
                fill.style.height = `${pct}%`;
            } else {
                fill.style.width = `${pct}%`;
            }
        }
        if (valueLabel) {
            valueLabel.textContent = valueType === 'int' ? clamped.toFixed(0) : clamped.toFixed(decimals);
        }
    }

}

// === CLASSIC SLIDER WIDGET ===========================================================================================
export class ClassicSliderWidget extends Widget {
    constructor(id, config = {}) {
        super(id, config);

        // Default configuration for the classic slider
        const default_configuration = {
            title: '',
            title_position: 'top',       // 'top' | 'bottom' | 'left' | 'right'
            valuePosition: 'center',    // 'top' | 'bottom' | 'left' | 'right' | 'center'
            visible: true,
            backgroundColor: '#333',
            stemColor: '#888',
            handleColor: '#ccc',
            text_color: '#fff',
            valueFontSize: 12,
            titleFontSize: 10,
            min_value: 0,
            max_value: 100,
            value: 0,
            increment: 1,
            direction: 'horizontal',    // 'horizontal' | 'vertical'
            continuousUpdates: false,
            maxContinuousUpdatesPerSecond: 10,
            snapToTicks: false,
            ticks: [],                  // array of numeric tick positions
            automaticReset: null        // numeric value to reset to after release, or null
        };

        // Merge defaults with any user-provided configuration
        this.configuration = {...default_configuration, ...this.configuration};

        // Create the root element, configure it, and wire up listeners
        this.element = this._initializeElement();
        this.configureElement(this.element);
        this.assignListeners(this.element);
    }

    // Create the root <div> for the widget
    _initializeElement() {
        const el = document.createElement('div');
        el.id = this.id;
        el.classList.add('widget', 'highlightable', 'classicSliderWidget');
        return el;
    }

    // Apply configuration to the element (build innerHTML, set styles & data-attributes)
    configureElement(element) {
        super.configureElement(element);
        const c = this.configuration;
        const el = this.element;

        // ── Visibility ─────────────────────────────────────────────────────────────────
        if (!c.visible) {
            el.style.display = 'none';
        } else {
            el.style.display = '';
        }

        // ── Colors & CSS variables ─────────────────────────────────────────────────────
        el.style.backgroundColor = getColor(c.backgroundColor);
        el.style.color = getColor(c.text_color);
        el.style.setProperty('--stem-color', getColor(c.stemColor));
        el.style.setProperty('--handle-color', getColor(c.handleColor));

        // ── Layout flags as data-attributes ─────────────────────────────────────────────
        el.dataset.titlePosition = c.title_position;
        el.dataset.valuePosition = c.valuePosition;
        el.dataset.direction = c.direction;
        el.dataset.continuousUpdates = String(c.continuousUpdates);
        el.dataset.snapToTicks = String(c.snapToTicks);

        // ── Numeric metadata ────────────────────────────────────────────────────────────
        const inc = parseFloat(c.increment);
        const decimals = Math.max(0, (inc.toString().split('.')[1] || '').length);

        el.dataset.min = c.min_value;
        el.dataset.max = c.max_value;
        el.dataset.increment = inc;
        el.dataset.decimals = decimals;
        el.dataset.ticks = JSON.stringify(c.ticks || []);
        if (c.automaticReset != null) {
            el.dataset.automaticReset = c.automaticReset;
        }

        // Compute max label width (for monospace alignment)
        const minStr = Number(c.min_value).toFixed(decimals);
        const maxStr = Number(c.max_value).toFixed(decimals);
        const maxLen = Math.max(minStr.length, maxStr.length);
        el.style.setProperty('--value-width', `${maxLen}ch`);

        // ── Compute current fill/handle percentage ───────────────────────────────────────
        const pctRaw = ((c.value - c.min_value) / (c.max_value - c.min_value)) * 100;
        const pct = Math.min(100, Math.max(0, pctRaw));

        // ── Build inner HTML ────────────────────────────────────────────────────────────
        // Note: CSS should use data-title-position and data-value-position to place .csTitle/.csValue appropriately.
        el.innerHTML = `
            <span class="csTitle">${c.title}</span>
            <div class="csMain">
                <div class="csSliderContainer">
                    <div class="csStem"></div>
                    <div class="csFill" style="${
            c.direction === 'vertical'
                ? `height: ${pct}%;`
                : `width: ${pct}%;`
        }"></div>
                    <div class="csHandle" style="${
            c.direction === 'vertical'
                ? `bottom: ${pct}%;`
                : `left: ${pct}%;`
        }"></div>
                </div>
                <span class="csValue">${Number(c.value).toFixed(decimals)}</span>
                ${c.continuousUpdates ? '<div class="continuousIcon">🔄</div>' : ''}
            </div>
        `;

        // ── Render tick marks if provided ────────────────────────────────────────────────
        if (Array.isArray(c.ticks) && c.ticks.length) {
            const track = el.querySelector('.csSliderContainer');
            c.ticks.forEach(v => {
                const t = document.createElement('div');
                t.className = 'csTick';
                const tPct = ((v - c.min_value) / (c.max_value - c.min_value)) * 100;
                if (c.direction === 'vertical') {
                    t.style.bottom = `${tPct}%`;
                } else {
                    t.style.left = `${tPct}%`;
                }
                track.appendChild(t);
            });
        }
    }

    // Return the root element so it can be inserted into the DOM
    getElement() {
        return this.element;
    }

    updateConfig(data) {
        // Merge any provided data (e.g., { value: 42 }) into configuration
        this.configuration = {...this.configuration, ...data};
        this.configureElement(this.configuration);
    }

    // Update the widget’s configuration and re-render
    update(data) {
        this.setValue(data);
    }

    setValue(value) {
        const el = this.element;

        const min = parseFloat(el.dataset.min);
        const max = parseFloat(el.dataset.max);
        const inc = parseFloat(el.dataset.increment);
        const decimals = parseInt(el.dataset.decimals, 10);
        const direction = el.dataset.direction;
        const valueType = inc % 1 === 0 ? 'int' : 'float';

        // Clamp and round the value
        let clamped = Math.max(min, Math.min(max, value));
        clamped = Math.round(clamped / inc) * inc;
        if (valueType === 'int') clamped = Math.round(clamped);
        else clamped = parseFloat(clamped.toFixed(decimals));

        // Update internal config
        this.configuration.value = clamped;

        // Update fill, handle, and display
        const pct = ((clamped - min) / (max - min)) * 100;
        const fill = el.querySelector('.csFill');
        const handle = el.querySelector('.csHandle');
        const valueLabel = el.querySelector('.csValue');

        if (direction === 'vertical') {
            if (fill) fill.style.height = `${pct}%`;
            if (handle) handle.style.bottom = `${pct}%`;
        } else {
            if (fill) fill.style.width = `${pct}%`;
            if (handle) handle.style.left = `${pct}%`;
        }

        if (valueLabel) {
            valueLabel.textContent = valueType === 'int'
                ? clamped.toFixed(0)
                : clamped.toFixed(decimals);
        }
    }


    assignListeners(el) {
        super.assignListeners(el);
        let dragging = false, trackLength, rect;
        const dir = el.dataset.direction;
        const trackEl = el.querySelector('.csSliderContainer');

        // ── Throttle state ─────────────────────────────────────────────────────────────
        const maxRate = this.configuration.maxContinuousUpdatesPerSecond;
        const interval = 1000 / maxRate;
        let lastSent = 0;
        let trailingTimer = null;
        let trailingValue = null;

        const sendEvent = (v) => {
            if (v === null || v === undefined || Number.isNaN(v)) {
                return;
            }
            this.callbacks.get('event').call({
                id: this.id,
                event: 'slider_change',
                data: {value: v}
            });
        };

        const maybeSend = (v) => {
            const now = Date.now();
            const since = now - lastSent;
            if (since >= interval) {
                sendEvent(v);
                lastSent = now;
            } else {
                trailingValue = v;
                if (!trailingTimer) {
                    trailingTimer = setTimeout(() => {
                        sendEvent(trailingValue);
                        lastSent = Date.now();
                        trailingTimer = null;
                    }, interval - since);
                }
            }
        };

        // ── Compute new value & update UI (fill + handle + label) ──────────────────────
        const updateFromPointer = (e) => {
            const min = +el.dataset.min;
            const max = +el.dataset.max;
            const inc = +el.dataset.increment;
            const dec = +el.dataset.decimals;
            let raw;

            // figure out pointer ×→percentage
            if (dir === 'vertical') {
                const pos = Math.max(0, Math.min(rect.height, rect.bottom - e.clientY));
                raw = min + (pos / trackLength) * (max - min);
            } else {
                const pos = Math.max(0, Math.min(rect.width, e.clientX - rect.left));
                raw = min + (pos / trackLength) * (max - min);
            }

            // optionally snap to ticks or increment
            if (el.dataset.snapToTicks === 'true') {
                const ticks = JSON.parse(el.dataset.ticks);
                if (ticks.length) {
                    raw = ticks.reduce((p, c) =>
                            Math.abs(c - raw) < Math.abs(p - raw) ? c : p,
                        ticks[0]
                    );
                }
            } else {
                raw = Math.round(raw / inc) * inc;
                raw = +raw.toFixed(dec);
            }

            // clamp
            raw = Math.max(min, Math.min(max, raw));
            this.configuration.value = raw;

            // update fill, handle, and value label
            const pct = ((raw - min) / (max - min)) * 100;
            const fill = el.querySelector('.csFill');
            const handle = el.querySelector('.csHandle');
            if (dir === 'vertical') {
                fill.style.height = `${pct}%`;
                handle.style.bottom = `${pct}%`;
            } else {
                fill.style.width = `${pct}%`;
                handle.style.left = `${pct}%`;
            }
            el.querySelector('.csValue').textContent = raw.toFixed(dec);

            return raw;
        };

        // ── Handlers ───────────────────────────────────────────────────────────────────
        trackEl.addEventListener('pointerdown', (e) => {
            if (e.button !== 0) return;
            e.preventDefault();
            rect = trackEl.getBoundingClientRect();
            trackLength = dir === 'vertical' ? rect.height : rect.width;
            dragging = true;
            el.classList.add('dragging');
            el.setPointerCapture?.(e.pointerId);

            const v = updateFromPointer(e);
            if (el.dataset.continuousUpdates === 'true') maybeSend(v);
        });

        el.addEventListener('pointermove', (e) => {
            if (!dragging) return;
            const v = updateFromPointer(e);
            if (el.dataset.continuousUpdates === 'true') maybeSend(v);
        });

        el.addEventListener('pointerup', (e) => {
            if (e.button !== 0) return;
            if (!dragging) return;
            dragging = false;
            el.releasePointerCapture?.(e.pointerId);

            // 1) always send the final value
            const finalV = this.configuration.value;
            sendEvent(finalV);

            // 2) automatic reset?
            if (el.dataset.automaticReset != null) {
                const rv = +el.dataset.automaticReset;
                this.configuration.value = rv;
                this.configureElement(this.configuration);
                sendEvent(rv);
            }

            // 3) “accepted” animation if not continuous
            if (el.dataset.continuousUpdates !== 'true') {
                el.classList.add('accepted');
                el.addEventListener('animationend', () => {
                    el.classList.remove('accepted');
                }, {once: true});
            }

            // 4) clear any trailing timer
            if (trailingTimer) {
                clearTimeout(trailingTimer);
                trailingTimer = null;
            }

            el.classList.remove('dragging');
        });
    }
}

/* ============================================================================================================== */
export class RotaryDialWidget extends Widget {
    constructor(id, config = {}) {
        super(id, config);

        // Default configuration
        const defaults = {
            visible: true,
            color: '#333',
            dialColor: '#3399FF',
            text_color: '#fff',
            title: '',
            titlePosition: 'top',   // only 'top' or 'left'
            min: 0,
            max: 100,
            value: 0,
            ticks: [],
            increment: 1,
            continuousUpdates: false,
            maxContinuousUpdatesPerSecond: 10,
            limitToTicks: false,
            dialWidth: 5           // thickness of the dial arc
        };

        // Enforce only 'top' or 'left' for titlePosition
        const pos = this.configuration.title_position === 'left' ? 'left' : 'top';
        this.configuration = {...defaults, ...this.configuration, title_position: pos};

        // Create and configure the root element
        this.element = this._initializeElement();
        this.configureElement(this.element);
        this.assignListeners(this.element);
    }

    /* ============================================================================================================== */
    _deg2rad(deg) {
        return (deg * Math.PI) / 180;
    }

    /* ============================================================================================================== */
    _drawDial(el) {
        const canvas = el.querySelector('canvas');
        const ctx = canvas.getContext('2d');
        const w = canvas.clientWidth, h = canvas.clientHeight;
        const cx = w / 2, cy = h / 2;
        const radius = (Math.min(w, h) / 2) * 0.8;

        const minVal = +el.dataset.min;
        const maxVal = +el.dataset.max;
        const curVal = +el.dataset.value;
        const ticks = JSON.parse(el.dataset.ticks);
        const clr = getColor(el.dataset.dialColor);
        const dialWidth = +el.dataset.dialWidth;

        // Define the angular span (gap of 20° centered at top)
        const gapDeg = 20;
        const startAngle = this._deg2rad(90 + gapDeg / 2);
        const endAngle = this._deg2rad(450 - gapDeg / 2);
        const totalAngle = endAngle <= startAngle
            ? endAngle + 2 * Math.PI - startAngle
            : endAngle - startAngle;

        ctx.clearRect(0, 0, w, h);

        // — background arc
        ctx.lineWidth = dialWidth;
        ctx.strokeStyle = '#555';
        ctx.beginPath();
        ctx.arc(cx, cy, radius, startAngle, startAngle + totalAngle);
        ctx.stroke();

        // — filled arc
        const pct = (curVal - minVal) / (maxVal - minVal);
        ctx.strokeStyle = clr;
        ctx.beginPath();
        ctx.arc(cx, cy, radius, startAngle, startAngle + totalAngle * pct);
        ctx.stroke();

        // — tick marks
        ctx.lineWidth = 1;
        ctx.strokeStyle = clr;
        ticks.forEach(v => {
            const tPct = (v - minVal) / (maxVal - minVal);
            const ang = startAngle + totalAngle * tPct;
            const x1 = cx + Math.cos(ang) * (radius + 2);
            const y1 = cy + Math.sin(ang) * (radius + 2);
            const x2 = cx + Math.cos(ang) * (radius - 4);
            const y2 = cy + Math.sin(ang) * (radius - 4);
            ctx.beginPath();
            ctx.moveTo(x1, y1);
            ctx.lineTo(x2, y2);
            ctx.stroke();
        });
    }

    /* ============================================================================================================== */
    _valueFromAngle(el, e) {
        const canvas = el.querySelector('canvas');
        const r = canvas.getBoundingClientRect();
        const cx = r.left + r.width / 2, cy = r.top + r.height / 2;
        let dx = e.clientX - cx, dy = e.clientY - cy;
        let ang = Math.atan2(dy, dx);
        if (ang < 0) ang += 2 * Math.PI;

        const minVal = +el.dataset.min;
        const maxVal = +el.dataset.max;
        const inc = +el.dataset.increment;
        const dec = +el.dataset.decimals;
        const ticks = JSON.parse(el.dataset.ticks);
        const limit = el.dataset.limitToTicks === 'true';

        const gapDeg = 20;
        const startAngle = this._deg2rad(90 + gapDeg / 2);
        const endAngle = this._deg2rad(450 - gapDeg / 2);
        const totalAngle = endAngle <= startAngle
            ? endAngle + 2 * Math.PI - startAngle
            : endAngle - startAngle;

        let delta = ang - startAngle;
        if (delta < 0) delta += 2 * Math.PI;
        delta = Math.min(delta, totalAngle);

        let raw = minVal + (delta / totalAngle) * (maxVal - minVal);

        if (limit && ticks.length) {
            raw = ticks.reduce((p, c) => Math.abs(c - raw) < Math.abs(p - raw) ? c : p, ticks[0]);
        } else {
            raw = Math.round(raw / inc) * inc;
            raw = parseFloat(raw.toFixed(dec));
        }

        return Math.max(minVal, Math.min(maxVal, raw));
    }

    /* ============================================================================================================== */
    checkGridSize(grid_size) {
        const {titlePosition} = this.configuration;
        return !(titlePosition === 'left' && (!grid_size || grid_size[0] < 2));
    }

    /* ============================================================================================================== */
    _initializeElement() {
        const el = document.createElement('div');
        el.id = this.id;
        el.classList.add('widget', 'highlightable', 'rotaryDialWidget');
        return el;
    }

    /* ============================================================================================================== */
    configureElement(element) {
        super.configureElement(element);
        const c = this.configuration;
        const el = this.element;

        // Visibility
        if (!c.visible) {
            el.style.display = 'none';
        } else {
            el.style.display = '';
        }

        // Base colors
        el.style.backgroundColor = getColor(c.color);
        el.style.color = getColor(c.text_color);

        // Numeric metadata
        const inc = +c.increment;
        const dec = Math.max(0, (inc.toString().split('.')[1] || '').length);

        el.dataset.min = c.min;
        el.dataset.max = c.max;
        el.dataset.value = c.value;
        el.dataset.ticks = JSON.stringify(c.ticks);
        el.dataset.dialColor = getColor(c.dialColor);
        el.dataset.increment = inc;
        el.dataset.decimals = dec;
        el.dataset.continuousUpdates = c.continuousUpdates;
        el.dataset.limitToTicks = c.limitToTicks;
        el.dataset.titlePosition = c.title_position;
        el.dataset.dialWidth = c.dialWidth;

        // Displayed value (integer if increment is integer, else fixed decimals)
        const disp = (inc % 1 === 0) ? c.value : Number(c.value).toFixed(dec);

        // Build innerHTML
        el.innerHTML = `
            <span class="rotaryTitle">${c.title}</span>
            <div class="dialWrapper">
                <canvas></canvas>
                <div class="value">${disp}</div>
            </div>
            ${c.continuousUpdates ? '<div class="continuousIcon">🔄</div>' : ''}
        `;
    }

    /* ============================================================================================================== */
    getElement() {
        return this.element;
    }

    /* ============================================================================================================== */
    update(data) {
        this.setValue(data);
    }

    setValue(value) {
        const el = this.element;

        const min = +el.dataset.min;
        const max = +el.dataset.max;
        const inc = +el.dataset.increment;
        const dec = +el.dataset.decimals;
        const limit = el.dataset.limitToTicks === 'true';
        const ticks = JSON.parse(el.dataset.ticks);
        const isInt = inc % 1 === 0;

        // Clamp and optionally snap
        let clamped = Math.max(min, Math.min(max, value));
        if (limit && ticks.length) {
            clamped = ticks.reduce((p, c) => Math.abs(c - clamped) < Math.abs(p - clamped) ? c : p, ticks[0]);
        } else {
            clamped = Math.round(clamped / inc) * inc;
            clamped = parseFloat(clamped.toFixed(dec));
        }

        // Update internal config and DOM
        this.configuration.value = clamped;
        el.dataset.value = clamped;

        const disp = isInt ? clamped.toFixed(0) : clamped.toFixed(dec);
        const valueLabel = el.querySelector('.value');
        if (valueLabel) {
            valueLabel.textContent = disp;
        }

        this._drawDial(el);
    }


    assignListeners(el) {
        super.assignListeners(el);
        // initial draw
        requestAnimationFrame(() => {
            const canvas = el.querySelector('canvas');
            const r = canvas.getBoundingClientRect();
            const dpr = window.devicePixelRatio || 1;
            canvas.width = r.width * dpr;
            canvas.height = r.height * dpr;
            canvas.getContext('2d').scale(dpr, dpr);
            this._drawDial(el);
        });

        const canvas = el.querySelector('canvas');
        const inc = +el.dataset.increment;
        const cont = el.dataset.continuousUpdates === 'true';

        // Throttle state
        const maxRate = this.configuration.maxContinuousUpdatesPerSecond;
        const interval = 1000 / maxRate;
        let lastSent = 0, trailingTimer = null, trailingValue = null;

        const sendEvent = v => {
            this.callbacks.get('event').call({id: this.id, event: 'rotary_dial_change', data: {value: v}});
        };
        const maybeSend = v => {
            const now = Date.now(), since = now - lastSent;
            if (since >= interval) {
                sendEvent(v);
                lastSent = now;
            } else {
                trailingValue = v;
                if (!trailingTimer) {
                    trailingTimer = setTimeout(() => {
                        sendEvent(trailingValue);
                        lastSent = Date.now();
                        trailingTimer = null;
                    }, interval - since);
                }
            }
        };

        let startX = null, startVal = null, moved = false;

        const onDown = e => {
            if (e.button !== 0) return;
            moved = false;
            startX = e.clientX;
            startVal = +el.dataset.value;
            el.classList.add('dragging');
            canvas.setPointerCapture(e.pointerId);
        };

        const onMove = e => {
            if (startX == null) return;
            moved = true;
            const dx = e.clientX - startX;
            const minVal = +el.dataset.min, maxVal = +el.dataset.max;
            const ticks = JSON.parse(el.dataset.ticks);
            const limit = el.dataset.limitToTicks === 'true';

            let raw = startVal + (dx / 150) * (maxVal - minVal);
            if (limit && ticks.length) {
                raw = ticks.reduce((p, c) => Math.abs(c - raw) < Math.abs(p - raw) ? c : p, ticks[0]);
            } else {
                raw = Math.round(raw / inc) * inc;
                raw = +raw.toFixed(+el.dataset.decimals);
            }
            raw = Math.max(minVal, Math.min(maxVal, raw));

            el.dataset.value = raw;
            el.querySelector('.value').textContent = inc % 1 === 0 ? raw : raw.toFixed(+el.dataset.decimals);
            this._drawDial(el);

            if (cont) maybeSend(raw);
        };

        const onUp = e => {
            if (e.button !== 0) return;
            canvas.releasePointerCapture(e.pointerId);
            startX = null;

            // final always
            const final = +el.dataset.value;
            sendEvent(final);

            // clear trailing
            if (trailingTimer) {
                clearTimeout(trailingTimer);
                trailingTimer = null;
            }

            if (!cont) {
                el.classList.add('accepted');
                el.addEventListener('animationend', () => el.classList.remove('accepted'), {once: true});
            }
            el.classList.remove('dragging');
        };

        canvas.addEventListener('pointerdown', onDown);
        canvas.addEventListener('pointermove', onMove);
        canvas.addEventListener('pointerup', onUp);
        canvas.addEventListener('pointercancel', onUp);

        canvas.addEventListener('click', e => {
            if (moved) return;
            const v = this._valueFromAngle(el, e);
            el.dataset.value = v;
            el.querySelector('.value').textContent = inc % 1 === 0 ? v : v.toFixed(+el.dataset.decimals);
            this._drawDial(el);
            sendEvent(v);
        });


        // — redraw on window resize —
        const onResize = () => {
            requestAnimationFrame(() => {
                const canvas = el.querySelector('canvas');
                const r = canvas.getBoundingClientRect();
                const dpr = window.devicePixelRatio || 1;
                canvas.width = r.width * dpr;
                canvas.height = r.height * dpr;
                canvas.getContext('2d').scale(dpr, dpr);
                this._drawDial(el);
            });
        };

        // kick it off once so it’s sized correctly from the get-go
        onResize();

        // and re-draw whenever the window changes size
        window.addEventListener('resize', onResize);
    }

    updateConfig(data) {
        if (data.value == null) return;
        // Merge into configuration
        this.configuration.value = data.value;

        const el = this.element;
        el.dataset.value = data.value;

        const inc = +el.dataset.increment;
        const dec = +el.dataset.decimals;
        el.querySelector('.value').textContent = (inc % 1 === 0) ? parseInt(data.value, 10) : Number(data.value).toFixed(dec);

        this._drawDial(el);
    }

    initializeElement() {
    }
}