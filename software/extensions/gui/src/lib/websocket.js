import {EventEmitter} from 'events';

// const WebSocket = require('ws');

export class Websocket extends EventEmitter {
    constructor({host, port, options = {}}) {
        super();

        const default_options = {
            reconnect_pause: 3000, // ms
            reconnect: true,
        }

        this.options = {
            ...default_options,
            ...(options || {})  // safely spread even if options is undefined
        };

        this.url = `ws://${host}:${port}`;
        this.connected = false;
        this.txQueue = [];


    }

    // -----------------------------------------------------------------------------------------------------------------
    close() {
        if (this.socket) {
            this.socket.close();
            this.socket = null;
            this.connected = false;
            this.txQueue = [];
            console.log("WebSocket closed");
        }
    }
    // -----------------------------------------------------------------------------------------------------------------
    connect() {
        this.socket = new WebSocket(this.url);

        if (!this.socket) {
            alert("Cannot start websocket")
        }

        this.socket.onopen = this.onOpen.bind(this);
        this.socket.onmessage = this.onMessage.bind(this);
        this.socket.onerror = this.onError.bind(this);
        this.socket.onclose = this.onClose.bind(this);
    }

    // -----------------------------------------------------------------------------------------------------------------
    onOpen(open) {
        console.log("Websocket connected!");
        this.connected = true;
        for (let message of this.txQueue) {
            this.send(message);
        }
        this.emit('connected')
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
        if (this.listenerCount('error') > 0) {
            this.emit('error', err);
        }
    }

    // -----------------------------------------------------------------------------------------------------------------
    onClose(close) {
        if (this.connected) {
            console.log("WebSocket has been closed", close, this);
            this.emit('close', close);
        }
        this.connected = false;
        if (this.options.reconnect)
            setTimeout(() => this.connect(), this.options.reconnect_pause);

    }

    // -----------------------------------------------------------------------------------------------------------------
    send(message) {

        if (this.connected) {
            this.socket.send(JSON.stringify(message))
        } else {
            this.txQueue.push(message);
        }
    }
}