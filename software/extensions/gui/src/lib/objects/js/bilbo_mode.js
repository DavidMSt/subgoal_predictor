import {Widget} from "../objects.js";
import {getColor} from "../../helpers.js";

/**
 * BilboModeWidget - Visual widget for displaying BILBO control modes as a state machine
 *
 * Shows modes as colored circles connected by lines indicating allowed transitions.
 * The current mode is highlighted with a ring, available modes are normal, unavailable are dimmed.
 * Responsive sizing calculates circle and font sizes based on widget dimensions.
 */

// Inject CSS for mode states
(function injectBilboModeStyles() {
    if (document.getElementById('bilbo-mode-widget-styles')) return;
    const style = document.createElement('style');
    style.id = 'bilbo-mode-widget-styles';
    style.textContent = `
        /* Ensure all modes have identical layout regardless of state */
        .bmw-mode {
            display: flex !important;
            flex-direction: column !important;
            align-items: center !important;
            transform: none !important;
            margin: 0 !important;
            padding: 0 !important;
        }
        .bmw-circle-wrapper {
            width: var(--bmw-circle-size) !important;
            height: var(--bmw-circle-size) !important;
            flex-shrink: 0 !important;
            transform: none !important;
            margin: 0 !important;
            padding: 0 !important;
        }
        .bmw-circle {
            width: var(--bmw-circle-size) !important;
            height: var(--bmw-circle-size) !important;
            border-radius: 50%;
            transition: transform 0.08s ease-out, filter 0.08s ease-out, box-shadow 0.15s ease-out;
            box-sizing: border-box;
        }
        .bmw-label {
            margin-top: var(--bmw-label-gap) !important;
            transform: none !important;
        }
        /* Unavailable: normal color at 25% opacity with dotted border */
        .bmw-mode-unavailable .bmw-circle {
            opacity: 0.25;
            border: 2px dotted rgba(255, 255, 255, 0.5);
        }
        .bmw-mode-unavailable .bmw-label {
            opacity: 0.25;
        }
        /* Available: color but dimmed */
        .bmw-mode-available .bmw-circle {
            filter: brightness(0.55);
        }
        .bmw-mode-available .bmw-label {
            opacity: 0.7;
        }
        /* Current: full color with inset border - no layout changes */
        /* Border color is set dynamically per mode (blend of white + mode color) */
        .bmw-mode-current .bmw-circle {
            filter: brightness(1);
        }
        .bmw-mode-current .bmw-label {
            opacity: 1;
            font-weight: 500;
        }
        /* Pressed state */
        .bmw-mode-pressed .bmw-circle {
            transform: scale(0.92);
            filter: brightness(0.45);
        }
    `;
    document.head.appendChild(style);
})();

export class BilboModeWidget extends Widget {
    constructor(id, data = {}) {
        super(id, data);

        const default_configuration = {
            // Mode data
            modes: [],
            edges: [],
            current_mode: 'OFF',
            available_modes: [],

            // Layout
            orientation: 'horizontal',

            // Styling
            background_color: [0.15, 0.15, 0.18, 1],
            circle_border_width: 2,
            circle_border_color: [1, 1, 1, 0.3],
            circle_active_border_color: [1, 1, 1, 0.8],
            circle_hover_scale: 1.08,

            label_color: [1, 1, 1, 0.9],

            line_color: [1, 1, 1, 0.2],
            line_width: 2,

            padding: 16,
        };

        this.configuration = {...default_configuration, ...this.configuration};

        // Internal state
        this._modes = this.configuration.modes || [];
        this._edges = this.configuration.edges || [];
        this._currentMode = this.configuration.current_mode || 'OFF';
        this._orientation = this.configuration.orientation || 'horizontal';

        // Build adjacency map for computing available modes
        this._adjacency = this._buildAdjacency();

        // Available modes can be provided or computed from edges
        this._availableModes = this.configuration.available_modes || this._getAvailableModesFromCurrent();

        console.log(this._adjacency);

        // Computed responsive sizes
        this._circleSize = 40;
        this._fontSize = 10;
        this._spacing = 60;
        this._labelGap = 6;

        // Element references
        this._modeElements = new Map();  // mode_id -> {circle, label, ring}
        this._resizeObserver = null;
        this._intersectionObserver = null;
        this._redrawTimeout = null;

        // Create elements
        this.element = document.createElement('div');
        this.element.id = this.id;
        this.element.classList.add('widget', 'bilbo-mode-widget');

        this._buildStructure();
        this._setupResizeObserver();
        this.configureElement(this.element);
        this.assignListeners(this.element);
    }

