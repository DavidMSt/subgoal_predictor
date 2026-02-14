import {WidgetGroup} from './objects/group.js';
import {Callbacks, getColor, splitPath} from './helpers.js';


export class Popup {
    // ── Static dock singleton (lives in left sidebar below favorites) ───
    static _dockEl = null;
    static _dockListEl = null;
    static _dockEntries = new Map(); // popupId → { popup, entryEl }

    static _getDock() {
        if (!Popup._dockEl) {
            const dock = document.createElement('div');
            dock.classList.add('popup-dock');

            // Collapsed label row (always visible when dock exists)
            const label = document.createElement('div');
            label.classList.add('popup-dock-label');
            label.innerHTML = '<span class="popup-dock-label-icon">▫</span> Minimized';
            dock.appendChild(label);

            // Expandable list (shown on hover)
            const list = document.createElement('div');
            list.classList.add('popup-dock-list');
            dock.appendChild(list);
            Popup._dockListEl = list;

            // Attach to sidebar below favorites, or fallback to body
            const sidebar = document.getElementById('category_bar');
            if (sidebar) {
                sidebar.appendChild(dock);
            } else {
                document.body.appendChild(dock);
            }
            Popup._dockEl = dock;
        }
        return Popup._dockEl;
    }

    static _removeDockEntry(id) {
        const entry = Popup._dockEntries.get(id);
        if (entry) {
            entry.entryEl.remove();
            Popup._dockEntries.delete(id);
        }
        if (Popup._dockEl && Popup._dockEntries.size === 0) {
            Popup._dockEl.remove();
            Popup._dockEl = null;
            Popup._dockListEl = null;
        } else {
            Popup._updateDockLabel();
        }
    }

    constructor(id, config = {}, payload = {}) {
        this.id = id;

        const defaultConfig = {
            type: 'window',      // 'window' or 'dialog' or 'tab'
            title: 'Popup',
            background_color: [0.2, 0.2, 0.2],
            text_color: [1, 1, 1],
            size: [800, 400],
            resizable: true,
            closeable: true,     // only applies to dialog
            minimizable: true,   // show minimize button (dialog only)
            disable_gui: true,   // disable GUI as long as popup is open (only for dialog)
            opacity: 1.0,        // global popup opacity (0.0 – 1.0)
            title_font_size: 10, // pt
        };

        // Merge without adopting undefined
        const safeConfig = {
            ...defaultConfig,
            ...Object.fromEntries(
                Object.entries(config).filter(([, v]) => v !== undefined)
            ),
        };

        this.config = safeConfig;
        this._title = (typeof this.config.title === 'string' && this.config.title.trim())
            ? this.config.title.trim()
            : defaultConfig.title;

        this.groupWidget = this.createGroupWidget(payload);

        this._win = null;
        this._poll = null;
        this._dialogEl = null;
        this._overlayEl = null;     // for dialog popups
        this._shellBlobUrl = null;  // keep to revoke later
        this._messageHandler = null;
        this._isClosed = false;     // prevents repeated closed events
        this._attached = false;     // ensure we attach only once
        this._posConverted = false; // CSS-centered → absolute px
        this._isMinimized = false;
        this._savedRect = null;     // { left, top, width, height }

        this.callbacks = new Callbacks();
        this.callbacks.add('event');
        this.callbacks.add('closed');
    }

    createGroupWidget(payload) {
        const {id} = payload;
        const groupWidget = new WidgetGroup(id, payload);
        groupWidget.callbacks.get('event').register((ev) => {
            this.callbacks.get('event').call({popupId: this.id, ...ev});
        });
        return groupWidget;
    }

    _getShellURL() {
        try {
            return new URL('./popup-shell.html', import.meta.url).href;
        } catch {
            return null;
        }
    }

