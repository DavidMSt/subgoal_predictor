import {CLI_Terminal} from './lib/cli_terminal/cli_terminal.js';
import {ButtonWidget} from './lib/objects/js/buttons.js';
import {ContextMenuItem} from './lib/objects/contextmenu.js'
import {openFilePicker} from './lib/file_picker.js';

import './lib/styles/popup.css'
import './lib/styles/objects.css';

import {OBJECT_MAPPING} from './lib/objects/mapping.js';
import {Widget} from './lib/objects/objects.js'
import {WidgetGroup} from './lib/objects/group.js';
import {activeGUI, setActiveGUI} from "./lib/globals.js";

import {
    Callbacks,
    existsInLocalStorage,
    getColor,
    getFromLocalStorage,
    isObject,
    removeFromLocalStorage,
    splitPath,
    writeToLocalStorage
} from './lib/helpers.js';
import {Websocket} from './lib/websocket.js';


const DEFAULT_BACKGROUND_COLOR = 'rgb(31,32,35)'
const DEBUG = true;

const GUI_WS_DEFAULT_PORT = 8100;


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

        // Render the widget’s DOM and append into the main grid container
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

/* ================================================================================================================== */

export class ShortcutButton extends ButtonWidget {
    constructor(id, data = {}) {
        super(id, data);

        // style the button
        this.element.classList.add('shortcut_button');
        this.on('click', this.onClick.bind(this));
        this.disabled = false;

        const context_menu_item_remove = new ContextMenuItem('remove',
            {
                name: 'Remove from Favorites',
                front_icon: '🗑️'
            });

        this.addItemToContextMenu(context_menu_item_remove);
        context_menu_item_remove.callbacks.get('click').register(this.removeFromFavorites.bind(this));

    }

    removeFromFavorites() {
        activeGUI.removeShortcut(this.id);

        delete this;
    }

    // clean up if destroying this button
    destroy() {
    }

    disable() {
        this.element.classList.add('disabled-shortcut');
        this.disabled = true;
    }

    enable() {
        this.element.classList.remove('disabled-shortcut');
        this.disabled = false;
    }

    onClick() {

        if (this.disabled) {
            return;
        }

        // Try to get the page from the gui
        const object = activeGUI.getObjectByUID(this.id);

        if (object instanceof Page) {
            if (object.parent && object.parent.setPage) {
                activeGUI.setCategory(object.parent.id);
                object.parent.setPage(object.id);
                writeToLocalStorage(`${activeGUI.id}_active_page`, object.id);
            } else {
                console.warn(`Cannot set page "${object.id}" in category "${object.parent ? object.parent.id : 'unknown'}".`);
            }
        } else if (object instanceof Category) {
            activeGUI.setCategory(object.id);
            // Set it to the first page
            const firstPage = Object.values(object.pages)[0];
            if (firstPage) {
                object.setPage(firstPage.id);
                writeToLocalStorage(`${activeGUI.id}_active_page`, firstPage.id);
            } else {
                console.warn(`Category "${object.id}" has no pages to select.`);
            }

        } else {
            console.warn(`Cannot find object with ID "${this.id}".`);
        }
    }

    resize() {
    }
}

/* ================================================================================================================== */


export class CategoryButton extends Widget {
    constructor(id, category, data = {}) {

        super(id, data);
        const CATEGORY_BTN_DEFAULTS = {
            name: '',
            icon: null,
            top_icon: null,
            text_color: 'rgba(255,255,255,0.7)',
        };

        this.configuration = {...CATEGORY_BTN_DEFAULTS, ...this.configuration};

        this.category = category;

        this.callbacks.add('click');

        // build the actual <button> element
        this.element = document.createElement('button');
        this.element.classList.add('category-button', 'not-selected');
        this.element.style.color = this.configuration.text_color;

        // left icon slot
        this.iconSlot = document.createElement('span');
        this.iconSlot.className = 'category-button__icon';
        if (this.configuration.icon) {
            if (/\.(png|jpe?g|svg)$/i.test(this.configuration.icon)) {
                const img = document.createElement('img');
                img.src = this.configuration.icon;
                this.iconSlot.appendChild(img);
            } else {
                this.iconSlot.textContent = this.configuration.icon;
            }
        }
        this.element.appendChild(this.iconSlot);

        // text
        this.textSpan = document.createElement('span');
        this.textSpan.className = 'category-button__text';
        this.textSpan.textContent = this.configuration.name;
        this.element.appendChild(this.textSpan);

        // top-right icon (e.g. ❗)
        if (this.configuration.top_icon) {
            this.topSlot = document.createElement('span');
            this.topSlot.className = 'category-button__top-icon';
            this.topSlot.textContent = this.configuration.top_icon;
            this.element.appendChild(this.topSlot);
        }

        // attach GUI_Object context‐menu machinery + your click handler
        this.assignListeners(this.element);

        // Add to favorites for categories
        const favorites_context_menu_item = new ContextMenuItem('favorites',
            {name: 'Add to favorites', front_icon: '⭐'})

        this.addItemToContextMenu(favorites_context_menu_item);
        favorites_context_menu_item.callbacks.get('click').register(this.onFavoritesClick.bind(this));
    }

    onFavoritesClick() {
        activeGUI.addShortcut(this.category);
    }

    /** required by GUI_Object */
    getElement() {
        return this.element;
    }

    /** retains the old “selected” / “not‐selected” styling */
    setSelected(selected) {
        this.element.classList.toggle('selected', selected);
        this.element.classList.toggle('not-selected', !selected);
    }

    /** fires the usual Category.setCategory */
    onClick() {
        console.log('CategoryButton clicked');
        this.callbacks.get('click').call(this.category);
        activeGUI.setCategory(this.category.id);
        // Save the first page into local storage
        const firstPage = Object.values(this.category.pages)[0];
        if (firstPage) {
            this.category.setPage(firstPage.id);
            writeToLocalStorage(`${activeGUI.id}_active_page`, firstPage.id);
        } else {
            console.warn(`Category "${this.category.id}" has no pages to select.`);
        }
    }

    /** if you ever need to update name / icon at runtime */
    updateConfig(cfg) {
        if (cfg.name != null) this.textSpan.textContent = cfg.name;
        if (cfg.icon != null) this.iconSlot.textContent = cfg.icon;
        if (cfg.top_icon != null) {
            if (!this.topSlot) {
                this.topSlot = document.createElement('span');
                this.topSlot.className = 'category-button__top-icon';
                this.element.appendChild(this.topSlot);
            }
            this.topSlot.textContent = cfg.top_icon;
        }
    }

    assignListeners(element) {
        super.assignListeners(element);
        element.addEventListener('click', this.onClick.bind(this));
    }

    update(data) {
    }

    initializeElement() {
    }

    resize() {
    }
}


class CategoryHeadbar extends WidgetGroup {
    constructor(id, payload = {}) {
        super(id, payload);
    }
}

/* ================================================================================================================== */
class Category {

    /** @type {Object<string,Page>} */
    pages = {};

    /** @type {Page|null} */
    page = null;

    /** @type {Object<string,Category>} */
    categories = {};

    /** @type {Callbacks} */
    callbacks = null;

    /** @type {Object} */
    configuration = {};

    /** @type {string} */
    id = '';

    /** @type {CategoryButton|null} */
    button = null;

    /** @type {Object<number,HTMLElement|null>} */
    page_buttons = {};

    /** @type {HTMLElement|null} */
    page_grid = null;

    /** @type {HTMLElement|null} */
    content_grid = null;


    /**
     * @param {string} id
     * @param {Object} [configuration={}]
     * @param {Object} [pages={}]         – map of page-definitions
     * @param {Object} [categories={}]    – map of subcategory-definitions
     * @param headbar_payload
     */
    constructor(id, configuration = {}, pages = {}, categories = {}, headbar_payload = {}) {
        this.id = id;

        const default_configuration = {
            name: id,
            collapsed: false,
            color: 'rgba(40,40,40,0.7)',
            text_color: 'rgba(255,255,255,0.7)',
            icon: null,
            top_icon: null,
            number_of_pages: +getComputedStyle(document.documentElement).getPropertyValue('--page_bar-cols'),
            max_pages: +getComputedStyle(document.documentElement).getPropertyValue('--page_bar-cols'),
        };

        this.configuration = {...default_configuration, ...configuration};
        this.parent = null;

        this.callbacks = new Callbacks();
        this.callbacks.add('event');
        this.pages = {};
        this.categories = {};
        this.page = null;

        // main button for this category
        this.button = this._generateButton();

        // slots for page-buttons
        this.page_buttons = {};
        for (let i = 0; i < this.configuration.number_of_pages; i++) {
            this.page_buttons[i] = null;
        }

        // container for page buttons
        this._createPageGrid();

        this.headbar = new CategoryHeadbar(headbar_payload.id, headbar_payload);
        this.headbar.callbacks.get('event').register(this.onEvent.bind(this))

        // build out any initially defined pages & categories
        if (Object.keys(pages).length > 0) {
            this.buildPagesFromDefinition(pages);
        }
        if (Object.keys(categories).length > 0) {
            this.buildCategoriesFromDefinition(categories);
        }
    }

    /* -------------------------------------------------------------------------------------------------------------- */

