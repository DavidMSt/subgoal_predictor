import {Widget} from "../objects.js";
import {getColor, shadeColor, interpolateColors, Callbacks} from "../../helpers.js";

/*
  Directory Widget tree looks like this:

  {
    dirs: [
      {
        name: <name>,
        path: <path>,
        type: <type>,
        text_color: <css color>,
        symbol: <emoji|string>,
        selectable: <bool>,     // NEW per‐item
        opacity: <number>,      // optional
        dirs: [...],
        files: [...]
      },
      ...
    ],
    files: [
      {
        name: <name>,
        path: <path>,
        type: <type>,
        text_color: <css color>,
        symbol: <emoji|string>,
        selectable: <bool>,     // NEW per‐item
        opacity: <number>       // optional
      },
      ...
    ]
  }
*/

const DEFAULT_SYMBOLS = {
    folder: '📁',
    file: '📄',
    link: '🔗',
    image: '🖼️',
};

export class DirectoryWidget extends Widget {
    constructor(id, config = {}) {
        super(id, config);
        const defaults = {
            title: 'Directory',
            background_color: 'transparent',
            text_color: '#aaa',
            triangle_color: '#888',  // NEW
            font_size: '9pt',
            highlight_color: [0.5, 0.5, 0.5, 0.15],
            tree: null,
            child_auto_collapse: true,
            show_files: true,
            select_folders: true,
            persistent_highlights: [],
        };
        this.configuration = {...defaults, ...this.configuration};
        this.callbacks.add('selected');
        this.callbacks.add('double_clicked');
        this.callbacks.add('event');
        this.selectedEl = null;

        this._storageKey = `${this.id}:directoryToggleStates`;
        this._scrollKey = `${this.id}:directoryScroll`;
        this._selectedKey = `${this.id}:directorySelected`;


        this.element = this.initializeElement();
        this.configureElement(this.element);


        if (this.configuration.tree) {
            this.update(this.configuration.tree);
        }
    }

    initializeElement() {
        const el = document.createElement('div');
        el.id = this.id;
        el.classList.add('widget', 'directoryWidget');
        return el;
    }


    configureElement(el) {
        super.configureElement(el);
        const c = this.configuration;

        this.toggleStates = JSON.parse(localStorage.getItem(this._storageKey) || '{}');
        this.scrollPosition = parseInt(localStorage.getItem(this._scrollKey), 10) || 0;

        // ——— CORE STYLING & MARKUP ———
        el.style.backgroundColor = getColor(c.background_color);
        el.style.color = getColor(c.text_color);
        el.style.fontSize = c.font_size;
        el.style.setProperty('--highlight-color', getColor(c.highlight_color));
        el.style.setProperty('--triangle-color', getColor(c.triangle_color));

        el.innerHTML = '';
        if (c.title) {
            const titleEl = document.createElement('div');
            titleEl.classList.add('directory-title');
            titleEl.textContent = c.title;
            el.appendChild(titleEl);
        } else {
            el.style.setProperty('--title-height', '0');
        }

        const container = document.createElement('div');
        container.classList.add('directory-container');
        if (c.tree) {
            container.appendChild(this._createList(c.tree));
        }
        el.appendChild(container);

        // ——— APPLY SAVED TOGGLE STATES ———
        container.querySelectorAll('li.directory-item').forEach(li => {
            const path = li.dataset.path;
            const expanded = !!this.toggleStates[path];
            const childUl = li.querySelector('ul');

            if (expanded) {
                childUl.style.display = 'block';
                li.classList.add('expanded');
                li.classList.remove('collapsed');
            } else {
                childUl.style.display = 'none';
                li.classList.add('collapsed');
                li.classList.remove('expanded');
            }
        });

        // ——— RESTORE SCROLL POSITION ———
        // (must do after the list is in the DOM)
        // if you find it “snaps” awkwardly, wrap in requestAnimationFrame
        container.scrollTop = this.scrollPosition;

        // ——— SAVE SCROLL on user scroll ———
        container.addEventListener('scroll', () => {
            localStorage.setItem(this._scrollKey, container.scrollTop);
        });

        // ——— PERSISTENT HIGHLIGHTS ———
        if (c.persistent_highlights.length) {
            for (const {path, color} of c.persistent_highlights) {
                this.persistentHighlight({path, color});
            }
        }

        // ——— RESTORE SELECTED ITEM ———
        const saved = localStorage.getItem(this._selectedKey);
        if (saved) {
            const el = container.querySelector(`[data-path="${saved}"]`);
            if (el && !el.classList.contains('not-selectable')) {
                el.classList.add('selected');
                this.selectedEl = el;
            }
        }

        this.assignListeners(el);
    }