    _buildShellHTML() {
        const popupCssURL = new URL('./styles/popup.css', import.meta.url).href;
        const objectsCssURL = new URL('./styles/objects.css', import.meta.url).href;
        const stylesCssURL = new URL('./styles/styles.css', import.meta.url).href;
        const widgetStylesURL = new URL('./styles/widget-styles.css', import.meta.url).href;
        const terminalStylesURL = new URL('./cli_terminal/cli_terminal.css', import.meta.url).href;
        const lineplotStylesURL = new URL('./plot/lineplot/lineplot.css', import.meta.url).href;

        // Ensure we always write a non-empty title
        const safeTitle = this._title;

        return `<!DOCTYPE html>
<html style="height:100%" lang="en">
<head>
  <meta charset="utf-8">
  <title>${safeTitle.replace(/</g, '&lt;').replace(/>/g, '&gt;')}</title>
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <link rel="stylesheet" href="${popupCssURL}">
  <link rel="stylesheet" href="${objectsCssURL}">
  <link rel="stylesheet" href="${stylesCssURL}">
  <link rel="stylesheet" href="${widgetStylesURL}">
  <link rel="stylesheet" href="${terminalStylesURL}">
  <link rel="stylesheet" href="${lineplotStylesURL}"></link>
  <script>
    // Re-apply title when DOM is ready, and notify the opener.
    document.addEventListener('DOMContentLoaded', function () {
      document.title = ${JSON.stringify(safeTitle)};
      try { window.opener && window.opener.postMessage({ type: 'popup-shell-ready' }, '*'); } catch {}
    });
  </script>
  <style>html, body { height:100%; margin:0; }</style>
</head>
<body>
  <div id="popup-root" style="height:100%; display:flex; flex-direction:column;"></div>
</body>
</html>`;
    }

    _openRealShell(target, features = '') {
        const shellURL = this._getShellURL();
        if (!shellURL) return null;

        // Add non-empty, encoded title param
        const url = new URL(shellURL);
        url.searchParams.set('t', this._title);

        try {
            const w = window.open(url.href, target, features || undefined);
            if (!w || w.closed) return null;
            return w;
        } catch (e) {
            console.warn('Popup: failed to open real shell URL.', e);
            return null;
        }
    }

    _openWithBlobURL(target, features = '') {
        return;
        try {
            const html = this._buildShellHTML();
            const blob = new Blob([html], {type: 'text/html'});
            this._shellBlobUrl = URL.createObjectURL(blob);
            const w = window.open(this._shellBlobUrl, target, features || undefined);
            if (!w || w.closed) return null;
            return w;
        } catch (e) {
            console.warn('Popup: failed to create/open Blob URL shell.', e);
            return null;
        }
    }

    _installMessageBridge() {
        if (this._messageHandler) return; // only once
        this._messageHandler = (ev) => {
            if (ev && ev.data && ev.data.type === 'popup-shell-ready') {
                this._attachIntoChildWindow();
            }
            if (ev && ev.data && ev.data.type === 'popup-set-title') {
                try {
                    if (this._win && this._win.document) this._win.document.title = String(ev.data.title || this._title);
                } catch {
                }
            }
        };
        window.addEventListener('message', this._messageHandler);
    }

    _removeMessageBridge() {
        if (this._messageHandler) {
            window.removeEventListener('message', this._messageHandler);
            this._messageHandler = null;
        }
    }

    async _attachIntoChildWindow() {
        if (!this._win || this._attached) return; // attach only once
        this._attached = true;

        // Apply title one more time (in case the shell didn't).
        try {
            this._win.document.title = this._title;
        } catch {
        }

        // Wait until #popup-root exists (the shell page has loaded)
        const root = await this._waitForElement(() => {
            try {
                return this._win && this._win.document && this._win.document.getElementById('popup-root');
            } catch {
                return null;
            }
        }, 4000);

        if (!root) {
            // As a last resort, write the shell directly (same-origin)
            try {
                const doc = this._win.document;
                doc.open();
                doc.write(this._buildShellHTML());
                doc.close();
            } catch (e) {
                console.warn('Popup: fallback document.write failed.', e);
            }
        }

        // Attach UI
        try {
            const doc = this._win.document;
            if (doc && doc.body) {
                doc.body.style.backgroundColor = getColor(this.config.background_color);
            }
            const mount = doc.getElementById('popup-root');
            if (mount) this._attachGroup(mount);
        } catch (e) {
            console.warn('Popup: failed to attach group into child window.', e);
        }

        // Install a single poller to watch for manual close
        if (!this._poll) {
            this._poll = setInterval(() => {
                // In some browsers, accessing .closed after navigation can throw
                try {
                    if (!this._win || this._win.closed) {
                        clearInterval(this._poll);
                        this._poll = null;
                        this.close_manually();
                    }
                } catch {
                    clearInterval(this._poll);
                    this._poll = null;
                    this.close_manually();
                }
            }, 500);
        }
    }

