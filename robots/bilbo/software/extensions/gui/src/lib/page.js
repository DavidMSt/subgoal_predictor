import {ButtonWidget} from './objects/js/buttons.js';
import {ContextMenuItem} from './objects/contextmenu.js';
import {OBJECT_MAPPING} from './objects/mapping.js';
import {Widget} from './objects/objects.js';
import {activeGUI} from './globals.js';
import {Callbacks, splitPath, writeToLocalStorage} from './helpers.js';


const DEFAULT_BACKGROUND_COLOR = 'rgb(31,32,35)'


class PageButton extends ButtonWidget {
    constructor(id, page, data = {}) {
        super(id, data);
        this.page = page;
        const favorites_context_menu_item = new ContextMenuItem('favorites',
            {name: 'Add to favorites', front_icon: '⭐'})

        this.addItemToContextMenu(favorites_context_menu_item);
        favorites_context_menu_item.callbacks.get('click').register(this.onFavoritesClick.bind(this));
        this.callbacks.get('click').register(this.onClick.bind(this));

    }

    select() {
        this.updateConfig({text_color: [0.8, 0.8, 0.8], color: [0.2, 0.2, 0.2], border_width: 2});
    }

    deselect() {
        this.updateConfig({text_color: [0.3, 0.3, 0.3], color: [0.15, 0.15, 0.15], border_width: 1});
    }

    onFavoritesClick() {
        activeGUI.addShortcut(this.page);
    }

    onClick() {
        writeToLocalStorage(`${activeGUI.id}_active_page`, this.page.id);
    }

    resize() {
    }
}

class Page {

    /** @type {Object} */
    objects = {};

    /** @type {Callbacks} */
    callbacks = null;

    /** @type {Object} */
    configuration = {};

    /** @type {string} */
    id = '';

    /** @type {HTMLElement | null} */
    grid = null;

    /** @type {PageButton | null} */
    button = null;

    constructor(id, configuration = {}, objects = {}) {
        this.id = id;

        const default_configuration = {
            // rows: 16,
            // columns: 40,
            rows: 18,
            columns: 50,
            fillEmptyCells: true,
            color: 'rgba(40,40,40,0.7)',
            backgroundColor: DEFAULT_BACKGROUND_COLOR,
            text_color: 'rgba(255,255,255,0.7)',
            name: id,
        }

        this.configuration = {...default_configuration, ...configuration};

        this.parent = null;
        this.callbacks = new Callbacks();
        this.callbacks.add('event');
        this.objects = {};

        this.occupied_grid_cells = new Set();

        // Create the main grid container for this page that gets later swapped into the content container
        this.grid = document.createElement('div');
        this.grid.id = `page_${this.id}_grid`;
        this.grid.className = 'grid';

        // Make the number of rows and columns based on the configuration
        this.grid.style.gridTemplateRows = `repeat(${this.configuration.rows}, 1fr)`;
        this.grid.style.gridTemplateColumns = `repeat(${this.configuration.columns}, 1fr)`;

        this.grid.style.display = 'grid';

        // Fill the grid with empty cells
        if (this.configuration.fillEmptyCells) {
            this._fillContentGrid();
        }

        // Generate the button for this page that the category will later attach to the page bar
        this.button = this._generateButton();

        if (Object.keys(objects).length > 0) {
            this.buildObjectsFromDefinition(objects);
        }

    }

    /* ⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯ */
    getObjectByPath(path) {
        // Example invocations:
        //   path = "button1"            → childKey = "/category1/page1/button1"
        //   path = "groupG/widgetX"     → childKey = "/category1/page1/groupG"
        //                                        then recurse with "widgetX"


        const [firstSegment, remainder] = splitPath(path);
        if (!firstSegment) {
            console.warn(`[Page ID: ${this.id}] No first segment in path "${path}"`);
            return null;
        }

        // Build the full‐UID key for the direct child:
        //   this.id is "/category1/page1"
        //   firstSegment might be "button1" or "groupG"
        const childKey = `${this.id}/${firstSegment}`;

        // Look up the widget or group in this.objects, which is keyed by full UID
        const child = this.objects[childKey];
        if (!child) {
            console.warn(`[Page ID: ${this.id}] No child found for key "${childKey}" in path "${path}"`);
            console.log(this.objects);
            return null;
        }

        if (!remainder) {
            // No deeper path → return the widget or group itself
            return child;
        }

        // Check if the child has a function called getObjectByPath()
        if (typeof child.getObjectByPath === "function") {
            return child.getObjectByPath(remainder);
        }
        return null;
    }

