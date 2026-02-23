import {OBJECT_MAPPING} from './mapping.js';
import {Widget} from "./objects.js";
import {getColor, isObject, splitPath} from '../helpers.js';

/* ================================================================================================================== */
export class WidgetGroup extends Widget {
    /** @type {Object.<string, Widget>} */
    objects = {};

    /** @type {Set<string>} */
    _occupiedSet = new Set();

    /** @type {ResizeObserver|null} */
    _ro = null;

    /**
     * @param {string} id
     * @param {Object} [data={}]
     */
    constructor(id, data = {}) {
        super(id, data);

        // ── Defaults ─────────────────────────────────────────────────────────
        const defaults = {
            rows: 10,
            columns: 10,
            fit: true,
            non_fit_aspect_ratio: 1,
            show_scrollbar: true,
            scrollbar_handle_color: '#888',
            title: '',
            title_font_size: 10,
            title_color: '#fff',
            title_position: 'center',
            show_title: false,
            title_on_hover: false,
            tabs: false,
            background_color: 'transparent',
            border_color: '#444',
            border_width: 1,
            gap: 2,
            fill_empty: true,
            title_bottom_border: true,
        };

        this.configuration = {...defaults, ...this.configuration};
        this.objects = {};  // now just a lookup map of id → GUI_Object

        // ── Build container skeleton ─────────────────────────────────────────
        this.element = document.createElement('div');
        this.element.id = this.id;
        this.element.classList.add('gridItem', 'object-group');

        this.gridDiv = document.createElement('div');
        this.gridDiv.classList.add('object-group__grid');
        this.element.appendChild(this.gridDiv);

        // apply configuration & hook up listeners
        this.configureElement(this.element);
        this.assignListeners(this.element);
        this.update(this.data.objects || {});

        // ── ResizeObserver for square cells when fit=false ─────────────────
        this._ro = new ResizeObserver(entries => {
            for (let entry of entries) {
                if (!this.configuration.fit) {
                    const widthPx = entry.contentRect.width;
                    const cols = this.configuration.columns;
                    const gapPx = this.configuration.gap;
                    const totalGap = gapPx * (cols - 1);
                    const cellWidth = (widthPx - totalGap) / cols;
                    const ratio = this.configuration.non_fit_aspect_ratio || 1;
                    const cellHeight = cellWidth * ratio;

                    this.gridDiv.style.removeProperty('gridTemplateRows');
                    this.gridDiv.style.gridAutoRows = `${cellHeight}px`;
                }
            }
        });
        this._ro.observe(this.gridDiv);
    }

    /** Apply styling/layout based on this.configuration */
    configureElement(element) {
        super.configureElement(element);
        const {
            background_color,
            border_color,
            border_width,
            title,
            title_font_size,
            title_color,
            title_position,
            tabs,
            rows,
            columns,
            fit,
            fill_empty,
            show_scrollbar,
            scrollbar_handle_color
        } = this.configuration;

        // ── Container styling ────────────────────────────────────────────────
        Object.assign(this.element.style, {
            background: getColor(background_color),
            border: `${border_width}px solid ${getColor(border_color)}`,
            display: 'flex',
            flexDirection: 'column',
            boxSizing: 'border-box',
            width: '100%',
            height: '100%',
            overflow: 'hidden',
        });

        // ── Title bar ────────────────────────────────────────────────────────
        if (this.titleBar) this.titleBar.remove();
        if (this.configuration.show_title) {
            this.titleBar = document.createElement('div');
            this.titleBar.classList.add('object-group__titlebar');
            this.titleBar.textContent = title;
            Object.assign(this.titleBar.style, {
                fontSize: `${title_font_size}pt`, color: getColor(title_color), textAlign: title_position,
            });
            if (!this.configuration.title_bottom_border) {
                this.titleBar.style.borderBottom = 'none';
            }
            this.element.insertBefore(this.titleBar, this.gridDiv);
        }

        // ── Tabs bar ─────────────────────────────────────────────────────────
        if (this.tabsBar) this.tabsBar.remove();
        if (tabs) {
            this.tabsBar = document.createElement('div');
            this.tabsBar.classList.add('object-group__tabs');
            this.tabsBar.textContent = tabs === true ? 'Tabs' : tabs;
            this.element.insertBefore(this.tabsBar, this.gridDiv);
        }

        // ── Grid DIV styling ─────────────────────────────────────────────────
        this.gridDiv.dataset.fit = String(fit);
        Object.assign(this.gridDiv.style, {
            display: 'grid', width: '100%', gap: `${this.configuration.gap}px`, minHeight: '0',
        });

        // ── Layout & placeholders ────────────────────────────────────────────
        this._updateGridTemplate();
        this._recomputeOccupied();
        if (fill_empty) {
            this._fill_emptySlots();
        }
    }

