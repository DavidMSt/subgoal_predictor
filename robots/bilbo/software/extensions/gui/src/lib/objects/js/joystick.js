// === JOYSTICK WIDGET ================================================================================================
import {Widget} from "../objects.js";
import {getColor} from "../../helpers.js";

export class JoystickWidget extends Widget {
    constructor(id, config = {}) {
        super(id, config);

        const default_configuration = {
            title: '',
            visible: true,
            color: [0.2, 0.2, 0.2],
            knob_color: [0.6, 0.6, 0.6],
            base_color: [0.35, 0.35, 0.35],
            text_color: [1, 1, 1],
            x: 0,
            y: 0,
            fixed_axis: null,  // 'horizontal', 'vertical', or null for both axes
            return_to_center: true,  // Whether to return to center on release
            continuous_updates: true,
            max_updates_per_second: 20,
            show_values: false,  // Whether to show x,y values
            deadzone: 0,  // Deadzone radius (0-1)
        };

        this.configuration = {...default_configuration, ...this.configuration};

        this.element = this._initializeElement();
        this.configureElement(this.element);
        this.assignListeners(this.element);
    }

    _initializeElement() {
        const el = document.createElement('div');
        el.id = this.id;
        el.classList.add('widget', 'highlightable', 'joystickWidget');
        return el;
    }

    configureElement(element) {
        super.configureElement(element);

        // ── Visibility ─────────────────────────────────────────────────────────────────────────────────────────────────
        if (!this.configuration.visible) {
            this.element.style.display = 'none';
        } else {
            this.element.style.display = '';
        }

        // ── Colors ─────────────────────────────────────────────────────────────────────────────────────────────────────
        this.element.style.backgroundColor = getColor(this.configuration.color);
        this.element.style.color = getColor(this.configuration.text_color);
        this.element.style.setProperty('--joystick-knob-color', getColor(this.configuration.knob_color));
        this.element.style.setProperty('--joystick-base-color', getColor(this.configuration.base_color));

        // ── Data attributes ────────────────────────────────────────────────────────────────────────────────────────────
        this.element.dataset.x = this.configuration.x;
        this.element.dataset.y = this.configuration.y;
        this.element.dataset.continuousUpdates = String(this.configuration.continuous_updates);
        if (this.configuration.fixed_axis) {
            this.element.dataset.fixedAxis = this.configuration.fixed_axis;
        }
        this.element.dataset.returnToCenter = String(this.configuration.return_to_center);
        this.element.dataset.deadzone = this.configuration.deadzone;

        // ── HTML ───────────────────────────────────────────────────────────────────────────────────────────────────────
        this.element.innerHTML = `
            <span class="joystickTitle">${this.configuration.title || ''}</span>
            <div class="joystickBase">
                <div class="joystickKnob"></div>
            </div>
            ${this.configuration.show_values ? '<div class="joystickValues"><span class="joystickX">X: 0.00</span><span class="joystickY">Y: 0.00</span></div>' : ''}
            ${this.configuration.continuous_updates ? '<div class="continuousIcon">🔄</div>' : ''}
        `;

        // Draw axis constraints indicator if fixed_axis is set
        if (this.configuration.fixed_axis) {
            const base = this.element.querySelector('.joystickBase');
            const indicator = document.createElement('div');
            indicator.className = 'joystickAxisIndicator';
            indicator.dataset.axis = this.configuration.fixed_axis;
            base.appendChild(indicator);
        }

        // Ensure the joystick base stays circular by resizing on layout changes
        this._setupResizeObserver();
    }