    _waitForElement(getterFn, timeoutMs = 3000) {
        return new Promise((resolve) => {
            const start = Date.now();
            const tick = () => {
                const el = getterFn();
                if (el) return resolve(el);
                if (Date.now() - start > timeoutMs) return resolve(null);
                setTimeout(tick, 50);
            };
            tick();
        });
    }

    _openDialogFallback() {
        if (this._dialogEl) return;

        this._dialogEl = document.createElement('div');
        this._dialogEl.id = this.id;
        this._dialogEl.classList.add('popup', 'popup-dialog');

        // Make the dialog the correct size and apply opacity
        const [width, height] = this.config.size;
        this._dialogEl.style.width = `${width}px`;
        this._dialogEl.style.height = `${height}px`;
        if (this.config.opacity < 1) {
            this._dialogEl.style.opacity = `${this.config.opacity}`;
        }

        // title bar
        const titleBar = document.createElement('div');
        titleBar.classList.add('popup-titlebar');
        titleBar.style.fontSize = `${this.config.title_font_size}pt`;
        titleBar.style.paddingTop = '3px';
        titleBar.style.paddingBottom = '3px';
        titleBar.style.paddingLeft = '10px';
        this._dialogEl.appendChild(titleBar);

        const titleText = document.createElement('span');
        titleText.textContent = this._title;
        titleBar.appendChild(titleText);

        // right-side button group
        const btnGroup = document.createElement('span');
        btnGroup.classList.add('popup-titlebar-buttons');

        // minimize button (only if minimizable)
        if (this.config.minimizable) {
            const minimizeBtn = document.createElement('button');
            minimizeBtn.classList.add('popup-minimize-btn');
            minimizeBtn.textContent = '▁';
            minimizeBtn.title = 'Minimize to dock';
            minimizeBtn.addEventListener('click', () => this.minimize());
            btnGroup.appendChild(minimizeBtn);
        }

        // "pop out" button — opens in a separate browser window from a real click (user gesture)
        const popOutBtn = document.createElement('button');
        popOutBtn.classList.add('popup-popout-btn');
        popOutBtn.textContent = '⧉';
        popOutBtn.title = 'Open in separate window';
        popOutBtn.addEventListener('click', () => this._popOutFromDialog());
        btnGroup.appendChild(popOutBtn);

        if (this.config.closeable) {
            const btn = document.createElement('button');
            btn.classList.add('popup-close-btn');
            btn.textContent = '×';
            btn.addEventListener('click', () => this.close_manually());
            btnGroup.appendChild(btn);
        }

        titleBar.appendChild(btnGroup);

        // content area
        const content = document.createElement('div');
        content.classList.add('popup-content');
        this._dialogEl.appendChild(content);

        // resize handle
        if (this.config.resizable) {
            const handle = document.createElement('div');
            handle.classList.add('popup-resize-handle');
            this._dialogEl.appendChild(handle);
            this._installResizeDrag(handle);
        }

        document.body.appendChild(this._dialogEl);

        this._attachGroup(content);
        this._installTitleBarDrag(titleBar);
    }

