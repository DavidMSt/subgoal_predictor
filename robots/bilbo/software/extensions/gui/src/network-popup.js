/**
 * Network Monitor popup window.
 *
 * Connects via Socket.io to the network monitor server (default port 8500)
 * and displays internet status, monitored hosts, network devices, and an event log.
 *
 * URL params: host, port, title
 */

import { io } from 'socket.io-client';

// ─── CSS ─────────────────────────────────────────────────────────────────────

const STYLE = document.createElement('style');
STYLE.textContent = `
/* Header */
.nm-header {
    height: 28px; min-height: 28px;
    display: flex; align-items: center; justify-content: space-between;
    padding: 0 10px;
    background: #111118;
    border-bottom: 1px solid #1e1e2a;
    font-size: 11px; font-weight: 600; color: #888;
    user-select: none;
}
.nm-header .nm-title { color: #aaa; }
.nm-conn-dot {
    width: 7px; height: 7px; border-radius: 50%;
    background: #555; display: inline-block; margin-left: 6px;
    transition: background 0.3s;
}
.nm-conn-dot.connected { background: #4a4; }

/* Content row */
.nm-content {
    flex: 1; min-height: 0;
    display: flex; gap: 1px;
    background: #0e0e14;
    overflow: hidden;
}

/* Cards / columns */
.nm-card {
    flex: 1; min-width: 0;
    display: flex; flex-direction: column;
    background: #0e0e14;
    overflow: hidden;
}
.nm-card-title {
    padding: 5px 8px;
    font-size: 9px; font-weight: 700;
    text-transform: uppercase; letter-spacing: 0.8px;
    color: #556; border-bottom: 1px solid #1a1a24;
    flex-shrink: 0;
}
.nm-card-body {
    flex: 1; overflow-y: auto; padding: 4px 0;
}
.nm-card-body::-webkit-scrollbar { width: 4px; }
.nm-card-body::-webkit-scrollbar-thumb { background: #222; border-radius: 2px; }

/* Internet card */
.nm-internet { max-width: 180px; min-width: 140px; flex: 0 0 auto; }
.nm-inet-row {
    display: flex; justify-content: space-between; align-items: center;
    padding: 3px 8px; font-size: 11px;
}
.nm-inet-row .label { color: #667; }
.nm-inet-row .value { color: #aab; font-weight: 500; }
.nm-inet-status {
    padding: 6px 8px; text-align: center;
    font-size: 13px; font-weight: 700;
}
.nm-inet-status.online { color: #5c5; }
.nm-inet-status.offline { color: #c55; }

/* Host / device rows */
.nm-row {
    display: flex; align-items: center; gap: 6px;
    padding: 3px 8px; font-size: 11px;
    border-bottom: 1px solid #12121a;
}
.nm-row:hover { background: #14141e; }
.nm-dot {
    width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0;
}
.nm-dot.online { background: #4a4; }
.nm-dot.offline { background: #a44; }
.nm-dot.unknown { background: #664; }
.nm-row .nm-name { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: #bbc; }
.nm-row .nm-detail { color: #556; font-size: 10px; white-space: nowrap; width: 100px; text-align: right; flex-shrink: 0; }
.nm-row .nm-conn-type { color: #668; font-size: 10px; white-space: nowrap; width: 70px; text-align: right; flex-shrink: 0; overflow: hidden; text-overflow: ellipsis; }

/* Devices card extras */
.nm-devices .nm-card-title {
    display: flex; align-items: center; justify-content: space-between;
}
.nm-scan-btn {
    font-size: 9px; padding: 1px 6px; cursor: pointer;
    background: #1a1a28; color: #779; border: 1px solid #2a2a3a; border-radius: 3px;
    font-family: inherit;
}
.nm-scan-btn:hover { background: #222238; color: #99b; }
.nm-scan-btn:active { background: #2a2a40; }

/* Log */
.nm-log {
    height: 80px; min-height: 60px; max-height: 120px; flex-shrink: 0;
    border-top: 1px solid #1a1a24;
    background: #08080c;
    overflow-y: auto; padding: 3px 0;
}
.nm-log::-webkit-scrollbar { width: 4px; }
.nm-log::-webkit-scrollbar-thumb { background: #222; border-radius: 2px; }
.nm-log-entry {
    padding: 1px 8px; font-size: 10px; color: #556;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.nm-log-entry .ts { color: #334; margin-right: 6px; }
.nm-log-entry.info { color: #668; }
.nm-log-entry.warn { color: #a86; }
.nm-log-entry.error { color: #a55; }
.nm-log-entry.success { color: #5a5; }
`;
document.head.appendChild(STYLE);

