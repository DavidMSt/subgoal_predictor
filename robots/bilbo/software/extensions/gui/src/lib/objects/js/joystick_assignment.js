import {Widget} from "../objects.js";
import {getColor} from "../../helpers.js";

/**
 * JoystickAssignmentWidget - Visual widget for assigning joysticks to robots
 *
 * Shows joysticks on the left and robots on the right with draggable connection lines.
 */
export class JoystickAssignmentWidget extends Widget {
    constructor(id, data = {}) {
        super(id, data);

        const default_configuration = {
            // Data
            joysticks: [],  // [{id: 'joy1', name: 'Joystick 1', color: [r,g,b,a]}, ...]
            robots: [],     // [{id: 'robot1', name: 'Robot 1', color: [r,g,b,a]}, ...]
            connections: {},

            // Styling
            background_color: [0.15, 0.15, 0.18, 1],
            box_color: [0.25, 0.25, 0.28, 1],
            box_hover_color: [0.35, 0.35, 0.38, 1],
            line_color: [0.3, 0.7, 1.0, 1],
            line_width: 3,
            handle_color: [0.5, 0.5, 0.55, 1],
            handle_hover_color: [0.3, 0.7, 1.0, 1],
            handle_size: 18,
            text_color: [1, 1, 1, 0.9],
            id_font_size: 10,
            box_min_width: 50,
            box_max_width: 80,
            box_min_height: 50,
            box_max_height: 80,
            box_gap: 8,
            column_gap: 80,
            box_border_radius: 8,
            button_color: [0.3, 0.3, 0.35, 1],
            button_hover_color: [0.4, 0.4, 0.45, 1],
            button_text_color: [1, 1, 1, 0.9],
            button_font_size: 11,
            button_height: 32,
            button_gap: 10,

            // Images
            joystick_image: '/src/lib/assets/gamepad.png',
            robot_image: '/src/lib/assets/bilbo_icon.png',
            image_opacity: 0.7,
            image_min_size: 18,
            image_max_size: 40,
        };

        this.configuration = {...default_configuration, ...this.configuration};

        // Internal state
        this._joysticks = this.configuration.joysticks || [];
        this._robots = this.configuration.robots || [];
        this._connections = {...(this.configuration.connections || {})};

        // Drawing state
        this._isDragging = false;
        this._dragStartId = null;
        this._dragStartType = null;  // 'joystick' or 'robot'
        this._dragCurrentPos = null;
        this._joystickBoxes = new Map();  // joystick_id -> {element, handleEl}
        this._robotBoxes = new Map();     // robot_id -> {element, handleEl}

        // Create elements
        this.element = document.createElement('div');
        this.element.id = this.id;
        this.element.classList.add('widget', 'joystick-assignment-widget');

        this._buildStructure();
        this.configureElement(this.element);
        this.assignListeners(this.element);
    }

    /* ============================================================================================================== */
    _buildStructure() {
        // Scroll wrapper for the entire content area
        this._scrollWrapper = document.createElement('div');
        this._scrollWrapper.className = 'jaw-scroll-wrapper';
        this.element.appendChild(this._scrollWrapper);

        // Main container (inside scroll wrapper)
        this._mainContainer = document.createElement('div');
        this._mainContainer.className = 'jaw-main-container';
        this._scrollWrapper.appendChild(this._mainContainer);

        // Left column (joysticks)
        this._leftColumn = document.createElement('div');
        this._leftColumn.className = 'jaw-column jaw-left-column';
        this._mainContainer.appendChild(this._leftColumn);

        // SVG canvas for connection lines (positioned absolutely within main container)
        this._svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
        this._svg.classList.add('jaw-svg');
        this._svg.style.pointerEvents = 'none';
        this._mainContainer.appendChild(this._svg);

        // Right column (robots)
        this._rightColumn = document.createElement('div');
        this._rightColumn.className = 'jaw-column jaw-right-column';
        this._mainContainer.appendChild(this._rightColumn);

        // Button container
        this._buttonContainer = document.createElement('div');
        this._buttonContainer.className = 'jaw-button-container';
        this.element.appendChild(this._buttonContainer);

        // Clear All button
        this._clearButton = document.createElement('button');
        this._clearButton.className = 'jaw-button jaw-clear-button';
        this._clearButton.textContent = 'Clear All';
        this._buttonContainer.appendChild(this._clearButton);

        // Auto button
        this._autoButton = document.createElement('button');
        this._autoButton.className = 'jaw-button jaw-auto-button';
        this._autoButton.textContent = 'Auto';
        this._buttonContainer.appendChild(this._autoButton);

        // Listen for scroll to redraw connections
        this._scrollWrapper.addEventListener('scroll', () => this._drawConnections());
    }