    /** Internal: updates gridTemplate based on fit-mode */
    _updateGridTemplate() {
        const {rows, columns, fit, show_scrollbar} = this.configuration;
        this.gridDiv.style.gridTemplateColumns = `repeat(${columns}, 1fr)`;

        if (fit) {
            this.gridDiv.style.gridTemplateRows = `repeat(${rows}, 1fr)`;
            this.gridDiv.style.removeProperty('gridAutoRows');
            this.gridDiv.style.overflowY = 'hidden';
            this.gridDiv.style.removeProperty('alignContent');
        } else {
            this.gridDiv.style.removeProperty('gridTemplateRows');
            this.gridDiv.style.gridAutoRows = 'auto';
            this.gridDiv.style.overflowY = show_scrollbar ? 'scroll' : 'auto';
            this.gridDiv.style.alignContent = 'start';
            this.gridDiv.style.setProperty('--scrollbar-thumb-color', getColor(this.configuration.scrollbar_handle_color));
            if (show_scrollbar) {
                this.gridDiv.style.setProperty('scrollbar-gutter', 'stable');
                this.gridDiv.classList.add('show-scrollbar');
                this.gridDiv.classList.remove('hide-custom-scrollbar');
            } else {
                this.gridDiv.style.removeProperty('scrollbar-gutter');
                this.gridDiv.classList.remove('show-scrollbar');
                this.gridDiv.classList.add('hide-custom-scrollbar');
            }
        }
        this.gridDiv.style.flex = '1';
    }

    /** No-op default listeners */
    assignListeners(element) {
    }

    /**
     * @override
     * Implements splitPath → full-UID lookup → recurse logic just like Page.
     * @param {string} path
     * @returns {Widget|null}
     */
    getObjectByPath(path) {
        const [first, rest] = splitPath(path);
        if (!first) return null;

        const childKey = `${this.id}/${first}`;
        const child = this.objects[childKey];
        if (!child) {
            console.warn(`ObjectGroup ${this.id}: no child with ID "${childKey}"`);
            console.log(this.objects);
            return null;
        }

        if (rest && child instanceof WidgetGroup) {
            return child.getObjectByPath(rest);
        }
        return child;
    }

    /** Adds a child object into the grid */
    addObject(child, row, col, width, height) {
        if (!(child instanceof Widget)) {
            console.warn('ObjectGroup can only contain GUI_Object instances');
            return;
        }
        const key = child.id;
        if (this.objects[key]) {
            console.warn(`ObjectGroup ${this.id}: child with ID "${key}" already exists`);
            return;
        }

        // store only the child
        this.objects[key] = child;

        // render & append
        // const el = child.render([row, col], [width, height]);
        // this.gridDiv.appendChild(el);

        child.attach(this.gridDiv, [row, col], [width, height]);

        child.callbacks.get('event').register(this._onChildEvent.bind(this));


        this._recomputeOccupied();
        if (this.configuration.fill_empty) this._fill_emptySlots();
    }


    addObjectFromPayload(id, payload) {
        const WidgetClass = OBJECT_MAPPING[payload.type];
        if (!WidgetClass) {
            console.warn(`ObjectGroup ${this.id}: unknown type "${payload.type}"`);
            return;
        }
        const widget = new WidgetClass(id, payload);
        this.addObject(widget, payload.row, payload.column, payload.width, payload.height);
    }

    /** Removes a child */
    removeObject(childOrId) {
        const key = typeof childOrId === 'string' ? childOrId : childOrId.id;
        const child = this.objects[key];
        if (!child) return;

        // destroy & remove DOM
        child.destroy();
        if (child.container && child.container.parentNode) {
            child.container.parentNode.removeChild(child.container);
        }

        delete this.objects[key];
        this._recomputeOccupied();
        if (this.configuration.fill_empty) this._fill_emptySlots();
    }

    clear() {
        // Remove all objects
        for (const key in this.objects) {
            this.removeObject(key);
        }

    }

