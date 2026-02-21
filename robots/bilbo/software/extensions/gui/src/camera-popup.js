/**
 * Camera popup window — opened from the CameraWidget's floating panel.
 *
 * Communicates with the main window's CameraWidget via BroadcastChannel.
 * Initial state (cameras, stream URL, rotation, crop) is passed through sessionStorage.
 */

window.addEventListener('DOMContentLoaded', () => {
    const params = new URLSearchParams(window.location.search);
    const widgetId = params.get('widget_id') || 'camera';
    const title = params.get('title') || 'Camera';
    document.title = title;

    // --- Load initial state from sessionStorage ---
    const storageKey = `camera_popup_${widgetId}`;
    let state = {cameras: {}, selected: null, stream_url: null, rotation: 0, crop: null};
    try {
        const raw = sessionStorage.getItem(storageKey);
        if (raw) {
            state = {...state, ...JSON.parse(raw)};
            sessionStorage.removeItem(storageKey);
        }
    } catch (e) {
        console.warn('Failed to load camera popup state:', e);
    }

    let rotation = state.rotation || 0;
    let cropRegion = state.crop || null;
    let streamUrl = state.stream_url;

    // --- BroadcastChannel for communication with the main window ---
    const channel = new BroadcastChannel(`camera_widget_${widgetId}`);

    // --- Build UI ---
    const root = document.getElementById('camera-root');

    // Toolbar
    const toolbar = document.createElement('div');
    toolbar.classList.add('cam-toolbar');
    root.appendChild(toolbar);

    const select = document.createElement('select');
    populateDropdown(select, state.cameras, state.selected);
    toolbar.appendChild(select);

    const rotateBtn = mkBtn('↻', 'Rotate 90°');
    const cropBtn = mkBtn('✂', 'Crop');
    const uncropBtn = mkBtn('↩', 'Remove crop');
    uncropBtn.style.display = cropRegion ? '' : 'none';

    // View area
    const view = document.createElement('div');
    view.classList.add('cam-view');
    root.appendChild(view);

    const img = document.createElement('img');
    view.appendChild(img);

    // Crop overlay
    const cropOverlay = document.createElement('div');
    cropOverlay.classList.add('cam-crop-overlay');
    view.appendChild(cropOverlay);

    const cropSelection = document.createElement('div');
    cropSelection.classList.add('cam-crop-selection');
    cropOverlay.appendChild(cropSelection);

    // --- Initial stream ---
    if (streamUrl) setStream(streamUrl);

    // Apply initial state
    applyRotation();
    if (cropRegion) applyCrop(cropRegion);

    // --- Event listeners ---
    select.addEventListener('change', () => {
        const key = select.value;
        if (!key) return;
        channel.postMessage({type: 'camera_select', camera_key: key});
    });

    rotateBtn.addEventListener('click', () => {
        rotation = (rotation + 90) % 360;
        applyRotation();
        channel.postMessage({type: 'rotation', rotation});
    });

    cropBtn.addEventListener('click', () => enterCropMode());

    uncropBtn.addEventListener('click', () => {
        clearCrop();
        channel.postMessage({type: 'crop', crop: null});
    });

    // --- BroadcastChannel incoming messages ---
    channel.onmessage = (e) => {
        const msg = e.data;
        if (!msg || !msg.type) return;

        switch (msg.type) {
            case 'stream_url':
                streamUrl = msg.stream_url;
                setStream(streamUrl);
                break;
            case 'cameras':
                populateDropdown(select, msg.cameras, msg.selected);
                break;
            case 'close':
                window.close();
                break;
        }
    };

    // Notify main window that the popup is open
    channel.postMessage({type: 'popup_opened'});

    // Notify on close
    window.addEventListener('beforeunload', () => {
        channel.postMessage({type: 'popup_closed'});
    });

    // --- Helpers ---

    function mkBtn(text, tooltip) {
        const b = document.createElement('button');
        b.textContent = text;
        b.title = tooltip;
        toolbar.appendChild(b);
        return b;
    }

    function populateDropdown(sel, cameras, selected) {
        sel.innerHTML = '';
        const entries = Object.entries(cameras || {});
        entries.sort((a, b) => (a[1].label || '').localeCompare(b[1].label || ''));

        if (entries.length === 0) {
            const opt = document.createElement('option');
            opt.value = '';
            opt.textContent = 'No cameras available';
            opt.disabled = true;
            opt.selected = true;
            sel.appendChild(opt);
            sel.disabled = true;
            return;
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

    function setStream(url) {
        if (!url) { img.style.display = 'none'; return; }
        const sep = url.includes('?') ? '&' : '?';
        img.src = `${url}${sep}_=${Date.now()}`;
        img.style.display = '';
    }

    function applyRotation() {
        if (rotation % 180 !== 0) {
            const rect = view.getBoundingClientRect();
            const scale = Math.min(rect.height / rect.width, rect.width / rect.height);
            img.style.transform = `rotate(${rotation}deg) scale(${scale})`;
        } else {
            img.style.transform = rotation ? `rotate(${rotation}deg)` : '';
        }
    }

    // Recompute rotation scaling on resize
    window.addEventListener('resize', () => {
        if (rotation % 180 !== 0) applyRotation();
    });

    function applyCrop(region) {
        cropRegion = region;
        const top = region.y * 100;
        const right = (1 - region.x - region.w) * 100;
        const bottom = (1 - region.y - region.h) * 100;
        const left = region.x * 100;
        img.style.objectViewBox = `inset(${top}% ${right}% ${bottom}% ${left}%)`;
        uncropBtn.style.display = '';
    }

    function clearCrop() {
        cropRegion = null;
        img.style.objectViewBox = '';
        uncropBtn.style.display = 'none';
    }

    function enterCropMode() {
        if (!img.naturalWidth || !img.naturalHeight) return;

        // Clear existing crop so user draws on full image
        if (cropRegion) {
            img.style.objectViewBox = '';
            cropRegion = null;
            uncropBtn.style.display = 'none';
        }

        cropOverlay.style.display = 'block';
        cropSelection.style.display = 'none';
        let startX, startY, dragging = false;

        const cleanup = () => {
            cropOverlay.removeEventListener('mousedown', onDown);
            document.removeEventListener('mousemove', onMove);
            document.removeEventListener('mouseup', onUp);
            document.removeEventListener('keydown', onKey);
            cropOverlay.style.display = 'none';
            cropSelection.style.display = 'none';
        };

        const onDown = (e) => {
            if (e.button !== 0) { cleanup(); return; }
            e.preventDefault();
            const r = view.getBoundingClientRect();
            startX = e.clientX - r.left;
            startY = e.clientY - r.top;
            dragging = true;
            cropSelection.style.left = startX + 'px';
            cropSelection.style.top = startY + 'px';
            cropSelection.style.width = '0';
            cropSelection.style.height = '0';
            cropSelection.style.display = 'block';
        };

        const onMove = (e) => {
            if (!dragging) return;
            const r = view.getBoundingClientRect();
            const curX = Math.max(0, Math.min(r.width, e.clientX - r.left));
            const curY = Math.max(0, Math.min(r.height, e.clientY - r.top));
            cropSelection.style.left = Math.min(startX, curX) + 'px';
            cropSelection.style.top = Math.min(startY, curY) + 'px';
            cropSelection.style.width = Math.abs(curX - startX) + 'px';
            cropSelection.style.height = Math.abs(curY - startY) + 'px';
        };

        const onUp = (e) => {
            if (!dragging) return;
            dragging = false;
            const r = view.getBoundingClientRect();
            const curX = Math.max(0, Math.min(r.width, e.clientX - r.left));
            const curY = Math.max(0, Math.min(r.height, e.clientY - r.top));

            // Map to image-relative coordinates
            const ir = getContainedImageRect();
            if (!ir) { cleanup(); return; }

            const selL = Math.min(startX, curX);
            const selT = Math.min(startY, curY);
            const selW = Math.abs(curX - startX);
            const selH = Math.abs(curY - startY);

            // Apply inverse rotation to get image coords
            const tl = viewToImageCoords(selL, selT, r, ir);
            const br = viewToImageCoords(selL + selW, selT + selH, r, ir);
            if (!tl || !br) { cleanup(); return; }

            const x1 = Math.max(0, Math.min(1, Math.min(tl.x, br.x)));
            const y1 = Math.max(0, Math.min(1, Math.min(tl.y, br.y)));
            const x2 = Math.max(0, Math.min(1, Math.max(tl.x, br.x)));
            const y2 = Math.max(0, Math.min(1, Math.max(tl.y, br.y)));
            const region = {x: x1, y: y1, w: x2 - x1, h: y2 - y1};

            cleanup();

            if (region.w < 0.05 || region.h < 0.05) return;

            applyCrop(region);
            channel.postMessage({type: 'crop', crop: region});
        };

        const onKey = (e) => { if (e.key === 'Escape') cleanup(); };

        cropOverlay.addEventListener('mousedown', onDown);
        document.addEventListener('mousemove', onMove);
        document.addEventListener('mouseup', onUp);
        document.addEventListener('keydown', onKey);
    }

    function getContainedImageRect() {
        const cW = view.clientWidth;
        const cH = view.clientHeight;
        const nW = img.naturalWidth;
        const nH = img.naturalHeight;
        if (!nW || !nH) return null;
        const scale = Math.min(cW / nW, cH / nH);
        const displayW = nW * scale;
        const displayH = nH * scale;
        return {
            offsetX: (cW - displayW) / 2,
            offsetY: (cH - displayH) / 2,
            displayW, displayH,
        };
    }

    function viewToImageCoords(px, py, viewRect, ir) {
        const cx = viewRect.width / 2, cy = viewRect.height / 2;
        const theta = -rotation * Math.PI / 180;
        const s = (rotation % 180 !== 0) ? Math.min(viewRect.height / viewRect.width, viewRect.width / viewRect.height) : 1;
        const dx = px - cx, dy = py - cy;
        const cosT = Math.cos(theta), sinT = Math.sin(theta);
        const ex = (dx * cosT - dy * sinT) / s + cx;
        const ey = (dx * sinT + dy * cosT) / s + cy;
        return {x: (ex - ir.offsetX) / ir.displayW, y: (ey - ir.offsetY) / ir.displayH};
    }
});