    /**
     * Look up something by path, descending into sub-categories first, then pages.
     * Now supports absolute UIDs that include the reserved "categories" keyword.
     * @param {string} path
     * @returns {Category|Page|CategoryHeadbar|null}
     */
    getObjectByPath(path) {
        const [firstSegment, remainder] = splitPath(path);
        if (!firstSegment) return null;

        // if the path explicitly includes the "categories" keyword,
        // treat the next segment as a subcategory ID
        if (firstSegment === 'categories') {
            // e.g. path = "categories/subcat1/…"
            const [catName, nextRemainder] = splitPath(remainder);
            if (!catName) return null;
            const fullKey = `${this.id}/categories/${catName}`;
            const subCat = this.categories[fullKey];
            if (!subCat) return null;
            return nextRemainder
                ? subCat.getObjectByPath(nextRemainder)
                : subCat;
        } else if (firstSegment === 'headbar') {
            if (!remainder) return this.headbar;
            return this.headbar.getObjectByPath(remainder);
        }

        // otherwise fall back to legacy behavior
        const fullKey = `${this.id}/${firstSegment}`;

        // 1) Sub-category?
        const subCat = this.categories[fullKey];
        if (subCat) {
            if (!remainder) return subCat;
            return subCat.getObjectByPath(remainder);
        }

        // 2) Page?
        const page = this.pages[fullKey];
        if (page) {
            if (!remainder) return page;
            return page.getObjectByPath(remainder);
        }

        return null;
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    getGUI() {
        if (this.parent instanceof Category) {
            return this.parent.getGUI();
        } else if (this.parent instanceof GUI) {
            return this.parent;
        }
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    update(data) {
        console.warn('Category update is not yet implemented.');
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    handleAddMessage(data) {

        const object_type = data.type

        switch (object_type) {
            case 'page':
                this.buildPageFromDefinition(data.config);
                break;
            case 'category':
                this.buildCategoryFromDefinition(data.config);

                const gui = this.getGUI();
                if (gui) {
                    gui.renderCategoryTree();
                }
                break;
        }
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    handleRemoveMessage(data) {
        const object_type = data.type

        switch (object_type) {
            case 'page':
                const page_id = data.id
                const page = this.pages[page_id]
                if (page) {

                    // Remove the page's button
                    page.button.remove()
                    page.grid.remove()
                    delete this.pages[page_id]

                    // Switch active page
                    if (this.page === page) {
                        // check the length of the this.pages array. If bigger than 0, then choose the first one
                        if (Object.keys(this.pages).length > 0) {
                            this.setPage(Object.keys(this.pages)[0])
                        } else {
                            // if the length is 0, then set the page to null
                            this.setPage(null)
                        }
                    }

                }
                break;
            case 'category':
                const category_id = data.id;
                const category = this.categories[category_id];
                if (category) {
                    // category.content_grid.remove()
                    delete this.categories[category_id];
                    // Switch active category if it was this category

                    if (isObject(category.id, this.getGUI().category.id)) {
                        this.getGUI().setCategory(this.id);
                    }


                    this.getGUI().renderCategoryTree();
                }
        }
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    /**
     * Build multiple pages from a definition map
     * @param {Object<string,*>} pages
     */
    buildPagesFromDefinition(pages) {
        for (const [_, config] of Object.entries(pages)) {
            this.buildPageFromDefinition(config);
        }
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    /**
     * Build a single page from its definition and add it
     * @param {{id:string, config:Object, objects:Object, position?:number}} page_definition
     */
    buildPageFromDefinition(page_definition) {
        const new_page = new Page(
            page_definition.id,
            page_definition.config,
            page_definition.objects
        );
        this.addPage(new_page, page_definition.position);
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    /**
     * Build multiple subcategories from a definition map
     * @param {Object<string,*>} categories
     */
    buildCategoriesFromDefinition(categories) {
        for (const [_, config] of Object.entries(categories)) {
            this.buildCategoryFromDefinition(config);
        }
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    /**
     * Build a single subcategory from its definition and add it
     * @param {{id:string, config:Object, pages:Object, categories:Object, position?:number}} cat_definition
     */
    buildCategoryFromDefinition(cat_definition) {
        const new_category = new Category(
            cat_definition.id,
            cat_definition.config,
            cat_definition.pages || {},
            cat_definition.categories || {},
            cat_definition.headbar || {}
        );
        this.addCategory(new_category, cat_definition.position);
    }


    /* -------------------------------------------------------------------------------------------------------------- */
    _generateButton() {
        return new CategoryButton(this.id,
            this,
            {
                config: {
                    name: this.configuration.name,
                    icon: this.configuration.icon,
                    top_icon: this.configuration.top_icon,
                    text_color: this.configuration.text_color
                }
            }
        );
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    _createPageGrid() {
        this.page_grid = document.createElement('div');
        this.page_grid.id = `page_${this.id}_grid`;
        this.page_grid.className = 'page_bar_grid';
    }


    hidePages() {
        Object.values(this.pages).forEach(pg => {
            pg.grid.style.display = 'none';
        });
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    /**
     * Add a ControlGUI_Page to this category
     * @param {Page} page
     * @param {number|null} position
     */
    addPage(page, position = null) {
        if (this.pages[page.id]) {
            console.warn(`Page with ID "${page.id}" already exists in category "${this.id}".`);
            return;
        }

        // find or validate slot
        if (position !== null) {
            if (this.page_buttons[position - 1] !== null) {
                console.warn(`Position ${position} already used in category "${this.id}".`);
                return;
            }
        } else {
            for (let i = 1; i <= this.configuration.number_of_pages; i++) {
                if (this.page_buttons[i - 1] === null) {
                    position = i;
                    break;
                }
            }
            if (position === null) {
                console.warn(`No free page slots in category "${this.id}".`);
                return;
            }
        }

        // wire up button
        this.page_buttons[position - 1] = page.button;
        // const button_element = page.button.getElement();
        // button_element.style.gridRow = '1';
        // button_element.style.gridColumn = String(position);
        // this.page_grid.appendChild(button_element);
        page.button.attach(this.page_grid, [1, position], [1, 1]);
        page.button.on('click', () => this.setPage(page.id));


        // register
        this.pages[page.id] = page;
        page.parent = this;
        page.callbacks.get('event').register(this.onEvent.bind(this));

        // Add the pages grid to my content grid
        if (this.content_grid) {
            // only attach it if it isn’t already in the DOM
            if (page.grid.parentNode !== this.content_grid) {
                this.content_grid.appendChild(page.grid);
            }
            Object.assign(page.grid.style, {
                position: 'absolute',
                top: '0',
                left: '0',
                width: '100%',
                height: '100%',
                display: 'none',
            });
        }

        // if first page, show it
        if (this.page === null) {
            this.setPage(page.id);
        }
    }


    /* -------------------------------------------------------------------------------------------------------------- */
    /**
     * Add a ControlGUI_Category as a nested subcategory
     * @param {Category} category
     * @param {number|null} position   – currently unused for UI
     */
    addCategory(category, position = null) {
        if (this.categories[category.id]) {
            console.warn(`Category with ID "${category.id}" already exists under "${this.id}".`);
            return;
        }
        this.categories[category.id] = category;
        category.parent = this;
        category.callbacks.get('event').register(this.onEvent.bind(this));

    }


    /* -------------------------------------------------------------------------------------------------------------- */
    /**
     * Render page-buttons into `container` and absolutely‐position all page.grids
     * (unchanged from before)
     */
    buildCategory(page_bar_container, headbar_container, content_grid) {

        const gui = this.getGUI();
        // 1) collapse or show the entire page‐bar row
        if (gui) {
            gui.showPageBar(this.configuration.max_pages > 1);
        }
        // 2) populate (or clear) the page‐bar itself
        page_bar_container.innerHTML = '';
        if (this.configuration.max_pages > 1) {
            page_bar_container.style.display = '';
            page_bar_container.appendChild(this.page_grid);
        } else {
            // we’ve already hidden the <nav>, but just in case:
            page_bar_container.style.display = 'none';
        }


        // 3) Set the headbar
        headbar_container.innerHTML = '';
        headbar_container.appendChild(this.headbar.element);


        this.content_grid = content_grid;
        this.content_grid.style.position = 'relative';

        Object.values(this.pages).forEach(page => {
            if (page.grid.parentNode !== this.content_grid) {
                this.content_grid.appendChild(page.grid);
                Object.assign(page.grid.style, {
                    position: 'absolute',
                    top: '0',
                    left: '0',
                    width: '100%',
                    height: '100%',
                    display: 'none',
                });
            } else {
                page.grid.style.display = 'none';
            }
        });

        const startId = this.page ? this.page.id : Object.keys(this.pages)[0];
        if (startId) this.setPage(startId);
        else this._renderEmpty(page_bar_container, content_grid);
    }

    _renderEmpty(container, content_grid) {
        content_grid.innerHTML = '';
    }


    /* -------------------------------------------------------------------------------------------------------------- */
    /**
     * Switch visible page (unchanged)
     * @param {string|Page} pageOrId
     */
    setPage(pageOrId) {
        const id = pageOrId instanceof Page ? pageOrId.id : pageOrId;
        const page = this.pages[id];
        if (!page) {
            console.warn(`Page "${id}" not found in category "${this.id}".`);
            return;
        }

        Object.values(this.pages).forEach(p => {
            p.grid.style.display = 'none';
            p.button.deselect();
        });

        page.grid.style.display = 'grid';
        page.button.select();
        window.dispatchEvent(new Event('resize'));
        this.page = page;

    }


    /* -------------------------------------------------------------------------------------------------------------- */
    onEvent(event) {
        this.callbacks.get('event').call(event);
    }
}

export class Popup {
    constructor(id, config = {}, payload = {}) {
        this.id = id;

        const defaultConfig = {
            type: 'window',      // 'window' or 'dialog' or 'tab'
            title: 'Popup',
            background_color: [0.2, 0.2, 0.2],
            text_color: [1, 1, 1],
            size: [800, 400],
            resizable: true,
            closeable: true,     // only applies to dialog
            disable_gui: true,   // disable GUI as long as popup is open (only for dialog)
            title_font_size: 10, // pt
        };

        // Merge without adopting undefined
        const safeConfig = {
            ...defaultConfig,
            ...Object.fromEntries(
                Object.entries(config).filter(([, v]) => v !== undefined)
            ),
        };

        this.config = safeConfig;
        this._title = (typeof this.config.title === 'string' && this.config.title.trim())
            ? this.config.title.trim()
            : defaultConfig.title;

        this.groupWidget = this.createGroupWidget(payload);

        this._win = null;
        this._poll = null;
        this._dialogEl = null;
        this._overlayEl = null;     // for dialog popups
        this._shellBlobUrl = null;  // keep to revoke later
        this._messageHandler = null;
        this._isClosed = false;     // prevents repeated closed events
        this._attached = false;     // ensure we attach only once

        this.callbacks = new Callbacks();
        this.callbacks.add('event');
        this.callbacks.add('closed');
    }

    createGroupWidget(payload) {
        const {id} = payload;
        const groupWidget = new WidgetGroup(id, payload);
        groupWidget.callbacks.get('event').register((ev) => {
            this.callbacks.get('event').call({popupId: this.id, ...ev});
        });
        return groupWidget;
    }

    _getShellURL() {
        try {
            return new URL('./lib/popup-shell.html', import.meta.url).href;
        } catch {
            return null;
        }
    }

    _buildShellHTML() {
        const popupCssURL = new URL('./lib/styles/popup.css', import.meta.url).href;
        const objectsCssURL = new URL('./lib/styles/objects.css', import.meta.url).href;
        const stylesCssURL = new URL('./lib/styles/styles.css', import.meta.url).href;
        const widgetStylesURL = new URL('./lib/styles/widget-styles.css', import.meta.url).href;
        const terminalStylesURL = new URL('./lib/cli_terminal/cli_terminal.css', import.meta.url).href;
        const lineplotStylesURL = new URL('./lib/plot/lineplot/lineplot.css', import.meta.url).href;

        // Ensure we always write a non-empty title
        const safeTitle = this._title;

        return `<!DOCTYPE html>
<html style="height:100%" lang="en">
<head>
  <meta charset="utf-8">
  <title>${safeTitle.replace(/</g, '&lt;').replace(/>/g, '&gt;')}</title>
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <link rel="stylesheet" href="${popupCssURL}">
  <link rel="stylesheet" href="${objectsCssURL}">
  <link rel="stylesheet" href="${stylesCssURL}">
  <link rel="stylesheet" href="${widgetStylesURL}">
  <link rel="stylesheet" href="${terminalStylesURL}">
  <link rel="stylesheet" href="${lineplotStylesURL}"></link>
  <script>
    // Re-apply title when DOM is ready, and notify the opener.
    document.addEventListener('DOMContentLoaded', function () {
      document.title = ${JSON.stringify(safeTitle)};
      try { window.opener && window.opener.postMessage({ type: 'popup-shell-ready' }, '*'); } catch {}
    });
  </script>
  <style>html, body { height:100%; margin:0; }</style>
</head>
<body>
  <div id="popup-root" style="height:100%; display:flex; flex-direction:column;"></div>
</body>
</html>`;
    }

    _openRealShell(target, features = '') {
        const shellURL = this._getShellURL();
        if (!shellURL) return null;

        // Add non-empty, encoded title param
        const url = new URL(shellURL);
        url.searchParams.set('t', this._title);

        try {
            const w = window.open(url.href, target, features || undefined);
            if (!w || w.closed) return null;
            return w;
        } catch (e) {
            console.warn('Popup: failed to open real shell URL.', e);
            return null;
        }
    }

    _openWithBlobURL(target, features = '') {
        return;
        try {
            const html = this._buildShellHTML();
            const blob = new Blob([html], {type: 'text/html'});
            this._shellBlobUrl = URL.createObjectURL(blob);
            const w = window.open(this._shellBlobUrl, target, features || undefined);
            if (!w || w.closed) return null;
            return w;
        } catch (e) {
            console.warn('Popup: failed to create/open Blob URL shell.', e);
            return null;
        }
    }

    _installMessageBridge() {
        if (this._messageHandler) return; // only once
        this._messageHandler = (ev) => {
            if (ev && ev.data && ev.data.type === 'popup-shell-ready') {
                this._attachIntoChildWindow();
            }
            if (ev && ev.data && ev.data.type === 'popup-set-title') {
                try {
                    if (this._win && this._win.document) this._win.document.title = String(ev.data.title || this._title);
                } catch {
                }
            }
        };
        window.addEventListener('message', this._messageHandler);
    }

    _removeMessageBridge() {
        if (this._messageHandler) {
            window.removeEventListener('message', this._messageHandler);
            this._messageHandler = null;
        }
    }

    async _attachIntoChildWindow() {
        if (!this._win || this._attached) return; // attach only once
        this._attached = true;

        // Apply title one more time (in case the shell didn't).
        try {
            this._win.document.title = this._title;
        } catch {
        }

        // Wait until #popup-root exists (the shell page has loaded)
        const root = await this._waitForElement(() => {
            try {
                return this._win && this._win.document && this._win.document.getElementById('popup-root');
            } catch {
                return null;
            }
        }, 4000);

        if (!root) {
            // As a last resort, write the shell directly (same-origin)
            try {
                const doc = this._win.document;
                doc.open();
                doc.write(this._buildShellHTML());
                doc.close();
            } catch (e) {
                console.warn('Popup: fallback document.write failed.', e);
            }
        }

        // Attach UI
        try {
            const doc = this._win.document;
            if (doc && doc.body) {
                doc.body.style.backgroundColor = getColor(this.config.background_color);
            }
            const mount = doc.getElementById('popup-root');
            if (mount) this._attachGroup(mount);
        } catch (e) {
            console.warn('Popup: failed to attach group into child window.', e);
        }

        // Install a single poller to watch for manual close
        if (!this._poll) {
            this._poll = setInterval(() => {
                // In some browsers, accessing .closed after navigation can throw
                try {
                    if (!this._win || this._win.closed) {
                        clearInterval(this._poll);
                        this._poll = null;
                        this.close_manually();
                    }
                } catch {
                    clearInterval(this._poll);
                    this._poll = null;
                    this.close_manually();
                }
            }, 500);
        }
    }

    _waitForElement(getterFn, timeoutMs = 3000) {
        return new Promise((resolve) => {
            const start = Date.now();
            const tick = () => {
                const el = getterFn();
                if (el) return resolve(el);
                if (Date.now() - start > timeoutMs) return resolve(null);
                setTimeout(tick, 50);
            };
            tick();
        });
    }

    _openDialogFallback() {
        if (this._dialogEl) return;

        this._dialogEl = document.createElement('div');
        this._dialogEl.id = this.id;
        this._dialogEl.classList.add('popup', 'popup-dialog');

        // Make the dialog the correct size
        const [width, height] = this.config.size;
        this._dialogEl.style.width = `${width}px`;
        this._dialogEl.style.height = `${height}px`;

        // title bar
        const titleBar = document.createElement('div');
        titleBar.classList.add('popup-titlebar');
        titleBar.textContent = this._title;
        titleBar.style.fontSize = `${this.config.title_font_size}pt`;
        titleBar.style.paddingTop = '3px';
        titleBar.style.paddingBottom = '3px';
        titleBar.style.paddingLeft = '10px';
        this._dialogEl.appendChild(titleBar);

        if (this.config.closeable) {
            const btn = document.createElement('button');
            btn.classList.add('popup-close-btn');
            btn.textContent = '×';
            btn.addEventListener('click', () => this.close_manually());
            titleBar.appendChild(btn);
        }

        // content area
        const content = document.createElement('div');
        content.classList.add('popup-content');
        this._dialogEl.appendChild(content);

        document.body.appendChild(this._dialogEl);

        this._attachGroup(content);
    }

    _attachGroup(container) {
        container.appendChild(this.groupWidget.getElement());
    }

    close_manually() {
        if (this._isClosed) return;
        this._isClosed = true;

        if (this._poll) {
            clearInterval(this._poll);
            this._poll = null;
        }
        this._removeMessageBridge();

        this.callbacks.get('event').call({
            id: this.id,
            event: 'closed',
            data: {}
        });

        this.callbacks.get('closed').call(this.id);
    }

    close() {
        if (this._isClosed) return;
        this._isClosed = true;

        if (this._win && !this._win.closed) {
            try {
                this._win.close();
            } catch {
            }
        }
        if (this._poll) {
            clearInterval(this._poll);
            this._poll = null;
        }
        this._removeMessageBridge();

        if (this._dialogEl) {
            this._dialogEl.remove();
            this._dialogEl = null;
        }
        if (this._shellBlobUrl) {
            URL.revokeObjectURL(this._shellBlobUrl);
            this._shellBlobUrl = null;
        }
        this._hideOverlay();

        console.warn(`Popup "${this.id}" closed.`);
        this.callbacks.get('closed').call(this.id);
    }

    _openTab() {
        this._installMessageBridge();

        // this._openWithBlobURL('_blank');
        // Prefer real same-origin shell → correct title immediately
        this._win = this._openRealShell('_blank');

        // Fallback to Blob shell (title set in HTML + JS)
        if (!this._win || this._win.closed) {
            this._win = this._openWithBlobURL('_blank');
        }

        if (!this._win || this._win.closed) {
            console.warn(`Popup.open: window.open blocked, falling back to dialog for "${this.id}"`);
            this._removeMessageBridge();
            this._openDialogFallback();
            return;
        }

        // Timed attach in case message fires too early
        this._attachIntoChildWindow();
    }

    open() {
        const [width, height] = this.config.size;

        // ── Compute center coordinates ─────────────────────────────────────────
        const screenX = window.screenX !== undefined ? window.screenX : window.screen.left;
        const screenY = window.screenY !== undefined ? window.screenY : window.screen.top;
        const availWidth = window.innerWidth || screen.width;
        const availHeight = window.innerHeight || screen.height;

        const left = Math.round(screenX + (availWidth - width) / 2);
        const top = Math.round(screenY + (availHeight - height) / 2);

        if (this.config.type === 'window') {
            const features = [
                `width=${width}`,
                `height=${height}`,
                `left=${left}`,
                `top=${top}`,
                `resizable=${this.config.resizable ? 'yes' : 'no'}`,
            ].join(',');

            this._installMessageBridge();

            // Prefer real same-origin shell
            this._win = this._openRealShell(this.id, features);

            // Fallback to Blob shell
            if (!this._win || this._win.closed) {
                this._win = this._openWithBlobURL(this.id, features);
            }

            // If popup blocked, fallback to dialog
            if (!this._win || this._win.closed) {
                console.warn(`Popup.open: window.open blocked, falling back to dialog for "${this.id}"`);
                this._removeMessageBridge();
                this._openDialogFallback();
                return;
            }

            // Timed attach as additional safety
            this._attachIntoChildWindow();

        } else if (this.config.type === 'tab') {
            this._openTab();
        } else {
            // dialog
            this._openDialogFallback();
        }

        // if it's a dialog and GUI should be disabled underneath
        if (this.config.type === 'dialog' && this.config.disable_gui) {
            this._showOverlay();
        }
    }

    hide() {
        if (this._dialogEl) this._dialogEl.style.display = 'none';
    }

    getObjectByPath(path) {
        let key, remainder;
        [key, remainder] = splitPath(path);

        const childKey = `${this.id}/${key}`;

        if (childKey === this.groupWidget.id) {
            if (!remainder) {
                return this.groupWidget;
            } else {
                return this.groupWidget.getObjectByPath(remainder);
            }
        }
    }

    // ── overlay helpers ─────────────────────────────────────────────────────
    _showOverlay() {
        const overlay = document.createElement('div');
        overlay.id = `${this.id}__overlay`;
        overlay.classList.add('popup-gui-overlay');
        document.body.appendChild(overlay);
        this._overlayEl = overlay;
    }

    _hideOverlay() {
        if (this._overlayEl) {
            this._overlayEl.display = 'none';
            document.body.removeChild(this._overlayEl);
            this._overlayEl.remove();
            this._overlayEl = null;
            console.log('Overlay removed.');
        }
    }
}

/* ================================================================================================================== */
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
        // user clicked “×” → notify backend
        if (this.on_event_callback) {
            this.on_event_callback({id: this.id, event: 'close', data: {}});
        }
    }

    close() {
        const el = this.element;
        // 1) start the CSS transition
        el.classList.add('closing');

        // 2) when it’s done, actually remove it
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

/* ================================================================================================================== */
export class GUI {

    grid = null;
    content = null;
    head_bar = null;
    head_bar_grid = null;
    page_bar = null;
    category_bar = null;
    terminal_container = null;
    rows = 0;
    cols = 0;

    _emergencyArmed = false;
    _armTimeoutId = null;

    /** @type {Object} */
    category_buttons = {};

    /** @type {Object} */
    popups = {};


    /** @type {Object} */
    callouts = {};


    /** @type {Object} */
    configuration = {};

    /** @type {boolean} */
    connected = false;

    /** @type {Object} */
    popup_terminals = {};


    /* ===============================================================================================================*/
    constructor(rootContainer, configuration = {}) {

        const default_configuration = {
            number_of_categories: 10,
            show_category_bar: true,
            // auto_hide_category_bar: true,
            callout_position: ['right', 'bottom'],
            callout_margins: [10, 200]
        }

        this.rootContainer = rootContainer;
        this.configuration = {...default_configuration, ...configuration};

        this.globalInitialize();
        this.initializeGUI();
        // 1) Kick off the splash
        // this.showSplash('bilbolab_logo.png', () => {
        //     // 2) Once done, run the normal GUI setup
        //     this.initializeGUI();
        // });

        setActiveGUI(this);
    }

    /* ===============================================================================================================*/
    initializeGUI() {
        this.drawGUI();
        this.showCategoryBar(this.configuration.show_category_bar);

        this.category = null;
        this.categories = {}
        this.category_buttons = {}

        for (let i = 0; i < this.configuration.number_of_categories; i++) {
            this.category_buttons[i] = null;
        }

        this.addLogo();
        this.addConnectionIndicator();

        const websocket_host = import.meta.env.VITE_WS_HOST || window.location.hostname;
        const websocket_port = parseInt(import.meta.env.VITE_WS_PORT, 10) || GUI_WS_DEFAULT_PORT;

        this.websocket = new Websocket({host: websocket_host, port: websocket_port})
        this.websocket.connect();
        this.websocket.on('message', this.onWsMessage.bind(this));
        this.websocket.on('connected', this.onWsConnected.bind(this));
        this.websocket.on('close', this.onWSDisconnected.bind(this));
        this.websocket.on('error', this.onWsError.bind(this));

        this.resetGUI();

        this._clearRateTimer = null;

        window.addEventListener('keydown', this._onWindowKeyDown.bind(this));

    }

    /* ===============================================================================================================*/
    closeWindow() {
        // hack to make some browsers treat this as a script-opened window
        window.open('', '_self').close();
    }

    /* ===============================================================================================================*/
    globalInitialize() {

    }

    /* ===============================================================================================================*/
    testFunction(input) {
        console.log("Test function called with input:");
        console.log(input);
        this.terminal.print(`Test function called with input: ${input}`);
    }

    /* ===============================================================================================================*/
    deleteAllLocalStorage() {
        // If the GUI is not initialized yet, i.e. has no ID, do nothing
        if (!this.id) {
            console.warn("GUI not initialized, cannot delete localStorage.");
            return;
        }

        // Get all keys in localStorage that start with this.id
        const keysToDelete = Object.keys(localStorage).filter(key => key.startsWith(this.id));

        // Delete each key
        keysToDelete.forEach(key => {
            localStorage.removeItem(key);
        });
    }


    /* ===============================================================================================================*/
    drawGUI() {
        // clear any existing content
        this.rootContainer.innerHTML = '';

        // ── HEADER / HEADBAR ────────────────────────────────────────────────────
        this.head_bar = document.createElement('header');
        this.head_bar.id = 'headbar';
        this.head_bar_grid = document.createElement('div');
        this.head_bar_grid.id = 'headbar_grid';
        this.head_bar.appendChild(this.head_bar_grid);
        this.rootContainer.appendChild(this.head_bar);

        // ── SIDE PLACEHOLDER ───────────────────────────────────────────────────
        this.side_placeholder = document.createElement('div');
        this.side_placeholder.id = 'side_placeholder';
        this.rootContainer.appendChild(this.side_placeholder);

        // ── ROBOT STATUS BAR ───────────────────────────────────────────────────
        this.category_head_bar = document.createElement('div');
        this.category_head_bar.id = 'category_head_bar';
        this.rootContainer.appendChild(this.category_head_bar);

        // ── PAGE BAR ───────────────────────────────────────────────────────────
        this.page_bar = document.createElement('nav');
        this.page_bar.id = 'page_bar';
        this.page_bar_grid = document.createElement('div');
        this.page_bar_grid.id = 'page_bar_grid';
        this.page_bar_grid.className = 'page_bar_grid';
        this.page_bar.appendChild(this.page_bar_grid);
        this.rootContainer.appendChild(this.page_bar);

        // ── CATEGORY BAR ───────────────────────────────────────────────────────
        this.category_bar = document.createElement('aside');
        this.category_bar.id = 'category_bar';

        // <— instead of a <div class="grid">, make a <ul> for nesting
        this.category_bar_list = document.createElement('ul');
        this.category_bar_list.id = 'category_bar_list';
        this.category_bar.appendChild(this.category_bar_list);

        this.rootContainer.appendChild(this.category_bar);


        // ── MAIN CONTENT ───────────────────────────────────────────────────────
        this.content = document.createElement('main');
        this.content.id = 'content';
        this.rootContainer.appendChild(this.content);

        // ── FOOTER / TERMINAL ──────────────────────────────────────────────────
        this.bottombar = document.createElement('footer');
        this.bottombar.id = 'bottombar';

        this.terminal_container = document.createElement('div');
        this.terminal_container.id = 'terminal-container';
        this.terminal_container.className = 'terminal-container';


        this.bottombar.appendChild(this.terminal_container);

        this.rootContainer.appendChild(this.bottombar);

        this.apps_container = document.createElement('div');
        this.apps_container.className = 'apps-container';
        this.bottombar.appendChild(this.apps_container);

        this.shortcuts_container = document.createElement('div');
        this.shortcuts_container.className = 'shortcuts-container';
        this.bottombar.appendChild(this.shortcuts_container);

        this.drawShortcutsContainer();

        const emergency_container = document.createElement('div');
        emergency_container.className = 'emergency-container';
        this.bottombar.appendChild(emergency_container);

        this.stopButton = document.createElement('button');
        this.stopButton.className = 'stop-button';
        emergency_container.appendChild(this.stopButton);

        const stopIcon = document.createElement('img');
        stopIcon.src = 'emergency_stop.png';
        stopIcon.alt = 'Stop';
        stopIcon.className = 'stop-icon';
        this.stopButton.appendChild(stopIcon);

        // Add a click listener to the stop button
        this.stopButton.addEventListener('click', () => {
            this._emergencyStop();
        });


        // Initial Display
        this.bottombar.style.display = 'none';
    }

    /* ===============================================================================================================*/
    drawShortcutsContainer() {
        this.shortcuts_group = new WidgetGroup('shortcuts', {
                config: {
                    rows: 3,
                    columns: 2,
                    border_width: 0,
                    gap: 3,
                    fit: true,
                    title: 'Favorites ⭐',
                    title_bottom_border: false,
                    fill_empty: true,
                    non_fit_aspect_ratio: 0.5
                }
            }
        );
        this.shortcuts_container.appendChild(this.shortcuts_group.getElement());
    }

    /* ===============================================================================================================*/
    addShortcut(object, text = null, save = true) {
        // Create a button widget for the shortcut

        let object_id;
        // Check if page is a string or an actual page
        if (typeof object === 'string') {
            object_id = object;
        } else {
            object_id = object.id;
        }

        let button_text = text;
        if (text === null) {
            if (object instanceof Page) {
                button_text = `${object.parent.configuration.name} / ${object.configuration.name}`
            } else if (object instanceof Category) {
                if (object.configuration.icon) {
                    button_text = `${object.configuration.icon} ${object.configuration.name}`
                } else {
                    button_text = object.configuration.name;
                }

            } else {
                button_text = object_id;
            }
        }

        const button = new ShortcutButton(object_id, {
                config: {
                    text: button_text,
                }
            }
        );

        const free_spot = this.shortcuts_group.getEmptySpot(1, 1);

        if (!free_spot) {
            this.terminal.print(`No free spot in shortcuts group for object "${object_id}".`, 'orange');
            return;
        }

        // Add the button to the shortcuts group
        this.shortcuts_group.addObject(button,
            free_spot[0], free_spot[1], 1, 1);

        if (save) {
            this.storeShortcuts();
        }
    }

    /* ===============================================================================================================*/
    removeShortcut(page) {
        // Lookup the entry by its id in the map
        const entry = this.shortcuts_group.objects[page];
        if (!entry) {
            console.warn(`Shortcut for page "${page}" not found in shortcuts group.`);
            return;
        }

        // Remove it (removeObject accepts either the id string or the child instance)
        this.shortcuts_group.removeObject(page);

        // Store the shortcuts
        this.storeShortcuts();
        this.updateShortcuts();
    }

    /* ===============================================================================================================*/
    /**
     * This is called whenever a page or category is added, to check if the stored shortcut is accessible
     */
    updateShortcuts() {
        // Make a copy of the current shortcut objects
        const shortcuts = {};

        // Copy the id and text out of each shortcut
        for (const [id, shortcut] of Object.entries(this.shortcuts_group.objects)) {
            shortcuts[id] = {
                id: id,
                text: shortcut.configuration.text
            }
        }

        // Clear the group
        this.shortcuts_group.clear();

        // Add the shortcuts back to the group
        for (const [id, shortcut] of Object.entries(shortcuts)) {
            this.addShortcut(id, shortcut.text, false);
        }

        // Loop through all objects in the shortcuts group
        for (const [id, entry] of Object.entries(this.shortcuts_group.objects)) {
            // Check if the object exists
            const object = this.getObjectByUID(id);
            if (!object) {
                entry.disable();
            } else {
                entry.enable();
            }
        }
    }

    /* ===============================================================================================================*/
    storeShortcuts() {
        const shortcuts_key = `${this.id}_shortcuts`;

        // Check if it already is in local storage, if yes, remove it
        if (existsInLocalStorage(shortcuts_key)) {
            removeFromLocalStorage(shortcuts_key);
        }

        // Generate a shortcut array and go through this.shortcuts_group to store their ids
        const shortcuts = [];
        for (const [key, value] of Object.entries(this.shortcuts_group.objects)) {

            if (key === 'undefined') continue;

            const shortcut_data = {
                page_id: key,
                text: value.configuration.text || key,
            }

            shortcuts.push(shortcut_data);
        }

        // Store the array in local storage
        writeToLocalStorage(shortcuts_key, shortcuts);
    }

    /* ===============================================================================================================*/
    /**
     * Load the shortcuts from local storage, if possible
     */
    restoreShortcuts() {
        this.shortcuts_group.clear();

        const shortcuts_key = `${this.id}_shortcuts`;
        if (existsInLocalStorage(shortcuts_key)) {
            const shortcuts = getFromLocalStorage(shortcuts_key);

            // Loop over the shortcut array and generate shortcuts
            for (const shortcut of shortcuts) {

                // Check if shortcut is an object, if not return
                if (typeof shortcut !== 'object') {
                    console.warn(`Shortcut "${shortcut}" is not an object.`);
                    continue;
                }
                this.addShortcut(shortcut.page_id, shortcut.text, false); // Do not save it to local storage since we just received it
            }
        }
        this.updateShortcuts();
    }

    /* ===============================================================================================================*/
    showPageBar(show) {
        if (show) {
            // put the page_bar back…
            this.page_bar.style.display = '';
            // …and restore your default CSS template‐rows
            this.rootContainer.style.gridTemplateRows = '';
        } else {
            // hide the page_bar completely
            this.page_bar.style.display = 'none';
            // collapse that row to zero and let content fill it
            this.rootContainer.style.gridTemplateRows =
                'var(--headbar-height) ' +
                'var(--category-bar-height) ' +
                '0 ' +               // ← collapse the “pages” row
                'auto ' +             // ← content now starts here
                'var(--bottom-height)';
        }
    }

    /* ===============================================================================================================*/
    showCategoryBar(show) {
        // Do we currently have the bar hidden?

        if (show) {
            // → SHOW IT AGAIN
            this.category_bar.style.display = '';
            // restore the grid-template-columns from your CSS
            this.rootContainer.style.gridTemplateColumns = '';
        } else {
            // → HIDE IT
            this.category_bar.style.display = 'none';
            // collapse the first column, let the 2nd column fill 100%
            this.rootContainer.style.gridTemplateColumns = '0 1fr';
        }
    }

    /* ===============================================================================================================*/
    getObjectByUID(uid) {

        if (this.id === undefined) {
            return null;
        }
        const trimmed = uid.replace(/^\/+|\/+$/g, '');

        const [gui_segment, gui_remainder] = splitPath(trimmed);

        if (!gui_segment || gui_segment !== this.id) {
            console.warn(`UID "${uid}" does not match this GUI's ID "${this.id}".`);
            return null;
        }

        if (!gui_remainder) {
            return this;
        }

        // Split off the type
        const [object_type, object_remainder] = splitPath(gui_remainder);

        // Check if the type is in ['categories', 'popups', 'callouts']
        if (object_type === 'categories') {
            const [category_segment, category_remainder] = splitPath(object_remainder);
            const fullKey = `${this.id}/categories/${category_segment}`;
            // 1) Sub‐category?
            const subCat = this.categories[fullKey];
            if (subCat) {
                if (!category_remainder) return subCat;
                return subCat.getObjectByPath(category_remainder);
            }
        } else if (object_type === 'popups') {
            const [popup_segment, popup_remainder] = splitPath(object_remainder);
            const fullKey = `${this.id}/popups/${popup_segment}`;
            // 1) Popup itself?
            const popup = this.popups[fullKey];
            if (popup) {
                return popup.getObjectByPath(popup_remainder);
            }
        } else if (object_type === 'callouts') {
            const [callout_segment, callout_remainder] = splitPath(object_remainder);
            const fullKey = `${this.id}/callouts/${callout_segment}`;
            // 1) Callout itself?
            const callout = this.callouts[fullKey];
            if (callout) {
                if (!callout_remainder) return callout.element;
                // Callout buttons are not nested, so we can just return the element
                // or null if it doesn't match any button.
                const button = callout.buttons[callout_remainder];
                return button ? button.element : null;
            }
        } else if (object_type === 'terminals') {
            const [cli_terminal_segment, cli_terminal_remainder] = splitPath(object_remainder);
            const fullKey = `${this.id}/terminals/${cli_terminal_segment}`;
            // 1) CLI terminal itself?
            if (!this.terminal) {
                console.warn(`CLI terminal "${fullKey}" not found.`);
                return null;
            }
            if (fullKey === this.terminal.id) {
                return this.terminal;
            }
        } else {
            console.warn(`UID "${uid}" does not start with a valid type (categories, popups, callouts).`);
            return null;
        }

        console.warn(`No matching object found for UID "${uid}" in GUI.`);
        return null; // not found
    }

    /* ===============================================================================================================*/
    resetGUI() {
        // Empty the content
        this.content.innerHTML = '';
        this.category_bar_list.innerHTML = '';
        this.page_bar.innerHTML = '';
        this.category_head_bar.innerHTML = '';

        // Delete all categories that are currently stored
        this.categories = {};
        this.category = null;

        for (let i = 0; i < this.configuration.number_of_categories; i++) {
            this.category_buttons[i] = null;
        }

        // Add the placeholder in the middle of the content area
        const placeholder = document.createElement('div');
        placeholder.className = 'content_placeholder';
        placeholder.innerHTML = `
            <span class="placeholder_title">Not connected</span>
            <span class="placeholder_info">${this.websocket.url}</span>
            `;
        this.content.appendChild(placeholder);

        this.msgRateDisplay.textContent = '-----';
    }

    /* ===============================================================================================================*/
    addLogo() {

        const logoLink = document.createElement('a')
        logoLink.href = 'https://github.com/dustin-lehmann/bilbolab' // Change to your desired URL
        logoLink.className = 'logo_link'
        logoLink.target = '_blank' // Opens in a new tab
        logoLink.rel = 'noopener noreferrer' // Security best practice

        const logo = document.createElement('img')
        logo.src = new URL('./lib/symbols/bilbolab_logo.png', import.meta.url).href
        logo.alt = 'Logo'
        logo.className = 'bilbolab_logo'

        logoLink.appendChild(logo)
        this.head_bar_grid.appendChild(logoLink)

    }

    /* ===============================================================================================================*/
    addConnectionIndicator() {

        // ——— websocket status & rate indicator ———
        this.msgTimestamps = [];
        this.msgRateWindow = 1;
        this.blinkThrottle = 100;      // ms between blinks
        this._lastBlinkTime = 0;

        // create a container in the head_bar_grid
        const statusContainer = document.createElement('div');
        statusContainer.style.gridRow = '1 / span 2';                       // top row
        statusContainer.style.gridColumn = `${String(this.headbar_cols - 1)} / span 2`; // far right
        statusContainer.style.justifySelf = 'end';
        statusContainer.style.marginRight = '10px';
        statusContainer.style.paddingRight = '10px';
        statusContainer.style.display = 'flex';
        statusContainer.style.alignItems = 'center';
        statusContainer.style.gap = '8px';


        // the little circle
        this.statusIndicator = document.createElement('div');
        this.statusIndicator.className = 'status-indicator';

        // the “X M/s” text
        this.msgRateDisplay = document.createElement('span');
        this.msgRateDisplay.className = 'msg-rate';
        this.msgRateDisplay.textContent = '-----';

        statusContainer.appendChild(this.statusIndicator);
        statusContainer.appendChild(this.msgRateDisplay);
        this.head_bar_grid.appendChild(statusContainer);
    }

    /* ===============================================================================================================*/
    addCategory(category, position = null) {
        // 1) Dedupe
        category.parent = this;
        if (this.categories[category.id]) {
            console.warn(`Category "${category.id}" already exists.`);
            return;
        }

        // 2) Register it
        this.categories[category.id] = category;
        category.callbacks.get('event').register(this._onEvent.bind(this));


        // 3) If this is the very first category, select it immediately
        if (this.category === null) {
            this.setCategory(category.id);
        }


        // 4) Rebuild the nested sidebar list so it shows the new category
        this.renderCategoryTree();
    }

    /* ===============================================================================================================*/
    setCategory(category_id) {

        // Try to retrieve the category from the object tree
        let category;
        if (category_id instanceof Category) {
            category = category_id;
        } else if (typeof category_id === 'string') {
            category = this.getObjectByUID(category_id);
        } else {
            console.warn(`Invalid category ID "${category_id}".`);
            return;
        }

        if (!category) {
            console.warn(`Category "${category_id}" not found.`);
            return;
        }
        // 1) Hide the page from the active category
        // 2) Make the category button unselected
        if (this.category) {
            this.category.hidePages();
            this.category.button.getElement().classList.remove('selected');
        }

        // 3) Save the category as the new active category
        this.category = category;

        this.category.buildCategory(this.page_bar, this.category_head_bar, this.content);

        this.renderCategoryTree();
    }


    setPage(page_id) {
        const page = this.getObjectByUID(page_id);
        if (!page) {
            console.warn(`Page "${page_id}" not found.`);
            return;
        }

        const category = page.parent;
        this.setCategory(category.id);
        category.setPage(page);
    }


    /* ===============================================================================================================*/
    renderCategoryTree() {
        const container = this.category_bar_list;
        container.innerHTML = '';

        // Grab indent size once
        const indentPx = parseInt(
            getComputedStyle(document.documentElement)
                .getPropertyValue('--category-indent-step'),
            10
        );

        const build = (cats, level = 0) => {
            cats.forEach(cat => {
                // 1) make the <li>
                const li = document.createElement('li');
                li.className = 'category-item';
                li.style.position = 'relative';
                li.style.paddingLeft = `${level * indentPx}px`;

                // 2) insert one <span> per ancestor-level to draw its vertical line
                for (let lv = 1; lv <= level; lv++) {
                    const line = document.createElement('span');
                    line.className = 'connector-line';
                    // position each at its own indent offset
                    line.style.left = `${lv * indentPx - 5}px`;
                    li.appendChild(line);
                }

                // 3) double-click toggles open/closed if it has children
                if (Object.keys(cat.categories).length > 0) {

                    cat.button.getElement().classList.add('has-children');

                    li.addEventListener('dblclick', e => {
                        e.stopPropagation();
                        cat.configuration.collapsed = !cat.configuration.collapsed;
                        this.renderCategoryTree();
                    });

                    cat.button.getElement().classList.toggle('collapsed', cat.configuration.collapsed);

                } else {
                    cat.button.getElement().classList.remove('has-children');
                    cat.button.getElement().classList.remove('collapsed');
                }

                // 4) style/select button
                cat.button.getElement().classList.toggle('selected',
                    this.category && this.category.id === cat.id
                );
                cat.button.getElement().classList.toggle('not-selected',
                    !(this.category && this.category.id === cat.id)
                );

                // 5) click selects

                li.appendChild(cat.button.getElement());

                container.appendChild(li);

                // 6) recurse into open subcategories
                if (!cat.configuration.collapsed) {
                    build(Object.values(cat.categories), level + 1);
                }
            });
        };

        build(Object.values(this.categories), 0);
    }


    /* ===============================================================================================================*/
    _initializeTerminal(id, payload = {}) {
        this.terminal = new CLI_Terminal(id, payload)

        this.terminal.attach(this.terminal_container);

        this.terminal.callbacks.get('maximize').register(() => {
            this.openTerminalInPopup();
        });
        this.terminal.callbacks.get('command').register(({command, set}) => {
            // this.websocket.sendCommand(command, set);
            // Print this in all popup terminals. Loop through the this.popup_terminals object
            for (const popup_terminal of Object.values(this.popup_terminals)) {
                // popup_terminal._printUserInput(command, set);
            }
            this.onTerminalCommand(id, command, set);
        });
        this.terminal.print(`Welcome to the terminal`);
    }

    /* ===============================================================================================================*/
    openTerminalInPopup() {
        // generate a random id
        const popup_id = `popup_${Math.random().toString(36).substring(2, 15)}`;

        // Generate the group payload
        const groupPayload = {
            id: popup_id + '_group',
            config: {
                rows: 1,
                columns: 1
            }
        }

        // Create a new popup window
        const popup = new Popup(popup_id,
            {size: [800, 400], type: 'window', title: 'Terminal'},
            groupPayload,);


        // Make a new div for in the popup group gridDiv
        const terminalContainer = document.createElement('div');
        terminalContainer.style.width = '100%';
        terminalContainer.style.height = '100%';
        terminalContainer.style.maxHeight = '100%';
        terminalContainer.style.minHeight = '0';
        terminalContainer.style.gridArea = '1 / 1 / 2 / 2'; // span the whole grid
        terminalContainer.style.zIndex = '1000'; // make sure it is on top
        popup.groupWidget.gridDiv.appendChild(terminalContainer);

        // Make a new terminal
        const newTerminal = new CLI_Terminal('terminal', this.terminal.root_command_set.toConfig());
        newTerminal.attach(terminalContainer);

        popup.open();

        this.popup_terminals[popup_id] = newTerminal;

        newTerminal.setOnScreenHistory(this.terminal.on_screen_history);
        newTerminal.history = this.terminal.history;
        newTerminal.setCurrentCommandSet(this.terminal.command_set);
        newTerminal.focusInputField();

        popup.callbacks.get('closed').register(() => {
            // Remove the terminal from the popup_terminals
            delete this.popup_terminals[popup_id];
        });

        newTerminal.callbacks.get('close').register(() => {
            popup.close();
        });

        newTerminal.callbacks.get('command').register(({command, set}) => {
            this.terminal._printUserInput(command, set);
            this.terminal.callbacks.get('command').call({command, set});
        });

        // attach the keydown listener here, because apparently it does not work from inside the class ...
        popup._win.addEventListener('keydown', e => {
            if (e.key === 'Meta') {
                newTerminal.input_field.focus();
            }
        });
    }

    /* ===============================================================================================================*/
    onTerminalCommand(id, command, set) {
        const message = {
            type: 'cli_command',
            id: id,
            'data': {
                'command': command,
                'set': set.getFullPath()
            },
        }
        if (this.connected) {
            this.websocket.send(message);
        }
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    print(text, color = 'white') {
        this.terminal.print(text, color);

        // Loop through all the popups and print the text in them
        for (const popup_terminal of Object.values(this.popup_terminals)) {
            popup_terminal.print(text, color);
        }
    }

    /* ===============================================================================================================*/
    drawHeadBarGrid() {
        for (let row = 0; row < this.headbar_rows; row++) {
            for (let col = 0; col < this.headbar_cols; col++) {
                const gridItem = document.createElement('div');
                gridItem.className = 'headbar_cell';
                // gridItem.textContent = `${row},${col}`;  // Optional: for debugging
                this.head_bar_grid.appendChild(gridItem);
            }
        }
    }


    /* ===============================================================================================================*/
    onWsConnected() {
        this.connected = true;
        this.setConnectionStatus(true);

        const handshake_message = {
            type: 'handshake',
            data: {
                'client_type': 'frontend'
            }
        }
        this.websocket.send(handshake_message);
    }

    onWSDisconnected() {
        this.connected = false;
        this.setConnectionStatus(false);
        this.resetGUI();
    }

    onWsMessage(msg) {
        switch (msg.type) {
            case 'init':
                this._initialize(msg);
                break;
            case 'close':
                this._handleCloseMessage(msg);
                break;
            case 'choose':
                this._handleFrontendChooseMessage(msg);
                break;
            case 'update':
                console.warn('This is deprecated!!!')
                console.log('Received update message:', msg);
                this._update(msg);
                break;
            case 'gui_update':
                this._handleGuiUpdate(msg);
                break;
            case 'add':
                this.handleAddMessage(msg);
                break;
            case 'remove':
                this.handleRemoveMessage(msg);
                break;
            case 'object_message':
                this._handleMessageForWidget(msg);
                break;
            default:
                console.warn('Unknown message type', msg.type);
        }

        this._recordMessage();
    }

    onWsError(err) {

    }

    /* ===============================================================================================================*/
    _onEvent(event) {
        const message = {
            'type': 'event', 'id': event.id, 'data': event,
        }

        if (this.connected) {
            this.websocket.send(message);
        }
    }

    /* ===============================================================================================================*/
    _initialize(msg) {
        // Check if msg has a field name configuration, if yes extract it
        if (msg.configuration) {
            const config = msg.configuration;

            this.id = config.id || 'gui';
            // TODO: Here we have to set some properties, such as show category bar or auto_hide

            if (config.categories) {
                for (let id in config.categories) {
                    const category = new Category(config.categories[id].id,
                        config.categories[id].config,
                        config.categories[id].pages,
                        config.categories[id].categories,
                        config.categories[id].headbar || {},);

                    this.addCategory(category);
                }
            }

            // Prepare the terminal
            if (config.cli_terminal) {
                console.log('Terminal is enabled');
                const rootPayload = config.cli_terminal.cli?.root || {}
                this._initializeTerminal(config.cli_terminal.id, rootPayload);

            } else {
                console.log('Terminal is disabled');
            }

            // Add all applications
            if (config.applications) {
                this._addApplications(config.applications);
            }

        }

        // Restore shortcuts
        this.restoreShortcuts();

        // Restore the active page
        const active_page_id = getFromLocalStorage(`${this.id}_active_page`);
        const test = `${active_page_id}`;
        if (active_page_id) {
            const page = this.getObjectByUID(test);
            if (page) {
                const category = page.parent;
                this.setCategory(category.id);
                category.setPage(test);
            }
        }
    }

    _addApplications(config) {
        this.app_group = new WidgetGroup(config.id, config);
        this.app_group.attach(this.apps_container);
        this.app_group.callbacks.get('event').register(this._onEvent.bind(this));
    }

    /* ===============================================================================================================*/
    _handleCloseMessage(msg) {
        this.close();
    }

    /* ===============================================================================================================*/
    close() {
        // Terminate the websocket connection
        if (this.websocket) {
            this.websocket.close();
            this.websocket = null;
        }
        this._showDisconnectedOverlay()
    }

    /* ===============================================================================================================*/
    _update(msg) {
        const object = this.getObjectByUID(msg.id);
        if (!object) {
            console.warn(`Object with UID "${msg.id}" not found.`);
            return;
        }
        object.update(msg.data);
    }

    /* ===============================================================================================================*/
    _handleGuiUpdate(message) {
        const messages = message.messages;
        // messages is an object with keys being the IDs of the objects
        for (const [id, message] of Object.entries(messages)) {
            const object = this.getObjectByUID(id);
            if (!object) {
                console.warn(`Object with UID "${id}" not found.`);
                continue;
            }
            // Check if the message is an array, if so, iterate over it
            if (Array.isArray(message)) {
                // console.warn(`Received array message for object "${id}":`, message);
                // If it's an array, we assume it's a list of updates
                for (const item of message) {
                    object.update(item.data);
                }
            } else {
                object.update(message.data);
            }

        }
    }

    /* ===============================================================================================================*/
    _handleMessageForWidget(message) {
        const object = this.getObjectByUID(message.id);
        if (object) {
            object.onMessage(message.data);
        } else {
            console.warn(`Received widget message for unknown object "${message.id}"`);
            console.warn('Message data:', message.data);
        }
    }

    /* ===============================================================================================================*/
    /**
     * This is called when a widget message is directly addressed to this GUI
     * @param message
     */
    onMessage(message) {
        switch (message.type) {
            case 'function': {
                this.callFunction(message.function_name, message.args, message.spread_args);
                break;
            }
            default:
        }
    }

    /* ===============================================================================================================*/
    callFunction(function_name, args, spread_args = true) {
        const fn = this[function_name];

        if (typeof fn !== 'function') {
            console.warn(`Function '${function_name}' not found or not callable.`);
            return null;
        }

        // If args is an array and spreading is enabled
        if (Array.isArray(args) && spread_args) {
            return fn.apply(this, args);
        }

        // Otherwise, pass as a single argument (object, primitive, etc.)
        return fn.call(this, args);
    }

    /* ===============================================================================================================*/
    handleAddMessage(message) {
        const data = message.data;

        if (data.type === 'popup') {
            this._addPopup(data);
            return;
        }

        if (data.type === 'callout') {
            this.addCallout(data);
            return;
        }

        // Get the object we want to add something to
        const parent = this.getObjectByUID(data.parent);

        if (!parent) {
            console.warn(`Received add message for unknown parent "${data.parent}"`);
            return
        }

        console.log('Received add message:', data);
        parent.handleAddMessage(data);
    }

    /* ===============================================================================================================*/
    handleRemoveMessage(message) {
        const data = message.data;

        if (data.type === 'popup') {
            // Check if the popup exists
            if (!this.popups[data.id]) {
                console.warn(`Received remove message for unknown popup "${data.id}"`);
                console.warn('Available popups:', Object.keys(this.popups));
                return;
            }


            this.popups[data.id]?.close();
            delete this.popups[data.id];
            return;
        } else if (data.type === 'callout') {
            // Check if the callout exists
            if (!this.callouts[data.id]) {
                console.warn(`Received remove message for unknown callout "${data.id}"`);
                console.warn('Available callouts:', Object.keys(this.callouts));
                return;
            }

            this.removeCallout(data);
            return;
        }

        const parent = this.getObjectByUID(data.parent);
        if (!parent) {
            console.warn(`Received remove message for unknown parent "${data.parent}"`);
            return;
        }
        parent.handleRemoveMessage(data);
    }

    /* ===============================================================================================================*/
    _addPopup(data) {
        console.log("Adding popup:", data);
        const popup = new Popup(data.id, data.config.config, data.config.group);
        this.popups[data.id] = popup;
        popup.callbacks.get('event').register(this._onEvent.bind(this));
        popup.open();
    }

    /* ===============================================================================================================*/
    addCallout(data) {
        const calloutId = data.id;
        const cfg = data.config.config || {};

        // callback when any button is clicked or “×” is pressed
        const onEvent = (evt) => {
            // evt = { id: calloutId, event: 'button_click'|'close', data: {...} }
            this._onEvent(evt);
        };

        // callback when the callout is actually closed() in JS
        const onClose = (id) => {
            delete this.callouts[id];
        };

        // instantiate & store
        console.warn('addCallout', data);
        this.callouts[calloutId] = new Callout(calloutId, cfg, onEvent, onClose);
    }


    /* ===============================================================================================================*/
    removeCallout(data) {
        const calloutId = data.id;
        const c = this.callouts[calloutId];
        if (!c) return;
        // this will remove it from DOM and fire its onClose → delete from this.callouts
        c.close();
    }


    /* ===============================================================================================================*/
    /**
     * Call on WebSocket open/close
     */
    setConnectionStatus(connected) {
        if (connected) {
            this.statusIndicator.classList.add('connected');
            const placeholder = this.content.querySelector('.content_placeholder');
            if (placeholder) placeholder.remove();

            this.bottombar.style.display = 'grid';

            if (this.terminal) {
                this.terminal.print('Connected to Server. Welcome!');
            }
        } else {
            this.terminal.destroy();
            this.terminal_container.innerHTML = '';
            this.statusIndicator.classList.remove('connected');
            this.msgRateDisplay.textContent = '---';
            this.bottombar.style.display = 'none';

        }
    }

    /* ===============================================================================================================*/
    /**
     * Call this for every incoming message event
     */
    _recordMessage() {
        const now = Date.now();
        // 1) record timestamp
        this.msgTimestamps.push(now);

        // 2) prune anything older than our window
        const cutoff = now - this.msgRateWindow * 1000;
        this.msgTimestamps = this.msgTimestamps.filter(ts => ts >= cutoff);

        // 3) blink indicator for this incoming message
        this._maybeBlink();

        // 4) immediately update the display
        this._updateMessageRate();

        // 5) (re)start a timeout that, once your window has passed
        //    with no new messages, will re-compute & zero out the rate
        if (this._clearRateTimer) {
            clearTimeout(this._clearRateTimer);
        }
        this._clearRateTimer = setTimeout(() => {
            const now2 = Date.now();
            const cutoff2 = now2 - this.msgRateWindow * 1000;
            this.msgTimestamps = this.msgTimestamps.filter(ts => ts >= cutoff2);
            this._updateMessageRate();
            this._clearRateTimer = null;
        }, this.msgRateWindow * 1000);
    }

    /* ===============================================================================================================*/
    /**
     * Recompute and display the messages/sec
     */
    _updateMessageRate() {
        const count = this.msgTimestamps.length;
        const rate = count / this.msgRateWindow;
        this.msgRateDisplay.textContent = rate.toFixed(1) + ' M/s';
    }

    /* ===============================================================================================================*/
    /**
     * Blink the status indicator at most once per blinkThrottle ms
     */
    _maybeBlink() {
        const now = Date.now();
        if (now - this._lastBlinkTime < this.blinkThrottle) return;
        this._lastBlinkTime = now;
        this.statusIndicator.classList.add('blink');
        this.statusIndicator.addEventListener(
            'animationend',
            () => this.statusIndicator.classList.remove('blink'),
            {once: true}
        );
    }


    showSplash(imgPath, onDone) {
        const splash = document.createElement('div');
        splash.id = 'splash';

        const img = document.createElement('img');
        img.src = imgPath;
        img.alt = 'Loading…';

        splash.appendChild(img);
        document.body.appendChild(splash);

        img.addEventListener('animationend', (e) => {
            if (e.animationName === 'fadeOut') {
                document.body.removeChild(splash);
                onDone();
            }
        });
    }


    _removeOverlay(id) {
        const o = document.getElementById(id);
        if (o) o.remove();
    }


    _showChooseOverlay() {
        // guard: only one
        if (document.getElementById('choose-overlay')) return;

        const overlay = document.createElement('div');
        overlay.id = 'choose-overlay';
        overlay.classList.add('custom-overlay');
        overlay.innerHTML = `
    <div class="overlay-content">
      <p>There is already an instance of the GUI opened on this machine.<br>
         Do you want to disconnect the other instance?</p>
      <div class="overlay-buttons">
        <button id="disconnect-btn">Use this instance</button>
        <button id="close-btn">Use the other instance</button>
      </div>
    </div>`;
        document.body.appendChild(overlay);

        document.getElementById('disconnect-btn').onclick = () => {
            // send a “disconnect_other” event back to Python
            this.websocket.send({
                type: 'event',
                x: 25,
                id: this.id,
                data: {event: 'disconnect_other', id: this.id}
            });
            this._removeOverlay('choose-overlay');
        };
        document.getElementById('close-btn').onclick = () => {
            this._removeOverlay('choose-overlay');
            this.close()
            this.closeWindow();
        };
    }


    _showDisconnectedOverlay() {
        if (document.getElementById('disconnected-overlay')) return;

        const overlay = document.createElement('div');
        overlay.id = 'disconnected-overlay';
        overlay.classList.add('custom-overlay');
        overlay.innerHTML = `
            <div class="overlay-content disconnected">
      <img src="bilbolab_logo.png" alt="Logo" class="disconnected-logo">
      <p>This GUI instance has been disconnected.</p>
        <p>You can close this window now.</p>
    </div>`;
        document.body.appendChild(overlay);


    }

    // =================================================================================================================
    _handleFrontendChooseMessage(msg) {
        this._showChooseOverlay();
    }

    // =================================================================================================================
    _emergencyStop() {
        // Get the <img> inside the button
        const stopIcon = this.stopButton.querySelector('.stop-icon');
        if (!stopIcon) return;

        // Remove previous animation class if needed
        stopIcon.classList.remove('activated');

        // Force reflow to allow re-triggering animation
        void stopIcon.offsetWidth;

        // Add animation class
        stopIcon.classList.add('activated');

        // Listen for animation end to clean up
        const onAnimationEnd = () => {
            stopIcon.classList.remove('activated');
            stopIcon.removeEventListener('animationend', onAnimationEnd);
        };

        stopIcon.addEventListener('animationend', onAnimationEnd);


        this.showEmergencyStopOverlay();

        const message = {
            type: 'event',
            id: this.id,
            data: {event: 'emergency_stop', id: this.id}
        }

        this.websocket.send(message);
    }

    // =================================================================================================================
    showEmergencyStopOverlay() {
        // 1) create the overlay
        const overlay = document.createElement('div');
        overlay.id = 'emergency-stop-overlay';
        overlay.className = 'emergency-stop-overlay';
        overlay.textContent = 'Emergency Stop!';
        document.body.appendChild(overlay);

        // 2) trigger the fade-in in the next frame
        requestAnimationFrame(() => {
            overlay.classList.add('visible');
        });

        // 3) after 2 s, fade out
        setTimeout(() => {
            overlay.classList.remove('visible');
            // 4) when the fade-out transition ends, remove from DOM
            overlay.addEventListener('transitionend', () => overlay.remove(), {once: true});
        }, 2000);
    }

    // =================================================================================================================
    /**
     * Opens a file picker dialog and sends the selected file back to Python.
     * This method is called from Python via gui.function('openFilePicker', {...})
     *
     * @param {Object} options - Options for the file picker
     * @param {string} options.request_id - Unique ID to match request with response
     * @param {string} options.accept - File type filter (e.g., '.yaml,.yml')
     * @param {string} options.title - Title for the dialog (informational only)
     */
    async openFilePicker(options = {}) {
        const requestId = options.request_id;

        try {
            const fileData = await openFilePicker({
                accept: options.accept || '',
                multiple: false,
                maxSize: options.max_size || 0
            });

            // Send response back to Python
            this.websocket.send({
                type: 'event',
                id: this.id,
                data: {
                    event: 'file_picker_response',
                    request_id: requestId,
                    success: fileData !== null,
                    file: fileData
                }
            });
        } catch (error) {
            console.error('File picker error:', error);
            this.websocket.send({
                type: 'event',
                id: this.id,
                data: {
                    event: 'file_picker_response',
                    request_id: requestId,
                    success: false,
                    error: error.message
                }
            });
        }
    }

    // =================================================================================================================
    /**
     * Triggers a file download on the client.
     * Called from Python via gui.function('downloadFile', {...})
     *
     * @param {Object} options - Options for the download
     * @param {string} options.filename - Name for the downloaded file
     * @param {string} options.content - Base64-encoded file content
     * @param {string} options.mimeType - MIME type of the file
     */
    downloadFile(options = {}) {
        try {
            const { filename, content, mimeType } = options;

            if (!filename || !content) {
                console.error('downloadFile: missing filename or content');
                return;
            }

            // Decode base64 content
            const byteCharacters = atob(content);
            const byteNumbers = new Array(byteCharacters.length);
            for (let i = 0; i < byteCharacters.length; i++) {
                byteNumbers[i] = byteCharacters.charCodeAt(i);
            }
            const byteArray = new Uint8Array(byteNumbers);
            const blob = new Blob([byteArray], { type: mimeType || 'application/octet-stream' });

            // Create download link and trigger click
            const url = URL.createObjectURL(blob);
            const link = document.createElement('a');
            link.href = url;
            link.download = filename;
            document.body.appendChild(link);
            link.click();

            // Cleanup
            setTimeout(() => {
                document.body.removeChild(link);
                URL.revokeObjectURL(url);
            }, 100);

            console.log(`Download triggered: ${filename}`);
        } catch (error) {
            console.error('downloadFile error:', error);
        }
    }

    // =================================================================================================================
    _onWindowKeyDown(e) {

        if (document.activeElement !== document.body) return;

        // Return on F12 because this opens up the console
        if (e.key === 'F12') {
            // e.preventDefault();
            return;
        }

        e.preventDefault();

        switch (e.code) {
            case 'Space':
                if (!this._emergencyArmed) {
                    this._armEmergencyStop();
                } else {
                    this._triggerEmergencyStop();
                }
                break;
        }


    }

    // -----------------------------------------------------------------------------------------------------------------
    _armEmergencyStop() {
        this._emergencyArmed = true;
        this.stopButton.classList.add('armed');
        // auto-disarm after 3s
        this._armTimeoutId = setTimeout(() => {
            this._disarmEmergencyStop();
        }, 3000);
    }

    // -----------------------------------------------------------------------------------------------------------------
    _disarmEmergencyStop() {
        this._emergencyArmed = false;
        clearTimeout(this._armTimeoutId);
        this.stopButton.classList.remove('armed');
    }

    // -----------------------------------------------------------------------------------------------------------------
    _triggerEmergencyStop() {
        // clear the pending auto-disarm
        this._disarmEmergencyStop();
        // call your existing click handler
        this._emergencyStop();
    }
}