    _recomputeOccupied() {
        this._occupiedSet.clear();
        for (const child of Object.values(this.objects)) {
            const el = child.container;
            const row = parseInt(el.style.gridRowStart, 10);
            const col = parseInt(el.style.gridColumnStart, 10);
            const width = parseInt(el.style.gridColumnEnd.replace('span', ''), 10);
            const height = parseInt(el.style.gridRowEnd.replace('span', ''), 10);
            for (let r = row; r < row + height; r++) {
                for (let c = col; c < col + width; c++) {
                    this._occupiedSet.add(`${r},${c}`);
                }
            }
        }
    }

    getEmptySpot(width = 1, height = 1) {
        const {rows, columns} = this.configuration;
        for (let row = 1; row <= rows - height + 1; row++) {
            for (let col = 1; col <= columns - width + 1; col++) {
                let fits = true;
                for (let dy = 0; dy < height && fits; dy++) {
                    for (let dx = 0; dx < width; dx++) {
                        if (this._occupiedSet.has(`${row + dy},${col + dx}`)) {
                            fits = false;
                            break;
                        }
                    }
                }
                if (fits) return [row, col];
            }
        }
        return null;
    }

    _fill_emptySlots() {
        Array.from(this.gridDiv.getElementsByClassName('group-placeholder'))
            .filter(el => el.parentNode === this.gridDiv)
            .forEach(el => el.remove());

        const {rows, columns} = this.configuration;
        for (let r = 0; r < rows; r++) {
            for (let c = 0; c < columns; c++) {
                const key = `${r + 1},${c + 1}`;
                if (!this._occupiedSet.has(key)) {
                    const ph = document.createElement('div');
                    ph.classList.add('group-placeholder');
                    ph.style.gridRowStart = `${r + 1}`;
                    ph.style.gridColumnStart = `${c + 1}`;
                    ph.style.zIndex = '10';
                    this.gridDiv.appendChild(ph);
                }
            }
        }
    }

    _onChildEvent(payload) {
        this.callbacks.get('event').call({groupId: this.id, ...payload});
    }

    /** @override */
    getElement() {
        return this.element;
    }

    /** @override */
    updateConfig(data) {
        this.configuration = {...this.configuration, ...data};
        this.configureElement(this.configuration);
    }

    /**
     * Handle a single “add” from backend
     * @param {Object} data
     */
    handleAdd(data) {
        const cfg = data.config;
        if (!cfg) return;
        const {id, type, row, column, width, height} = cfg;
        const WidgetClass = OBJECT_MAPPING[type];
        if (!WidgetClass) {
            console.warn(`ObjectGroup ${this.id}: unknown type "${type}"`);
            return;
        }

        const widget = new WidgetClass(id, cfg);
        this.addObject(widget, row, column, width, height);
    }

    /**
     * Handle a single “remove” from backend
     * @param {Object} data
     */
    handleRemove(data) {
        const object_id = data.id;
        if (!object_id) return;
        this.removeObject(object_id);
    }

    /**
     * Full‐layout refresh: wipe out old and rebuild all children
     * @param {Object<string, Object>} data
     */
    update(data) {
        // 1) destroy any existing
        Object.values(this.objects).forEach(child => child.destroy());
        this.objects = {};
        this._occupiedSet.clear();
        this.gridDiv.innerHTML = '';

        // 2) rebuild
        for (const payload of Object.values(data)) {
            const {row, column, width, height, id, type, config: widgetConfig} = payload;
            const WidgetClass = OBJECT_MAPPING[type];
            if (!WidgetClass) {
                console.warn(`ObjectGroup ${this.id}: unknown type "${type}" in update`);
                continue;
            }
            const widget = new WidgetClass(id, payload);
            this.addObject(widget, row, column, width, height);
        }

        this._recomputeOccupied();
        if (this.configuration.fill_empty) this._fill_emptySlots();
    }

    initializeElement() {
    }

    resize() {
    }
}

/* ================================================================================================================== */
export class PagedGroupsWidget extends Widget {
    /** @type {Object.<string, WidgetGroup>} */
    groups = {};
    active_group = null;

