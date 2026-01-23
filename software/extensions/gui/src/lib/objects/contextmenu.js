import {Callbacks, getColor} from "../helpers.js";
import {activeGUI} from "../globals.js"


const SUBMENU_GRACE_DELAY = 300; // milliseconds

/** Utility: get ordered array of item-configs (supports object or array input) */
function normalizeItemConfigs(items, isRoot = false) {
    if (!items) return [];
    if (Array.isArray(items)) return items.slice();
    // object map: keep insertion order via Object.values
    const list = Object.values(items);
    // root uses cfg.id; groups commonly use cfg.item_id
    // we keep as-is; reconciliation reads both keys.
    return list;
}

/** Utility: tiny equality for group-vs-item classification */
function isCfgGroup(cfg) {
    return !!(cfg?.config?.type === "group" || cfg?.items);
}

/** Utility: read id from cfg (root: id; group children: item_id) */
function cfgId(cfg) {
    return cfg?.id ?? cfg?.item_id;
}

/** Utility: ensure a node is appended before a reference (or appended at end) */
function insertBeforeOrAppend(container, node, beforeNode) {
    if (!container || !node) return;
    if (beforeNode && beforeNode.parentNode === container) {
        container.insertBefore(node, beforeNode);
    } else {
        container.appendChild(node);
    }
}

/** ─── ContextMenuItem ───────────────────────────────────────────────────── */
export class ContextMenuItem {
    constructor(id, config = {}) {
        this.id = id;
        const default_config = {
            name: "",
            front_icon: "",
            back_icon: "",
            text_color: [1, 1, 1, 0.8],
            background_color: [0, 0, 0, 0],
            font_weight: "normal",
            border: false,
            border_color: [0.5, 0.5, 0.5],
            hover_background_color: [1, 1, 1, 0.1],
        };
        this.config = {...default_config, ...config};
        this.parent = null;
        this.callbacks = new Callbacks();
        this.callbacks.add("click");

        this.initializeElement();
        this.configureElement();
        this.addListeners();
    }

    initializeElement() {
        this.element = document.createElement("div");
        this.element.classList.add("context-menu__item");
    }

    configureElement() {
        this.element.style.backgroundColor = getColor(this.config.background_color);
        this.element.style.color = getColor(this.config.text_color);
        this.element.style.fontWeight = this.config.font_weight;
        if (this.config.border) {
            this.element.style.borderBottom = `1px solid ${getColor(
                this.config.border_color
            )}`;
        } else {
            this.element.style.borderBottom = "none";
        }
        this.element.innerHTML = "";
        if (this.config.front_icon) {
            const ico = document.createElement("span");
            ico.classList.add("context-menu__item-icon", "left");
            ico.innerHTML = this.config.front_icon;
            this.element.appendChild(ico);
        }
        const txt = document.createElement("span");
        txt.classList.add("context-menu__item-text");
        txt.innerText = this.config.name || this.id;
        this.element.appendChild(txt);
        if (this.config.back_icon) {
            const ico2 = document.createElement("span");
            ico2.classList.add("context-menu__item-icon", "right");
            ico2.innerHTML = this.config.back_icon;
            this.element.appendChild(ico2);
        }
    }

    addListeners() {
        this.element.addEventListener("click", (ev) => {
            ev.stopPropagation();
            this.callbacks.get("click").call(this, 'click');
            const menu = this.getContextMenu();
            if (menu) menu.hide();
        });
        this.element.addEventListener("mouseenter", () => {
            this.element.classList.add("cmh");
        });
        this.element.addEventListener("mouseleave", () => {
            this.element.classList.remove("cmh");
        });
    }

    /** New: update item config in place */
    update(config = {}) {
        this.config = {...this.config, ...config};
        this.configureElement();
    }

    getContextMenu() {
        if (this.parent && typeof this.parent.show === "function") return this.parent;
        if (this.parent && typeof this.parent.getContextMenu === "function")
            return this.parent.getContextMenu();
        return null;
    }
}

