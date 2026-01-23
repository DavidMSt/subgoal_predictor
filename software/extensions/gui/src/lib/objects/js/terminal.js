import {Terminal} from 'xterm';
import {io} from 'socket.io-client';
import 'xterm/css/xterm.css';
import {FitAddon} from 'xterm-addon-fit';

import {Widget} from "../objects.js";

export class TerminalWidget extends Widget {
    constructor(id, config = {}) {
        super(id, config);

        const default_config = {
            host: 'localhost',
            port: 5555,
            font_size: 12,  // px
        }

        this.configuration = {...default_config, ...this.configuration};
        this.callbacks.add('event');


        this.terminal = new Terminal({
            fontFamily: 'monospace',
            fontSize: this.configuration['font_size'],           // ← here
            lineHeight: 1.0,
            convertEol: false,    // ← treat “\n” as CR+LF
            cursorBlink: true,
        });
        this.socket = io(`http://${this.configuration.host}:${this.configuration.port}`, {
            reconnection: true,
            reconnectionAttempts: Infinity,
            reconnectionDelay: 500,
            reconnectionDelayMax: 2000,
        });


        this.element = this.initializeElement();
        this.configureElement(this.element);

        const fitAddon = new FitAddon();
        this.terminal.loadAddon(fitAddon);
        this.terminal.open(this.element);
        fitAddon.fit();

        this.terminal.onData(data => this.socket.emit('input', data));
        this.socket.on('output', data => this.terminal.write(data));
        window.addEventListener('resize', () => {
                fitAddon.fit();
            }
        );
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    initializeElement() {
        const element = document.createElement('div');
        element.id = this.id;
        element.classList.add('widget','highlightable', 'terminal-widget');
        return element;
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    configureElement(element) {
        super.configureElement(element);
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    assignListeners(element) {
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    getElement() {
        return this.container;
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    update(data) {
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    updateConfig(data) {
        this.configuration = {...this.configuration, data};
        this.configureElement(this.element);
    }
}