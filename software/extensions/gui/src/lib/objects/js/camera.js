import {Widget} from '../objects.js';
import {getFromLocalStorage} from '../../helpers.js';

/* ================================================================================================================== */
export class CameraWidget extends Widget {
    constructor(id, config = {}) {
        super(id, config);

        const defaults = {
            cameras: {},
            selected: null,
            stream_url: null,
            fit: 'contain',
            enable_enlarge: true,
            enable_fullscreen: true,
            lock_aspect_ratio: true,
        };
        this.configuration = {...defaults, ...this.configuration};

        this._rotation = 0;
        this._isPopped = false;
        this._noCameras = false;
        this._aspectRatio = null; // width / height, set on image load
        this._lastFloatRect = null; // {left, top, width, height} remembered across pop-out sessions
        this._cropRegion = null;   // {x, y, w, h} fractions of natural image, or null
        this._isCropping = false;

        // ── Build main element ──────────────────────────────────────────────
        this.element = document.createElement('div');
        this.element.id = this.id;
        this.element.classList.add('cameraWidget', 'widget');

        // ── Video container (fills the entire widget) ───────────────────────
        this.videoContainer = document.createElement('div');
        this.videoContainer.classList.add('cameraWidget__videoContainer');
        this.element.appendChild(this.videoContainer);

        // ── Media (MJPEG img) ───────────────────────────────────────────────
        this.media = document.createElement('img');
        this.media.classList.add('cameraWidget__media');
        this.videoContainer.appendChild(this.media);

        // ── Status text overlay ─────────────────────────────────────────────
        this.statusText = document.createElement('div');
        this.statusText.classList.add('cameraWidget__statusText');
        this.videoContainer.appendChild(this.statusText);

        // ── Compact pop-out button (visible only when widget is small) ──────
        this.compactBtn = document.createElement('button');
        this.compactBtn.classList.add('cameraWidget__compactBtn');
        this.compactBtn.textContent = '⬈';
        this.compactBtn.title = 'Pop out';
        this.element.appendChild(this.compactBtn);

        // ── Toolbar (overlaid, slides in on hover) ──────────────────────────
        this._createToolbar();

        // ── Floating pop-out panel ──────────────────────────────────────────
        this._createFloatingPanel();

        // ── Final wiring ────────────────────────────────────────────────────
        this.configureElement(this.element);
        this.assignListeners(this.element);
    }

    // ── TOOLBAR ─────────────────────────────────────────────────────────────

    _createToolbar() {
        this.toolbar = document.createElement('div');
        this.toolbar.classList.add('cameraWidget__toolbar');
        this.element.appendChild(this.toolbar);

        this.select = document.createElement('select');
        this.select.classList.add('cameraWidget__select');
        this.toolbar.appendChild(this.select);

        this.rescanBtn = this._mkToolbarBtn('🔍', 'Rescan cameras');
        this.refreshBtn = this._mkToolbarBtn('🔄', 'Refresh stream');
        this.rotateBtn = this._mkToolbarBtn('↻', 'Rotate 90°');

        if (this.configuration.enable_enlarge) {
            this.enlargeBtn = this._mkToolbarBtn('⬈', 'Pop out');
        }
        if (this.configuration.enable_fullscreen) {
            this.fsBtn = this._mkToolbarBtn('⛶', 'Open in new tab');
        }

        this._populateDropdown(this.configuration.cameras, this.configuration.selected);
    }

    _mkToolbarBtn(text, title) {
        const b = document.createElement('button');
        b.classList.add('cameraWidget__button');
        b.textContent = text;
        b.title = title;
        this.toolbar.appendChild(b);
        return b;
    }

    // ── FLOATING POP-OUT PANEL ──────────────────────────────────────────────