    /* ============================================================================================================== */
    _buildStructure() {
        // SVG container for lines (z-index 0, behind circles)
        this._svgContainer = document.createElement('div');
        this._svgContainer.className = 'bmw-svg-container';
        this._svgContainer.style.zIndex = '0';
        this.element.appendChild(this._svgContainer);

        this._svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
        this._svg.classList.add('bmw-svg');
        this._svgContainer.appendChild(this._svg);

        // Modes container (z-index 1, above lines)
        this._modesContainer = document.createElement('div');
        this._modesContainer.className = 'bmw-modes-container';
        this._modesContainer.style.zIndex = '1';
        this._modesContainer.style.position = 'relative';
        this._modesContainer.style.display = 'flex';
        this._modesContainer.style.width = '100%';
        this._modesContainer.style.height = '100%';
        this.element.appendChild(this._modesContainer);
    }

    /* ============================================================================================================== */
    _setupResizeObserver() {
        this._resizeObserver = new ResizeObserver((entries) => {
            for (const entry of entries) {
                this._calculateResponsiveSizes(entry.contentRect.width, entry.contentRect.height);
                this._applyResponsiveSizes();
                // Use double requestAnimationFrame to ensure layout is fully settled
                requestAnimationFrame(() => {
                    requestAnimationFrame(() => this._drawLines());
                });
            }
        });
        this._resizeObserver.observe(this.element);

        // IntersectionObserver to redraw lines when widget becomes visible (e.g., page switch)
        this._intersectionObserver = new IntersectionObserver((entries) => {
            for (const entry of entries) {
                if (entry.isIntersecting) {
                    // Widget became visible, redraw lines after layout settles
                    // Use timeout as fallback for CSS transitions that RAF doesn't catch
                    this._scheduleRedraw();
                }
            }
        });
        this._intersectionObserver.observe(this.element);
    }

    /* ============================================================================================================== */
    _scheduleRedraw() {
        // Cancel any pending redraw
        if (this._redrawTimeout) {
            clearTimeout(this._redrawTimeout);
        }
        // Immediate attempt with double RAF
        requestAnimationFrame(() => {
            requestAnimationFrame(() => this._drawLines());
        });
        // Delayed fallback for CSS transitions
        this._redrawTimeout = setTimeout(() => {
            this._drawLines();
        }, 100);
    }

    /* ============================================================================================================== */
    _calculateResponsiveSizes(width, height) {
        const cfg = this.configuration;
        const numModes = this._modes.length || 1;
        const isHorizontal = this._orientation === 'horizontal';

        // Scale padding based on widget size - smaller widgets need less padding
        const effectivePadding = Math.max(4, Math.min(cfg.padding, Math.min(width, height) * 0.08));

        const availableWidth = width - (effectivePadding * 2);
        const availableHeight = height - (effectivePadding * 2);

        if (isHorizontal) {
            // Horizontal: circles distributed evenly across full width
            const sliceWidth = availableWidth / numModes;

            // Label height scales with available space - smaller for tight layouts
            const labelHeight = Math.max(10, Math.min(16, availableHeight * 0.22));
            const circleAreaHeight = availableHeight - labelHeight - 6; // 3px padding top + bottom

            // Circle size = min of slice width and available height
            const maxFromWidth = sliceWidth * 0.85;
            const maxFromHeight = circleAreaHeight * 0.95;

            this._circleSize = Math.max(16, Math.min(100, Math.min(maxFromWidth, maxFromHeight)));
            this._spacing = 0; // Not used - layout handled by space-evenly

            // Calculate font size with constraint to prevent label overlap
            const baseFontSize = this._circleSize * 0.32;
            // Find longest mode name
            const longestLabel = this._modes.reduce((max, m) => {
                const name = m.name || m.id;
                return name.length > max ? name.length : max;
            }, 1);
            // Constrain font size so labels fit within slice with 10px min gap between them
            // Approximate character width is ~0.55 * fontSize for typical fonts
            const maxFontFromWidth = (sliceWidth - 10) / (longestLabel * 0.55);
            this._fontSize = Math.max(7, Math.min(14, Math.min(baseFontSize, maxFontFromWidth)));
            this._labelGap = Math.max(1, this._circleSize * 0.05);

            // Inset border width scales with circle size
            this._currentBorderWidth = Math.max(2, Math.min(6, this._circleSize * 0.12));
        } else {
            // Vertical: circles distributed evenly across full height
            const sliceHeight = availableHeight / numModes;

            // Label width scales with available space
            const labelWidth = Math.max(40, Math.min(70, availableWidth * 0.3));
            const circleAreaWidth = availableWidth - labelWidth;

            const maxFromHeight = sliceHeight * 0.85;
            const maxFromWidth = circleAreaWidth * 0.95;

            this._circleSize = Math.max(16, Math.min(100, Math.min(maxFromWidth, maxFromHeight)));
            this._spacing = 0; // Not used - layout handled by space-evenly
            this._fontSize = Math.max(7, Math.min(14, this._circleSize * 0.32));
            this._labelGap = Math.max(1, this._circleSize * 0.06);

            // Inset border width scales with circle size
            this._currentBorderWidth = Math.max(2, Math.min(6, this._circleSize * 0.12));
        }
    }

