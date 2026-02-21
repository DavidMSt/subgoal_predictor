// import {GUI_Object} from "../objects.js";
//
//
// export class CheckboxWidget extends GUI_Object {
//
//     constructor(id, config = {}) {
//         super(id, config);
//
//         const default_configuration = {
//             title: '',
//             title_position: 'left',
//             background_color: 'transparent',
//             text_color: '#fff',
//             value: false,
//         }
//
//         this.configuration = {...default_configuration, ...this.configuration};
//         this.element = this._initializeElement();
//         this.configureElement(this.element);
//         this.assignListeners(this.element);
//
//     }
//
//     _initializeElement() {
//
//     }
//
//     assignListeners(element) {
//     }
//
//     getElement() {
//         return undefined;
//     }
//
//     update(data) {
//     }
//
//     updateConfig(data) {
//         this.configuration = {...this.configuration, ...data};
//         this.configureElement(this.configuration);
//     }
//
//     setValue(value) {
//         this.configuration.value = value;
//         this.configureElement(this.configuration);
//     }
// }

import {getColor} from "../../helpers.js";

// src/lib/objects/checkbox.js
import {Widget} from "../objects.js";

export class CheckboxWidget extends Widget {
    constructor(id, config = {}) {
        super(id, config);

        const defaults = {
            visible: true,
            color: 'transparent',              // widget background
            text_color: '#ffffff',                // title color
            title: 'Checkbox:',
            title_position: 'left',            // 'top' or 'left'
            value: true,
            tooltip: null,

            checkbox_border_color: '#999',     // box border
            checkbox_background_color: [1, 1, 1, 0.1], // box fill
            checkbox_check_color: [0, 1, 0, 1],   // checkmark
            checkbox_size: '16pt',
            margin_right: '10px',
        };

        this.configuration = {...defaults, ...this.configuration};
        this.element = this._initializeElement();
        this.configureElement(this.element);
    }

    _initializeElement() {
        const el = document.createElement('div');
        el.id = this.id;
        el.classList.add('widget', 'highlightable','checkboxWidget');
        return el;
    }

    configureElement(el) {
        super.configureElement(el);
        const c = this.configuration;

        // ── container attrs ───────────────────────────────────────────────────────
        el.dataset.titlePosition = c.title_position;
        el.style.display = c.visible ? '' : 'none';
        el.style.backgroundColor = getColor(c.color);
        el.style.color = getColor(c.text_color);

        // ── CSS variables for the checkbox ────────────────────────────────────────
        el.style.setProperty('--cb-border-color', getColor(c.checkbox_border_color));
        el.style.setProperty('--cb-bg-color', getColor(c.checkbox_background_color));
        el.style.setProperty('--cb-check-color', getColor(c.checkbox_check_color));
        el.style.setProperty('--cb-size', `${c.checkbox_size}`);
        el.style.setProperty('--cb-margin-right', `${c.margin_right}`);

        // ── inner HTML ───────────────────────────────────────────────────────────
        let html = '';
        if (c.title) html += `<span class="cbTitle">${c.title}</span>`;
        html += `
            <div class="cbInputContainer">
                <input
                    type="checkbox"
                    class="cbCheckbox"
                    ${c.value ? 'checked' : ''}
                />
            </div>
        `;
        el.innerHTML = html;

        this.assignListeners(el);
    }

    assignListeners(el) {
        super.assignListeners(el);
        const checkbox = el.querySelector('.cbCheckbox');
        checkbox.addEventListener('change', e => {
            const v = e.target.checked;
            this.callbacks.get('event').call({
                event: 'checkbox_change',
                id: this.id,
                data: {value: v}
            });
        });
    }

    updateConfig(data) {
        Object.assign(this.configuration, data);
        this.configureElement(this.element);
    }

    setValue(value) {
        this.configuration.value = Boolean(value);
        const cb = this.element.querySelector('.cbCheckbox');
        if (cb) cb.checked = this.configuration.value;
    }

    update(data) {
        this.setValue(data);
    }

    getElement() {
        return this.element;
    }

    accept(accept = true) {
        const el = this.element.querySelector('.cbCheckbox');
        if (accept) {
            el.classList.add('accepted');
            el.addEventListener('animationend', () => el.classList.remove('accepted'), {once: true});
        } else {
            el.classList.add('error');
            el.addEventListener('animationend', () => el.classList.remove('error'), {once: true});
        }
    }
}