/** ─── ContextMenuGroup ──────────────────────────────────────────────────── */
export class ContextMenuGroup {
    constructor(id, config = {}, items = {}) {
        this.id = id;
        const default_config = {
            type: "inline",            // "inline" or "submenu"
            name: "",
            background_color: "inherit",
            text_color: [1, 1, 1, 0.8],
            show_inline_title: true,
            inline_border_top: false,
            inline_border_bottom: false,
            border_color: [0.5, 0.5, 0.5],
            open_on_hover: true,
        };
        this.config = {...default_config, ...config};
        if (!this.config.name) this.config.name = this.id;

        this.items = {};
        this.parent = null;
        this.callbacks = new Callbacks();
        this.callbacks.add("click");
        this.callbacks.add("event");

        this.callbacks.add("enter");
        this.callbacks.add("leave");
        this.callbacks.add("open");
        this.callbacks.add("close");
        this.callbacks.add("trigger_enter");
        this.callbacks.add("trigger_leave");

        this._closeTimeout = null;

        this.triggerEl = null;
        this._inlineWrapEl = null; // persistent wrapper for inline groups
        this._triggerEl = null;    // which node opened this submenu

        this.initializeElement();
        this.configureElement();
        this.buildItemsFromConfig(items);
    }

    initializeElement() {
        this.element = document.createElement("div");
        this.element.classList.add("context-menu", "context-menu--submenu");
        Object.assign(this.element.style, {
            position: "absolute",
            display: "none",
        });

        if (this.config.type === "submenu") {
            this._ensureTriggerEl();
        }

        document.body.appendChild(this.element);
    }

    /** ensure submenu trigger exists (used on init and when switching to submenu) */
    _ensureTriggerEl() {
        if (this.triggerEl) return;

        this.triggerEl = document.createElement("div");
        this.triggerEl.classList.add(
            "context-menu__item",
            "context-menu__item--submenu-trigger"
        );
        const txt = document.createElement("span");
        txt.classList.add("context-menu__item-text");
        txt.innerText = this.config.name;
        const arrow = document.createElement("span");
        arrow.classList.add("context-menu__item-icon", "right");
        arrow.innerText = "▶";
        this.triggerEl.append(txt, arrow);

        this.triggerEl.addEventListener("mouseenter", () => {
            clearTimeout(this._closeTimeout);
            this.open(this.triggerEl);
            this.callbacks.get("trigger_enter").call(this);
        });

        this.triggerEl.addEventListener("mouseleave", ev => {
            this._closeTimeout = setTimeout(() => {
                    this.close()
                }
                , SUBMENU_GRACE_DELAY / 4);
            this.callbacks.get("trigger_leave").call(this);
        });

        this.element.addEventListener("mouseenter", () => {
            clearTimeout(this._closeTimeout);
            this.callbacks.get("enter").call(this);
        });

        this.element.addEventListener("mouseleave", ev => {
            this._closeTimeout = setTimeout(() => {
                this.close()
            }, SUBMENU_GRACE_DELAY);
            this.callbacks.get("leave").call(this);
        });
    }

    /** ensure inline wrapper exists inside the currently rendered parent container */
    _ensureInlineWrap(parentContainer) {
        if (this._inlineWrapEl && this._inlineWrapEl.parentNode) return this._inlineWrapEl;

        const wrap = document.createElement("div");
        wrap.classList.add("context-menu__inline-group");
        wrap.style.borderTop = this.config.inline_border_top
            ? `1px solid ${getColor(this.config.border_color)}`
            : "none";
        wrap.style.borderBottom = this.config.inline_border_bottom
            ? `1px solid ${getColor(this.config.border_color)}`
            : "none";

        // Title
        if (this.config.show_inline_title && this.config.name) {
            const ttl = document.createElement("div");
            ttl.classList.add("context-menu__group-title");
            ttl.innerText = this.config.name;
            ttl.style.borderBottom = `1px solid ${getColor(
                this.config.border_color
            )}`;
            wrap.appendChild(ttl);
        }

        parentContainer && parentContainer.appendChild(wrap);
        this._inlineWrapEl = wrap;
        return wrap;
    }

