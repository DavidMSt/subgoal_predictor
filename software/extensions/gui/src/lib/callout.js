import {getColor} from './helpers.js';


class CalloutButton {
    constructor(text, text_color, color, size, on_click_callback) {
        this.text = text;
        this.text_color = text_color;
        this.color = color;
        this.size = size;
        this.on_click_callback = on_click_callback;
        this.element = this.configureElement();
        this.attachListeners(this.element);
    }

    configureElement() {
        const btn = document.createElement('button');
        btn.classList.add('callout-btn');
        btn.textContent = this.text;
        Object.assign(btn.style, {
            background: getColor(this.color),
            color: getColor(this.text_color),
            border: 'none',
            borderRadius: '4px',
            cursor: 'pointer',
            flex: `0 0 ${this.size}%`,   // width = size% of callout
        });
        return btn;
    }

    attachListeners(element) {
        element.addEventListener('click', () => {
            if (this.on_click_callback) this.on_click_callback();
        });
    }
}

class Callout {
    // you can override these from GUI with Callout.baseRightMargin = ... etc.
    static baseRightMargin = 10;
    static baseBottomMargin = 200;
    static gap = 10;
    static container = null;

    static getContainer() {
        if (!Callout.container) {
            const c = document.createElement('div');
            c.id = 'callout-container';
            c.classList.add('callout-container');
            document.body.appendChild(c);
            Callout.container = c;
        }
        return Callout.container;
    }

    constructor(id, config = {}, on_event_callback, close_callback) {
        this.id = id;
        this.on_event_callback = on_event_callback;
        this.close_callback = close_callback;

        const defaults = {
            background_color: [0.2, 0.2, 0.2, 0.4],
            border_color: [0.6, 0.6, 0.6],
            border_width: 1,
            size: [200, 80],  // [width, height] in px
            expand: true,
            text_color: [1, 1, 1],
            font_size: 9,    // pt
            font_family: 'Roboto',
            closeable: true,
            title: '',
            title_font_size: 10,   // pt
            title_text_color: [1, 1, 1],
            title_text_weight: 'bold',
            content: '',
            symbol: 'ℹ️',
            buttons: {},   // { key: { text, text_color, color, size } }
        };

        this.config = {...defaults, ...config};
        this.buttons = {};

        // build DOM
        this.element = document.createElement('div');
        this.element.id = this.id;
        this.element.classList.add('callout');
        this.configureElement(this.element);
    }

    configureElement(el) {
        const [w, h] = this.config.size;
        Object.assign(el.style, {
            width: `${w}px`,
            background: getColor(this.config.background_color),
            border: `${this.config.border_width}px solid ${getColor(this.config.border_color)}`,
            borderRadius: '6px',
            boxSizing: 'border-box',
            fontFamily: this.config.font_family,
            fontSize: `${this.config.font_size}pt`,
            color: getColor(this.config.text_color),
            display: 'flex',
            flexDirection: 'column',
            position: 'relative',
            overflow: 'hidden',
        });

        el.classList.add('callout')

        if (this.config.expand) {
            Object.assign(el.style, {
                height: '100%',
                flex: '1 1 auto',
                minHeight: `${h}px`,
            });
        } else {
            Object.assign(el.style, {
                height: `${h}px`,
                minHeight: `${h}px`,
                // flex: '0 0 auto',
            });
        }

        // header (title + optional ×)
        const header = document.createElement('div');
        header.classList.add('callout-header');
        const title = document.createElement('span');
        title.classList.add('callout-title');
        title.textContent = this.config.title;
        header.appendChild(title);
        if (this.config.closeable) {
            const x = document.createElement('button');
            x.classList.add('callout-close-btn');
            x.textContent = '×';
            x.addEventListener('click', () => this.close_manually());
            header.appendChild(x);
        }
        el.appendChild(header);

        // content text
        const content = document.createElement('div');
        content.classList.add('callout-content');
        content.textContent = this.config.content;
        el.appendChild(content);

        // buttons row
        const btnRow = document.createElement('div');
        btnRow.classList.add('callout-buttons');
        this.buttons = this.generateButtons(this.config.buttons);
        Object.values(this.buttons).forEach(b => btnRow.appendChild(b.element));
        el.appendChild(btnRow);

        // symbol in lower-right
        const sym = document.createElement('div');
        sym.classList.add('callout-symbol');
        sym.textContent = this.config.symbol;
        el.appendChild(sym);

        // inject into page
        const container = Callout.getContainer();
        container.prepend(el);


        // Add double click listener to element
        el.addEventListener('dblclick', () => {
            this.close_manually();
        });
    }

    generateButtons(cfg) {
        const btns = {};
        Object.entries(cfg).forEach(([key, bcfg]) => {
            btns[key] = new CalloutButton(
                bcfg.text,
                bcfg.text_color,
                bcfg.color,
                bcfg.size,
                () => {
                    if (this.on_event_callback) {
                        this.on_event_callback({
                            id: this.id,
                            event: 'button_click',
                            data: {button: key}
                        });
                    }
                }
            );
        });
        return btns;
    }

    close_manually() {
        // user clicked "×" → notify backend
        if (this.on_event_callback) {
            this.on_event_callback({id: this.id, event: 'close', data: {}});
        }
    }

    close() {
        const el = this.element;
        // 1) start the CSS transition
        el.classList.add('closing');

        // 2) when it's done, actually remove it
        el.addEventListener('transitionend', () => {
            const container = Callout.getContainer();
            if (container.contains(el)) container.removeChild(el);
            if (this.close_callback) this.close_callback(this.id);
            // if that was the last callout, tear down the whole container
            if (!container.childElementCount) {
                container.remove();
                Callout.container = null;
            }
        }, {once: true});

    }
}

export {Callout, CalloutButton};