    /* -------------------------------------------------------------------------------------------------------------- */
    constructor(id, data = {}) {
        super(id, data);

        const default_config = {
            'show_group_bar': true,
            'group_bar_style': 'buttons',  // 'buttons', 'icons', 'dots'
            'button_style': 'fit',  // 'fit' or 'stretch'
        }

        this.configuration = {...default_config, ...this.configuration};

        this.element = this.initializeElement()
        this.configureElement(this.element);
        this.assignListeners(this.element);

        // Build the groups
        this._buildGroups(this.data.groups || {});
        // Build the group bar & show the first visible group
        this.buildGroupBar();

        if (this.data.start_group) {
            this.showGroup(this.data.start_group);
        } else {
            const first = this._getFirstVisibleGroup();
            if (first) this.showGroup(first);
        }
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    initializeElement() {

        const element = document.createElement('div');
        element.id = this.id;
        element.classList.add('gridItem', 'widget', 'groupContainer');


        if (this.configuration.group_bar_position === 'bottom') {
            element.dataset.groupBarPosition = 'bottom';
        } else if (this.configuration.group_bar_position === 'top') {
            element.dataset.groupBarPosition = 'top';
        } else {
            element.dataset.groupBarPosition = 'top';
        }

        element.dataset.showGroupBar = this.configuration.show_group_bar;

        this.group_bar = document.createElement('div');
        this.group_bar.className = 'titlebar';
        element.appendChild(this.group_bar);

        this.group_bar.dataset.groupBarStyle = this.configuration.group_bar_style;

        this.group_container = document.createElement('div');
        this.group_container.className = 'content';
        element.appendChild(this.group_container);

        return element;
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    buildGroupBar() {
        // reset bar
        while (this.group_bar.firstChild) this.group_bar.removeChild(this.group_bar.firstChild);

        const style = (this.configuration.group_bar_style || 'buttons').toLowerCase();
        this.group_bar.dataset.groupBarStyle = style;

        // "dots" style intentionally does nothing (as requested)
        if (style === 'dots') return;

        const visibleGroups = this._getVisibleGroups();
        if (!visibleGroups.length) return;

        // container (keeps our layout tidy even if the bar element already has styles)
        const bar = document.createElement('div');
        bar.className = 'gwp-bar';
        bar.dataset.buttonStyle = (this.configuration.button_style || 'fit').toLowerCase();

        // build entries
        for (const group of visibleGroups) {
            const id = group.id; // full UID already set in addGroupFromPayload
            const label = this._getGroupLabel(group);
            const iconText = this._getGroupIcon(group, label);

            let el;
            if (style === 'buttons') {
                el = document.createElement('button');
                el.className = 'gwp-tab gwp-tab--button';
                el.type = 'button';
                el.textContent = label;
                el.title = label;
            } else if (style === 'icons') {
                el = document.createElement('button');
                el.className = 'gwp-tab gwp-tab--icon';
                el.type = 'button';
                el.title = label;
                const span = document.createElement('span');
                span.className = 'gwp-tab__icon';
                span.textContent = iconText;
                el.appendChild(span);
            } else {
                // unknown style: bail out gracefully
                continue;
            }

            el.dataset.groupId = id;
            el.setAttribute('role', 'tab');
            el.setAttribute('aria-selected', 'false');

            // stretch vs. fit
            if ((this.configuration.button_style || 'fit').toLowerCase() === 'stretch') {
                el.classList.add('is-stretch');
            }

            el.addEventListener('click', () => {
                const group = this.groups[id];
                if (group) this.showGroup(group);
            });

            bar.appendChild(el);
        }

        this.group_bar.appendChild(bar);

        // reflect current active group in UI
        const active = this.active_group && !this._isHidden(this.active_group)
            ? this.active_group
            : this._getFirstVisibleGroup();
        if (active) this._setActiveTabUI(active.id);

        this._wireOverflow(bar); // <-- add this
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    resize() {

    }

    /* -------------------------------------------------------------------------------------------------------------- */
    update(data) {
        return undefined;
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    updateConfig(data) {
        return undefined;
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    showGroup(group) {
        // if string id passed, resolve to group
        if (typeof group === 'string') {
            const found = this.groups[group];
            if (!found) return;
            group = found;
        }

        // Make all groups invisible
        for (const [, group_obj] of Object.entries(this.groups)) {
            if (group_obj?.container) {
                group_obj.container.style.display = 'none';
                group_obj.container.dataset.active = 'false';
            }
        }

        // Show the selected group
        if (group?.container) {
            group.container.style.display = 'block';
            group.container.dataset.active = 'true';
        }

        this.active_group = group;

        // sync group bar UI
        this._setActiveTabUI(group.id);
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    addGroup(group) {
        // Check if this group is already in the list
        if (this.groups[group.id]) {
            console.warn(`GroupWithPages ${this.id}: group with ID "${group.id}" already exists`);
            return;
        }

        // Add the group to the list
        this.groups[group.id] = group;

        group.on('event', this.onEvent.bind(this));
        group.callbacks.get('event').register(this.onEvent.bind(this));

        group.attach(this.group_container);
        group.container.dataset.active = 'false';
        group.container.style.display = 'none';

        // refresh the bar & auto-select a page if none active
        this.buildGroupBar();
        if (!this.active_group) {
            const first = this._getFirstVisibleGroup();
            if (first) this.showGroup(first);
        }
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    addGroupFromPayload(id, payload) {
        const group = new WidgetGroup(id, payload);
        this.addGroup(group);
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    removeGroup(group) {
        // Check if group is of type string
        if (typeof group === 'string') {
            const group_id = group;
            if (!this.groups[group_id]) {
                console.warn(`GroupWithPages ${this.id}: no group with ID "${group_id}"`);
                return;
            }
            group = this.groups[group_id];
        }

        if (group?.container?.parentNode === this.group_container) {
            this.group_container.removeChild(group.container);
        }
        group.destroy?.();
        delete this.groups[group.id];

        const wasActive = this.active_group && this.active_group.id === group.id;
        this.active_group = wasActive ? null : this.active_group;

        // Rebuild bar and select first visible if needed
        this.buildGroupBar();
        if (!this.active_group) {
            const first = this._getFirstVisibleGroup();
            if (first) this.showGroup(first);
        }

        this._overflowCleanup?.();
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    getObjectByPath(path) {
        const [first, rest] = splitPath(path);
        if (!first) return null;

        const childKey = `${this.id}/${first}`;
        const child = this.groups[childKey];
        if (!child) {
            console.warn(`ObjectGroup ${this.id}: no child with ID "${childKey}"`);
            console.log(this.groups);
            return null;
        }

        if (rest && child instanceof WidgetGroup) {
            return child.getObjectByPath(rest);
        }
        return child;
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    handleAdd(message) {
        console.warn(`GroupWithPages ${this.id}: handleAddMessage not yet implemented: ${message}`);
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    handleRemove(message) {
        console.warn(`GroupWithPages ${this.id}: handleRemoveMessage not yet implemented: ${message}`);
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    _buildGroups(groups) {

        for (const [group_id, group_payload] of Object.entries(groups)) {
            const group_uid = group_payload.id;
            this.addGroupFromPayload(group_uid, group_payload);
        }
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    hideGroupBar() {
        this.element.dataset.showGroupBar = false;
        this.configuration.show_group_bar = false;
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    showGroupBar() {
        this.element.dataset.showGroupBar = true;
        this.configuration.show_group_bar = true;
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    onEvent(event) {
        this.callbacks.get('event').call(event);
    }

    /* === PRIVATE METHODS ========================================================================================== */
    _isHidden(group) {
        // Respect "hidden = true" only if the config actually has the property
        const cfg = group?.configuration || {};
        return Object.prototype.hasOwnProperty.call(cfg, 'hidden') ? !!cfg.hidden : false;
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    _getVisibleGroups() {
        return Object.values(this.groups).filter(g => !this._isHidden(g));
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    _getFirstVisibleGroup() {
        const arr = this._getVisibleGroups();
        return arr.length ? arr[0] : null;
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    _getGroupLabel(group) {
        // prefer config.title or config.name; fallback to last segment of id
        const cfg = group?.configuration || {};
        const label = (cfg.title ?? cfg.name ?? group?.id ?? '').toString();
        if (label) return label;
        const parts = (group?.id || '').split('/');
        return parts[parts.length - 1] || 'Group';
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    _getGroupIcon(group, fallbackLabel = '') {
        const cfg = group?.configuration || {};
        if (Object.prototype.hasOwnProperty.call(cfg, 'icon') && cfg.icon != null && cfg.icon !== '')
            return String(cfg.icon);
        if (Object.prototype.hasOwnProperty.call(cfg, 'position') && cfg.position != null && cfg.position !== '')
            return String(cfg.position);
        const label = fallbackLabel || this._getGroupLabel(group);
        return label.trim().charAt(0) || '•';
    }

    // /* -------------------------------------------------------------------------------------------------------------- */
    // _setActiveTabUI(activeId) {
    //     const tabs = this.group_bar.querySelectorAll('.gwp-tab');
    //     tabs.forEach(tab => {
    //         const isActive = tab.dataset.groupId === activeId;
    //         tab.classList.toggle('is-active', isActive);
    //         tab.setAttribute('aria-selected', isActive ? 'true' : 'false');
    //         tab.tabIndex = isActive ? 0 : -1;
    //     });
    // }

    /* -------------------------------------------------------------------------------------------------------------- */

    _wireOverflow(bar) {
        // 1) Wrap the bar to host fades and the … button
        const wrap = document.createElement('div');
        wrap.className = 'gwp-bar-wrap';
        bar.parentNode.replaceChild(wrap, bar);
        wrap.appendChild(bar);

        // 2) Overflow button
        const moreBtn = document.createElement('button');
        moreBtn.type = 'button';
        moreBtn.className = 'gwp-overflow-btn';
        moreBtn.setAttribute('aria-haspopup', 'menu');
        moreBtn.setAttribute('aria-expanded', 'false');
        moreBtn.title = 'More';
        moreBtn.textContent = '…';
        wrap.appendChild(moreBtn);

        // 3) Menu element (we’ll portal it to <body>)
        const menu = document.createElement('div');
        menu.className = 'gwp-overflow-menu';
        menu.setAttribute('role', 'menu');
        menu.hidden = true;
        this._overflowMenu = menu;

        // 4) Portal container (create once per instance)
        if (!this._overflowPortal) {
            const portal = document.createElement('div');
            portal.className = 'gwp-overflow-portal';
            document.body.appendChild(portal);
            this._overflowPortal = portal;
        }
        const portal = this._overflowPortal;

        // 5) Keep a canonical list of tabs (DOM nodes are stable across reflows)
        const allTabs = Array.from(bar.querySelectorAll('.gwp-tab'));

        // 6) Layout / relayout
        const relayout = () => {
            this._applyOverflowLayout({wrap, bar, moreBtn, menu, allTabs});

            // update button label with hidden count (nice hint)
            const hiddenCount = menu.childElementCount;
            moreBtn.textContent = hiddenCount ? `… ${hiddenCount}` : '…';

            // if menu is open, keep it positioned under the button
            if (!menu.hidden) positionMenu();
        };
        this._applyOverflowLayout({wrap, bar, moreBtn, menu, allTabs});

        // 7) Observe size changes
        this._ro?.disconnect();
        this._ro = new ResizeObserver(relayout);
        this._ro.observe(wrap);

        // 8) Helpers
        const positionMenu = () => {
            // ensure menu is in the portal (so it isn’t clipped)
            if (menu.parentNode !== portal) portal.appendChild(menu);

            // place it under the button; clamp to viewport
            menu.style.position = 'fixed';
            menu.style.zIndex = '9999';

            const rect = moreBtn.getBoundingClientRect();
            const vw = window.innerWidth;
            const vh = window.innerHeight;

            // If width/height are zero (hidden), estimate — styles will take over after paint
            const menuW = menu.offsetWidth || 200;
            const menuH = menu.offsetHeight || 16;

            const left = Math.min(vw - menuW - 8, Math.max(8, rect.right - menuW));
            const top = Math.min(vh - menuH - 8, rect.bottom + 6);

            menu.style.left = `${left}px`;
            menu.style.top = `${top}px`;
        };

        const openMenu = () => {
            menu.hidden = false;
            moreBtn.setAttribute('aria-expanded', 'true');
            positionMenu();
            // focus first item if any
            const first = menu.querySelector('[role="menuitem"]');
            first?.focus();
        };

        const closeMenu = () => {
            if (menu.hidden) return;
            menu.hidden = true;
            moreBtn.setAttribute('aria-expanded', 'false');
        };

        // 9) Toggle on button
        moreBtn.addEventListener('click', () => {
            if (menu.hidden) openMenu();
            else closeMenu();
        });

        // 10) Close on outside click (allow clicks inside wrap OR inside menu)
        const onDocClick = (e) => {
            if (!wrap.contains(e.target) && !menu.contains(e.target)) {
                closeMenu();
            }
        };

        // 11) Close on Escape
        const onKey = (e) => {
            if (e.key === 'Escape') {
                closeMenu();
                moreBtn.focus();
            }
        };

        document.addEventListener('click', onDocClick);
        document.addEventListener('keydown', onKey);

        // 12) Cleanup hook for rebuilds
        this._overflowCleanup = () => {
            document.removeEventListener('click', onDocClick);
            document.removeEventListener('keydown', onKey);
            this._ro?.disconnect();
        };

        // 13) Make sure the container isn't scrolled
        this.group_bar.scrollLeft = 0;

        // Reposition menu on scroll/resize (rare but nice)
        window.addEventListener('resize', positionMenu, {passive: true});
    }

    /* -------------------------------------------------------------------------------------------------------------- */

    /* -------------------------------------------------------------------------------------------------------------- */
    _applyOverflowLayout({wrap, bar, moreBtn, menu, allTabs}) {
        // Reset state
        menu.innerHTML = '';
        moreBtn.style.display = 'none';
        allTabs.forEach(tab => {
            tab.style.display = '';
        });

        const wrapW = wrap.clientWidth;
        const gap = 3;                  // visual gap between tabs
        const btnReserve = 34;          // rough space for the "…" button when needed
        const activeId = this.active_group?.id || null;

        let used = 0;
        const visible = [];
        const overflow = [];

        // First pass: assume no overflow button, reserve if we start overflowing
        for (const tab of allTabs) {
            tab.style.display = ''; // ensure measurable
            const w = tab.offsetWidth;
            const needBtn = overflow.length > 0;
            const limit = wrapW - (needBtn ? btnReserve : 0);

            if (used + w <= limit) {
                used += w + gap;
                visible.push(tab);
            } else {
                overflow.push(tab);
            }
        }

        // If we overflow, recompute with the real button width visible
        if (overflow.length) {
            // show button so we can measure it
            moreBtn.style.display = '';
            // reset and recompute which tabs fit with button present
            allTabs.forEach(t => {
                t.style.display = '';
            });
            used = 0;

            for (const t of allTabs) {
                const w = t.offsetWidth;
                const limit = wrapW - moreBtn.offsetWidth; // exact button width
                if (used + w + gap <= limit) {
                    used += w + gap;
                    t.style.display = '';
                } else {
                    t.style.display = 'none';
                }
            }

            // Build the overflow menu for hidden tabs
            for (const t of allTabs) {
                if (t.style.display === 'none') {
                    const gid = t.dataset.groupId;
                    const item = document.createElement('button');
                    item.setAttribute('role', 'menuitem');
                    item.className = 'gwp-overflow-item';
                    item.type = 'button';
                    item.textContent = t.title || t.textContent || 'Tab';
                    item.dataset.groupId = gid;

                    // ✅ Mark active on build
                    const isActive = !!activeId && gid === activeId;
                    if (isActive) {
                        item.classList.add('is-active');
                        item.setAttribute('aria-current', 'page');
                    }

                    item.addEventListener('click', () => {
                        const group = this.groups[gid];
                        if (group) this.showGroup(group);
                        menu.hidden = true;
                        moreBtn.setAttribute('aria-expanded', 'false');
                    });

                    menu.appendChild(item);
                }
            }

            // Update button label with hidden count (nice hint)
            const hiddenCount = menu.childElementCount;
            moreBtn.textContent = hiddenCount ? `… ${hiddenCount}` : '…';
        } else {
            // No overflow -> simple label
            moreBtn.textContent = '…';
        }

        // Edge fades: indicate when there is content clipped on the right
        const totalTabsWidth = allTabs.reduce((acc, t) => acc + (t.offsetWidth || 0) + gap, 0);
        wrap.dataset.overflowLeft = 'false';
        wrap.dataset.overflowRight = String(totalTabsWidth > wrap.clientWidth);
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    _setActiveTabUI(activeId) {
        // update visible tabs
        const tabs = this.group_bar.querySelectorAll('.gwp-tab');
        tabs.forEach(tab => {
            const isActive = tab.dataset.groupId === activeId;
            tab.classList.toggle('is-active', isActive);
            tab.setAttribute('aria-selected', isActive ? 'true' : 'false');
            tab.tabIndex = isActive ? 0 : -1;
        });

        // update overflow menu items (portaled)
        const menu = this._overflowMenu;
        if (menu) {
            menu.querySelectorAll('.gwp-overflow-item').forEach(b => {
                const isActive = b.dataset.groupId === activeId;
                b.classList.toggle('is-active', isActive);
                if (isActive) b.setAttribute('aria-current', 'page');
                else b.removeAttribute('aria-current');
            });
        }
    }
}