    configureElement() {
        this.element.style.backgroundColor = getColor(
            this.config.background_color
        );
        this.element.style.color = getColor(this.config.text_color);

        // Also style existing trigger/wrap if present
        if (this.triggerEl) {
            // update title text if exists
            const txt = this.triggerEl.querySelector(".context-menu__item-text");
            if (txt) txt.innerText = this.config.name;
        }
        if (this._inlineWrapEl) {
            this._inlineWrapEl.style.borderTop = this.config.inline_border_top
                ? `1px solid ${getColor(this.config.border_color)}`
                : "none";
            this._inlineWrapEl.style.borderBottom = this.config.inline_border_bottom
                ? `1px solid ${getColor(this.config.border_color)}`
                : "none";
            // update title if present (first child with class)
            const ttl = this._inlineWrapEl.querySelector(".context-menu__group-title");
            if (ttl) {
                ttl.innerText = this.config.name;
                ttl.style.borderBottom = `1px solid ${getColor(this.config.border_color)}`;
            } else if (this.config.show_inline_title && this.config.name) {
                const title = document.createElement("div");
                title.classList.add("context-menu__group-title");
                title.innerText = this.config.name;
                title.style.borderBottom = `1px solid ${getColor(this.config.border_color)}`;
                this._inlineWrapEl.prepend(title);
            }
        }
    }

    buildItemsFromConfig(items) {
        for (const cfg of normalizeItemConfigs(items)) {
            this.buildItemFromConfig(cfg);
        }
    }

    buildItemFromConfig(cfg) {
        if (!cfgId(cfg)) {
            console.warn(`ContextMenuGroup ${this.id}: missing id`);
            return;
        }
        const isGroup = isCfgGroup(cfg);
        if (isGroup) {
            const sub = new ContextMenuGroup(cfgId(cfg), cfg.config, cfg.items);
            this.addItem(sub);
        } else {
            const it = new ContextMenuItem(cfgId(cfg), cfg.config);
            this.addItem(it);
        }
    }

    addItem(item) {
        if (this.items[item.id]) {
            console.warn(`Group ${this.id}: duplicate item ${item.id}`);
            return;
        }
        this.items[item.id] = item;
        item.parent = this;
        item.callbacks.get("click").register(this.onItemClick.bind(this));

        // wire submenu hover timing if child is submenu
        if (item instanceof ContextMenuGroup) {
            if (item.config.type === "submenu") {
                item.callbacks.get("enter").register(() => {
                    this.exitCloseTimer();
                });
                if (this.config.type === "submenu") {
                    item.callbacks.get("leave").register(() => {
                        this.startCloseTimer();
                    })
                }
            }
        }

        // If we are currently rendered, insert DOM node immediately at end (ordering is reconciled later)
        const container = this._childrenContainerEl();
        if (container) {
            const mount = this._nodeForChild(item, /*createIfMissing*/true);
            if (mount) container.appendChild(mount);
        }
    }

    removeItem(id) {
        const child = this.items[id];
        if (!child) return;

        // Close submenus & remove DOM nodes
        if (child instanceof ContextMenuGroup) {
            child.close();
            // remove submenu panel
            if (child.element && child.element.parentNode) {
                child.element.parentNode.removeChild(child.element);
            }
            // remove trigger or inline wrapper
            const node = child.config.type === "submenu" ? child.triggerEl : child._inlineWrapEl;
            if (node && node.parentNode) node.parentNode.removeChild(node);
        } else {
            if (child.element && child.element.parentNode) {
                child.element.parentNode.removeChild(child.element);
            }
        }

        delete this.items[id];
    }

