import {Widget} from "../objects.js";
import {BabylonContainer} from "@babylon_vis/babylon.js"

export class BabylonWidget extends Widget {
    constructor(id, payload = {}) {
        super(id, payload);

        const default_config = {
            babylon_id: 'babylon'
        }

        this.configuration = {...default_config, ...this.configuration};

        this.element = this.initializeElement();
        this.configureElement(this.element);
        this.assignListeners(this.element);

        this.babylon = new BabylonContainer(this.configuration.babylon_id, this.element, this.data.babylon);

    }

    /* -------------------------------------------------------------------------------------------------------------- */
    initializeElement() {
        const element = document.createElement('div');
        element.id = this.id;
        element.classList.add('widget', 'babylon-widget');
        return element;
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    onFirstShow() {
        this.babylon.onFirstShow();
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    resize() {
        this.babylon.resize();
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    update(data) {
        return undefined;
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    updateConfig(data) {
        return undefined;
    }
}