    _createFloatingPanel() {
        const panel = this.floatPanel = document.createElement('div');
        panel.classList.add('cameraWidget__float');
        panel.style.display = 'none';
        document.body.appendChild(panel);

        // Stream image
        this.floatMedia = document.createElement('img');
        this.floatMedia.classList.add('cameraWidget__floatMedia');
        panel.appendChild(this.floatMedia);

        // Crop selection overlay (hidden until crop mode)
        this.cropOverlay = document.createElement('div');
        this.cropOverlay.classList.add('cameraWidget__cropOverlay');
        this.cropOverlay.style.display = 'none';
        panel.appendChild(this.cropOverlay);

        this.cropSelection = document.createElement('div');
        this.cropSelection.classList.add('cameraWidget__cropSelection');
        this.cropOverlay.appendChild(this.cropSelection);

        // Hover controls overlay
        this.floatHover = document.createElement('div');
        this.floatHover.classList.add('cameraWidget__floatHover');
        panel.appendChild(this.floatHover);

        // Top bar: camera select, rotate, close
        const topBar = document.createElement('div');
        topBar.classList.add('cameraWidget__floatBar', 'cameraWidget__floatBar--top');
        this.floatHover.appendChild(topBar);

        this.floatSelect = document.createElement('select');
        this.floatSelect.classList.add('cameraWidget__floatSelect');
        topBar.appendChild(this.floatSelect);

        this.floatRotateBtn = document.createElement('button');
        this.floatRotateBtn.classList.add('cameraWidget__floatBtn');
        this.floatRotateBtn.textContent = '↻';
        this.floatRotateBtn.title = 'Rotate 90°';
        topBar.appendChild(this.floatRotateBtn);

        this.floatNewTabBtn = document.createElement('button');
        this.floatNewTabBtn.classList.add('cameraWidget__floatBtn');
        this.floatNewTabBtn.textContent = '⛶';
        this.floatNewTabBtn.title = 'Open in new tab';
        topBar.appendChild(this.floatNewTabBtn);

        this.floatCropBtn = document.createElement('button');
        this.floatCropBtn.classList.add('cameraWidget__floatBtn');
        this.floatCropBtn.textContent = '✂';
        this.floatCropBtn.title = 'Crop';
        topBar.appendChild(this.floatCropBtn);

        this.floatUncropBtn = document.createElement('button');
        this.floatUncropBtn.classList.add('cameraWidget__floatBtn');
        this.floatUncropBtn.textContent = '↩';
        this.floatUncropBtn.title = 'Remove crop';
        this.floatUncropBtn.style.display = 'none';
        topBar.appendChild(this.floatUncropBtn);

        this.floatCloseBtn = document.createElement('button');
        this.floatCloseBtn.classList.add('cameraWidget__floatBtn');
        this.floatCloseBtn.textContent = '✖';
        this.floatCloseBtn.title = 'Close';
        topBar.appendChild(this.floatCloseBtn);

        // Bottom bar: opacity slider
        const bottomBar = document.createElement('div');
        bottomBar.classList.add('cameraWidget__floatBar', 'cameraWidget__floatBar--bottom');
        this.floatHover.appendChild(bottomBar);

        const label = document.createElement('span');
        label.classList.add('cameraWidget__floatLabel');
        label.textContent = 'Opacity';
        bottomBar.appendChild(label);

        this.floatOpacity = document.createElement('input');
        this.floatOpacity.type = 'range';
        this.floatOpacity.min = '0.1';
        this.floatOpacity.max = '1';
        this.floatOpacity.step = '0.05';
        this.floatOpacity.value = '1';
        this.floatOpacity.classList.add('cameraWidget__floatSlider');
        bottomBar.appendChild(this.floatOpacity);

        // Populate the float dropdown (main dropdown was already populated in _createToolbar)
        this._populateDropdown(this.configuration.cameras, this.configuration.selected);
    }

    // ── DROPDOWN ────────────────────────────────────────────────────────────

    _populateDropdown(cameras, selected) {
        const entries = Object.entries(cameras || {});
        entries.sort((a, b) => (a[1].label || '').localeCompare(b[1].label || ''));

        // Populate both the main and float dropdowns (floatSelect may not exist yet during init)
        const targets = this.floatSelect ? [this.select, this.floatSelect] : [this.select];
        for (const sel of targets) {
            sel.innerHTML = '';

            if (entries.length === 0) {
                const opt = document.createElement('option');
                opt.value = '';
                opt.textContent = 'No cameras available';
                opt.disabled = true;
                opt.selected = true;
                sel.appendChild(opt);
                sel.disabled = true;
                continue;
            }

            sel.disabled = false;
            for (const [key, cam] of entries) {
                const opt = document.createElement('option');
                opt.value = key;
                opt.textContent = cam.label || `Camera ${key}`;
                if (key === selected) opt.selected = true;
                sel.appendChild(opt);
            }
        }
    }