    onItemClick(item, event) {
        this.callbacks.get("click").call(item, event);
    }

    renderItems(container) {
        for (const child of Object.values(this.items)) {
            if (child instanceof ContextMenuItem) {
                container.appendChild(child.element);
            } else if (child instanceof ContextMenuGroup) {
                if (child.config.type === "inline") {
                    const wrap = document.createElement("div");
                    child._inlineWrapEl = wrap; // persist
                    wrap.classList.add("context-menu__inline-group");
                    wrap.style.borderTop = child.config.inline_border_top
                        ? `1px solid ${getColor(child.config.border_color)}`
                        : "none";
                    wrap.style.borderBottom = child.config.inline_border_bottom
                        ? `1px solid ${getColor(child.config.border_color)}`
                        : "none";
                    if (child.config.show_inline_title && child.config.name) {
                        const ttl = document.createElement("div");
                        ttl.classList.add("context-menu__group-title");
                        ttl.innerText = child.config.name;
                        ttl.style.borderBottom = `1px solid ${getColor(
                            child.config.border_color
                        )}`;
                        wrap.appendChild(ttl);
                    }
                    child.renderItems(wrap);
                    container.appendChild(wrap);
                } else {
                    child._ensureTriggerEl();
                    container.appendChild(child.triggerEl);
                }
            }
        }
    }

    /** get the element currently displaying this group's children (if any) */
    _childrenContainerEl() {
        if (this.config.type === "submenu") {
            // children show inside submenu panel only when open
            if (this.element && this.element.style.display !== "none") return this.element;
            return null;
        } else {
            // inline groups render into their inline wrapper, which exists if our parent is rendered
            return this._inlineWrapEl || null;
        }
    }

    /** get the parent container where *this group* is mounted as a child */
    _parentContainerEl() {
        if (!this.parent) return null;
        if (this.parent instanceof ContextMenu) {
            // mounted directly inside root menu container
            if (this.parent.element && this.parent.element.style.display !== "none") {
                return this.parent.element;
            }
            return null;
        } else if (this.parent instanceof ContextMenuGroup) {
            // mounted inside parent's children container
            return this.parent._childrenContainerEl();
        }
        return null;
    }

    /** resolve DOM node representing a direct child of this group */
    _nodeForChild(child, createIfMissing = false) {
        if (child instanceof ContextMenuItem) {
            if (createIfMissing && !child.element) child.initializeElement();
            return child.element;
        } else if (child instanceof ContextMenuGroup) {
            if (child.config.type === "submenu") {
                if (createIfMissing) child._ensureTriggerEl();
                return child.triggerEl;
            } else {
                if (createIfMissing) {
                    const container = this._childrenContainerEl() || this._parentContainerEl();
                    child._ensureInlineWrap(container || document.createDocumentFragment());
                }
                return child._inlineWrapEl;
            }
        }
        return null;
    }

    /** reconcile order of DOM nodes to match ordered ids */
    _reorderChildrenDOM(orderedIds) {
        const container = this._childrenContainerEl();
        if (!container) return; // not currently rendered/open—skip

        // Build a map from id -> mount node
        const idToNode = new Map();
        for (const id of Object.keys(this.items)) {
            const ch = this.items[id];
            const node = this._nodeForChild(ch, /*create*/true);
            if (node) idToNode.set(id, node);
        }

        // insert in correct order
        let reference = null;
        for (let idx = orderedIds.length - 1; idx >= 0; idx--) {
            const id = orderedIds[idx];
            const node = idToNode.get(id);
            if (!node) continue;
            insertBeforeOrAppend(container, node, reference);
            reference = node;
        }
    }