    /** Retry window.open() from a real user click (bypasses popup blocker). */
    _popOutFromDialog() {
        const [width, height] = this.config.size;
        const screenX = window.screenX !== undefined ? window.screenX : window.screen.left;
        const screenY = window.screenY !== undefined ? window.screenY : window.screen.top;
        const availWidth = window.innerWidth || screen.width;
        const availHeight = window.innerHeight || screen.height;
        const left = Math.round(screenX + (availWidth - width) / 2);
        const top = Math.round(screenY + (availHeight - height) / 2);
        const features = `width=${width},height=${height},left=${left},top=${top},resizable=yes`;

        this._installMessageBridge();
        this._attached = false;
        this._win = this._openRealShell(this.id, features);

        if (!this._win || this._win.closed) {
            console.warn('Pop-out still blocked by browser.');
            return;
        }

        // Success — tear down the in-page dialog and use the real window
        if (this._dialogEl) {
            this._dialogEl.remove();
            this._dialogEl = null;
        }
        this._hideOverlay();
        this._attachIntoChildWindow();
    }

    /** Switch from CSS-centered (transform + top/left 50%) to absolute px positioning. */
    _ensureAbsolutePos() {
        if (!this._posConverted && this._dialogEl) {
            this._posConverted = true;
            const rect = this._dialogEl.getBoundingClientRect();
            this._dialogEl.style.left = `${rect.left}px`;
            this._dialogEl.style.top = `${rect.top}px`;
            this._dialogEl.style.transform = 'none';
        }
    }

    /** Make the dialog draggable by its title bar. */
    _installTitleBarDrag(titleBar) {
        const el = this._dialogEl;
        let dragging = false, startX, startY, origX, origY;

        titleBar.addEventListener('mousedown', (e) => {
            if (e.target.closest('button')) return; // don't drag from buttons
            dragging = true;
            this._ensureAbsolutePos();
            startX = e.clientX;
            startY = e.clientY;
            origX = parseInt(el.style.left, 10);
            origY = parseInt(el.style.top, 10);
            e.preventDefault();
        });

        window.addEventListener('mousemove', (e) => {
            if (!dragging) return;
            el.style.left = `${origX + e.clientX - startX}px`;
            el.style.top = `${origY + e.clientY - startY}px`;
        });

        window.addEventListener('mouseup', () => { dragging = false; });
    }

    /** Make the dialog resizable via a bottom-right handle. */
    _installResizeDrag(handle) {
        const el = this._dialogEl;
        let resizing = false, startX, startY, origW, origH;

        handle.addEventListener('mousedown', (e) => {
            resizing = true;
            startX = e.clientX;
            startY = e.clientY;
            origW = el.offsetWidth;
            origH = el.offsetHeight;
            e.preventDefault();
            e.stopPropagation();
        });

        window.addEventListener('mousemove', (e) => {
            if (!resizing) return;
            const w = Math.max(200, origW + e.clientX - startX);
            const h = Math.max(120, origH + e.clientY - startY);
            el.style.width = `${w}px`;
            el.style.height = `${h}px`;
            window.dispatchEvent(new Event('resize'));
        });

        window.addEventListener('mouseup', () => { resizing = false; });
    }

    _attachGroup(container) {
        container.appendChild(this.groupWidget.getElement());
    }

    // ── Minimize / Restore ──────────────────────────────────────────────

    minimize() {
        if (!this._dialogEl || this._isMinimized || this._isClosed) return;

        this._ensureAbsolutePos();

        // Save current geometry
        this._savedRect = {
            left: this._dialogEl.style.left,
            top: this._dialogEl.style.top,
            width: this._dialogEl.style.width,
            height: this._dialogEl.style.height,
        };

        this._dialogEl.classList.add('popup-minimizing');
        const onEnd = () => {
            this._dialogEl.removeEventListener('animationend', onEnd);
            this._dialogEl.classList.remove('popup-minimizing');
            this._dialogEl.style.display = 'none';
            if (this._overlayEl) this._overlayEl.style.display = 'none';
            this._addDockEntry();
        };
        this._dialogEl.addEventListener('animationend', onEnd);
        this._isMinimized = true;

        this.callbacks.get('event').call({
            id: this.id,
            event: 'minimized',
            data: {}
        });
    }