// ─── URL PARAMS ──────────────────────────────────────────────────────────────

const params = new URLSearchParams(window.location.search);
const serverHost = params.get('host') || window.location.hostname || 'localhost';
const serverPort = params.get('port') || '8500';
const titleParam = params.get('title') || 'Network Monitor';
document.title = titleParam;

// ─── STATE ───────────────────────────────────────────────────────────────────

let internetState = {};
let monitoredHosts = [];          // array from init / ping_update
let devices = [];                 // array from init / devices_update
let openwrtData = null;           // full openwrt object
let openwrtByMac = {};            // MAC → client
let openwrtByIp = {};             // IP → client
let openwrtByHostname = {};       // hostname → client

const MAX_LOG = 200;
const logEntries = [];

// ─── BUILD DOM ───────────────────────────────────────────────────────────────

const root = document.getElementById('network-root');

// Header
const header = el('div', 'nm-header');
const titleEl = el('span', 'nm-title');
titleEl.textContent = titleParam;
const connDot = el('span', 'nm-conn-dot');
const headerRight = el('span');
headerRight.appendChild(document.createTextNode('Socket.io '));
headerRight.appendChild(connDot);
header.appendChild(titleEl);
header.appendChild(headerRight);
root.appendChild(header);

// Content row
const content = el('div', 'nm-content');
root.appendChild(content);

// Internet card
const internetCard = makeCard('Internet', 'nm-internet');
content.appendChild(internetCard.wrapper);

// Hosts card
const hostsCard = makeCard('Monitored Hosts');
content.appendChild(hostsCard.wrapper);

// Devices card (with scan button)
const devicesCard = makeCard('Network Devices', 'nm-devices');
const scanBtn = el('button', 'nm-scan-btn');
scanBtn.textContent = 'Scan';
devicesCard.titleEl.appendChild(scanBtn);
content.appendChild(devicesCard.wrapper);

// Log
const logEl = el('div', 'nm-log');
root.appendChild(logEl);

// ─── SOCKET.IO ───────────────────────────────────────────────────────────────

const serverUrl = `http://${serverHost}:${serverPort}`;
const socket = io(serverUrl, {
    transports: ['websocket', 'polling'],
    reconnection: true,
    reconnectionDelay: 2000,
});

socket.on('connect', () => {
    connDot.classList.add('connected');
    log('Connected to network monitor', 'success');
});

socket.on('disconnect', () => {
    connDot.classList.remove('connected');
    log('Disconnected', 'warn');
});

socket.on('connect_error', (err) => {
    connDot.classList.remove('connected');
    log(`Connection error: ${err.message}`, 'error');
});

socket.on('init', (data) => {
    if (data.internet) {
        internetState = data.internet;
        renderInternet();
    }
    if (data.monitored) {
        monitoredHosts = data.monitored;
        renderHosts();
    }
    if (data.devices) {
        devices = data.devices;
        renderDevices();
    }
    if (data.openwrt) {
        setOpenwrt(data.openwrt);
        // Re-render with connection type info
        renderHosts();
        renderDevices();
    }
    log('Received initial state', 'info');
});

socket.on('internet_update', (data) => {
    const wasOnline = internetState.connected;
    internetState = data;
    renderInternet();
    if (wasOnline !== undefined && wasOnline !== data.connected) {
        log(`Internet ${data.connected ? 'online' : 'offline'}`, data.connected ? 'success' : 'error');
    }
});

socket.on('ping_update', (data) => {
    const idx = monitoredHosts.findIndex(h => h.hostname === data.hostname);
    if (idx >= 0) {
        const prev = monitoredHosts[idx];
        if (prev.status !== data.status) {
            log(`${data.description || data.hostname}: ${data.status}`, data.status === 'online' ? 'success' : 'warn');
        }
        monitoredHosts[idx] = data;
    } else {
        monitoredHosts.push(data);
        log(`New host: ${data.description || data.hostname}`, 'info');
    }
    renderHosts();
});

