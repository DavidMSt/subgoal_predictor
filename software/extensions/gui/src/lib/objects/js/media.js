import {Widget} from "../objects.js";
import {getColor} from "../../helpers.js";


export class UpdatableImageWidget extends Widget {
    constructor(id, payload = {}) {
        super(id, payload);

        // defaults (kept parallel to backend)
        const defaults = {
            image: '',                 // data URI or URL
            background_color: 'transparent',
            fit: 'contain',            // 'contain' | 'cover' | 'fill'
            title: null,
            clickable: false,
        };
        this.configuration = {...defaults, ...this.configuration, ...payload};

        this.element = this.initializeElement();
        this.configureElement(this.element);
        this.assignListeners(this.element);

        if (this.configuration.image) {
            this.updateImage(this.configuration.image);
        }
    }

    initializeElement() {
        const el = document.createElement('div');
        el.id = this.id;
        el.classList.add('widget', 'updatableImageWidget');

        this.img = document.createElement('img');
        this.img.classList.add('updatableImageWidget__img');
        el.appendChild(this.img);

        return el;
    }

    configureElement(element) {
        super.configureElement(element);
        const c = this.configuration;

        // container styles
        element.style.backgroundColor = getColor(c.background_color);

        // image styles
        if (this.img) {
            this.img.style.objectFit = c.fit;
            this.img.style.width = '100%';
            this.img.style.height = '100%';

            if (c.title) {
                this.img.alt = c.title;
                this.img.title = c.title;
            }
        }

        // clickable
        if (c.clickable) {
            element.classList.add('clickable');
            this.img.style.pointerEvents = 'auto';
            this.img.style.cursor = 'pointer';
        } else {
            element.classList.remove('clickable');
            this.img.style.pointerEvents = 'none';
            this.img.style.cursor = 'default';
        }
    }

    resize() {
        // No-op: the <img> fills the container via object-fit
    }

    /**
     * Accepts:
     *   - data URI string (recommended),
     *   - plain URL string,
     *   - { mime: "image/png", b64: "..." } object,
     *   - Blob / ArrayBuffer / Uint8Array (we'll convert to blob: URL).
     */
    updateImage(image_data) {
        let src = null;

        if (typeof image_data === 'string') {
            src = image_data;
        } else if (image_data && typeof image_data === 'object' && 'b64' in image_data) {
            const mime = image_data.mime || 'image/png';
            try {
                const binary = atob(image_data.b64);
                const len = binary.length;
                const bytes = new Uint8Array(len);
                for (let i = 0; i < len; i++) bytes[i] = binary.charCodeAt(i);
                const blob = new Blob([bytes], {type: mime});
                src = URL.createObjectURL(blob);
            } catch (e) {
                console.warn('Failed to decode base64 image payload', e);
                return;
            }
        } else if (image_data instanceof Blob) {
            src = URL.createObjectURL(image_data);
        } else if (image_data instanceof ArrayBuffer || image_data instanceof Uint8Array) {
            const buf = image_data instanceof Uint8Array ? image_data : new Uint8Array(image_data);
            const blob = new Blob([buf], {type: 'image/png'});
            src = URL.createObjectURL(blob);
        }

        if (!src) {
            console.warn('UpdatableImageWidget.updateImage: unsupported image_data', image_data);
            return;
        }

        this.img.src = src;
        this.configuration.image = src;
    }

    /**
     * Called when the backend sends an update payload.
     * Accept either a raw string or a full payload with { image, ... }.
     */
    update(data) {
        if (data && typeof data === 'object' && 'image' in data) {
            // Optionally merge new config bits (background, fit, title, etc.)
            const {image, ...rest} = data;
            if (Object.keys(rest).length) {
                this.updateConfig(rest);
            }
            this.updateImage(image);
        } else {
            this.updateImage(data);
        }
    }

    updateConfig(data) {
        this.configuration = {...this.configuration, ...data};
        this.configureElement(this.element);
        return undefined;
    }