    /* ⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯ */
    getGUI() {
        if (this.parent) {
            return this.parent.getGUI();
        }
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    update(data) {
        console.log('Updating page:', this.id);
    }


    /* ⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯ */
    handleAddMessage(data) {
        const object_config = data.config;
        if (object_config) {
            this.buildObjectFromData(object_config)
        }
    }

    /* ⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯ */
    handleRemoveMessage(data) {
        const object_id = data.id;
        if (object_id) {
            const object = this.objects[object_id];
            if (object) {
                this.removeObject(object);
            } else {
                console.warn(`Object ${object_id} not found`);
            }
        }
    }

    /* ⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯ */
    buildObjectsFromDefinition(objects) {
        for (const [id, config] of Object.entries(objects)) {
            this.buildObjectFromData(config);
        }
    }

    /* ⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯ */
    buildObjectFromData(data) {
        const id = data.id;
        const type = data.type;
        const width = data.width;
        const height = data.height;
        const row = data.row;
        const col = data.column;

        // Check if the type is in the object mapping variable
        if (!OBJECT_MAPPING[type]) {
            console.warn(`Object type "${type}" is not defined.`);
            console.log(data);
            return;
        }

        const object_class = OBJECT_MAPPING[type];

        const object = new object_class(id, data);
        this.addObject(object, row, col, width, height);
    }

    /* ⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯ */
    /**
     * Replace your old stub with this:
     * @param {Widget} widget  — any widget subclass
     * @param {int} row
     * @param {int} col
     * @param {int} width
     * @param {int} height
     */
    addObject(widget, row, col, width, height) {
        if (!(widget instanceof Widget)) {
            console.warn('Expected a GUI_Object, got:', widget);
            return;
        }

        if (!widget.id) {
            console.warn('Widget must have an ID');
            return;
        }

        if (this.objects[widget.id]) {
            console.warn(`Widget with ID "${widget.id}" already exists in the grid.`);
            return;
        }

        if (row < 0 || col < 0 || row >= this.configuration.rows || col >= this.configuration.columns) {
            console.warn(`Invalid grid coordinates: row=${row}, col=${col}`);
            return;
        }

        if (row + height - 1 > this.configuration.rows || col + width - 1 > this.configuration.columns) {
            console.warn(`Invalid grid dimensions: row=${row}, col=${col}, width=${width}, height=${height}`);
        }

        const newCells = this._getOccupiedCells(row, col, width, height);

        // Check for cell conflicts
        for (const cell of newCells) {
            if (this.occupied_grid_cells.has(cell)) {
                console.warn(`Grid cell ${cell} is already occupied. Cannot place widget "${widget.id}".`);
                return;
            }
        }

        // Mark the cells as occupied
        newCells.forEach(cell => this.occupied_grid_cells.add(cell));

        // Render the widget's DOM and append into the main grid container
        widget.attach(this.grid, [row, col], [width, height]);
        this.objects[widget.id] = widget;

        widget.callbacks.get('event').register(this.onEvent.bind(this));


        if (this.configuration.fillEmptyCells) {
            this._fillContentGrid();
        }

    }

    /* -------------------------------------------------------------------------------------------------------------- */
    removeObject(object) {
        // Check if the object is a string
        if (typeof object === 'string') {
            // If it's a string, assume it's the ID of the object
            object = this.objects[object];
        }
        if (!(object instanceof Widget)) {
            console.warn('Expected a GUI_Object, got:', object);
            return;
        }

        // Check if the object exists in the page
        if (!this.objects[object.id]) {
            console.warn(`Object with ID "${object.id}" does not exist in this page.`);
            return;
        }

        // Remove the object from the occupied cells. We need to get the occupied cells from the object.container html element
        if (!object.container) {
            console.warn(`Object "${object.id}" does not have a container. Cannot remove.`);
            return;
        }
        // Get the row, column, width, and height from the object
        const row = parseInt(object.container.style.gridRowStart, 10);
        const col = parseInt(object.container.style.gridColumnStart, 10);
        const width = parseInt(object.container.style.gridColumnEnd.replace('span', ''), 10);
        const height = parseInt(object.container.style.gridRowEnd.replace('span', ''), 10);

        const occupiedCells = this._getOccupiedCells(row, col, width, height);
        occupiedCells.forEach(cell => this.occupied_grid_cells.delete(cell));

        // Remove the object from the grid
        this.grid.removeChild(object.container);

        // Remove the object from the object dictionary
        delete this.objects[object.id];

        // Redraw the placeholders
        this._fillContentGrid();
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    _generateButton() {
        return new PageButton(this.id, this, {config: {text: this.configuration.name}});
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    _getOccupiedCells(row, col, width, height) {
        const cells = [];
        for (let r = row; r < row + height; r++) {
            for (let c = col; c < col + width; c++) {
                cells.push(`${r},${c}`);
            }
        }
        return cells;
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    _fillContentGrid() {
        let occupied_cells = 0;

        // Remove any existing placeholders
        this.grid
            .querySelectorAll('.placeholder')
            .forEach((el) => el.remove());

        for (let row = 1; row < this.configuration.rows + 1; row++) {
            for (let col = 1; col < this.configuration.columns + 1; col++) {
                if (!this.occupied_grid_cells.has(`${row},${col}`)) {
                    const gridItem = document.createElement('div');
                    gridItem.className = 'placeholder';

                    // Set a tooltip showing the 1-based row and column
                    gridItem.title = `Row ${row}, Column ${col}`;

                    gridItem.style.fontSize = '6px';
                    gridItem.style.color = 'rgba(255,255,255,0.5)';
                    this.grid.appendChild(gridItem);
                } else {
                    occupied_cells++;
                }
            }
        }

        // console.log(`Page "${this.id}" has ${occupied_cells} occupied cells.`);
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    onEvent(event) {
        // Check if there is an 'event' callback for this page
        // if (DEBUG) {
        //     console.log(`[Page ID: ${this.id}] Event received:`, event);
        // }
        this.callbacks.get('event').call(event);
    }

}

export {Page, PageButton};
