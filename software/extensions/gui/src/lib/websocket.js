import {EventEmitter} from 'events';

// const WebSocket = require('ws');

export class Websocket extends EventEmitter {
    constructor({host, port, options = {}}) {
        super();

        const default_options = {
            reconnect_pause: 1000, // ms (base delay, will increase on consecutive failures)
            reconnect_pause_max: 10000, // ms (max delay between reconnects)
            reconnect: true,
        }

        this.options = {
            ...default_options,
            ...(options || {})  // safely spread even if options is undefined
        };

        this.url = `ws://${host}:${port}`;
        this.connected = false;
        this.txQueue = [];
        this._reconnectAttempts = 0;
        this._connecting = false; // Prevent overlapping connection attempts
        this._reconnectTimer = null;
        this._connectionTimeout = null;
        this._connectionTimeoutMs = 3000; // If onopen doesn't fire within this time, retry
        this._probeSocket = null; // Dummy socket to work around iOS Safari bug
    }

    // -----------------------------------------------------------------------------------------------------------------
    close() {
        // Cancel any pending reconnect
        if (this._reconnectTimer) {
            clearTimeout(this._reconnectTimer);
            this._reconnectTimer = null;
        }

        // Cancel any pending connection timeout
        if (this._connectionTimeout) {
            clearTimeout(this._connectionTimeout);
            this._connectionTimeout = null;
        }

        this._connecting = false;

        // Close probe socket
        this._closeProbeSocket();

        if (this.socket) {
            try {
                this.socket.onclose = null;
                this.socket.onerror = null;
                this.socket.onopen = null;
                this.socket.onmessage = null;
                this.socket.close();
            } catch (e) {}
            this.socket = null;
            this.connected = false;
            this.txQueue = [];
            console.log("WebSocket closed");
        }
    }

    // -----------------------------------------------------------------------------------------------------------------
    connect() {
        // Prevent overlapping connection attempts
        if (this._connecting) {
            console.log("WebSocket connection already in progress, skipping");
            return;
        }

        // On mobile, wait for document to be visible before connecting
        // This prevents connection issues when page loads in background
        if (typeof document !== 'undefined' && document.hidden) {
            console.log("Document hidden, waiting for visibility before connecting");
            const onVisible = () => {
                if (!document.hidden) {
                    document.removeEventListener('visibilitychange', onVisible);
                    this.connect();
                }
            };
            document.addEventListener('visibilitychange', onVisible);
            return;
        }

        // Clean up any existing sockets
        this._closeProbeSocket();
        if (this.socket) {
            try {
                this.socket.onclose = null;
                this.socket.onerror = null;
                this.socket.onopen = null;
                this.socket.onmessage = null;
                this.socket.close();
            } catch (e) {}
            this.socket = null;
        }

        this._connecting = true;
        console.log(`WebSocket connecting to ${this.url}...`);

        try {
            this.socket = new WebSocket(this.url);
        } catch (e) {
            console.error("Failed to create WebSocket:", e);
            this._connecting = false;
            this._scheduleReconnect();
            return;
        }

        if (!this.socket) {
            console.error("Cannot create WebSocket");
            this._connecting = false;
            this._scheduleReconnect();
            return;
        }

        // iOS Safari bug workaround: create a "probe" socket that helps the main socket connect
        // This dummy connection seems to prime the WebSocket subsystem
        try {
            this._probeSocket = new WebSocket(this.url);
            // We don't need to do anything with it - just creating it helps
            // Close it after the main socket connects (handled in onOpen)
        } catch (e) {
            // Probe socket is optional, ignore errors
        }

        this.socket.onopen = this.onOpen.bind(this);
        this.socket.onmessage = this.onMessage.bind(this);
        this.socket.onerror = this.onError.bind(this);
        this.socket.onclose = this.onClose.bind(this);

        // Set up connection timeout - if onopen doesn't fire within the timeout,
        // assume the connection failed silently (common on mobile browsers)
        this._connectionTimeout = setTimeout(() => {
            if (this._connecting && !this.connected) {
                console.warn(`WebSocket connection timeout - onopen did not fire within ${this._connectionTimeoutMs}ms, retrying...`);
                // Force close the socket and retry
                if (this.socket) {
                    try {
                        this.socket.onclose = null;
                        this.socket.onerror = null;
                        this.socket.onopen = null;
                        this.socket.close();
                    } catch (e) {}
                    this.socket = null;
                }
                this._connecting = false;
                this._scheduleReconnect();
            }
        }, this._connectionTimeoutMs);
    }