    /** Wire up event listeners (click -> send to backend via callbacks) */
    assignListeners(el) {
        super.assignListeners(el);

        // Clear previous
        el.onmousedown = null;
        el.onmouseup = null;
        el.onmouseleave = null;
        el.onclick = null;

        if (this.configuration.clickable) {
            el.addEventListener('mousedown', () => el.classList.add('pressed'));
            el.addEventListener('mouseup', () => el.classList.remove('pressed'));
            el.addEventListener('mouseleave', () => el.classList.remove('pressed'));
            el.addEventListener('click', () => {
                this.callbacks.get('event').call({id: this.id, event: 'click', data: {}});
            });
        }
    }

    /** Return root DOM node */
    getElement() {
        return this.element;
    }
}

export class ImageWidget extends Widget {
    /**
     * @param {string} id – unique widget id
     * @param {Object} config – configuration object
     */
    constructor(id, config = {}) {
        super(id, config);

        // Defaults
        const defaults = {
            image: '',                // data URI or URL
            background_color: 'transparent',
            fit: 'contain',           // 'contain' | 'cover' | 'fill'
            title: null,
            clickable: false,
        };
        this.configuration = {...defaults, ...this.configuration};

        // Build DOM
        this.element = document.createElement('div');
        this.element.id = this.id;
        this.element.classList.add('widget', 'imageWidget');

        this.img = document.createElement('img');
        this.img.classList.add('imageWidget__img');
        this.element.appendChild(this.img);

        // Apply initial config
        this.configureElement(this.element);
        this.assignListeners(this.element);
    }

    /** Apply configuration to DOM */
    configureElement(element) {
        super.configureElement(element);
        const c = this.configuration;

        // Container style
        this.element.style.backgroundColor = getColor(c.background_color);

        // Image attributes & style
        this.img.src = c.image;
        this.img.style.objectFit = c.fit;
        this.img.style.width = '100%';
        this.img.style.height = '100%';

        // Accessibility
        if (c.title) {
            this.img.alt = c.title;
            this.img.title = c.title;
        }

        // Clickable
        if (c.clickable) {
            this.element.classList.add('clickable');
            this.img.style.pointerEvents = 'auto';
            this.img.style.cursor = 'pointer';
        } else {
            this.element.classList.remove('clickable');
            this.img.style.pointerEvents = 'none';
        }
    }

    /** Return the root element */
    getElement() {
        return this.element;
    }

    /** Update configuration and re-render */
    update(data) {

    }

    /** Wire up event listeners */
    assignListeners(el) {
        super.assignListeners(el);
        // Remove old listeners if re-assigning
        el.onmousedown = null;
        el.onmouseup = null;
        el.onmouseleave = null;
        el.onclick = null;

        if (this.configuration.clickable) {
            // Hover brightness is handled in CSS
            // Press animation
            el.addEventListener('mousedown', () => {
                el.classList.add('pressed');
            });
            el.addEventListener('mouseup', () => {
                el.classList.remove('pressed');
            });
            el.addEventListener('mouseleave', () => {
                el.classList.remove('pressed');
            });

            // Click event
            el.addEventListener('click', () => {
                this.callbacks.get('event').call({id: this.id, event: 'click', data: {}});
            });
        }
    }

    updateConfig(data) {
        this.configuration = {...this.configuration, ...data};
        this.configureElement(this.configuration);
    }

    initializeElement() {
    }

    resize() {
    }
}