    /** New: update this group's config and children in place */
    update(config = {}, items = {}) {
        // handle type change (inline <-> submenu)
        const prevType = this.config.type;
        this.config = {...this.config, ...config};
        if (!this.config.name) this.config.name = this.id;

        // If type changed, swap mounting node
        if (prevType !== this.config.type) {
            if (prevType === "submenu" && this.triggerEl) {
                // we were a submenu, now inline: remove trigger; keep panel closed
                this.close();
                if (this.triggerEl.parentNode) this.triggerEl.parentNode.removeChild(this.triggerEl);
                this.triggerEl = null;
                // create inline wrapper in parent container if currently rendered
                const parentContainer = this._parentContainerEl();
                if (parentContainer) {
                    this._ensureInlineWrap(parentContainer);
                }
            } else if (prevType === "inline") {
                // we were inline, now submenu: remove wrapper, create trigger
                if (this._inlineWrapEl && this._inlineWrapEl.parentNode) {
                    this._inlineWrapEl.parentNode.removeChild(this._inlineWrapEl);
                }
                this._inlineWrapEl = null;
                this._ensureTriggerEl();
                const parentContainer = this._parentContainerEl();
                if (parentContainer && this.triggerEl && !this.triggerEl.parentNode) {
                    parentContainer.appendChild(this.triggerEl);
                }
            }
        }

        // apply style/text updates on existing nodes
        this.configureElement();

        // Reconcile children
        const newList = normalizeItemConfigs(items);
        const newIds = newList.map(cfg => cfgId(cfg));
        const newIdSet = new Set(newIds);

        // Remove missing children
        for (const id of Object.keys(this.items)) {
            if (!newIdSet.has(id)) {
                this.removeItem(id);
            }
        }

        // Insert / Update / Replace & preserve order
        for (let i = 0; i < newList.length; i++) {
            const cfg = newList[i];
            const id = cfgId(cfg);
            const wantGroup = isCfgGroup(cfg);
            const existing = this.items[id];

            if (!existing) {
                // create new child
                const created = wantGroup
                    ? new ContextMenuGroup(id, cfg.config, cfg.items)
                    : new ContextMenuItem(id, cfg.config);
                this.addItem(created);

                // Insert at correct position in parent container if rendered
                const container = this._childrenContainerEl();
                if (container) {
                    const beforeId = newList[i + 1] ? cfgId(newList[i + 1]) : null;
                    const beforeNode = beforeId && this.items[beforeId]
                        ? this._nodeForChild(this.items[beforeId], /*create*/true)
                        : null;
                    const node = this._nodeForChild(created, /*create*/true);
                    insertBeforeOrAppend(container, node, beforeNode);
                }
            } else {
                // type change? replace node
                const isExistingGroup = existing instanceof ContextMenuGroup;
                if (Boolean(isExistingGroup) !== Boolean(wantGroup)) {
                    // remove old
                    this.removeItem(id);
                    // create new fresh node
                    const created = wantGroup
                        ? new ContextMenuGroup(id, cfg.config, cfg.items)
                        : new ContextMenuItem(id, cfg.config);
                    this.addItem(created);

                    // place in order
                    const container = this._childrenContainerEl();
                    if (container) {
                        const beforeId = newList[i + 1] ? cfgId(newList[i + 1]) : null;
                        const beforeNode = beforeId && this.items[beforeId]
                            ? this._nodeForChild(this.items[beforeId], /*create*/true)
                            : null;
                        const node = this._nodeForChild(created, /*create*/true);
                        insertBeforeOrAppend(container, node, beforeNode);
                    }
                } else {
                    // update in place
                    if (isExistingGroup) {
                        existing.update(cfg.config || {}, cfg.items || {});
                    } else {
                        existing.update(cfg.config || {});
                    }
                }
            }
        }

        // reorder DOM nodes to match new order
        this._reorderChildrenDOM(newIds);

        // Hide empty inline groups visually (but do not remove)
        if (this.config.type === "inline" && this._inlineWrapEl) {
            const hasChildren = Object.keys(this.items).length > 0;
            this._inlineWrapEl.style.display = hasChildren ? "" : "none";
        }
    }