    assignListeners(el) {
        super.assignListeners(el);
        const container = el.querySelector('.directory-container');

        container.addEventListener('click', e => {
            const toggleEl = e.target.closest('.directory-toggle');
            const row = e.target.closest('.directory-row, .file-row');
            if (!row) return;
            const li = row.parentElement;

            // DIRECTORY
            if (li.classList.contains('directory-item')) {
                if (toggleEl) {
                    // only the little triangle toggles
                    e.stopPropagation();
                    this._toggleDir(li);
                } else if (this.configuration.select_folders) {
                    // click anywhere else on the row => select folder
                    this._selectFile(li);
                    this.callbacks.get('event').call({
                        id: this.id,
                        event: 'directory_select',
                        data: {path: li.dataset.path}
                    })
                }
            }
            // FILE
            else {
                this._selectFile(li);

                this.callbacks.get('event').call({
                    id: this.id,
                    event: 'file_select',
                    data: {path: li.dataset.path}
                })
            }
        });

        container.addEventListener('dblclick', e => {
            const row = e.target.closest('.directory-row, .file-row');
            if (!row) return;
            const li = row.parentElement;

            // NEW: if it’s a directory, toggle it
            if (li.classList.contains('directory-item')) {
                e.stopPropagation();
                this._toggleDir(li);
            }

            this.callbacks.get('double_clicked').call({
                id: this.id,
                event: 'double_click',
                data: {path: li.dataset.path}
            });

            // Check if it is a file or folder
            if (li.classList.contains('file-item')) {
                this.callbacks.get('event').call({
                    id: this.id,
                    event: 'file_double_click',
                    data: {path: li.dataset.path}
                })
            } else {
                this.callbacks.get('event').call({
                    id: this.id,
                    event: 'directory_double_click',
                    data: {path: li.dataset.path}
                })
            }


        });
    }