    // -----------------------------------------------------------------------------------------------------------------
    onOpen(event) {
        console.log("WebSocket connected!");

        // Clear connection timeout
        if (this._connectionTimeout) {
            clearTimeout(this._connectionTimeout);
            this._connectionTimeout = null;
        }

        // Close the probe socket now that we're connected
        this._closeProbeSocket();

        this._connecting = false;
        this.connected = true;
        this._reconnectAttempts = 0; // Reset on successful connection

        // Send any queued messages
        while (this.txQueue.length > 0) {
            const message = this.txQueue.shift();
            this.send(message);
        }

        this.emit('connected');
    }

    // -----------------------------------------------------------------------------------------------------------------
    _closeProbeSocket() {
        if (this._probeSocket) {
            try {
                this._probeSocket.onclose = null;
                this._probeSocket.onerror = null;
                this._probeSocket.onopen = null;
                this._probeSocket.close();
            } catch (e) {}
            this._probeSocket = null;
        }
    }

    // -----------------------------------------------------------------------------------------------------------------
    onMessage(message) {
        try {
            const msg = JSON.parse(message.data);
            this.emit('message', msg);
        } catch (e) {
            console.log("Error parsing message", message.data, e);
        }
    }

    // -----------------------------------------------------------------------------------------------------------------
    onError(err) {
        console.log("WebSocket error:", err);
        // Don't emit if no listeners to prevent unhandled error
        if (this.listenerCount('error') > 0) {
            this.emit('error', err);
        }
    }

    // -----------------------------------------------------------------------------------------------------------------
    onClose(event) {
        // Clear connection timeout
        if (this._connectionTimeout) {
            clearTimeout(this._connectionTimeout);
            this._connectionTimeout = null;
        }

        const wasConnected = this.connected;
        this._connecting = false;
        this.connected = false;

        console.log(`WebSocket closed (code: ${event.code}, reason: ${event.reason || 'none'}, wasConnected: ${wasConnected})`);

        if (wasConnected) {
            this.emit('close', event);
        }

        if (this.options.reconnect) {
            this._scheduleReconnect();
        }
    }

    // -----------------------------------------------------------------------------------------------------------------
    _scheduleReconnect() {
        // Cancel any existing reconnect timer
        if (this._reconnectTimer) {
            clearTimeout(this._reconnectTimer);
            this._reconnectTimer = null;
        }

        // Exponential backoff with jitter for reconnection
        this._reconnectAttempts++;
        const baseDelay = this.options.reconnect_pause;
        const maxDelay = this.options.reconnect_pause_max;
        // Exponential backoff: delay = base * 1.5^attempts, capped at max
        const delay = Math.min(baseDelay * Math.pow(1.5, this._reconnectAttempts - 1), maxDelay);
        // Add small random jitter (±20%) to prevent thundering herd
        const jitter = delay * (0.8 + Math.random() * 0.4);

        console.log(`WebSocket reconnecting in ${Math.round(jitter)}ms (attempt ${this._reconnectAttempts})`);

        this._reconnectTimer = setTimeout(() => {
            this._reconnectTimer = null;
            this.connect();
        }, jitter);
    }

    // -----------------------------------------------------------------------------------------------------------------
    send(message) {
        if (this.connected && this.socket && this.socket.readyState === WebSocket.OPEN) {
            try {
                this.socket.send(JSON.stringify(message));
            } catch (e) {
                console.error("Failed to send message:", e);
                this.txQueue.push(message);
            }
        } else {
            this.txQueue.push(message);
        }
    }
}
