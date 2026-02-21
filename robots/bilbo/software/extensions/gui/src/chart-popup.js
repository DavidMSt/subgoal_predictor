import {RT_Plot} from "./lib/plot/realtime/rt_plot.js";

window.addEventListener('DOMContentLoaded', () => {
    const params = new URLSearchParams(window.location.search);
    const id = params.get('id') || 'chart';
    const host = params.get('host') || 'localhost';
    const port = params.get('port') || '8800';
    const title = params.get('title') || 'Chart';

    document.title = title;

    const root = document.getElementById('chart-root');

    const payload = {
        config: {},
        y_axes: {},
        timeseries: {},
        websocket: {
            host: host,
            port: port,
        },
    };

    const plot = new RT_Plot(id, root, payload);
});