    // ── PUBLIC API (called from Python backend) ─────────────────────────────

    setStreamUrl(url) {
        if (!url) {
            this.media.style.display = 'none';
            this._showStatus('No stream');
            return;
        }
        if (!this._isPopped) this._showStatus('Connecting...');
        const sep = url.includes('?') ? '&' : '?';
        const fresh = `${url}${sep}_=${Date.now()}`;
        this.media.src = fresh;
        if (this._isPopped) this.floatMedia.src = fresh;
    }

    setCameras({cameras, selected}) {
        this._populateDropdown(cameras, selected);
        this.configuration.cameras = cameras;
        this.configuration.selected = selected;
        this._noCameras = Object.keys(cameras || {}).length === 0;
        if (this._noCameras) this._showNoCameras();
    }

    closePopout() {
        if (this._isPopped) this._popIn();
    }

    // ── WIDGET LIFECYCLE ────────────────────────────────────────────────────

    getElement() {
        return this.element;
    }

    configureElement(element) {
        super.configureElement(element);
        this.media.style.objectFit = this.configuration.fit;

        if (this.configuration.stream_url) {
            this.setStreamUrl(this.configuration.stream_url);
        } else if (Object.keys(this.configuration.cameras || {}).length === 0) {
            this._noCameras = true;
            this._showNoCameras();
        } else {
            this._showStatus('Select a camera');
        }
    }

    assignListeners(element) {
        super.assignListeners(element);

        // Camera selection
        this.select.addEventListener('change', () => {
            const key = this.select.value;
            if (!key) return;
            this.configuration.selected = key;
            this.floatSelect.value = key; // sync float dropdown
            this._clearCrop();
            this._showStatus('Connecting...');
            this.media.style.display = 'none';
            this.callbacks.get('event').call({
                id: this.id, event: 'camera_select_change', camera_key: key,
            });
        });

        this.rescanBtn.addEventListener('click', () => {
            this.callbacks.get('event').call({id: this.id, event: 'rescan'});
        });

        this.statusText.addEventListener('click', () => {
            if (!this._noCameras) return;
            this.callbacks.get('event').call({id: this.id, event: 'rescan'});
        });

        this.refreshBtn.addEventListener('click', () => {
            this.callbacks.get('event').call({id: this.id, event: 'refresh'});
            this._reloadStream();
        });

        // Rotate
        this.rotateBtn.addEventListener('click', () => {
            this._rotation = (this._rotation + 90) % 360;
            this._applyRotation();
        });

        // Pop out (toolbar button + compact button)
        if (this.enlargeBtn) {
            this.enlargeBtn.addEventListener('click', () => this._popOut());
        }
        this.compactBtn.addEventListener('click', () => this._popOut());

        // Fullscreen (new tab)
        if (this.fsBtn) {
            this.fsBtn.addEventListener('click', () => {
                if (this.media.src) window.open(this.media.src, '_blank');
            });
        }

        // Stream load/error
        this.media.addEventListener('load', () => {
            if (this.media.naturalWidth && this.media.naturalHeight) {
                this._aspectRatio = this.media.naturalWidth / this.media.naturalHeight;
            }
            if (!this._isPopped) {
                this.media.style.display = 'block';
                this._hideStatus();
            }
        });
        this.media.addEventListener('error', () => {
            if (this.media.src && this.media.src !== window.location.href) {
                this.media.style.display = 'none';
                this._showStatus('Stream error - click refresh');
            }
        });

        // ── Floating panel listeners ────────────────────────────────────────
        this.floatCloseBtn.addEventListener('click', () => this._popIn());

        this.floatRotateBtn.addEventListener('click', () => {
            this._rotation = (this._rotation + 90) % 360;
            this._applyRotation();
            this._saveFloatState();
        });

        this.floatNewTabBtn.addEventListener('click', () => {
            if (this.floatMedia.src) window.open(this.floatMedia.src, '_blank');
        });
        this.floatCropBtn.addEventListener('click', () => this._enterCropMode());
        this.floatUncropBtn.addEventListener('click', () => this._clearCrop());

        this.floatSelect.addEventListener('change', () => {
            const key = this.floatSelect.value;
            if (!key) return;
            this.configuration.selected = key;
            this.select.value = key; // sync main dropdown
            this._clearCrop();
            this.callbacks.get('event').call({
                id: this.id, event: 'camera_select_change', camera_key: key,
            });
        });

        this.floatOpacity.addEventListener('input', () => {
            this.floatMedia.style.opacity = this.floatOpacity.value;
            this._saveFloatState();
        });

        this.floatMedia.addEventListener('load', () => {
            this.floatMedia.style.display = 'block';
        });

        this._setupPanelInteraction();

        // Detect widget removal from DOM (e.g. GUI disconnect) to close the float panel
        this._disconnectObserver = new MutationObserver(() => {
            if (this.element && !this.element.isConnected) {
                if (this._isPopped) {
                    this.floatPanel.style.display = 'none';
                    this.floatMedia.src = '';
                    this._isPopped = false;
                }
                this._disconnectObserver.disconnect();
            }
        });
        this._disconnectObserver.observe(document.body, {childList: true, subtree: true});

        // Compact mode when widget is small
        this._compact = false;
        this._resizeObserver = new ResizeObserver(([entry]) => {
            const {width, height} = entry.contentRect;
            const small = width < 180 || height < 140;
            if (small !== this._compact) {
                this._compact = small;
                this.element.classList.toggle('cameraWidget--compact', small);
                this.media.style.objectFit = small ? 'cover' : this.configuration.fit;
                if (this._noCameras) this._showNoCameras();
            }
        });
        this._resizeObserver.observe(this.element);
    }

