import {Map} from "./lib/map/map.js";

window.addEventListener('DOMContentLoaded', () => {
    const params = new URLSearchParams(window.location.search);
    const id = params.get('id') || 'map';
    const host = params.get('host') || 'localhost';
    const port = params.get('port') || '8700';
    const title = params.get('title') || 'Map';

    document.title = title;

    const root = document.getElementById('map-root');

    const payload = {
        config: {},
        objects: {},
        groups: {},
        websocket: {
            host: host,
            port: port,
        },
    };

    const map = new Map(id, root, payload);
});