    /* ============================================================================================================== */
    _applyResponsiveSizes() {
        this.element.style.setProperty('--bmw-circle-size', `${this._circleSize}px`);
        this.element.style.setProperty('--bmw-spacing', `${this._spacing}px`);
        this.element.style.setProperty('--bmw-label-font-size', `${this._fontSize}pt`);
        this.element.style.setProperty('--bmw-label-gap', `${this._labelGap}px`);
        this.element.style.setProperty('--bmw-current-border-width', `${this._currentBorderWidth}px`);
    }

    /* ============================================================================================================== */
    _buildAdjacency() {
        // Build adjacency map from edges for quick lookup of available transitions
        const adjacency = {};

        // Initialize all modes with empty arrays
        for (const mode of this._modes) {
            adjacency[mode.id] = [];
        }
        // Add unidirectional edges (from -> to only)
        for (const edge of this._edges) {
            if (edge.length >= 2) {
                const fromMode = edge[0];
                const toMode = edge[1];

                // Unidirectional: only add from_mode -> to_mode
                if (adjacency[fromMode] && !adjacency[fromMode].includes(toMode)) {
                    adjacency[fromMode].push(toMode);
                }
            }
        }

        return adjacency;
    }

    /* ============================================================================================================== */
    _getAvailableModesFromCurrent() {
        // Get modes that can be reached from current mode
        return this._adjacency[this._currentMode] || [];
    }

    /* ============================================================================================================== */
    configureElement(element) {
        super.configureElement(element);

        const cfg = this.configuration;

        // Apply CSS custom properties
        element.style.setProperty('--bmw-bg-color', getColor(cfg.background_color));
        element.style.setProperty('--bmw-circle-border-width', `${cfg.circle_border_width}px`);
        element.style.setProperty('--bmw-circle-border-color', getColor(cfg.circle_border_color));
        element.style.setProperty('--bmw-circle-active-border-color', getColor(cfg.circle_active_border_color));
        element.style.setProperty('--bmw-circle-hover-scale', cfg.circle_hover_scale);
        element.style.setProperty('--bmw-label-color', getColor(cfg.label_color));
        element.style.setProperty('--bmw-line-color', getColor(cfg.line_color));
        element.style.setProperty('--bmw-line-width', `${cfg.line_width}px`);
        element.style.setProperty('--bmw-padding', `${cfg.padding}px`);

        // Set orientation and layout
        element.dataset.orientation = this._orientation;
        this._modesContainer.dataset.orientation = this._orientation;

        // Configure flex layout based on orientation
        this._modesContainer.style.flexDirection = this._orientation === 'horizontal' ? 'row' : 'column';
        this._modesContainer.style.justifyContent = 'space-evenly';
        this._modesContainer.style.alignItems = 'center';

        this._rebuildModes();
    }

    /* ============================================================================================================== */
    _rebuildModes() {
        // Clear existing
        this._modesContainer.innerHTML = '';
        this._modeElements.clear();

        // Build mode elements
        for (const mode of this._modes) {
            const modeEl = this._createModeElement(mode);
            this._modesContainer.appendChild(modeEl.container);
            this._modeElements.set(mode.id, modeEl);
        }

        // Update states and draw lines after layout settles
        requestAnimationFrame(() => {
            this._updateModeStates();
            requestAnimationFrame(() => this._drawLines());
        });
    }