    /* ============================================================================================================== */
    configureElement(element) {
        super.configureElement(element);

        const cfg = this.configuration;

        // Apply colors via CSS custom properties
        element.style.setProperty('--jaw-bg-color', getColor(cfg.background_color));
        element.style.setProperty('--jaw-box-color', getColor(cfg.box_color));
        element.style.setProperty('--jaw-box-hover-color', getColor(cfg.box_hover_color));
        element.style.setProperty('--jaw-line-color', getColor(cfg.line_color));
        element.style.setProperty('--jaw-line-width', `${cfg.line_width}px`);
        element.style.setProperty('--jaw-handle-color', getColor(cfg.handle_color));
        element.style.setProperty('--jaw-handle-hover-color', getColor(cfg.handle_hover_color));
        element.style.setProperty('--jaw-handle-size', `${cfg.handle_size}px`);
        element.style.setProperty('--jaw-text-color', getColor(cfg.text_color));
        element.style.setProperty('--jaw-id-font-size', `${cfg.id_font_size}pt`);
        element.style.setProperty('--jaw-box-min-width', `${cfg.box_min_width}px`);
        element.style.setProperty('--jaw-box-max-width', `${cfg.box_max_width}px`);
        element.style.setProperty('--jaw-box-min-height', `${cfg.box_min_height}px`);
        element.style.setProperty('--jaw-box-max-height', `${cfg.box_max_height}px`);
        element.style.setProperty('--jaw-box-gap', `${cfg.box_gap}px`);
        element.style.setProperty('--jaw-column-gap', `${cfg.column_gap}px`);
        element.style.setProperty('--jaw-box-border-radius', `${cfg.box_border_radius}px`);
        element.style.setProperty('--jaw-button-color', getColor(cfg.button_color));
        element.style.setProperty('--jaw-button-hover-color', getColor(cfg.button_hover_color));
        element.style.setProperty('--jaw-button-text-color', getColor(cfg.button_text_color));
        element.style.setProperty('--jaw-button-font-size', `${cfg.button_font_size}pt`);
        element.style.setProperty('--jaw-button-height', `${cfg.button_height}px`);
        element.style.setProperty('--jaw-button-gap', `${cfg.button_gap}px`);
        element.style.setProperty('--jaw-image-opacity', cfg.image_opacity);
        element.style.setProperty('--jaw-image-min-size', `${cfg.image_min_size}px`);
        element.style.setProperty('--jaw-image-max-size', `${cfg.image_max_size}px`);

        this._rebuildBoxes();
    }

    /* ============================================================================================================== */
    _rebuildBoxes() {
        // Clear existing
        this._leftColumn.innerHTML = '';
        this._rightColumn.innerHTML = '';
        this._joystickBoxes.clear();
        this._robotBoxes.clear();

        // Build joystick boxes
        for (const joystick of this._joysticks) {
            const box = this._createBox(joystick, 'joystick');
            this._leftColumn.appendChild(box.element);
            this._joystickBoxes.set(joystick.id, box);
        }

        // Build robot boxes
        for (const robot of this._robots) {
            const box = this._createBox(robot, 'robot');
            this._rightColumn.appendChild(box.element);
            this._robotBoxes.set(robot.id, box);
        }

        // Draw existing connections after a tick (to allow layout)
        requestAnimationFrame(() => this._drawConnections());
    }