    update(data) {
        // Store new tree
        this.configuration.tree = data;

        const container = this.element.querySelector('.directory-container');
        // Find (or create) the root <ul>
        let rootUl = container.querySelector('ul.directory-list');
        if (!rootUl) {
            container.innerHTML = '';
            rootUl = this._createList(data);
            container.appendChild(rootUl);
            return;
        }

        const showFiles = this.configuration.show_files;

        // Recursive diffing function
        const syncList = (ul, node) => {
            // Map existing <li> by path
            const existing = new Map();
            Array.from(ul.children).forEach(li => {
                if (li.dataset && li.dataset.path) existing.set(li.dataset.path, li);
            });

            // Build ordered list of new items
            const items = [];
            if (node.dirs) node.dirs.forEach(d => items.push({type: 'dir', data: d}));
            if (showFiles && node.files) node.files.forEach(f => items.push({type: 'file', data: f}));

            // Process each desired item in order
            for (const {type, data: item} of items) {
                const path = item.path;
                let li = existing.get(path);

                if (li) {
                    // ——— Update existing node ———
                    existing.delete(path);

                    // Update row attributes
                    const row = li.querySelector(type === 'dir' ? '.directory-row' : '.file-row');
                    if (item.opacity != null) row.style.opacity = item.opacity;
                    else row.style.opacity = '';

                    // Symbol
                    const sym = row.querySelector('.item-symbol');
                    sym.textContent = item.symbol
                        || (type === 'dir'
                            ? DEFAULT_SYMBOLS[item.type] || DEFAULT_SYMBOLS.folder
                            : DEFAULT_SYMBOLS[item.type] || DEFAULT_SYMBOLS.file);
                    if (item.text_color) sym.style.color = getColor(item.text_color);
                    else sym.style.color = '';

                    // Label
                    row.querySelector('.item-name').textContent = item.name;

                    // Selectable flag
                    if (item.selectable === false) li.classList.add('not-selectable');
                    else li.classList.remove('not-selectable');

                    // Recurse into directories
                    if (type === 'dir') {
                        let childUl = li.querySelector('ul');
                        if (!childUl) {
                            childUl = this._createList(item);
                            childUl.style.display = 'none';
                            li.appendChild(childUl);
                        }
                        syncList(childUl, item);
                    }

                    // Re-append to enforce new order
                    ul.appendChild(li);
                } else {
                    // ——— Create brand-new node ———
                    let newLi;

                    if (type === 'dir') {
                        newLi = document.createElement('li');
                        newLi.classList.add('directory-item', 'collapsed');
                        newLi.dataset.path = item.path;

                        const row = document.createElement('div');
                        row.classList.add('directory-row');
                        if (item.opacity != null) row.style.opacity = item.opacity;

                        const toggle = document.createElement('span');
                        toggle.classList.add('directory-toggle');
                        toggle.textContent = '▶';

                        const symbol = document.createElement('span');
                        symbol.classList.add('item-symbol');
                        symbol.textContent = item.symbol
                            || DEFAULT_SYMBOLS[item.type] || DEFAULT_SYMBOLS.folder;
                        if (item.text_color) symbol.style.color = getColor(item.text_color);

                        const label = document.createElement('span');
                        label.classList.add('item-name');
                        label.textContent = item.name;

                        row.append(toggle, symbol, label);
                        if (item.selectable === false) newLi.classList.add('not-selectable');
                        newLi.appendChild(row);

                        const childrenUl = this._createList(item);
                        childrenUl.style.display = 'none';
                        newLi.appendChild(childrenUl);
                    } else {
                        newLi = document.createElement('li');
                        newLi.classList.add('file-item');
                        newLi.dataset.path = item.path;

                        const row = document.createElement('div');
                        row.classList.add('file-row');
                        if (item.opacity != null) row.style.opacity = item.opacity;

                        const symbol = document.createElement('span');
                        symbol.classList.add('item-symbol');
                        symbol.textContent = item.symbol
                            || DEFAULT_SYMBOLS[item.type] || DEFAULT_SYMBOLS.file;
                        if (item.text_color) symbol.style.color = getColor(item.text_color);

                        const label = document.createElement('span');
                        label.classList.add('item-name');
                        label.textContent = item.name;

                        row.append(symbol, label);
                        if (item.selectable === false) newLi.classList.add('not-selectable');
                        newLi.appendChild(row);
                    }

                    ul.appendChild(newLi);
                }
            }

            // Remove any old nodes that weren’t in the new data
            for (const [oldPath, oldLi] of existing.entries()) {
                if (oldLi === this.selectedEl) {
                    // Clear selection if the deleted node was selected
                    this.removeSelectHighLight();
                    this.selectedEl = null;
                    localStorage.removeItem(this._selectedKey);
                }
                oldLi.remove();
            }
        };

        // Kick off diff at the root
        syncList(rootUl, data);
    }


    _createList(node) {
        const ul = document.createElement('ul');
        ul.classList.add('directory-list');

        // DIRECTORIES
        if (node.dirs) {
            node.dirs.forEach(dir => {
                const li = document.createElement('li');
                li.classList.add('directory-item', 'collapsed');
                li.dataset.path = dir.path;

                const row = document.createElement('div');
                row.classList.add('directory-row');
                if (dir.opacity != null) row.style.opacity = dir.opacity;

                const toggle = document.createElement('span');
                toggle.classList.add('directory-toggle');
                toggle.textContent = '▶';

                const symbol = document.createElement('span');
                symbol.classList.add('item-symbol');
                symbol.textContent = dir.symbol || DEFAULT_SYMBOLS[dir.type] || DEFAULT_SYMBOLS.folder;
                if (dir.text_color) symbol.style.color = getColor(dir.text_color);

                const label = document.createElement('span');
                label.classList.add('item-name');
                label.textContent = dir.name;

                row.append(toggle, symbol, label);
                if (dir.selectable === false) li.classList.add('not-selectable');
                li.append(row);

                const childrenUl = this._createList(dir);
                childrenUl.style.display = 'none';
                li.append(childrenUl);

                ul.appendChild(li);
            });
        }

        // FILES (optional)
        if (this.configuration.show_files && node.files) {
            node.files.forEach(file => {
                const li = document.createElement('li');
                li.classList.add('file-item');
                li.dataset.path = file.path;

                const row = document.createElement('div');
                row.classList.add('file-row');
                if (file.opacity != null) row.style.opacity = file.opacity;

                const symbol = document.createElement('span');
                symbol.classList.add('item-symbol');
                symbol.textContent = file.symbol || DEFAULT_SYMBOLS[file.type] || DEFAULT_SYMBOLS.file;
                if (file.text_color) symbol.style.color = getColor(file.text_color);

                const label = document.createElement('span');
                label.classList.add('item-name');
                label.textContent = file.name;

                row.append(symbol, label);
                if (file.selectable === false) li.classList.add('not-selectable');
                li.append(row);

                ul.appendChild(li);
            });
        }

        return ul;
    }

