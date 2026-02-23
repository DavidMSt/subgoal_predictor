// websocket_joysticks.js
import {Joystick, JoystickManager} from './joystick.js';
import {Websocket} from "../websocket.js";

const AXES_POLL_RATE = 20;  // Hz

export class WebsocketJoystick {

    /** @type {Joystick} */ joystick;
    /** @type {Websocket} */ websocket;
    /** @type {boolean} */ connected = false;
    /** @type {number|null} */ _axesInterval = null;

    /**
     * @param {Joystick} joystick
     * @param {string} websocket_host
     * @param {number} websocket_port
     */
    constructor(joystick, websocket_host, websocket_port) {
        this.joystick = joystick;

        // Forward button events immediately
        this.joystick.callbacks.get('button').register((evt) => {
            this.websocket?.send({
                type: 'button',
                index: this.joystick.index,
                name: evt.name ?? null,
                event: evt.type,
                value: evt.value,
                pressed: evt.pressed,
                ts: evt.ts ?? performance.now(),
            });
        });

        // Watch for joystick disconnects
        this.joystick.callbacks.get('disconnected').register(this._onJoystickDisconnect.bind(this));

        // Optional: when joystick (re)connects, re-identify
        if (this.joystick.callbacks.get('connected')) {
            this.joystick.callbacks.get('connected').register(() => {
                if (this.connected) this._sendIdentification();
            });
        }

        // Prepare websocket
        this.websocket = new Websocket({host: websocket_host, port: websocket_port});

        this.websocket.on('connected', this._onWebsocketConnected.bind(this));
        // The provided Websocket emits 'close' on close; handle both just in case.
        this.websocket.on('disconnected', this._onWebsocketDisconnected.bind(this));
        this.websocket.on('close', this._onWebsocketDisconnected.bind(this));

        // (Optional) bubble up errors if consumer attached listeners
        this.websocket.on('error', (err) => {
            if (this.joystick?.callbacks?.get('error')) {
                this.joystick.callbacks.get('error').call(err);
            } else {
                console.warn('Websocket error (WebsocketJoystick):', err);
            }
        });

        // Connect now
        this.websocket.connect();
    }


    // -----------------------------------------------------------------------------------------------------------------
    _onJoystickDisconnect() {
        // Inform remote peer that this joystick went away
        this.websocket?.send({
            type: 'joystick_disconnected',
            index: this.joystick.index,
            ts: performance.now(),
        });
        // Stop streaming axes if we were doing so
        if (this._axesInterval) {
            clearInterval(this._axesInterval);
            this._axesInterval = null;
        }
    }

    // -----------------------------------------------------------------------------------------------------------------
    _onWebsocketConnected() {
        this.connected = true;
        this._sendIdentification();

        // Begin streaming axes at fixed rate
        if (this._axesInterval) clearInterval(this._axesInterval);
        const periodMs = Math.max(10, Math.round(1000 / AXES_POLL_RATE));
        this._axesInterval = setInterval(() => this._task(), periodMs);
    }

    // -----------------------------------------------------------------------------------------------------------------
    _onWebsocketDisconnected() {
        this.connected = false;
        if (this._axesInterval) {
            clearInterval(this._axesInterval);
            this._axesInterval = null;
        }
    }

    // -----------------------------------------------------------------------------------------------------------------
    _task() {
        // Send current axes snapshot continuously.
        // (Even if identical to last — server can choose to debounce.)
        const axes = this.joystick.getAxes();
        const buttons = this.joystick.getButtons(); // can be useful to have analog triggers, etc.
        this.websocket?.send({
            type: 'axes',
            index: this.joystick.index,
            axes,
            buttonsAnalog: buttons.map(b => b.value), // lightweight analog snapshot
            ts: performance.now(),
        });
    }

    // -----------------------------------------------------------------------------------------------------------------
    _sendIdentification() {
        const info = this.joystick.getInfo();
        this.websocket?.send({
            type: 'identify',
            joystick: {
                index: info.index,
                id: info.id,
                mapping: info.mapping,
                axes: (info.axes || []).length ?? 0,
                buttons: (info.buttons || []).length ?? 0,
                connected: info.connected,
            },
            ts: performance.now(),
        });
    }

    // -----------------------------------------------------------------------------------------------------------------
    /** Close websocket and stop timers (does not destroy the underlying Joystick). */
    close() {
        if (this._axesInterval) {
            clearInterval(this._axesInterval);
            this._axesInterval = null;
        }
        if (this.websocket) {
            this.websocket.close();
        }
        this.connected = false;
    }
}


export class WebsocketJoystickManager {

    /** @type {JoystickManager} */ joystick_manager;
    /** @type {Object.<string, WebsocketJoystick> }*/ websocket_joysticks = {};
    /** @type {string} */ _host;
    /** @type {number} */ _port;

    /**
     * @param {Object} [opts]
     * @param {string} [opts.host='localhost']
     * @param {number} [opts.port=8765]
     * @param {boolean} [opts.autoStart=true] - passed to JoystickManager
     */
    constructor(opts = {}) {
        const {
            host = 'localhost',
            port = 8765,
            autoStart = true,
        } = opts;

        this._host = host;
        this._port = Number(port);

        this.joystick_manager = new JoystickManager({autoStart});
        this.joystick_manager.callbacks.get('new_joystick').register(this._newJoystickCallback.bind(this));

        // Clean up wrapper when source joystick disconnects
        this.joystick_manager.callbacks.get('joystick_disconnected').register((info) => {
            const key = String(info.index);
            const wj = this.websocket_joysticks[key];
            if (wj) {
                wj._onJoystickDisconnect(); // notify remote
                wj.close();
                delete this.websocket_joysticks[key];
            }
        });
    }

    // -----------------------------------------------------------------------------------------------------------------
    _newJoystickCallback(info) {
        // Create a Joystick bound to the announced index, then wrap it.
        const js = new Joystick({index: info.index});
        const wj = new WebsocketJoystick(js, this._host, this._port);
        this.websocket_joysticks[String(info.index)] = wj;
    }
    // -----------------------------------------------------------------------------------------------------------------

    /** Number of active websocket-wrapped joysticks. */
    count() {
        return Object.keys(this.websocket_joysticks).length;
    }

    /** List a summary of active websocket joysticks. */
    list() {
        return Object.entries(this.websocket_joysticks).map(([key, wj]) => {
            const info = wj.joystick.getInfo();
            return {
                key,
                index: info.index,
                id: info.id,
                mapping: info.mapping,
                axes: (info.axes || []).length ?? 0,
                buttons: (info.buttons || []).length ?? 0,
                joystickConnected: info.connected,
                websocketConnected: !!wj.connected,
            };
        });
    }

    /**
     * Get a WebsocketJoystick by joystick index (string or number).
     * @param {string|number} index
     * @returns {WebsocketJoystick|null}
     */
    get(index) {
        const key = String(index);
        return this.websocket_joysticks[key] || null;
    }

    /** Disconnect & remove all WebsocketJoysticks (does not destroy source Joysticks). */
    disconnectAll() {
        for (const key of Object.keys(this.websocket_joysticks)) {
            this.websocket_joysticks[key].close();
            delete this.websocket_joysticks[key];
        }
    }

    /** Stop everything: disconnect wrappers and stop the JoystickManager. */
    destroy() {
        this.disconnectAll();
        if (this.joystick_manager?.stop) {
            this.joystick_manager.stop();
        }
    }
}