    // ── ROTATION ────────────────────────────────────────────────────────────

    _applyRotation() {
        const target = this._isPopped ? this.floatMedia : this.media;
        if (this._rotation % 180 !== 0) {
            const rect = (this._isPopped ? this.floatPanel : this.videoContainer).getBoundingClientRect();
            const ratio = Math.min(rect.height / rect.width, rect.width / rect.height);
            target.style.transform = `rotate(${this._rotation}deg) scale(${ratio})`;
        } else {
            target.style.transform = this._rotation ? `rotate(${this._rotation}deg)` : '';
        }
        // Sync both
        const other = target === this.media ? this.floatMedia : this.media;
        other.style.transform = target.style.transform;
    }

    _getEffectiveAspectRatio() {
        if (!this._aspectRatio) return null;
        let ar = this._aspectRatio;
        // Crop changes effective aspect ratio
        if (this._cropRegion) {
            ar = (this._cropRegion.w / this._cropRegion.h) * ar;
        }
        // When rotated 90/270, the aspect ratio is inverted
        return (this._rotation % 180 !== 0) ? (1 / ar) : ar;
    }

    // ── POP OUT / POP IN ────────────────────────────────────────────────────

    _popOut() {
        if (this._isPopped) return;
        this._isPopped = true;

        // Try to restore saved state for this camera from localStorage
        const saved = this._loadFloatState();

        if (saved) {
            this.floatPanel.style.left = saved.left + 'px';
            this.floatPanel.style.top = saved.top + 'px';
            this.floatPanel.style.width = saved.width + 'px';
            this.floatPanel.style.height = saved.height + 'px';

            if (saved.opacity != null) {
                this.floatOpacity.value = saved.opacity;
            }
            if (saved.rotation != null) {
                this._rotation = saved.rotation;
            }
            if (saved.crop) {
                this._cropRegion = saved.crop;
            }
        } else if (this._lastFloatRect) {
            // Fallback to in-memory position from earlier pop-out
            const r = this._lastFloatRect;
            this.floatPanel.style.left = r.left + 'px';
            this.floatPanel.style.top = r.top + 'px';
            this.floatPanel.style.width = r.width + 'px';
            this.floatPanel.style.height = r.height + 'px';
        } else {
            // First pop-out ever: compute from widget size + aspect ratio
            const rect = this.element.getBoundingClientRect();
            let w = Math.max(rect.width * 1.2, 320);
            let h = Math.max(rect.height * 1.2, 240);

            const ar = this._getEffectiveAspectRatio();
            if (this.configuration.lock_aspect_ratio && ar) {
                if (w / h > ar) {
                    w = h * ar;
                } else {
                    h = w / ar;
                }
                w = Math.max(w, 200);
                h = Math.max(h, 150);
            }

            const l = Math.min(rect.left + (rect.width - w) / 2, window.innerWidth - w - 16);
            const t = Math.min(rect.top + (rect.height - h) / 2, window.innerHeight - h - 16);

            this.floatPanel.style.left = Math.max(16, l) + 'px';
            this.floatPanel.style.top = Math.max(16, t) + 'px';
            this.floatPanel.style.width = w + 'px';
            this.floatPanel.style.height = h + 'px';
        }

        if (this._noCameras) return;

        this.floatMedia.src = this.media.src;
        this.floatMedia.style.opacity = this.floatOpacity.value;
        this.floatPanel.style.display = 'block';

        // Apply restored rotation and crop
        this._applyRotation();
        if (this._cropRegion) {
            this._applyCrop(this._cropRegion);
        }

        // Hide original, show placeholder
        this.media.style.display = 'none';
        this._showStatus(this._compact ? '📷' : 'Popped out — drag to reposition');
    }

