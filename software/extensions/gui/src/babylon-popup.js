import {BabylonContainer} from "@babylon_vis/babylon.js";

window.addEventListener('DOMContentLoaded', () => {
    const params = new URLSearchParams(window.location.search);
    const id = params.get('id') || 'babylon';
    const host = params.get('host') || 'localhost';
    const port = params.get('port') || '9000';
    const title = params.get('title') || 'Babylon Visualization';

    document.title = title;

    const root = document.getElementById('babylon-root');

    // Try to load the full config stored by the popout button
    const storageKey = `babylon_config_${id}`;
    let storedConfig = {};
    try {
        const raw = sessionStorage.getItem(storageKey);
        if (raw) {
            storedConfig = JSON.parse(raw);
            sessionStorage.removeItem(storageKey);
        }
    } catch (e) {
        console.warn('Failed to load stored babylon config:', e);
    }

    const payload = {
        config: {
            ...storedConfig,
            websocket_host: host,
            websocket_port: port,
            widget_controls_position: 'inside',
            title: title,
        },
        objects: {},
    };

    const container = new BabylonContainer(id, root, payload);
    container.onFirstShow();
});