    /* ============================================================================================================== */
    _createBox(item, type) {
        const cfg = this.configuration;
        const isJoystick = type === 'joystick';

        const element = document.createElement('div');
        element.className = `jaw-box jaw-${type}-box`;
        element.dataset.id = item.id;
        element.dataset.type = type;

        // Apply individual box color if provided (subtle background tint)
        if (item.color && Array.isArray(item.color) && item.color.length >= 3) {
            const [r, g, b, a = 0.25] = item.color;
            // Blend the custom color with the default box color at low opacity for subtle tint
            element.style.setProperty('--jaw-box-custom-color', `rgba(${Math.round(r * 255)}, ${Math.round(g * 255)}, ${Math.round(b * 255)}, ${a})`);
            element.classList.add('jaw-box-colored');
        }

        // ID label (centered at top)
        const idLabel = document.createElement('div');
        idLabel.className = 'jaw-box-id';
        idLabel.textContent = item.name || item.id;
        element.appendChild(idLabel);

        // Image
        const img = document.createElement('img');
        img.className = 'jaw-box-image';
        img.src = isJoystick ? cfg.joystick_image : cfg.robot_image;
        img.alt = item.name || item.id;
        img.draggable = false;
        element.appendChild(img);

        // Handle
        const handleEl = document.createElement('div');
        handleEl.className = `jaw-handle jaw-handle-${isJoystick ? 'right' : 'left'}`;
        handleEl.dataset.id = item.id;
        handleEl.dataset.type = type;
        element.appendChild(handleEl);

        // Double-click handler for box (only triggers callback, doesn't remove connection)
        element.addEventListener('dblclick', (e) => {
            if (e.target.classList.contains('jaw-handle')) return;
            this._handleBoxDoubleClick(item.id, type);
        });

        return {element, handleEl, id: item.id};
    }

    /* ============================================================================================================== */
    assignListeners(element) {
        super.assignListeners(element);

        // Handle dragging for connections
        element.addEventListener('mousedown', (e) => this._onMouseDown(e));
        element.addEventListener('mousemove', (e) => this._onMouseMove(e));
        element.addEventListener('mouseup', (e) => this._onMouseUp(e));
        element.addEventListener('mouseleave', (e) => this._onMouseUp(e));

        // Touch support
        element.addEventListener('touchstart', (e) => this._onTouchStart(e), {passive: false});
        element.addEventListener('touchmove', (e) => this._onTouchMove(e), {passive: false});
        element.addEventListener('touchend', (e) => this._onTouchEnd(e));

        // Button handlers
        this._clearButton.addEventListener('click', () => this._handleClearAll());
        this._autoButton.addEventListener('click', () => this._handleAutoAssign());
    }

    /* ============================================================================================================== */
    _onMouseDown(e) {
        const handle = e.target.closest('.jaw-handle');
        if (!handle) return;

        const type = handle.dataset.type;
        const id = handle.dataset.id;

        // Start dragging from either joystick or robot
        this._isDragging = true;
        this._dragStartId = id;
        this._dragStartType = type;
        this._dragCurrentPos = {x: e.clientX, y: e.clientY};
        this.element.classList.add('jaw-dragging');
        e.preventDefault();
    }

    /* ============================================================================================================== */
    _onMouseMove(e) {
        if (!this._isDragging) return;
        this._dragCurrentPos = {x: e.clientX, y: e.clientY};
        this._drawConnections();
    }

    /* ============================================================================================================== */
    _onMouseUp(e) {
        if (!this._isDragging) return;

        // Check if dropped on a valid target handle
        const handle = e.target.closest('.jaw-handle');
        if (handle) {
            const targetType = handle.dataset.type;
            const targetId = handle.dataset.id;

            // Only make connection if dragging between different types
            if (this._dragStartType === 'joystick' && targetType === 'robot') {
                this._makeConnection(this._dragStartId, targetId);
            } else if (this._dragStartType === 'robot' && targetType === 'joystick') {
                this._makeConnection(targetId, this._dragStartId);
            }
        }

        this._isDragging = false;
        this._dragStartId = null;
        this._dragStartType = null;
        this._dragCurrentPos = null;
        this.element.classList.remove('jaw-dragging');
        this._drawConnections();
    }

    /* ============================================================================================================== */
    _onTouchStart(e) {
        const touch = e.touches[0];
        const target = document.elementFromPoint(touch.clientX, touch.clientY);
        const handle = target?.closest('.jaw-handle');

        if (handle) {
            this._isDragging = true;
            this._dragStartId = handle.dataset.id;
            this._dragStartType = handle.dataset.type;
            this._dragCurrentPos = {x: touch.clientX, y: touch.clientY};
            this.element.classList.add('jaw-dragging');
            e.preventDefault();
        }
    }