    _popIn() {
        if (!this._isPopped) return;
        this._isPopped = false;

        // Save state for this camera to localStorage
        this._saveFloatState();

        // Remember position in memory as well
        const r = this.floatPanel.getBoundingClientRect();
        this._lastFloatRect = {left: r.left, top: r.top, width: r.width, height: r.height};

        this.floatPanel.style.display = 'none';
        this.floatMedia.src = '';

        if (this._noCameras) {
            this._showNoCameras();
        } else {
            this.media.style.display = 'block';
            this._hideStatus();
        }
    }

    // ── DRAG & RESIZE (edge-detect, no extra DOM elements) ──────────────────

    _setupPanelInteraction() {
        const panel = this.floatPanel;
        const EDGE = 8, MIN_W = 200, MIN_H = 150;
        let mode = null, startX, startY, startRect;

        const getDir = (cx, cy, r) => {
            const x = cx - r.left, y = cy - r.top;
            const onL = x < EDGE, onR = x > r.width - EDGE;
            const onT = y < EDGE, onB = y > r.height - EDGE;
            if (onT && onL) return 'nw'; if (onT && onR) return 'ne';
            if (onB && onL) return 'sw'; if (onB && onR) return 'se';
            if (onT) return 'n'; if (onB) return 's';
            if (onL) return 'w'; if (onR) return 'e';
            return 'move';
        };

        const cursorMap = {
            move: 'move', n: 'n-resize', s: 's-resize', e: 'e-resize', w: 'w-resize',
            nw: 'nw-resize', ne: 'ne-resize', sw: 'sw-resize', se: 'se-resize',
        };

        panel.addEventListener('mousemove', (e) => {
            if (mode || this._isCropping) return;
            if (e.target.closest('.cameraWidget__floatBar')) {
                panel.style.cursor = '';
                return;
            }
            const dir = getDir(e.clientX, e.clientY, panel.getBoundingClientRect());
            panel.style.cursor = cursorMap[dir];
        });

        panel.addEventListener('mousedown', (e) => {
            if (this._isCropping) return;
            if (e.target.closest('.cameraWidget__floatBar')) return;
            e.preventDefault();
            const rect = panel.getBoundingClientRect();
            mode = getDir(e.clientX, e.clientY, rect);
            startX = e.clientX;
            startY = e.clientY;
            startRect = {left: rect.left, top: rect.top, width: rect.width, height: rect.height};

            const onMove = (ev) => {
                const dx = ev.clientX - startX, dy = ev.clientY - startY;

                if (mode === 'move') {
                    panel.style.left = (startRect.left + dx) + 'px';
                    panel.style.top = (startRect.top + dy) + 'px';
                    return;
                }

                let {left: nL, top: nT, width: nW, height: nH} = startRect;

                if (mode.includes('e')) nW = Math.max(MIN_W, startRect.width + dx);
                if (mode.includes('s')) nH = Math.max(MIN_H, startRect.height + dy);
                if (mode.includes('w')) {
                    nW = Math.max(MIN_W, startRect.width - dx);
                    nL = nW === MIN_W ? startRect.left + startRect.width - MIN_W : startRect.left + dx;
                }
                if (mode.includes('n')) {
                    nH = Math.max(MIN_H, startRect.height - dy);
                    nT = nH === MIN_H ? startRect.top + startRect.height - MIN_H : startRect.top + dy;
                }

                // Enforce aspect ratio
                const ar = this.configuration.lock_aspect_ratio ? this._getEffectiveAspectRatio() : null;
                if (ar) {
                    const isCorner = mode.length === 2;
                    const isHoriz = mode === 'e' || mode === 'w';

                    if (isCorner || isHoriz) {
                        // Width drives height
                        const newH = Math.max(MIN_H, nW / ar);
                        if (mode.includes('n')) nT += (nH - newH);
                        nH = newH;
                    } else {
                        // Height drives width
                        const newW = Math.max(MIN_W, nH * ar);
                        if (mode.includes('w')) nL += (nW - newW);
                        nW = newW;
                    }
                }

                panel.style.left = nL + 'px';
                panel.style.top = nT + 'px';
                panel.style.width = nW + 'px';
                panel.style.height = nH + 'px';
            };

            const onUp = () => {
                mode = null;
                document.removeEventListener('mousemove', onMove);
                document.removeEventListener('mouseup', onUp);
                // Re-apply rotation scaling for new dimensions
                if (this._rotation % 180 !== 0) this._applyRotation();
                this._saveFloatState();
            };

            document.addEventListener('mousemove', onMove);
            document.addEventListener('mouseup', onUp);
        });
    }