    // _toggleDir(li) {
    //     const childUl = li.querySelector('ul');
    //     const isHidden = childUl.style.display === 'none';
    //     childUl.style.display = isHidden ? 'block' : 'none';
    //     li.classList.toggle('expanded', isHidden);
    //     li.classList.toggle('collapsed', !isHidden);
    //
    //     if (this.configuration.child_auto_collapse && !isHidden) {
    //         // collapse all descendants when you close
    //         li.querySelectorAll('li').forEach(ch => {
    //             ch.classList.remove('expanded');
    //             ch.classList.add('collapsed');
    //             const u = ch.querySelector('ul');
    //             if (u) u.style.display = 'none';
    //         });
    //     }
    // }

    _toggleDir(li) {
        const childUl = li.querySelector('ul');
        const isHidden = childUl.style.display === 'none';
        childUl.style.display = isHidden ? 'block' : 'none';
        li.classList.toggle('expanded', isHidden);
        li.classList.toggle('collapsed', !isHidden);

        if (this.configuration.child_auto_collapse && !isHidden) {
            li.querySelectorAll('li').forEach(ch => {
                ch.classList.remove('expanded');
                ch.classList.add('collapsed');
                const u = ch.querySelector('ul');
                if (u) u.style.display = 'none';
            });
        }

        // ——————— SAVE STATE ———————
        const path = li.dataset.path;
        this.toggleStates[path] = li.classList.contains('expanded');
        localStorage.setItem(this._storageKey, JSON.stringify(this.toggleStates));
    }


    _selectFile(li) {
        if (li.classList.contains('not-selectable')) return;
        if (this.selectedEl) {
            this.selectedEl.classList.remove('selected');
        }
        li.classList.add('selected');
        this.selectedEl = li;

        const path = li.dataset.path;
        localStorage.setItem(this._selectedKey, path);

        this.callbacks.get('selected').call({
            id: this.id,
            event: 'selected',
            data: {path: li.dataset.path}
        });
    }

    getElement() {
        return this.element;
    }

    updateConfig(data) {
        console.log('Update config', data);
        this.configuration = {...this.configuration, ...data};
        this.configureElement(this.element);
        console.log('Update with config', this.configuration);
    }

    removeSelectHighLight() {
        if (this.selectedEl) {
            this.selectedEl.classList.remove('selected');
        }
    }

    highlight(path) {
        const el = this.element.querySelector(`[data-path="${path}"]`);
        if (el) {
            el.classList.add('selected');
            this.selectedEl = el;
        }
    }

    persistentHighlight({path, color = [0, 0.9, 0.4, 0.5]}) {

        const highlightcolor = getColor(color);

        const el = this.element.querySelector(`[data-path="${path}"]`);
        if (el) {
            el.classList.add('persistent-selected');
            el.style.setProperty('--persistent-selected-color', highlightcolor);
        }
    }

    removePersistentHighlight(path) {
        const el = this.element.querySelector(`[data-path="${path}"]`);
        if (el) {
            el.classList.remove('persistent-selected');
        }
    }

    removeAllPersistentHighlights() {
        const els = this.element.querySelectorAll('.persistent-selected');
        els.forEach(el => {
            el.classList.remove('persistent-selected');
        })
    }

    resize() {
    }
}