    restore() {
        if (!this._dialogEl || !this._isMinimized || this._isClosed) return;

        Popup._removeDockEntry(this.id);

        // Restore overlay
        if (this._overlayEl) this._overlayEl.style.display = '';

        // Restore saved geometry
        if (this._savedRect) {
            this._dialogEl.style.left = this._savedRect.left;
            this._dialogEl.style.top = this._savedRect.top;
            this._dialogEl.style.width = this._savedRect.width;
            this._dialogEl.style.height = this._savedRect.height;
        }

        this._dialogEl.style.display = '';
        this._dialogEl.classList.add('popup-restoring');
        const onEnd = () => {
            this._dialogEl.removeEventListener('animationend', onEnd);
            this._dialogEl.classList.remove('popup-restoring');
        };
        this._dialogEl.addEventListener('animationend', onEnd);
        this._isMinimized = false;

        this.callbacks.get('event').call({
            id: this.id,
            event: 'restored',
            data: {}
        });
    }

    _addDockEntry() {
        Popup._getDock(); // ensure dock + list exist

        const entry = document.createElement('div');
        entry.classList.add('popup-dock-entry');

        const titleSpan = document.createElement('span');
        titleSpan.classList.add('popup-dock-entry-title');
        titleSpan.textContent = this._title;
        titleSpan.title = this._title;
        entry.appendChild(titleSpan);

        const closeBtn = document.createElement('button');
        closeBtn.classList.add('popup-dock-entry-close');
        closeBtn.textContent = '×';
        closeBtn.title = 'Close';
        closeBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            this.close_manually();
        });
        entry.appendChild(closeBtn);

        entry.addEventListener('click', () => this.restore());

        Popup._dockListEl.appendChild(entry);
        Popup._dockEntries.set(this.id, { popup: this, entryEl: entry });

        // Update counter on label
        Popup._updateDockLabel();
    }

    static _updateDockLabel() {
        if (!Popup._dockEl) return;
        const label = Popup._dockEl.querySelector('.popup-dock-label');
        if (label) {
            const n = Popup._dockEntries.size;
            label.innerHTML = `<span class="popup-dock-label-icon">▫</span> Minimized (${n})`;
        }
    }

    close_manually() {
        if (this._isClosed) return;
        this._isClosed = true;

        // Clean up dock entry if minimized
        if (this._isMinimized) {
            Popup._removeDockEntry(this.id);
            if (this._dialogEl) this._dialogEl.style.display = '';
            if (this._overlayEl) this._overlayEl.style.display = '';
            this._isMinimized = false;
        }

        if (this._poll) {
            clearInterval(this._poll);
            this._poll = null;
        }
        this._removeMessageBridge();

        // Clean up DOM (dialog element, overlay, blob URL)
        if (this._dialogEl) {
            this._dialogEl.remove();
            this._dialogEl = null;
        }
        if (this._shellBlobUrl) {
            URL.revokeObjectURL(this._shellBlobUrl);
            this._shellBlobUrl = null;
        }
        this._hideOverlay();

        this.callbacks.get('event').call({
            id: this.id,
            event: 'closed',
            data: {}
        });

        this.callbacks.get('closed').call(this.id);
    }

    close() {
        if (this._isClosed) return;
        this._isClosed = true;

        // Clean up dock entry if minimized
        if (this._isMinimized) {
            Popup._removeDockEntry(this.id);
            if (this._dialogEl) this._dialogEl.style.display = '';
            if (this._overlayEl) this._overlayEl.style.display = '';
            this._isMinimized = false;
        }

        if (this._win && !this._win.closed) {
            try {
                this._win.close();
            } catch {
            }
        }
        if (this._poll) {
            clearInterval(this._poll);
            this._poll = null;
        }
        this._removeMessageBridge();

        if (this._dialogEl) {
            this._dialogEl.remove();
            this._dialogEl = null;
        }
        if (this._shellBlobUrl) {
            URL.revokeObjectURL(this._shellBlobUrl);
            this._shellBlobUrl = null;
        }
        this._hideOverlay();

        console.warn(`Popup "${this.id}" closed.`);
        this.callbacks.get('closed').call(this.id);
    }

    _openTab() {
        this._installMessageBridge();

        // this._openWithBlobURL('_blank');
        // Prefer real same-origin shell → correct title immediately
        this._win = this._openRealShell('_blank');

        // Fallback to Blob shell (title set in HTML + JS)
        if (!this._win || this._win.closed) {
            this._win = this._openWithBlobURL('_blank');
        }

        if (!this._win || this._win.closed) {
            console.warn(`Popup.open: window.open blocked, falling back to dialog for "${this.id}"`);
            this._removeMessageBridge();
            this._openDialogFallback();
            return;
        }

        // Timed attach in case message fires too early
        this._attachIntoChildWindow();
    }

    open() {
        const [width, height] = this.config.size;

        // ── Compute center coordinates ─────────────────────────────────────────
        const screenX = window.screenX !== undefined ? window.screenX : window.screen.left;
        const screenY = window.screenY !== undefined ? window.screenY : window.screen.top;
        const availWidth = window.innerWidth || screen.width;
        const availHeight = window.innerHeight || screen.height;

        const left = Math.round(screenX + (availWidth - width) / 2);
        const top = Math.round(screenY + (availHeight - height) / 2);

        if (this.config.type === 'window') {
            const features = [
                `width=${width}`,
                `height=${height}`,
                `left=${left}`,
                `top=${top}`,
                `resizable=${this.config.resizable ? 'yes' : 'no'}`,
            ].join(',');

            this._installMessageBridge();

            // Prefer real same-origin shell
            this._win = this._openRealShell(this.id, features);

            // Fallback to Blob shell
            if (!this._win || this._win.closed) {
                this._win = this._openWithBlobURL(this.id, features);
            }

            // If popup blocked, fallback to dialog
            if (!this._win || this._win.closed) {
                console.warn(`Popup.open: window.open blocked, falling back to dialog for "${this.id}"`);
                this._removeMessageBridge();
                this._openDialogFallback();
                return;
            }

            // Timed attach as additional safety
            this._attachIntoChildWindow();

        } else if (this.config.type === 'tab') {
            this._openTab();
        } else {
            // dialog
            this._openDialogFallback();
        }

        // if it's a dialog and GUI should be disabled underneath
        if (this.config.type === 'dialog' && this.config.disable_gui) {
            this._showOverlay();
        }

        // Restore minimized state from backend (e.g. after page reload)
        if (this.config.minimized && this._dialogEl) {
            this._minimizeInstant();
        }
    }

    /** Minimize without animation (used to restore state on reconnect). */
    _minimizeInstant() {
        if (!this._dialogEl || this._isMinimized) return;

        this._ensureAbsolutePos();
        this._savedRect = {
            left: this._dialogEl.style.left,
            top: this._dialogEl.style.top,
            width: this._dialogEl.style.width,
            height: this._dialogEl.style.height,
        };
        this._dialogEl.style.display = 'none';
        if (this._overlayEl) this._overlayEl.style.display = 'none';
        this._isMinimized = true;
        this._addDockEntry();
    }

    hide() {
        if (this._dialogEl) this._dialogEl.style.display = 'none';
    }

    getObjectByPath(path) {
        let key, remainder;
        [key, remainder] = splitPath(path);

        const childKey = `${this.id}/${key}`;

        if (childKey === this.groupWidget.id) {
            if (!remainder) {
                return this.groupWidget;
            } else {
                return this.groupWidget.getObjectByPath(remainder);
            }
        }
    }

    // ── overlay helpers ─────────────────────────────────────────────────────
    _showOverlay() {
        const overlay = document.createElement('div');
        overlay.id = `${this.id}__overlay`;
        overlay.classList.add('popup-gui-overlay');
        document.body.appendChild(overlay);
        this._overlayEl = overlay;
    }

    _hideOverlay() {
        if (this._overlayEl) {
            this._overlayEl.display = 'none';
            document.body.removeChild(this._overlayEl);
            this._overlayEl.remove();
            this._overlayEl = null;
            console.log('Overlay removed.');
        }
    }
}