    /* ============================================================================================================== */
    _createModeElement(mode) {
        const cfg = this.configuration;

        const container = document.createElement('div');
        container.className = 'bmw-mode';
        container.dataset.modeId = mode.id;

        // Wrapper for circle
        const circleWrapper = document.createElement('div');
        circleWrapper.className = 'bmw-circle-wrapper';
        container.appendChild(circleWrapper);

        // Circle (current mode highlighted with inset border via CSS)
        const circle = document.createElement('div');
        circle.className = 'bmw-circle';
        circle.style.backgroundColor = getColor(mode.color);
        circleWrapper.appendChild(circle);

        // Label
        const label = document.createElement('div');
        label.className = 'bmw-label';
        label.textContent = mode.name || mode.id;
        container.appendChild(label);

        // Click handler
        container.addEventListener('click', () => this._handleModeClick(mode.id));

        // Pressed/touched state handlers - only for available (non-current) modes
        const addPressed = () => {
            const isCurrent = mode.id === this._currentMode;
            const isAvailable = this._availableModes.includes(mode.id);
            if (isAvailable && !isCurrent) {
                container.classList.add('bmw-mode-pressed');
            }
        };
        const removePressed = () => container.classList.remove('bmw-mode-pressed');

        container.addEventListener('mousedown', addPressed);
        container.addEventListener('mouseup', removePressed);
        container.addEventListener('mouseleave', removePressed);
        container.addEventListener('touchstart', addPressed, {passive: true});
        container.addEventListener('touchend', removePressed);
        container.addEventListener('touchcancel', removePressed);

        return {container, circle, circleWrapper, label, id: mode.id};
    }

    /* ============================================================================================================== */
    _updateModeStates() {
        for (const [modeId, modeEl] of this._modeElements) {
            const isCurrent = modeId === this._currentMode;
            const isAvailable = this._availableModes.includes(modeId);

            modeEl.container.classList.toggle('bmw-mode-current', isCurrent);
            modeEl.container.classList.toggle('bmw-mode-available', isAvailable && !isCurrent);
            modeEl.container.classList.toggle('bmw-mode-unavailable', !isAvailable && !isCurrent);

            // Apply blended border color for current mode (80% white + 20% mode color)
            if (isCurrent) {
                const mode = this._modes.find(m => m.id === modeId);
                if (mode && mode.color) {
                    const [r, g, b] = mode.color;
                    // Blend: 80% white (255) + 20% mode color
                    const blendR = Math.round(255 * 0.8 + (r * 255) * 0.2);
                    const blendG = Math.round(255 * 0.8 + (g * 255) * 0.2);
                    const blendB = Math.round(255 * 0.8 + (b * 255) * 0.2);
                    const borderColor = `rgba(${blendR}, ${blendG}, ${blendB}, 0.9)`;
                    const borderWidth = this._currentBorderWidth || 4;
                    modeEl.circle.style.boxShadow = `inset 0 0 0 ${borderWidth}px ${borderColor}`;
                }
            } else {
                modeEl.circle.style.boxShadow = '';
            }
        }
    }

    /* ============================================================================================================== */
    _drawLines() {
        // Clear SVG
        this._svg.innerHTML = '';

        if (this._modeElements.size < 2) return;

        const svgRect = this._svg.getBoundingClientRect();
        const cfg = this.configuration;
        const isHorizontal = this._orientation === 'horizontal';

        // For horizontal mode, get baseline y from a non-current mode circle
        // to ensure all circles align on the same horizontal line
        let baselineY = null;
        if (isHorizontal) {
            for (const mode of this._modes) {
                if (mode.id !== this._currentMode) {
                    const modeEl = this._modeElements.get(mode.id);
                    if (modeEl) {
                        const rect = modeEl.circleWrapper.getBoundingClientRect();
                        baselineY = rect.top + rect.height / 2 - svgRect.top;
                        break;
                    }
                }
            }
        }

        // Get all circle centers in order
        const positions = [];
        for (const mode of this._modes) {
            const modeEl = this._modeElements.get(mode.id);
            if (modeEl) {
                const wrapper = modeEl.circleWrapper;
                const rect = wrapper.getBoundingClientRect();
                positions.push({
                    id: mode.id,
                    x: rect.left + rect.width / 2 - svgRect.left,
                    y: rect.top + rect.height / 2 - svgRect.top
                });
            }
        }

        // Draw simple lines between adjacent modes (connecting line along axis)
        const radius = this._circleSize / 2;

        for (let i = 0; i < positions.length - 1; i++) {
            const from = positions[i];
            const to = positions[i + 1];

            let startX, startY, endX, endY;

            if (isHorizontal) {
                // Horizontal line from edge of first circle to edge of second
                // Use baseline y so all lines are perfectly horizontal
                startX = from.x + radius;
                startY = baselineY ?? from.y;
                endX = to.x - radius;
                endY = baselineY ?? to.y;
            } else {
                // Vertical line from bottom of first circle to top of second
                startX = from.x;
                startY = from.y + radius;
                endX = to.x;
                endY = to.y - radius;
            }

            this._drawSimpleLine(startX, startY, endX, endY);
        }
    }