    /* ============================================================================================================== */
    _onTouchMove(e) {
        if (!this._isDragging) return;
        const touch = e.touches[0];
        this._dragCurrentPos = {x: touch.clientX, y: touch.clientY};
        this._drawConnections();
        e.preventDefault();
    }

    /* ============================================================================================================== */
    _onTouchEnd(e) {
        if (!this._isDragging) return;

        const touch = e.changedTouches[0];
        const target = document.elementFromPoint(touch.clientX, touch.clientY);
        const handle = target?.closest('.jaw-handle');

        if (handle) {
            const targetType = handle.dataset.type;
            const targetId = handle.dataset.id;

            // Only make connection if dragging between different types
            if (this._dragStartType === 'joystick' && targetType === 'robot') {
                this._makeConnection(this._dragStartId, targetId);
            } else if (this._dragStartType === 'robot' && targetType === 'joystick') {
                this._makeConnection(targetId, this._dragStartId);
            }
        }

        this._isDragging = false;
        this._dragStartId = null;
        this._dragStartType = null;
        this._dragCurrentPos = null;
        this.element.classList.remove('jaw-dragging');
        this._drawConnections();
    }

    /* ============================================================================================================== */
    _makeConnection(joystickId, robotId) {
        // Check if this robot already has a connection (remove it first)
        for (const [jId, rId] of Object.entries(this._connections)) {
            if (rId === robotId && jId !== joystickId) {
                delete this._connections[jId];
                this.callbacks.get('event').call({
                    id: this.id,
                    event: 'connection_removed',
                    data: {joystick_id: jId, robot_id: rId}
                });
            }
        }

        // Make new connection
        this._connections[joystickId] = robotId;
        this.callbacks.get('event').call({
            id: this.id,
            event: 'connection_made',
            data: {joystick_id: joystickId, robot_id: robotId}
        });
        this._drawConnections();
    }

    /* ============================================================================================================== */
    _removeConnection(joystickId) {
        if (joystickId in this._connections) {
            const robotId = this._connections[joystickId];
            delete this._connections[joystickId];
            this.callbacks.get('event').call({
                id: this.id,
                event: 'connection_removed',
                data: {joystick_id: joystickId, robot_id: robotId}
            });
            this._drawConnections();
        }
    }

    /* ============================================================================================================== */
    _handleBoxDoubleClick(id, type) {
        // Double-click on boxes only triggers callbacks, doesn't affect connections
        // To remove connections, double-click on the connection line itself
        if (type === 'joystick') {
            this.callbacks.get('event').call({
                id: this.id,
                event: 'joystick_double_click',
                data: {joystick_id: id}
            });
        } else {
            this.callbacks.get('event').call({
                id: this.id,
                event: 'robot_double_click',
                data: {robot_id: id}
            });
        }
    }

    /* ============================================================================================================== */
    _handleClearAll() {
        this._connections = {};
        this.callbacks.get('event').call({
            id: this.id,
            event: 'clear_all',
            data: {}
        });
        this._drawConnections();
    }

    /* ============================================================================================================== */
    _handleAutoAssign() {
        // Auto-assign: pair joysticks to robots in order
        this._connections = {};
        const numPairs = Math.min(this._joysticks.length, this._robots.length);
        for (let i = 0; i < numPairs; i++) {
            this._connections[this._joysticks[i].id] = this._robots[i].id;
        }
        this.callbacks.get('event').call({
            id: this.id,
            event: 'auto_assign',
            data: {connections: {...this._connections}}
        });
        this._drawConnections();
    }