// VideoWidget.js
export class VideoWidget extends Widget {
    constructor(id, config = {}) {
        super(id, config);

        // ── Defaults ────────────────────────────────────────────────────────────
        const defaults = {
            video_path: '',
            stream_type: 'mjpeg',
            fit: 'fill',
            enable_enlarge: true,
            enlarge_size: 1,
            enlarge_opacity: 0.75,
            overlay_bg_opacity: 0,
            enable_fullscreen: true,
            enable_refresh: true,
            enable_settings: true,
            clickable: false,
            title: null,
            title_font_size: 12,
            title_color: [1, 1, 1]
        };
        this.configuration = {...defaults, ...this.configuration};
        this._onSaveCallback = null;

        // ── Build main element ─────────────────────────────────────────────────
        this.element = document.createElement('div');
        this.element.id = this.id;
        this.element.classList.add('videoWidget', 'widget');

        // ── Media & overlay-media ──────────────────────────────────────────────
        this._createMediaElements();

        // ── Title overlay & error ──────────────────────────────────────────────
        this._setupTitleOverlay();
        this.media.addEventListener('error', () => this.showErrorText());

        // ── HUD overlay container ──────────────────────────────────────────────
        this.videoOverlay = document.createElement('div');
        this.videoOverlay.classList.add('videoWidget__videoOverlay');
        this.element.appendChild(this.videoOverlay);
        if (this.overlayText) this.videoOverlay.appendChild(this.overlayText);

        // ── Control buttons ────────────────────────────────────────────────────
        this._createControlButtons();

        // ── Enlarge lightbox overlay ───────────────────────────────────────────
        this._createEnlargeOverlay();

        // ── Settings overlay (inside widget) ──────────────────────────────────
        this._createSettingsOverlay();

        // ── Final wiring ───────────────────────────────────────────────────────
        this.configureElement(this.element);
        this.assignListeners(this.element);
    }

    // ── PRIVATE HELPERS ─────────────────────────────────────────────────────

    _createMediaElements() {
        const {stream_type} = this.configuration;
        this.media = document.createElement(stream_type === 'mjpeg' ? 'img' : 'video');
        if (stream_type !== 'mjpeg') this.media.controls = true;
        this.media.classList.add('videoWidget__media');
        this.element.appendChild(this.media);

        this.overlayMedia = document.createElement(stream_type === 'mjpeg' ? 'img' : 'video');
        if (stream_type !== 'mjpeg') this.overlayMedia.controls = true;
        this.overlayMedia.classList.add('videoWidget__overlayMedia');
    }

    _setupTitleOverlay() {
        if (!this.configuration.title) return;
        this.overlayText = document.createElement('div');
        this.overlayText.classList.add('videoWidget__overlayText');
        this.overlayText.textContent = this.configuration.title;
        this.overlayText.style.fontSize = `${this.configuration.title_font_size}pt`;
        this.overlayText.style.color = getColor(this.configuration.title_color);
        const loadEvt = this.media.tagName === 'IMG' ? 'load' : 'loadeddata';
        this.media.addEventListener(loadEvt, () => this.showOverlayTitle());
    }

    _createControlButtons() {
        const mk = (cls, txt) => {
            const b = document.createElement('button');
            b.classList.add('videoWidget__button', cls);
            b.textContent = txt;
            this.element.appendChild(b);
            return b;
        };
        if (this.configuration.enable_enlarge) this.enlargeBtn = mk('videoWidget__button--enlarge', '⬈');
        if (this.configuration.enable_fullscreen) this.fsBtn = mk('videoWidget__button--fullscreen', '⛶');
        if (this.configuration.enable_refresh) this.refreshBtn = mk('videoWidget__button--refresh', '🔄');
        if (this.configuration.enable_settings) this.settingsBtn = mk('videoWidget__button--settings', '⚙️');
    }

    _createEnlargeOverlay() {
        this.overlay = document.createElement('div');
        this.overlay.classList.add('videoWidget__overlay');
        this.overlay.style.background = `rgba(0,0,0,${this.configuration.overlay_bg_opacity})`;
        this.overlay.style.display = 'none';
        document.body.appendChild(this.overlay);
        this.overlay.appendChild(this.overlayMedia);

        this.closeBtn = document.createElement('button');
        this.closeBtn.classList.add('videoWidget__button', 'videoWidget__button--close');
        this.closeBtn.textContent = '✖';
        this.overlay.appendChild(this.closeBtn);
    }

