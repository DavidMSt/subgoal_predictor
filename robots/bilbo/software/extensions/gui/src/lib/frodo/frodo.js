import {Widget} from "../objects/objects.js";


class FRODO_Agent {
    /** @type {object} */ state = {'x': 0, 'y': 0, 'psi': 0};
    /** @type {Array} */ history = [];
    /** @type {object} */ waypoints = {};

    constructor(id, payload = {}) {

        const defaults = {
            name: id,
            color: [0, 0, 0, 1],
            vision_radius: 1.5,  // in m,
            vision_fov: 90, // in deg
            fov_opacity: 0.5,
            visible: true,
            dim: false,
        };

        this.config = {...defaults, ...payload.config};
    }
}

class FRODO_Static {
}

class FRODO_Map {

    /** @type {object} */ agents = {};
    /** @type {object} */ statics = {};


    constructor(id, container, payload = {}) {

        const defaults = {
            tile_size: 0.5,  // in m
            tiles: [6, 6], // Tiles in x and y direction
            tile_colors: [[0.3, 0.3, 0.3], [0.5, 0.5, 0.5]], // RGB values for the tiles for the checkerboard pattern
            show_coordinate_system: true,
            coordinate_system_position: 'center',  // Can also be 'bottom-left', 'top-left', 'bottom-right', 'top-right'
            coordinate_system_size: 0.5,  // in m
            rotation: 0,  // Rotation of the whole map in degrees

            // Style
            background_color: [0, 0, 0, 0],
            border_width_map: 1, // in px
            border_color_map: [1, 1, 1],
            tile_border_width: 1,
            tile_border_color: [0, 0, 0, 1],
        }


        this.config = {...defaults, ...payload.config}


    }

    initializeElement() {

    }
}


export class FRODO_Map_Widget extends Widget {
    constructor(id, payload = {}) {
        super(id, payload);

        this.element = this.initializeElement();
        this.configureElement(this.element);
        this.assignListeners(this.element);

        this.frodo_map = new FRODO_Map(this.id, this.element, this.data.map);
    }

    initializeElement() {

        const element = document.createElement("div");
        element.classList.add('gridItem', 'widget', 'frodo-map-widget');
        return element;
    }

    resize() {
    }

    update(data) {
        return undefined;
    }

    updateConfig(data) {
        return undefined;
    }
}