    // ── CROP ──────────────────────────────────────────────────────────────

    _enterCropMode() {
        if (this._isCropping) return;
        if (!this.floatMedia.naturalWidth || !this.floatMedia.naturalHeight) return;
        this._isCropping = true;

        // Clear any existing crop so user draws on full image
        if (this._cropRegion) {
            this.floatMedia.style.objectViewBox = '';
            this.media.style.objectViewBox = '';
            this._cropRegion = null;
            this.floatUncropBtn.style.display = 'none';
            const ar = this._getEffectiveAspectRatio();
            if (this.configuration.lock_aspect_ratio && ar) {
                const rect = this.floatPanel.getBoundingClientRect();
                this.floatPanel.style.height = (rect.width / ar) + 'px';
            }
        }

        // Show crop overlay, hide hover controls
        this.cropOverlay.style.display = 'block';
        this.cropSelection.style.display = 'none';
        this.floatHover.style.display = 'none';

        let startX, startY, dragging = false;

        const cleanup = () => {
            this.cropOverlay.removeEventListener('mousedown', onDown);
            document.removeEventListener('mousemove', onMove);
            document.removeEventListener('mouseup', onUp);
            document.removeEventListener('keydown', onKey);
            this.cropOverlay.style.display = 'none';
            this.cropSelection.style.display = 'none';
            this.floatHover.style.display = '';
            this._isCropping = false;
        };

        const onDown = (e) => {
            if (e.button !== 0) { cleanup(); return; }
            e.preventDefault();
            const r = this.floatPanel.getBoundingClientRect();
            startX = e.clientX - r.left;
            startY = e.clientY - r.top;
            dragging = true;
            this.cropSelection.style.left = startX + 'px';
            this.cropSelection.style.top = startY + 'px';
            this.cropSelection.style.width = '0';
            this.cropSelection.style.height = '0';
            this.cropSelection.style.display = 'block';
        };

        const onMove = (e) => {
            if (!dragging) return;
            const r = this.floatPanel.getBoundingClientRect();
            const curX = Math.max(0, Math.min(r.width, e.clientX - r.left));
            const curY = Math.max(0, Math.min(r.height, e.clientY - r.top));
            this.cropSelection.style.left = Math.min(startX, curX) + 'px';
            this.cropSelection.style.top = Math.min(startY, curY) + 'px';
            this.cropSelection.style.width = Math.abs(curX - startX) + 'px';
            this.cropSelection.style.height = Math.abs(curY - startY) + 'px';
        };

        const onUp = (e) => {
            if (!dragging) return;
            dragging = false;
            const r = this.floatPanel.getBoundingClientRect();
            const curX = Math.max(0, Math.min(r.width, e.clientX - r.left));
            const curY = Math.max(0, Math.min(r.height, e.clientY - r.top));
            const selX = Math.min(startX, curX);
            const selY = Math.min(startY, curY);
            const selW = Math.abs(curX - startX);
            const selH = Math.abs(curY - startY);

            cleanup();

            // Map selection corners through inverse CSS transform, then to image coords
            const tl = this._panelToImageCoords(selX, selY);
            const br = this._panelToImageCoords(selX + selW, selY + selH);
            if (!tl || !br) return;

            // For 90/270 rotations the corners swap — use min/max
            const x1 = Math.max(0, Math.min(1, Math.min(tl.x, br.x)));
            const y1 = Math.max(0, Math.min(1, Math.min(tl.y, br.y)));
            const x2 = Math.max(0, Math.min(1, Math.max(tl.x, br.x)));
            const y2 = Math.max(0, Math.min(1, Math.max(tl.y, br.y)));
            const region = {x: x1, y: y1, w: x2 - x1, h: y2 - y1};

            // Minimum 5% of image in each dimension
            if (region.w < 0.05 || region.h < 0.05) return;

            this._applyCrop(region);
        };

        const onKey = (e) => {
            if (e.key === 'Escape') cleanup();
        };

        this.cropOverlay.addEventListener('mousedown', onDown);
        document.addEventListener('mousemove', onMove);
        document.addEventListener('mouseup', onUp);
        document.addEventListener('keydown', onKey);
    }