    _createSettingsOverlay() {
        this.settingsOverlay = document.createElement('div');
        this.settingsOverlay.classList.add('videoWidget__settingsOverlay');
        this.element.appendChild(this.settingsOverlay);

        this.settingsContent = document.createElement('div');
        this.settingsContent.classList.add('videoWidget__settingsContent');
        this.settingsOverlay.appendChild(this.settingsContent);

        // close “X”
        this.closeSettingsBtn = document.createElement('button');
        this.closeSettingsBtn.textContent = '✖';
        this.closeSettingsBtn.classList.add('videoWidget__button', 'videoWidget__button--close-settings');
        this.settingsContent.appendChild(this.closeSettingsBtn);

        const makeField = (labelText, input) => {
            const w = document.createElement('div');
            w.style.margin = '8px 0';
            const lbl = document.createElement('label');
            lbl.textContent = labelText;
            lbl.style.display = 'block';
            w.append(lbl, input);
            return w;
        };

        // URL
        this.urlInput = document.createElement('input');
        this.urlInput.type = 'text';
        this.urlInput.value = this.configuration.video_path;
        this.settingsContent.appendChild(makeField('URL', this.urlInput));

        // Stream type
        this.streamTypeSelect = document.createElement('select');
        ['mjpeg', 'rtsp'].forEach(opt => {
            const o = document.createElement('option');
            o.value = opt;
            o.textContent = opt.toUpperCase();
            if (opt === this.configuration.stream_type) o.selected = true;
            this.streamTypeSelect.appendChild(o);
        });
        this.settingsContent.appendChild(makeField('Stream Type', this.streamTypeSelect));

        // Title
        this.titleInput = document.createElement('input');
        this.titleInput.type = 'text';
        this.titleInput.value = this.configuration.title || '';
        this.settingsContent.appendChild(makeField('Title', this.titleInput));

        // Save
        this.saveSettingsBtn = document.createElement('button');
        this.saveSettingsBtn.textContent = 'Save';
        this.saveSettingsBtn.classList.add('videoWidget__button', 'videoWidget__button--save-settings');
        this.settingsContent.appendChild(this.saveSettingsBtn);
    }

    registerOnSaveCallback(fn) {
        this._onSaveCallback = fn;
    }

    getElement() {
        return this.element;
    }

    updateConfig(data) {
        this.configuration = {...this.configuration, ...data};
        this.configureElement(this.element);
    }

    configureElement(element) {
        super.configureElement(element);
        const src = this._getStreamUrl();

        [this.media, this.overlayMedia].forEach(m => {
            m.src = src;
            m.style.objectFit = this.configuration.fit;
            m.style.display = 'block';       // ensure visible
            m.style.visibility = 'visible';
        });

        this.overlay.style.background = `rgba(0,0,0,${this.configuration.overlay_bg_opacity})`;
        this.overlayMedia.style.opacity = this.configuration.enlarge_opacity;

        if (this.overlayText) {
            this.overlayText.textContent = this.configuration.title;
            this.overlayText.style.display = 'block';
        }
        if (this.errorText) {
            this.errorText.textContent = src;
        }
    }