    _setupResizeObserver() {
        // Clean up any existing observer
        if (this._resizeObserver) {
            this._resizeObserver.disconnect();
        }

        const base = this.element.querySelector('.joystickBase');
        if (!base) return;

        const resizeBase = () => {
            const container = this.element;
            const rect = container.getBoundingClientRect();

            // Account for padding and title/values space
            const padding = 16;
            const titleSpace = this.configuration.title ? 24 : 8;
            const valuesSpace = this.configuration.show_values ? 20 : 8;

            const availableWidth = rect.width - padding;
            const availableHeight = rect.height - titleSpace - valuesSpace;

            // Use the smaller dimension to keep it circular
            const size = Math.max(20, Math.min(availableWidth, availableHeight) * 0.85);

            base.style.width = `${size}px`;
            base.style.height = `${size}px`;
        };

        // Initial sizing after a brief delay to ensure layout is complete
        requestAnimationFrame(resizeBase);

        // Observe container size changes
        this._resizeObserver = new ResizeObserver(resizeBase);
        this._resizeObserver.observe(this.element);
    }

    getElement() {
        return this.element;
    }

    updateConfig(data) {
        this.configuration = {...this.configuration, ...data};
        this.configureElement(this.element);
    }

    update(data) {
        // Update from backend - set the joystick position
        if (typeof data === 'object' && data !== null) {
            if (data.x !== undefined) this.setPosition(data.x, data.y);
        }
    }

    setPosition(x, y) {
        const el = this.element;
        const knob = el.querySelector('.joystickKnob');
        const base = el.querySelector('.joystickBase');

        if (!knob || !base) return;

        // Clamp values to -1 to 1
        x = Math.max(-1, Math.min(1, x));
        y = Math.max(-1, Math.min(1, y));

        // Apply fixed axis constraint
        const fixedAxis = el.dataset.fixedAxis;
        if (fixedAxis === 'horizontal') {
            y = 0;
        } else if (fixedAxis === 'vertical') {
            x = 0;
        }

        // Store values
        el.dataset.x = x.toFixed(2);
        el.dataset.y = y.toFixed(2);
        this.configuration.x = x;
        this.configuration.y = y;

        // Calculate pixel offset based on base size
        const rect = base.getBoundingClientRect();
        const maxDistance = rect.width / 2;
        const dx = x * maxDistance;
        const dy = -y * maxDistance;  // Invert Y for screen coordinates

        knob.style.transform = `translate(calc(-50% + ${dx}px), calc(-50% + ${dy}px))`;

        // Update value display if shown
        if (this.configuration.show_values) {
            const xLabel = el.querySelector('.joystickX');
            const yLabel = el.querySelector('.joystickY');
            if (xLabel) xLabel.textContent = `X: ${x.toFixed(2)}`;
            if (yLabel) yLabel.textContent = `Y: ${y.toFixed(2)}`;
        }
    }