    open(triggerEl) {
        // remember which trigger opened us
        clearTimeout(this._closeTimeout);

        this._triggerEl = triggerEl;

        // clear old contents & build menu
        this.element.innerHTML = "";
        if (Object.keys(this.items).length === 0) return;
        if (this.config.show_inline_title && this.config.name) {
            const head = document.createElement("div");
            head.classList.add("context-menu__group-title");
            head.innerText = this.config.name;
            head.style.borderBottom = `1px solid ${getColor(this.config.border_color)}`;
            this.element.appendChild(head);
        }
        this.renderItems(this.element);

        // position & show
        this.element.style.display = "block";
        this.element.style.visibility = "hidden";
        const W = this.element.offsetWidth, H = this.element.offsetHeight;
        const tr = triggerEl.getBoundingClientRect();
        let left = tr.right + 4, top = tr.top;
        if (left + W > window.innerWidth) left = tr.left - W - 4;
        if (top + H > window.innerHeight) top = window.innerHeight - H - 4;
        Object.assign(this.element.style, {
            left: `${left}px`,
            top: `${top}px`,
            visibility: "visible",
        });

        // add highlight‐class to the trigger
        triggerEl.classList.add("cmh");
    }

    close() {
        // remove highlight from trigger
        if (this._triggerEl) {
            this._triggerEl.classList.remove("cmh");
            this._triggerEl = null;
        }
        clearTimeout(this._closeTimeout);

        // recursively close any open child submenus
        for (const child of Object.values(this.items)) {
            if (child instanceof ContextMenuGroup) child.close();
        }
        this.element.style.display = "none";
    }

    exitCloseTimer() {
        clearTimeout(this._closeTimeout);
    }

    startCloseTimer() {
        this._closeTimeout = setTimeout(() => {
            this.close();
        }, SUBMENU_GRACE_DELAY);
    }

    getContextMenu() {
        if (this.parent && typeof this.parent.show === "function") return this.parent;
        if (
            this.parent &&
            typeof this.parent.getContextMenu === "function"
        )
            return this.parent.getContextMenu();
        return null;
    }
}