socket.on('devices_update', (data) => {
    const prevCount = devices.length;
    devices = data;
    renderDevices();
    if (prevCount !== data.length) {
        log(`Devices: ${data.length} found`, 'info');
    }
});

socket.on('openwrt_update', (data) => {
    setOpenwrt(data);
    renderHosts();
    renderDevices();
});

socket.on('host_removed', (data) => {
    monitoredHosts = monitoredHosts.filter(h => h.hostname !== data.hostname);
    renderHosts();
    log(`Host removed: ${data.description || data.hostname}`, 'warn');
});

// Scan button
scanBtn.addEventListener('click', () => {
    socket.emit('request_scan');
    log('Scan requested', 'info');
    scanBtn.disabled = true;
    setTimeout(() => { scanBtn.disabled = false; }, 3000);
});

// ─── OPENWRT LOOKUP ──────────────────────────────────────────────────────────

function setOpenwrt(data) {
    openwrtData = data;
    openwrtByMac = {};
    openwrtByIp = {};
    openwrtByHostname = {};
    if (data && data.clients) {
        for (const c of data.clients) {
            if (c.mac) openwrtByMac[c.mac.toLowerCase()] = c;
            if (c.ip) openwrtByIp[c.ip] = c;
            if (c.hostname) openwrtByHostname[c.hostname.toLowerCase()] = c;
        }
    }
}

function baseHostname(name) {
    if (!name) return '';
    return name.toLowerCase().replace(/\.(local|lan|home|localdomain)$/, '');
}

function findDeviceMac(ip, hostname) {
    // Try by IP
    if (ip) {
        const dev = devices.find(d => d.ip === ip);
        if (dev && dev.mac) return dev.mac.toLowerCase();
    }
    // Try by hostname (exact then base match)
    if (hostname) {
        const base = baseHostname(hostname);
        const dev = devices.find(d => {
            if (!d.hostname) return false;
            const devBase = baseHostname(d.hostname);
            return devBase === base;
        });
        if (dev && dev.mac) return dev.mac.toLowerCase();
    }
    return null;
}

function getConnectionType(ip, mac, hostname) {
    let client = null;

    // Direct lookups against OpenWRT data
    if (ip) client = openwrtByIp[ip];
    if (!client && mac) client = openwrtByMac[mac.toLowerCase()];
    if (!client && hostname) {
        const hn = hostname.toLowerCase();
        client = openwrtByHostname[hn];
        if (!client) client = openwrtByHostname[baseHostname(hostname)];
    }

    // Cross-reference: find MAC via ARP devices (by IP or hostname), then look up in OpenWRT
    if (!client) {
        const deviceMac = findDeviceMac(ip, hostname) || (mac ? mac.toLowerCase() : null);
        if (deviceMac) {
            client = openwrtByMac[deviceMac];
            // If MAC found in ARP but not in OpenWRT WiFi clients → Ethernet
            if (!client && openwrtData && openwrtData.router_online) return 'Ethernet';
        }
    }

    if (!client) return '--';
    if (client.is_wireless && client.ssid) return client.ssid;
    if (client.is_wireless) return 'WiFi';
    return 'Ethernet';
}

// ─── RENDER: INTERNET ────────────────────────────────────────────────────────

function renderInternet() {
    const body = internetCard.body;
    const s = internetState;
    const online = s.connected;

    body.innerHTML = '';

    const status = el('div', `nm-inet-status ${online ? 'online' : 'offline'}`);
    status.textContent = online ? 'ONLINE' : 'OFFLINE';
    body.appendChild(status);

    addInetRow(body, 'Latency', s.latency_ms != null ? `${Math.round(s.latency_ms)} ms` : '--');
    addInetRow(body, 'DNS', s.dns_working ? 'OK' : s.dns_working === false ? 'Fail' : '--');
    addInetRow(body, 'Gateway', s.gateway_reachable ? 'OK' : s.gateway_reachable === false ? 'Fail' : '--');

    if (openwrtData) {
        if (openwrtData.wireless_clients != null) {
            addInetRow(body, 'WiFi clients', String(openwrtData.wireless_clients));
        }
        if (openwrtData.connected_clients != null) {
            addInetRow(body, 'All clients', String(openwrtData.connected_clients));
        }
    }
}