    assignListeners(el) {
        super.assignListeners(el);

        const base = el.querySelector('.joystickBase');
        const knob = el.querySelector('.joystickKnob');

        let dragging = false;
        let centerX, centerY, maxDistance;

        // ── Throttle state ─────────────────────────────────────────────────────────────────────────────────────────────
        const maxRate = this.configuration.max_updates_per_second;
        const interval = 1000 / maxRate;
        let lastSent = 0;
        let trailingTimer = null;
        let trailingValue = null;

        // Helper to actually send an event
        const sendEvent = (x, y) => {
            this.callbacks.get('event').call({
                id: this.id,
                event: 'joystick_change',
                data: {x, y}
            });
        };

        // Throttle + trailing
        const maybeSend = (x, y) => {
            const now = Date.now();
            const since = now - lastSent;
            if (since >= interval) {
                sendEvent(x, y);
                lastSent = now;
            } else {
                trailingValue = {x, y};
                if (!trailingTimer) {
                    trailingTimer = setTimeout(() => {
                        sendEvent(trailingValue.x, trailingValue.y);
                        lastSent = Date.now();
                        trailingTimer = null;
                    }, interval - since);
                }
            }
        };

        const updateDimensions = () => {
            const rect = base.getBoundingClientRect();
            centerX = rect.left + rect.width / 2;
            centerY = rect.top + rect.height / 2;
            maxDistance = rect.width / 2;
        };

        const processPointer = (e) => {
            let dx = e.clientX - centerX;
            let dy = e.clientY - centerY;
            let distance = Math.sqrt(dx * dx + dy * dy);

            // Constrain to circle
            if (distance > maxDistance) {
                const angle = Math.atan2(dy, dx);
                dx = maxDistance * Math.cos(angle);
                dy = maxDistance * Math.sin(angle);
            }

            // Apply axis constraint
            const fixedAxis = el.dataset.fixedAxis;
            if (fixedAxis === 'horizontal') {
                dy = 0;
            } else if (fixedAxis === 'vertical') {
                dx = 0;
            }

            // Normalize to -1 to 1
            let normX = dx / maxDistance;
            let normY = -dy / maxDistance;  // Invert Y so up is positive

            // Apply deadzone
            const deadzone = parseFloat(el.dataset.deadzone) || 0;
            if (deadzone > 0) {
                const mag = Math.sqrt(normX * normX + normY * normY);
                if (mag < deadzone) {
                    normX = 0;
                    normY = 0;
                } else {
                    // Rescale from deadzone to 1
                    const scale = (mag - deadzone) / (1 - deadzone) / mag;
                    normX *= scale;
                    normY *= scale;
                }
            }

            // Update DOM
            knob.style.transform = `translate(calc(-50% + ${dx}px), calc(-50% + ${dy}px))`;

            el.dataset.x = normX.toFixed(2);
            el.dataset.y = normY.toFixed(2);
            this.configuration.x = normX;
            this.configuration.y = normY;

            // Update value display if shown
            if (this.configuration.show_values) {
                const xLabel = el.querySelector('.joystickX');
                const yLabel = el.querySelector('.joystickY');
                if (xLabel) xLabel.textContent = `X: ${normX.toFixed(2)}`;
                if (yLabel) yLabel.textContent = `Y: ${normY.toFixed(2)}`;
            }

            return {x: normX, y: normY};
        };

        // ── Pointer Events ─────────────────────────────────────────────────────────────────────────────────────────────
        base.addEventListener('pointerdown', (e) => {
            if (el.dataset.disabled === 'true') return;
            e.preventDefault();
            e.stopPropagation();
            dragging = true;
            updateDimensions();
            base.setPointerCapture(e.pointerId);
            el.classList.add('dragging');

            const {x, y} = processPointer(e);
            if (el.dataset.continuousUpdates === 'true') {
                maybeSend(x, y);
            }
        });

        base.addEventListener('pointermove', (e) => {
            if (!dragging) return;
            e.stopPropagation();

            const {x, y} = processPointer(e);
            if (el.dataset.continuousUpdates === 'true') {
                maybeSend(x, y);
            }
        });

        const endDrag = (e) => {
            if (!dragging) return;
            e.stopPropagation();
            dragging = false;
            base.releasePointerCapture(e.pointerId);
            el.classList.remove('dragging');

            // Clear any pending trailing send
            if (trailingTimer) {
                clearTimeout(trailingTimer);
                trailingTimer = null;
            }

            // Return to center if configured
            if (el.dataset.returnToCenter === 'true') {
                knob.style.transition = 'transform 0.2s ease';
                knob.style.transform = 'translate(-50%, -50%)';

                el.dataset.x = '0';
                el.dataset.y = '0';
                this.configuration.x = 0;
                this.configuration.y = 0;

                if (this.configuration.show_values) {
                    const xLabel = el.querySelector('.joystickX');
                    const yLabel = el.querySelector('.joystickY');
                    if (xLabel) xLabel.textContent = 'X: 0.00';
                    if (yLabel) yLabel.textContent = 'Y: 0.00';
                }

                // Send final position (center)
                sendEvent(0, 0);

                setTimeout(() => {
                    knob.style.transition = '';
                }, 200);
            } else {
                // Send final position (wherever it ended up)
                const finalX = parseFloat(el.dataset.x);
                const finalY = parseFloat(el.dataset.y);
                sendEvent(finalX, finalY);
            }

            // "Accepted" animation for non-continuous
            if (el.dataset.continuousUpdates !== 'true') {
                el.classList.add('accepted');
                el.addEventListener('animationend', () => {
                    el.classList.remove('accepted');
                }, {once: true});
            }
        };

        base.addEventListener('pointerup', endDrag);
        base.addEventListener('pointercancel', endDrag);
    }
}