    _getContainedImageRect() {
        const cW = this.floatPanel.clientWidth;
        const cH = this.floatPanel.clientHeight;
        const nW = this.floatMedia.naturalWidth;
        const nH = this.floatMedia.naturalHeight;
        if (!nW || !nH) return null;

        const scale = Math.min(cW / nW, cH / nH);
        const displayW = nW * scale;
        const displayH = nH * scale;
        return {
            offsetX: (cW - displayW) / 2,
            offsetY: (cH - displayH) / 2,
            displayW,
            displayH,
        };
    }

    _panelToImageCoords(px, py) {
        const pW = this.floatPanel.clientWidth;
        const pH = this.floatPanel.clientHeight;
        const cx = pW / 2, cy = pH / 2;

        // Inverse of CSS transform: rotate(θ) scale(s)
        const θ = -this._rotation * Math.PI / 180;
        const s = (this._rotation % 180 !== 0) ? Math.min(pH / pW, pW / pH) : 1;
        const dx = px - cx, dy = py - cy;
        const cosT = Math.cos(θ), sinT = Math.sin(θ);
        const ex = (dx * cosT - dy * sinT) / s + cx;
        const ey = (dx * sinT + dy * cosT) / s + cy;

        // Map element-space point to normalised image coords
        const ir = this._getContainedImageRect();
        if (!ir) return null;
        return {x: (ex - ir.offsetX) / ir.displayW, y: (ey - ir.offsetY) / ir.displayH};
    }

    _applyCrop(region) {
        this._cropRegion = region;
        const top = region.y * 100;
        const right = (1 - region.x - region.w) * 100;
        const bottom = (1 - region.y - region.h) * 100;
        const left = region.x * 100;
        const vb = `inset(${top}% ${right}% ${bottom}% ${left}%)`;
        this.floatMedia.style.objectViewBox = vb;
        this.media.style.objectViewBox = vb;

        // Resize panel to match crop aspect ratio
        const ar = this._getEffectiveAspectRatio();
        if (this.configuration.lock_aspect_ratio && ar) {
            const rect = this.floatPanel.getBoundingClientRect();
            this.floatPanel.style.height = (rect.width / ar) + 'px';
        }

        this.floatUncropBtn.style.display = '';

        // Re-apply rotation scaling for new panel dimensions
        if (this._rotation % 180 !== 0) this._applyRotation();
        this._saveFloatState();
    }