    /* ============================================================================================================== */
    _drawConnections() {
        // Clear SVG
        this._svg.innerHTML = '';

        // Size SVG to match main container
        const containerRect = this._mainContainer.getBoundingClientRect();
        this._svg.style.width = `${this._mainContainer.scrollWidth}px`;
        this._svg.style.height = `${this._mainContainer.scrollHeight}px`;

        const svgRect = this._svg.getBoundingClientRect();
        const cfg = this.configuration;

        // Draw existing connections
        for (const [joystickId, robotId] of Object.entries(this._connections)) {
            const joystickBox = this._joystickBoxes.get(joystickId);
            const robotBox = this._robotBoxes.get(robotId);

            if (joystickBox && robotBox) {
                const startPos = this._getHandleCenter(joystickBox.handleEl, svgRect);
                const endPos = this._getHandleCenter(robotBox.handleEl, svgRect);

                this._drawLine(startPos, endPos, false, joystickId);
            }
        }

        // Draw dragging line
        if (this._isDragging && this._dragStartId && this._dragCurrentPos) {
            let startBox;
            if (this._dragStartType === 'joystick') {
                startBox = this._joystickBoxes.get(this._dragStartId);
            } else {
                startBox = this._robotBoxes.get(this._dragStartId);
            }

            if (startBox) {
                const startPos = this._getHandleCenter(startBox.handleEl, svgRect);
                const endPos = {
                    x: this._dragCurrentPos.x - svgRect.left,
                    y: this._dragCurrentPos.y - svgRect.top
                };
                this._drawLine(startPos, endPos, true, null);
            }
        }
    }

    /* ============================================================================================================== */
    _getHandleCenter(handleEl, svgRect) {
        const rect = handleEl.getBoundingClientRect();
        return {
            x: rect.left + rect.width / 2 - svgRect.left,
            y: rect.top + rect.height / 2 - svgRect.top
        };
    }

    /* ============================================================================================================== */
    _drawLine(start, end, isDragging, joystickId = null) {
        const cfg = this.configuration;

        // Create a curved path (bezier)
        const dx = end.x - start.x;
        const controlOffset = Math.abs(dx) * 0.4;

        const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        const d = `M ${start.x} ${start.y} C ${start.x + controlOffset} ${start.y}, ${end.x - controlOffset} ${end.y}, ${end.x} ${end.y}`;
        path.setAttribute('d', d);
        path.setAttribute('stroke', getColor(cfg.line_color));
        path.setAttribute('stroke-width', cfg.line_width);
        path.setAttribute('fill', 'none');
        path.setAttribute('stroke-linecap', 'round');

        if (isDragging) {
            path.setAttribute('stroke-dasharray', '8 4');
            path.classList.add('jaw-line-dragging');
        } else {
            path.classList.add('jaw-line');
            // Add invisible wider stroke for easier clicking
            path.style.cursor = 'pointer';
            path.style.pointerEvents = 'stroke';

            // Store joystick ID for removal on double-click
            if (joystickId) {
                path.dataset.joystickId = joystickId;
                path.addEventListener('dblclick', (e) => {
                    e.stopPropagation();
                    this._removeConnection(joystickId);
                });
            }
        }

        this._svg.appendChild(path);

        // For established connections, add an invisible wider hitbox path for easier clicking
        if (!isDragging && joystickId) {
            const hitPath = document.createElementNS('http://www.w3.org/2000/svg', 'path');
            hitPath.setAttribute('d', d);
            hitPath.setAttribute('stroke', 'transparent');
            hitPath.setAttribute('stroke-width', Math.max(cfg.line_width * 4, 16));  // At least 16px wide hitbox
            hitPath.setAttribute('fill', 'none');
            hitPath.style.cursor = 'pointer';
            hitPath.style.pointerEvents = 'stroke';
            hitPath.dataset.joystickId = joystickId;
            hitPath.addEventListener('dblclick', (e) => {
                e.stopPropagation();
                this._removeConnection(joystickId);
            });
            this._svg.appendChild(hitPath);
        }
    }

    /* ============================================================================================================== */
    updateConfig(data) {
        this.configuration = {...this.configuration, ...data};

        if ('joysticks' in data) this._joysticks = data.joysticks || [];
        if ('robots' in data) this._robots = data.robots || [];
        if ('connections' in data) this._connections = {...(data.connections || {})};

        this.configureElement(this.element);
    }

    /* ============================================================================================================== */
    update(data) {
        // Handle updates (same as updateConfig for this widget)
        this.updateConfig(data);
    }

    /* ============================================================================================================== */
    updateState(data) {
        // Called from backend to update state
        if ('joysticks' in data) this._joysticks = data.joysticks || [];
        if ('robots' in data) this._robots = data.robots || [];
        if ('connections' in data) this._connections = {...(data.connections || {})};

        this._rebuildBoxes();
    }

    /* ============================================================================================================== */
    resize() {
        // Redraw connections when resized
        requestAnimationFrame(() => this._drawConnections());
    }

    /* ============================================================================================================== */
    getElement() {
        return this.element;
    }
}