function addInetRow(parent, label, value) {
    const row = el('div', 'nm-inet-row');
    const l = el('span', 'label');
    l.textContent = label;
    const v = el('span', 'value');
    v.textContent = value;
    row.appendChild(l);
    row.appendChild(v);
    parent.appendChild(row);
}

// ─── RENDER: HOSTS ───────────────────────────────────────────────────────────

function renderHosts() {
    const body = hostsCard.body;
    body.innerHTML = '';

    if (monitoredHosts.length === 0) {
        const empty = el('div', 'nm-row');
        empty.style.color = '#445';
        empty.textContent = 'No monitored hosts';
        body.appendChild(empty);
        return;
    }

    // Sort: online first, then by description/hostname
    const sorted = [...monitoredHosts].sort((a, b) => {
        if (a.status === 'online' && b.status !== 'online') return -1;
        if (a.status !== 'online' && b.status === 'online') return 1;
        return (a.description || a.hostname).localeCompare(b.description || b.hostname);
    });

    for (const h of sorted) {
        const row = el('div', 'nm-row');

        const dot = el('span', `nm-dot ${h.status || 'unknown'}`);
        row.appendChild(dot);

        const name = el('span', 'nm-name');
        name.textContent = h.description || h.hostname;
        name.title = `${h.hostname}${h.ip ? ' (' + h.ip + ')' : ''}`;
        row.appendChild(name);

        const latency = el('span', 'nm-detail');
        latency.textContent = h.status === 'online' && h.latency_ms != null ? `${Math.round(h.latency_ms)}ms` : '';
        row.appendChild(latency);

        const conn = el('span', 'nm-conn-type');
        conn.textContent = getConnectionType(h.ip, null, h.hostname);
        row.appendChild(conn);

        body.appendChild(row);
    }
}

// ─── RENDER: DEVICES ─────────────────────────────────────────────────────────

function renderDevices() {
    const body = devicesCard.body;
    body.innerHTML = '';

    if (devices.length === 0) {
        const empty = el('div', 'nm-row');
        empty.style.color = '#445';
        empty.textContent = 'No devices found';
        body.appendChild(empty);
        return;
    }

    // Sort by hostname/IP
    const sorted = [...devices].sort((a, b) => {
        const na = a.hostname || a.ip || '';
        const nb = b.hostname || b.ip || '';
        return na.localeCompare(nb);
    });

    for (const d of sorted) {
        const row = el('div', 'nm-row');

        const name = el('span', 'nm-name');
        name.textContent = d.hostname || d.ip;
        name.title = `IP: ${d.ip}\nMAC: ${d.mac || '--'}${d.vendor ? '\nVendor: ' + d.vendor : ''}`;
        row.appendChild(name);

        const ip = el('span', 'nm-detail');
        ip.textContent = d.hostname ? d.ip : '';
        row.appendChild(ip);

        const conn = el('span', 'nm-conn-type');
        conn.textContent = getConnectionType(d.ip, d.mac);
        row.appendChild(conn);

        body.appendChild(row);
    }
}

// ─── LOG ─────────────────────────────────────────────────────────────────────

function log(message, level = 'info') {
    const now = new Date();
    const ts = `${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`;

    const entry = el('div', `nm-log-entry ${level}`);
    const tsSpan = el('span', 'ts');
    tsSpan.textContent = ts;
    entry.appendChild(tsSpan);
    entry.appendChild(document.createTextNode(message));
    logEl.appendChild(entry);

    logEntries.push(entry);
    if (logEntries.length > MAX_LOG) {
        const old = logEntries.shift();
        old.remove();
    }

    logEl.scrollTop = logEl.scrollHeight;
}

// ─── HELPERS ─────────────────────────────────────────────────────────────────

function el(tag, className) {
    const e = document.createElement(tag);
    if (className) e.className = className;
    return e;
}

function makeCard(title, extraClass) {
    const wrapper = el('div', `nm-card${extraClass ? ' ' + extraClass : ''}`);
    const titleEl = el('div', 'nm-card-title');
    titleEl.textContent = title;
    const body = el('div', 'nm-card-body');
    wrapper.appendChild(titleEl);
    wrapper.appendChild(body);
    return { wrapper, titleEl, body };
}

function pad(n) { return String(n).padStart(2, '0'); }