/** ─── ContextMenu (root) ───────────────────────────────────────────────── */
export class ContextMenu {
    constructor(id, object, config = {}, items = {}) {
        this.id = id;
        this.object = object;
        const default_config = {
            background_color: [0.1, 0.1, 0.1, 0.9],
            text_color: [1, 1, 1, 0.8],
        };
        this.config = {...default_config, ...config};
        this.items = {};
        this.callbacks = new Callbacks();
        this.callbacks.add("event");
        this.callbacks.add("click");

        this.initializeElement();
        this.configureElement();
        this.addListeners();
        this.buildItemsFromConfig(items);
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    initializeElement() {
        this.element = document.createElement("div");
        this.element.classList.add("context-menu");
        Object.assign(this.element.style, {
            position: "absolute",
            display: "none",
        });
        document.body.appendChild(this.element);
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    configureElement() {
        this.element.style.backgroundColor = getColor(
            this.config.background_color
        );
        this.element.style.color = getColor(this.config.text_color);
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    addListeners() {
        document.addEventListener("click", (ev) => {
            if (!this.element.contains(ev.target)) this.hide();
        });
        document.addEventListener("contextmenu", () => this.hide());
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    buildItemsFromConfig(items) {
        for (const cfg of normalizeItemConfigs(items, true)) {
            this.buildItemFromConfig(cfg);
        }
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    buildItemFromConfig(cfg) {
        if (!cfg?.item_id) {
            console.warn(`ContextMenu ${this.id}: missing id`);
            console.warn(cfg);
            return;
        }
        const isGroup = isCfgGroup(cfg);
        if (isGroup) {
            const grp = new ContextMenuGroup(cfg.item_id, cfg.config, cfg.items);
            this.addItem(grp);
        } else {
            const it = new ContextMenuItem(cfg.item_id, cfg.config);
            this.addItem(it);
        }
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    addItem(item) {
        if (this.items[item.id]) {
            console.warn(`ContextMenu ${this.id}: dup item ${item.id}`);
            return;
        }
        this.items[item.id] = item;
        item.parent = this;
        item.callbacks.get("click").register(this.onItemClick.bind(this));

        // If menu is open, mount the node now
        if (this.isOpen()) {
            const node = this._nodeForChild(item, /*create*/true);
            if (node) this.element.appendChild(node);
        }
    }

    removeItem(id) {
        const ch = this.items[id];
        if (!ch) return;

        if (this.items[id]?.protected) return;

        if (ch instanceof ContextMenuGroup) {
            // If this group was open anywhere, close & remove
            ch.close();
            if (ch.element && ch.element.parentNode) {
                ch.element.parentNode.removeChild(ch.element);
            }
            const trigger = ch.config.type === "submenu" ? ch.triggerEl : ch._inlineWrapEl;
            if (trigger && trigger.parentNode) trigger.parentNode.removeChild(trigger);
        } else {
            if (ch.element && ch.element.parentNode) {
                ch.element.parentNode.removeChild(ch.element);
            }
        }
        delete this.items[id];
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    onItemClick(item, event) {
        this.callbacks.get("click").call(item, event);
        this.hide();
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    renderItems(container) {
        for (const child of Object.values(this.items)) {
            if (child instanceof ContextMenuItem) {
                container.appendChild(child.element);
            } else if (child instanceof ContextMenuGroup) {
                if (child.config.type === "inline") {
                    const wrap = document.createElement("div");
                    child._inlineWrapEl = wrap; // persist for in-place updates
                    wrap.classList.add("context-menu__inline-group");
                    wrap.style.borderTop = child.config.inline_border_top
                        ? `1px solid ${getColor(child.config.border_color)}`
                        : "none";
                    wrap.style.borderBottom = child.config.inline_border_bottom
                        ? `1px solid ${getColor(child.config.border_color)}`
                        : "none";

                    // Hide empty inline groups
                    if (Object.keys(child.items).length === 0) {
                        wrap.style.display = "none";
                    }

                    if (child.config.show_inline_title && child.config.name) {
                        const ttl = document.createElement("div");
                        ttl.classList.add("context-menu__group-title");
                        ttl.innerText = child.config.name;
                        ttl.style.borderBottom = `1px solid ${getColor(
                            child.config.border_color
                        )}`;
                        wrap.appendChild(ttl);
                    }
                    child.renderItems(wrap);
                    container.appendChild(wrap);
                } else {
                    child._ensureTriggerEl();
                    const trigger = child.triggerEl;
                    if (child.config.open_on_hover) {
                        // listeners are already set in _ensureTriggerEl
                    } else {
                        trigger.addEventListener("click", () =>
                            child.open(trigger)
                        );
                    }
                    container.appendChild(trigger);
                }
            }
        }
    }

    _nodeForChild(child, createIfMissing = false) {
        if (child instanceof ContextMenuItem) {
            if (createIfMissing && !child.element) child.initializeElement();
            return child.element;
        } else if (child instanceof ContextMenuGroup) {
            if (child.config.type === "submenu") {
                if (createIfMissing) child._ensureTriggerEl();
                return child.triggerEl;
            } else {
                if (createIfMissing) child._ensureInlineWrap(this.element);
                return child._inlineWrapEl;
            }
        }
        return null;
    }

    _reorderChildrenDOM(orderedIds) {
        if (!this.isOpen()) return;
        const container = this.element;
        const idToNode = new Map();
        for (const id of Object.keys(this.items)) {
            const ch = this.items[id];
            const node = this._nodeForChild(ch, /*create*/true);
            if (node) idToNode.set(id, node);
        }
        let ref = null;
        for (let i = orderedIds.length - 1; i >= 0; i--) {
            const id = orderedIds[i];
            const node = idToNode.get(id);
            if (!node) continue;
            insertBeforeOrAppend(container, node, ref);
            ref = node;
        }
    }

    /** New: public update API (patch in place, recursive) */
    update(config = {}, items = {}) {
        // Update config & styles without toggling visibility
        this.config = {...this.config, ...config};
        this.configureElement();


        const newList = normalizeItemConfigs(items, true);
        const newIds = newList.map(cfg => cfg.id);
        const newIdSet = new Set(newIds);

        // Remove missing
        for (const id of Object.keys(this.items)) {
            if (!newIdSet.has(id)) {
                this.removeItem(id);
            }
        }

        // Insert / Update / Replace
        for (let i = 0; i < newList.length; i++) {
            const cfg = newList[i];
            const id = cfg.id;
            const wantGroup = isCfgGroup(cfg);
            const existing = this.items[id];

            if (!existing) {
                const created = wantGroup
                    ? new ContextMenuGroup(id, cfg.config, cfg.items)
                    : new ContextMenuItem(id, cfg.config);
                this.addItem(created);

                if (this.isOpen()) {
                    const beforeId = newList[i + 1]?.id;
                    const beforeNode = beforeId && this.items[beforeId]
                        ? this._nodeForChild(this.items[beforeId], /*create*/true)
                        : null;
                    const node = this._nodeForChild(created, /*create*/true);
                    insertBeforeOrAppend(this.element, node, beforeNode);
                }
            } else {
                const isExistingGroup = existing instanceof ContextMenuGroup;
                if (Boolean(isExistingGroup) !== Boolean(wantGroup)) {
                    // Replace node
                    this.removeItem(id);
                    const created = wantGroup
                        ? new ContextMenuGroup(id, cfg.config, cfg.items)
                        : new ContextMenuItem(id, cfg.config);
                    this.addItem(created);

                    if (this.isOpen()) {
                        const beforeId = newList[i + 1]?.id;
                        const beforeNode = beforeId && this.items[beforeId]
                            ? this._nodeForChild(this.items[beforeId], /*create*/true)
                            : null;
                        const node = this._nodeForChild(created, /*create*/true);
                        insertBeforeOrAppend(this.element, node, beforeNode);
                    }
                } else {
                    if (isExistingGroup) {
                        existing.update(cfg.config || {}, cfg.items || {});
                    } else {
                        existing.update(cfg.config || {});
                    }
                }
            }
        }
        //
        if (this.isOpen()) {
            if (Object.keys(this.items).length === 0) {
                this.hide();
            }
        }
        // Reorder
        this._reorderChildrenDOM(newIds);
    }

    isOpen() {
        return this.element && this.element.style.display !== "none";
    }

    show({x, y}) {
        this.hide();
        if (Object.keys(this.items).length === 0) {
            return;
        }
        // if (this.element.children.length === 0) return;
        this.element.innerHTML = "";
        this.renderItems(this.element);
        this.element.style.display = "block";
        this.element.style.visibility = "hidden";

        if (this.element.offsetHeight === 0) {
            this.element.style.display = "none";
            return;
        }

        const W = this.element.offsetWidth,
            H = this.element.offsetHeight;
        let left = x,
            top = y;
        if (left + W > window.innerWidth) left = window.innerWidth - W - 4;
        if (top + H > window.innerHeight) top = window.innerHeight - H - 4;
        Object.assign(this.element.style, {
            left: `${left}px`,
            top: `${top}px`,
            visibility: "visible",
        });
        this.object.element.classList.add("context-menu-active");
    }

    hide() {
        this.element.style.display = "none";
        for (const ch of Object.values(this.items)) {
            if (ch instanceof ContextMenuGroup) ch.close();
        }
        this.object.element.classList.remove("context-menu-active");
    }
}