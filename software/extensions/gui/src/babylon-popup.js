import {BabylonContainer} from "@babylon_vis/babylon.js";

window.addEventListener('DOMContentLoaded', () => {
    const params = new URLSearchParams(window.location.search);
    const id = params.get('id') || 'babylon';
    const host = params.get('host') || 'localhost';
    const port = params.get('port') || '9000';
    const title = params.get('title') || 'Babylon Visualization';

    document.title = title;

    const root = document.getElementById('babylon-root');

    const payload = {
        config: {
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