    /* ============================================================================================================== */
    _drawSimpleLine(x1, y1, x2, y2) {
        const cfg = this.configuration;

        const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
        line.setAttribute('x1', x1);
        line.setAttribute('y1', y1);
        line.setAttribute('x2', x2);
        line.setAttribute('y2', y2);
        line.setAttribute('stroke', getColor(cfg.line_color));
        line.setAttribute('stroke-width', cfg.line_width);
        line.setAttribute('stroke-linecap', 'round');
        line.classList.add('bmw-line');

        this._svg.appendChild(line);
    }

    /* ============================================================================================================== */
    _handleModeClick(modeId) {
        // Only emit if it's an available mode or the current mode
        const isAvailable = this._availableModes.includes(modeId);
        const isCurrent = modeId === this._currentMode;

        if (isAvailable || isCurrent) {
            this.callbacks.get('event').call({
                id: this.id,
                event: 'mode_clicked',
                data: {mode_id: modeId}
            });
        }
    }

    /* ============================================================================================================== */
    assignListeners(element) {
        super.assignListeners(element);
    }

    /* ============================================================================================================== */
    updateConfig(data) {
        this.configuration = {...this.configuration, ...data};

        if ('modes' in data) this._modes = data.modes || [];
        if ('edges' in data) this._edges = data.edges || [];
        if ('current_mode' in data) this._currentMode = data.current_mode || 'OFF';
        if ('orientation' in data) this._orientation = data.orientation || 'horizontal';

        // Rebuild adjacency if modes or edges changed
        if ('modes' in data || 'edges' in data) {
            this._adjacency = this._buildAdjacency();
        }

        // Use provided available_modes or compute from adjacency
        if ('available_modes' in data && data.available_modes && data.available_modes.length > 0) {
            this._availableModes = data.available_modes;
        } else if ('modes' in data || 'edges' in data || 'current_mode' in data) {
            this._availableModes = this._getAvailableModesFromCurrent();
        }

        this.configureElement(this.element);
    }

    /* ============================================================================================================== */
    update(data) {
        this.updateConfig(data);
    }

    /* ============================================================================================================== */
    updateState(data) {
        // Called from backend to update state
        if ('modes' in data) this._modes = data.modes || [];
        if ('edges' in data) this._edges = data.edges || [];
        if ('current_mode' in data) this._currentMode = data.current_mode || 'OFF';
        if ('orientation' in data) {
            this._orientation = data.orientation || 'horizontal';
            this.element.dataset.orientation = this._orientation;
            this._modesContainer.dataset.orientation = this._orientation;
            this._modesContainer.style.flexDirection = this._orientation === 'horizontal' ? 'row' : 'column';
        }

        // Rebuild adjacency if modes or edges changed
        if ('modes' in data || 'edges' in data) {
            this._adjacency = this._buildAdjacency();
        }

        // Use provided available_modes or compute from adjacency
        if ('available_modes' in data && data.available_modes && data.available_modes.length > 0) {
            this._availableModes = data.available_modes;
        } else {
            this._availableModes = this._getAvailableModesFromCurrent();
        }

        this._rebuildModes();
    }

    /* ============================================================================================================== */
    setMode(modeId) {
        // Called from backend to set the current mode
        this._currentMode = modeId;
        // Recompute available modes for new current mode
        this._availableModes = this._getAvailableModesFromCurrent();
        this._updateModeStates();
        this._drawLines();
    }

    /* ============================================================================================================== */
    setAvailableModes(modes) {
        // Called from backend to update available modes
        this._availableModes = modes || this._getAvailableModesFromCurrent();
        this._updateModeStates();
        this._drawLines();
    }

    /* ============================================================================================================== */
    resize() {
        // ResizeObserver handles this automatically now
        // This method kept for compatibility if called manually
        const rect = this.element.getBoundingClientRect();
        this._calculateResponsiveSizes(rect.width, rect.height);
        this._applyResponsiveSizes();
        requestAnimationFrame(() => this._drawLines());
    }

    /* ============================================================================================================== */
    destroy() {
        if (this._resizeObserver) {
            this._resizeObserver.disconnect();
            this._resizeObserver = null;
        }
        if (this._intersectionObserver) {
            this._intersectionObserver.disconnect();
            this._intersectionObserver = null;
        }
        if (this._redrawTimeout) {
            clearTimeout(this._redrawTimeout);
            this._redrawTimeout = null;
        }
    }

    /* ============================================================================================================== */
    getElement() {
        return this.element;
    }
}