    assignListeners(element) {
        super.assignListeners(element);
        if (this.configuration.clickable) {
            this.media.style.cursor = 'pointer';
            this.media.addEventListener('click', () => this.callbacks.get('event').call({
                id: this.id,
                event: 'click',
                data: {}
            }));
        }
        if (this.enlargeBtn) this.enlargeBtn.addEventListener('click', () => {
            this.callbacks.get('event').call({id: this.id, event: 'enlarge'});
            this.showOverlay();
        });
        if (this.fsBtn) this.fsBtn.addEventListener('click', () => {
            this.callbacks.get('event').call({id: this.id, event: 'fullscreen'});
            this.openFullscreenPage();
        });
        if (this.refreshBtn) this.refreshBtn.addEventListener('click', () => {
            this.callbacks.get('event').call({id: this.id, event: 'refresh'});
            this.reloadStream();
        });
        this.closeBtn.addEventListener('click', () => {
            this.callbacks.get('event').call({id: this.id, event: 'close'});
            this.hideOverlay();
        });
        this.overlay.addEventListener('click', e => {
            if (e.target === this.overlay) this.hideOverlay();
        });

        if (this.settingsBtn) this.settingsBtn.addEventListener('click', () => this.showSettingsOverlay());
        this.closeSettingsBtn.addEventListener('click', () => this.hideSettingsOverlay());
        this.settingsOverlay.addEventListener('click', e => {
            if (e.target === this.settingsOverlay) this.hideSettingsOverlay();
        });
        this.saveSettingsBtn.addEventListener('click', () => {
            this.configuration.video_path = this.urlInput.value;
            this.configuration.stream_type = this.streamTypeSelect.value;
            this.configuration.title = this.titleInput.value;
            this.configureElement(this.element);
            this.reloadStream();
            this.hideSettingsOverlay();
            if (typeof this._onSaveCallback === 'function') this._onSaveCallback({...this.configuration});
        });
    }

    _getStreamUrl() {
        return this.configuration.video_path;
    }

    showOverlay() {
        const pct = Math.min(Math.max(this.configuration.enlarge_size, 0), 1);
        const mw = window.innerWidth * pct, mh = window.innerHeight * pct;
        this.overlayMedia.style.width = `${mw}px`;
        this.overlayMedia.style.maxHeight = `${mh}px`;
        this.media.style.visibility = 'hidden';
        this.element.style.background = 'transparent';
        this.overlay.style.display = 'flex';
    }

    hideOverlay() {
        this.overlay.style.display = 'none';
        this.media.style.visibility = '';
        this.media.style.display = 'block';
        this.element.style.background = '';
        if (this.errorText) this.errorText.style.display = 'none';
    }

    showSettingsOverlay() {
        this.urlInput.value = this.configuration.video_path;
        this.streamTypeSelect.value = this.configuration.stream_type;
        this.titleInput.value = this.configuration.title || '';
        this.settingsOverlay.style.display = 'flex';
    }

    hideSettingsOverlay() {
        this.settingsOverlay.style.display = 'none';
    }

    openFullscreenPage() {
        window.open(this._getStreamUrl(), '_blank');
    }

    reloadStream() {
        this.media.style.display = 'block';  // restore if hidden by error
        if (this.errorText) this.errorText.style.display = 'none';
        if (this.overlayText) this.overlayText.style.display = 'block';

        if (this.configuration.stream_type === 'mjpeg') {
            const base = this._getStreamUrl();
            const sep = base.includes('?') ? '&' : '?';
            const fresh = `${base}${sep}_=${Date.now()}`;
            this.media.src = fresh;
            this.overlayMedia.src = fresh;
        } else {
            this.media.load();
            this.overlayMedia.load();
            this.media.play().catch(() => {
            });
            this.overlayMedia.play().catch(() => {
            });
        }
    }

    showErrorText() {
        this.media.style.display = 'none';
        if (!this.errorText) {
            this.errorText = document.createElement('div');
            this.errorText.classList.add('videoWidget__errorText');
            this.element.appendChild(this.errorText);
            window.addEventListener('resize', () => this.updateErrorTextSize());
        }
        this.errorText.textContent = this._getStreamUrl();
        if (this.overlayText) this.overlayText.style.display = 'block';
        this.updateErrorTextSize();
        this.errorText.style.display = 'flex';
    }

    updateErrorTextSize() {
        const r = this.element.getBoundingClientRect();
        this.errorText.style.fontSize = `${Math.min(r.width, r.height) * 0.05}px`;
    }

    showOverlayTitle() {
        if (this.overlayText) this.overlayText.style.display = 'block';
    }

    registerOverlay(fn) {
        this._customOverlayFn = fn;
        fn(this.videoOverlay, this.media);
    }
}