    _clearCrop() {
        if (!this._cropRegion) return;
        this._cropRegion = null;
        this.floatMedia.style.objectViewBox = '';
        this.media.style.objectViewBox = '';
        this.floatUncropBtn.style.display = 'none';

        // Resize panel to original aspect ratio
        const ar = this._getEffectiveAspectRatio();
        if (this.configuration.lock_aspect_ratio && ar && this._isPopped) {
            const rect = this.floatPanel.getBoundingClientRect();
            this.floatPanel.style.height = (rect.width / ar) + 'px';
        }

        // Re-apply rotation scaling for new panel dimensions
        if (this._rotation % 180 !== 0) this._applyRotation();
        this._saveFloatState();
    }

    // ── HELPERS ─────────────────────────────────────────────────────────────

    _showNoCameras() {
        this.media.style.display = 'none';
        this.compactBtn.style.display = 'none';
        if (this._compact) {
            const rect = this.element.getBoundingClientRect();
            const size = Math.floor(Math.min(rect.width, rect.height) * 0.45);
            const btnSize = Math.floor(size * 0.7);
            this.statusText.innerHTML =
                `<span class="cameraWidget__noCamIcon" style="font-size:${size}px">📷</span>` +
                `<button class="cameraWidget__rescanOverlay" style="font-size:${btnSize}px">🔄</button>`;
        } else {
            this.statusText.innerHTML = '';
            this.statusText.textContent = 'No cameras found — click to rescan';
        }
        this.statusText.style.display = 'flex';
        this.statusText.style.pointerEvents = 'auto';
        this.statusText.style.cursor = 'pointer';
    }

    _showStatus(text) {
        this._noCameras = false;
        this.compactBtn.style.display = '';
        this.statusText.innerHTML = '';
        this.statusText.textContent = text;
        this.statusText.style.display = 'flex';
        this.statusText.style.pointerEvents = '';
        this.statusText.style.cursor = '';
    }

    _hideStatus() {
        this.statusText.style.display = 'none';
    }

    _reloadStream() {
        if (!this.media.src) return;
        this._showStatus('Reconnecting...');
        this.media.style.display = 'none';
        const base = this.configuration.stream_url || this.media.src.split('?')[0];
        const sep = base.includes('?') ? '&' : '?';
        const fresh = `${base}${sep}_=${Date.now()}`;
        this.media.src = fresh;
        if (this._isPopped) this.floatMedia.src = fresh;
    }

    // ── FLOAT STATE PERSISTENCE (per camera) ────────────────────────────────

    _floatStorageKey() {
        const camKey = this.configuration.selected;
        if (!camKey) return null;
        return `camera_float_${this.id}_${camKey}`;
    }

    _saveFloatState() {
        const key = this._floatStorageKey();
        if (!key) return;
        const rect = this.floatPanel.getBoundingClientRect();
        const state = {
            left: rect.left,
            top: rect.top,
            width: rect.width,
            height: rect.height,
            opacity: parseFloat(this.floatOpacity.value),
            rotation: this._rotation,
            crop: this._cropRegion,
        };
        try {
            localStorage.setItem(key, JSON.stringify(state));
        } catch (e) { /* quota exceeded – ignore */ }
    }

    _loadFloatState() {
        const key = this._floatStorageKey();
        if (!key) return null;
        return getFromLocalStorage(key);
    }

    destroy() {
        if (this._resizeObserver) {
            this._resizeObserver.disconnect();
            this._resizeObserver = null;
        }
        if (this._disconnectObserver) {
            this._disconnectObserver.disconnect();
            this._disconnectObserver = null;
        }
        if (this.floatPanel && this.floatPanel.parentNode) {
            this.floatPanel.parentNode.removeChild(this.floatPanel);
        }
        super.destroy();
    }
}
