// === HELPERS =========================================================================================================
import {Widget} from "../objects/objects.js";

// === TerminalCommandInput ============================================================================================
import {Callbacks, getColor, getFromLocalStorage, writeToLocalStorage} from "../helpers.js";

function splitTokens(text) {
    return text.match(/(?:[^\s"]+|"[^"]*")+/g) || [];
}

class TerminalCommandInput {
    /** @type {string} */
    name;

    /** @type {string} */
    short_name;

    /** @type {string} */
    description;

    /** @type {string} */
    type;

    /** @type {number} */
    position;

    /** @type {boolean} */
    optional;

    /** @type {boolean} */
    is_flag = false;

    constructor(name, short_name, position, type, is_flag, optional, description) {
        this.name = name;
        this.short_name = short_name;
        this.description = description;
        this.type = type;
        this.position = position;
        this.optional = optional;
        this.is_flag = is_flag;
    }

    // -----------------------------------------------------------------------------------------------------------------
    static fromConfig(config) {
        if (!config || typeof config !== 'object') {
            throw new Error("Invalid config for TerminalCommandInput");
        }
        const {name, short_name, position, type, is_flag, optional, description} = config;
        return new TerminalCommandInput(name, short_name, position, type, is_flag, optional, description);
    }
}


// === TerminalCommand =================================================================================================
class TerminalCommand {
    /** @type {string} */
    name;

    /** @type {Object<string, TerminalCommandInput>} */
    inputs;

    /** @type {boolean} */
    allow_positionals;

    /** @type {TerminalCommandSet} */
    parent = null;


    constructor(name, inputs = {}, allow_positionals) {
        this.name = name;
        this.inputs = inputs;
        this.allow_positionals = allow_positionals || false;  // if true, allows positional arguments
    }

    // -----------------------------------------------------------------------------------------------------------------
    static fromConfig(config) {
        if (!config || typeof config !== 'object') {
            throw new Error("Invalid config for TerminalCommand");
        }
        const {name, inputs, allow_positionals} = config;
        const command = new TerminalCommand(name, {}, allow_positionals);
        if (inputs && typeof inputs === 'object') {
            for (const key in inputs) {
                command.inputs[key] = TerminalCommandInput.fromConfig(inputs[key]);
            }
        }
        return command;
    }

    // -----------------------------------------------------------------------------------------------------------------
    parseCommand(command) {

    }
}

// === TerminalCommandSet ==============================================================================================
class TerminalCommandSet {

    /** @type {string} */
    name;

    /** @type {string} */
    description;

    /** @type {Object<string, TerminalCommand>} */
    commands;

    /** @type {Object<string, TerminalCommandSet>} */
    sets;

    /** @type {TerminalCommandSet | CLI_Terminal } */
    parent = null;


    /* === CONSTRUCTOR ============================================================================================== */
    constructor(name, description) {
        this.name = name;
        this.description = description;
        this.commands = {};  // will hold commands by name
        this.sets = {};  // will hold sub command sets by name
    }


    // -----------------------------------------------------------------------------------------------------------------
    addCommand(command) {
        if (!(command instanceof TerminalCommand)) {
            throw new Error("Invalid command type");
        }

        if (this.commands[command.name]) {
            throw new Error(`Command with name ${command.name} already exists in this command set`);
        }

        this.commands[command.name] = command;
        command.parent = this;
    }

    // -----------------------------------------------------------------------------------------------------------------
    // -----------------------------------------------------------------------------------------------------------------
    addSet(set) {
        if (!(set instanceof TerminalCommandSet)) {
            throw new Error("Invalid command set type");
        }
        if (this.sets[set.name]) {
            throw new Error(`Command set with name ${set.name} already exists in this command set`);
        }
        this.sets[set.name] = set;
        set.parent = this;

        // Bubble to the terminal and rehydrate history
        let p = this;
        while (p && !(p instanceof CLI_Terminal)) p = p.parent;
        if (p && typeof p._rehydrateHistory === 'function') {
            p._rehydrateHistory();
        }
    }

    // -----------------------------------------------------------------------------------------------------------------
    removeCommand(name) {
        if (!this.commands[name]) {
            throw new Error(`Command with name ${name} does not exist in this command set`);
        }
        delete this.commands[name];
    }

    // -----------------------------------------------------------------------------------------------------------------
    removeSet(name) {
        if (!this.sets[name]) {
            throw new Error(`Command set with name ${name} does not exist in this command set`);
        }
        delete this.sets[name];
    }

    // -----------------------------------------------------------------------------------------------------------------
    getFullPath() {
        if (!this.parent) {
            return this.name;
        }
        // Check if the parent is the terminal itself
        if (this.parent instanceof CLI_Terminal) {
            return "~"
        }

        return `${this.parent.getFullPath()} ${this.name}`;
    }

    // -----------------------------------------------------------------------------------------------------------------
    handleAdd(id, type, config) {
        if (type === "command") {
            const command = TerminalCommand.fromConfig(config);
            this.addCommand(command);
        } else if (type === "set") {
            const set = TerminalCommandSet.fromConfig(config);
            this.addSet(set);
        } else {
            throw new Error(`Unknown type: ${type}`);
        }
    }

    // -----------------------------------------------------------------------------------------------------------------
    static fromConfig(config) {
        if (!config || typeof config !== 'object') {
            throw new Error("Invalid config for TerminalCommandSet");
        }
        const {name, description, commands, sets} = config;
        const commandSet = new TerminalCommandSet(name, description);

        if (commands && typeof commands === 'object') {
            for (const key in commands) {
                commandSet.addCommand(TerminalCommand.fromConfig(commands[key]));
            }
        }

        if (sets && typeof sets === 'object') {
            for (const key in sets) {
                commandSet.addSet(TerminalCommandSet.fromConfig(sets[key]));
            }
        }
        return commandSet;
    }

    // -----------------------------------------------------------------------------------------------------------------
    // -----------------------------------------------------------------------------------------------------------------
    toConfig() {
        // serialize commands
        const commandsConfig = {};
        for (const cmd of Object.values(this.commands)) {
            const inputsConfig = {};
            if (cmd.inputs && typeof cmd.inputs === 'object') {
                for (const inp of Object.values(cmd.inputs)) {
                    inputsConfig[inp.name] = {
                        name: inp.name,
                        short_name: inp.short_name,
                        position: inp.position,
                        type: inp.type,
                        is_flag: inp.is_flag,
                        optional: inp.optional,
                        description: inp.description,
                    };
                }
            }

            commandsConfig[cmd.name] = {
                name: cmd.name,
                allow_positionals: !!cmd.allow_positionals,
                inputs: inputsConfig,
            };
        }

        // serialize child sets (recursive)
        const setsConfig = {};
        for (const set of Object.values(this.sets)) {
            setsConfig[set.name] = set.toConfig();
        }

        // root object for this set
        return {
            name: this.name,
            description: this.description,
            commands: commandsConfig,
            sets: setsConfig,
        };
    }

    // -----------------------------------------------------------------------------------------------------------------
    parseCommand(command) {

    }

    // -----------------------------------------------------------------------------------------------------------------
    getPossibleCommands(prefix) {
        const lower = (prefix || '').toLowerCase();
        return Object.values(this.commands).filter(cmd =>
            !lower || cmd.name.toLowerCase().startsWith(lower)
        );
    }

    // -----------------------------------------------------------------------------------------------------------------
    getPossibleSets(prefix) {
        const lower = (prefix || '').toLowerCase();
        return Object.values(this.sets).filter(set =>
            !lower || set.name.toLowerCase().startsWith(lower)
        );
    }

    // -----------------------------------------------------------------------------------------------------------------
    getCommandAndSetHints(string) {
        const hints = ['.', '..'];
        const commands = this.getPossibleCommands(string);
        const sets = this.getPossibleSets(string);
        // Push set names into hints
        for (const set of sets) {
            hints.push(set.name);
        }
        // Push command names into hints
        for (const command of commands) {
            hints.push(command.name);
        }
        return hints;
    }

    // -----------------------------------------------------------------------------------------------------------------
    getByPath(path) {
        const [object, remainder] = splitTokens(path);

        // Check if the object is in the set's sets
        if (this.sets[object]) {
            if (!remainder) {
                return this.sets[object];
            } else {
                return this.sets[object].getByPath(remainder);
            }
        }

        // Check if the object is in the set's commands
        if (this.commands[object]) {
            if (!remainder) {
                return this.commands[object];
            }
        }

        return null;
    }
}


// === Terminal =========================================================================================================
export class CLI_Terminal extends Widget {

    /** @type {HTMLElement|null} */
    element = null;  // will hold the DOM element

    /** @type {HTMLElement|null} */
    input_container = null;  // will hold the input container element

    /** @type {HTMLElement|null} */
    input_field = null;  // will hold the input field element

    /** @type {HTMLElement|null} */
    output_field = null;  // will hold the output field element

    /** @type {HTMLElement|null} */
    hints_field = null;  // will hold the hints field element

    /** @type {TerminalCommandSet} */
    command_set = null;  // will hold the command set

    /** @type {TerminalCommandSet} */
    root_command_set = null;  // will hold the root command set

    /** @type {function} */
    onCommand = null;  // will hold the callback function for command execution

    /** @type {Array} */
    history = [];  // will hold the command history

    /** @type {Array} */
    on_screen_history = [];  // will hold the command history

    /** @type {Callbacks} */
    callbacks = null;  // will hold the callbacks for command execution

    /* === CONSTRUCTOR ============================================================================================== */
    constructor(id, payload = {}) {

        super(id, payload);

        const default_config = {
            mode: 'widget',   // Can be 'widget' or 'standalone'. Standalone is not implemented yet
            show_hint_window: true,
        }

        this.config = {...default_config, ...this.config};
        this.id = id;
        this.root_command_set = null;

        this.callbacks = new Callbacks();
        this.callbacks.add('command');

        this.element = this.initializeElement();
        this.configureElement();

        this.callbacks = new Callbacks();
        this.callbacks.add('command');
        this.callbacks.add('maximize');
        this.callbacks.add('close');

        const default_root_config = {
            name: "root",
            description: "Root command set for the terminal",
            commands: {},
            sets: {},
        };

        const rootConfig = {...default_root_config, ...payload};

        this.setRootCommandSetFromConfig(rootConfig);

        this._loadHistory();

        this.currentSuggestion = null;
        this.historyMode = null;
        this.historyIndex = -1;
        this.historyPrefix = '';

        this._acceptedHistoryBuffer = null;

        this.currentHistorySuggestion = null;
        this.currentHistorySet = null;

    }

    // === WIDGET CREATION MESSAGES ================================================================================= */
    initializeElement() {

        const el = document.createElement('div');
        el.classList.add('terminal');

        // Make the grid
        if (this.config.show_hint_window) {
            el.style.setProperty('--terminal-grid-rows', '1fr 30px 25px');
            el.style.setProperty('--terminal-grid-areas', '"output" "hints" "input"');
        } else {
            // TODO: We do this another time.
            // el.style.setProperty('--terminal-grid-rows', '75% 15%');
            // el.style.setProperty('--terminal-grid-areas', '"output" "input"');
        }

        // Make the output area
        this.output_field = document.createElement('div');
        this.output_field.classList.add('terminal-output');
        el.appendChild(this.output_field);

        // ------- HINTS AREA ------------------------------------------------
        // Make the hint area
        if (this.config.show_hint_window) {
            const middle_container = document.createElement('div');
            middle_container.classList.add('middle-container');
            el.appendChild(middle_container);

            this.hints_field = document.createElement('div');
            this.hints_field.classList.add('terminal-hints');
            middle_container.appendChild(this.hints_field);
            this.hints_field.tabIndex = -1;

            const button_container = document.createElement('div');
            button_container.classList.add('buttons-container');
            middle_container.appendChild(button_container);

            const settingsBtn = document.createElement('button');
            settingsBtn.classList.add('toolbar-button', 'settings-button');
            settingsBtn.textContent = '⚙️';
            settingsBtn.addEventListener('click', () => {
                // Remove the active class from the help overlay
                this.settings_overlay.classList.toggle('active');
                this.help_overlay.classList.remove('active');
            });

            settingsBtn.tabIndex = -1;


            // — Help button —
            const helpBtn = document.createElement('button');
            helpBtn.classList.add('toolbar-button', 'help-button');
            helpBtn.textContent = '❔';
            helpBtn.addEventListener('click', () => {
                // Remove the active class from the settings overlay

                this._showHelpOverlay();
            });
            helpBtn.tabIndex = -1;

            // — Cancel button —
            const cancelBtn = document.createElement('button');
            cancelBtn.classList.add('toolbar-button', 'cancel-button');
            cancelBtn.textContent = '❌';
            cancelBtn.addEventListener('click', () => {
                this._clearInputField();
            });
            cancelBtn.tabIndex = -1;

            const maximizeBtn = document.createElement('button');
            maximizeBtn.classList.add('toolbar-button', 'maximize-button');
            maximizeBtn.textContent = '';
            maximizeBtn.addEventListener('click', () => {
                this.callbacks.get('maximize').call();
            });

            // Create an <img> for your SVG:
            const svgImg = document.createElement('img');
            svgImg.src = 'maximize_icon.svg';  // adjust path as needed
            svgImg.alt = 'Maximize';
            svgImg.classList.add('toolbar-icon');

            maximizeBtn.appendChild(svgImg);
            maximizeBtn.tabIndex = -1;


            const folderBtn = document.createElement('button');
            folderBtn.classList.add('toolbar-button', 'folder-button');
            folderBtn.textContent = '📁';
            folderBtn.addEventListener('click', () => {
                this.print("Folder button clicked");
            });
            folderBtn.tabIndex = -1;

            const trashButton = document.createElement('button');
            trashButton.classList.add('toolbar-button', 'folder-button');
            trashButton.textContent = '🗑️';
            trashButton.addEventListener('click', () => {
                this.clear();
            });
            trashButton.tabIndex = -1;

            button_container.appendChild(cancelBtn);
            button_container.appendChild(helpBtn);
            button_container.appendChild(settingsBtn);
            button_container.appendChild(folderBtn);
            button_container.appendChild(maximizeBtn);
            button_container.appendChild(trashButton);

        }

        // ------- INPUT AREA ------------------------------------------------
        this.input_container = document.createElement('div');
        this.input_container.classList.add('terminal-input-container');
        el.appendChild(this.input_container);

        /** PATH (left column) **/
        this.path_container = document.createElement('div');
        this.path_container.classList.add('terminal-path');
        this.input_container.appendChild(this.path_container);

        /** INPUT STACK (middle column) **/
        this.input_stack = document.createElement('div');
        this.input_stack.classList.add('terminal-input-stack');
        this.input_container.appendChild(this.input_stack);

        /** Highlight layer (behind the real input) **/
        this.input_highlight = document.createElement('div');
        this.input_highlight.classList.add('terminal-input-highlight');
        this.input_stack.appendChild(this.input_highlight);

        /** Real input **/
        this.input_field = document.createElement('input');
        this.input_field.type = 'text';
        this.input_field.classList.add('terminal-input-field');
        this.input_stack.appendChild(this.input_field);

        this.input_field.addEventListener('focus', () => {
            this._updateCommandHints();
            this._updateInputField();
        });

        /** Send button (right column) **/
        const sendButton = document.createElement('button');
        sendButton.classList.add('terminal-send-button');
        sendButton.textContent = '➡️';
        sendButton.addEventListener('click', () => this._onUserInputEvent());
        sendButton.tabIndex = -1;
        this.input_container.appendChild(sendButton);

        /** Events **/
        this.input_field.addEventListener('input', (e) => {
            this._handleCurrentInputFieldContent(e);
            this._updateInputField();
            this._updateHistory();
        });
        this.input_field.addEventListener('keydown', (e) => this._handleKeyDown(e));

        /** History depth bar lives inside the input stack now **/
        this.historyIndicator = document.createElement('div');
        this.historyIndicator.classList.add('history-indicator');
        this.historyIndicatorFill = document.createElement('div');
        this.historyIndicatorFill.classList.add('history-indicator-fill');
        this.historyIndicator.appendChild(this.historyIndicatorFill);
        this.historyIndicator.style.display = 'none';
        this.input_stack.appendChild(this.historyIndicator);


        this._initializeHintHoverBox();

        // === OVERLAYS ====================================================================
        this.help_overlay = document.createElement('div');
        this.help_overlay.classList.add('terminal-overlay', 'help-overlay');
        el.appendChild(this.help_overlay);

        const help_close_button = document.createElement('button');
        help_close_button.classList.add('terminal-close-button');
        help_close_button.textContent = '❌';
        help_close_button.addEventListener('click', () => {
            this.help_overlay.classList.remove('active');
        });
        this.help_overlay.appendChild(help_close_button);


        this.settings_overlay = document.createElement('div');
        this.settings_overlay.classList.add('terminal-overlay', 'settings-overlay');
        this.settings_overlay.innerHTML = `HALLO`
        el.appendChild(this.settings_overlay);

        const settings_close_button = document.createElement('button');
        settings_close_button.classList.add('terminal-close-button');
        settings_close_button.textContent = '❌';
        settings_close_button.addEventListener('click', () => {
            this.settings_overlay.classList.remove('active');
        });
        this.settings_overlay.appendChild(settings_close_button);


        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                this._hideAllOverlays();
                this.input_field.focus();
            }
        });

        const doc = this.input_field.ownerDocument;

        document.addEventListener('keydown', e => {
            if (e.key === 'Meta') {
                const input = this.input_field;
                if (document.activeElement === input) {
                    input.blur();      // remove focus if it’s already there
                } else {
                    input.focus();     // otherwise, give it focus
                }
            }
        });


        return el;
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    configureElement() {
        super.configureElement(this.element);
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    resize() {
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    update(data) {
        return undefined;
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    updateConfig(data) {
        return undefined;
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    onMessage(message) {
        switch (message.type) {
            case 'add':
                this._handleAddMessage(message);
                break;
            case 'remove':
                this._handleRemoveMessage(message);
                break;
            case 'function': {
                this.callFunction(message.function_name, message.args, message.spread_args);
                break;
            }
            case 'print':
                this._handlePrintMessage(message);
                break;
        }
    }

    /* -------------------------------------------------------------------------------------------------------------- */

    updateRootSet(payload) {
        try {
            if (!payload || typeof payload !== 'object') {
                throw new Error('updateRootSet: invalid payload');
            }

            // Remember current absolute path tokens (excluding "~")
            let prevTokens = [];
            try {
                if (this.command_set) {
                    prevTokens = (this.command_set.getFullPath() || '')
                        .split(/\s+/)
                        .filter(t => t && t !== '~');
                }
            } catch (e) {
                prevTokens = [];
            }

            // Build and install new root
            this.root_command_set = (payload instanceof TerminalCommandSet)
                ? payload
                : TerminalCommandSet.fromConfig(payload);
            this.root_command_set.parent = this;

            // Walk previous path on new tree (back off when missing)
            let target = this.root_command_set;
            for (const tok of prevTokens) {
                if (target.sets && Object.prototype.hasOwnProperty.call(target.sets, tok)) {
                    target = target.sets[tok];
                } else {
                    break;
                }
            }

            this.setCurrentCommandSet(target);
            this._updateCommandHints();
            this._updateInputField();

            // IMPORTANT: try resolving history again against the new tree
            this._rehydrateHistory();
        } catch (err) {
            console.error('updateRootSet failed:', err);
            this._updateCommandHints();
            this._updateInputField();
        }
    }

    /* === PUBLIC METHODS =========================================================================================== */

    /* COMMAND SET ADDING AND HANDLING */
    setRootCommandSetFromConfig(config) {
        const rootSet = TerminalCommandSet.fromConfig(config);
        this.setRootCommandSet(rootSet);
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    setRootCommandSet(command_set) {
        this.root_command_set = command_set;
        this.root_command_set.parent = this;
        this.setCurrentCommandSet(this.root_command_set);
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    setCurrentCommandSet(command_set) {
        this.command_set = command_set;
        this._updateCommandHints();
        this._updateInputField();
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    getCommandSetByPath(path) {
        const [set_name, remainder] = splitTokens(path);

        switch (set_name) {
            case '.':
                if (!remainder) {
                    return this.root_command_set;
                } else {
                    return this.root_command_set.getByPath(remainder);
                }
            case '..':
                if (!this.command_set.parent) {
                    return null;
                }

                if (!remainder) {
                    return this.command_set.parent;
                } else {
                    return this.command_set.parent.getByPath(remainder);
                }
            default:
                if (!this.command_set) {
                    return null;
                }
                return this.command_set.getByPath(path);
        }
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    setOnScreenHistory(history) {
        this.on_screen_history = history;
        for (const line of this.on_screen_history) {
            this._printUserInput(line.command, line.set);
        }
        setTimeout(() => this._scrollDown(), 250);
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    clear() {
        this.output_field.innerHTML = '';
        this.on_screen_history = [];
        this._updateInputField();
        this._updateCommandHints();
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    print(text, color = 'white') {
        const now = new Date();
        const hh = String(now.getHours()).padStart(2, '0');
        const mm = String(now.getMinutes()).padStart(2, '0');
        const ss = String(now.getSeconds()).padStart(2, '0');
        const ts = `[${hh}:${mm}:${ss}]`;
        const lineEl = document.createElement('div');
        lineEl.className = 'terminal-line';
        lineEl.textContent = `${ts} ${text}`;
        lineEl.style.color = getColor(color);
        const {scrollTop, clientHeight, scrollHeight} = this.output_field;
        let scrollDown = false;
        if (scrollTop + clientHeight >= scrollHeight - 40) {
            scrollDown = true;
        }
        this.output_field.appendChild(lineEl);

        if (scrollDown) {
            this._scrollDown();
        }
    }

    focusInputField() {
        this.input_field.focus();
    }

    /* === PRIVATE METHODS ========================================================================================== */
    /* MESSAGE HANDLING */

    /* -------------------------------------------------------------------------------------------------------------- */
    _handleAddMessage(message) {

    }

    /* -------------------------------------------------------------------------------------------------------------- */
    _handleRemoveMessage(message) {

    }

    /* -------------------------------------------------------------------------------------------------------------- */
    _handlePrintMessage(message) {
        console.warn(`Handle print with message:`)
        console.log(message)
    }

    /* INPUT HANDLING */

    /* -------------------------------------------------------------------------------------------------------------- */
    // _onUserInputEvent() {
    //     // Fetch the input from the input field, clear it, and parse the command
    //     let input = this.input_field.value;
    //     let comes_from_history = false;
    //     // Check if we are in history mode
    //     if (this.historyMode === 'all' || this.historyMode === 'local') {
    //         if (this.currentHistorySuggestion) {
    //             input = this.currentHistorySuggestion;
    //             comes_from_history = true;
    //         }
    //     } else if (this.historyMode === 'global') {
    //         if (this.currentHistorySuggestion) {
    //             input = this.currentHistorySet.getFullPath() + ' ' + this.currentHistorySuggestion;
    //             comes_from_history = true;
    //         }
    //     }
    //
    //     if (comes_from_history && this.currentHistorySuggestion && this.currentHistorySet) {
    //         this._promoteHistoryEntry(this.currentHistorySuggestion, this.currentHistorySet);
    //     }
    //
    //
    //     this._exitHistoryMode();
    //     this._clearInputField();
    //     this._parseUserInput(input, comes_from_history);
    // }
    _onUserInputEvent() {
        let input = this.input_field.value;

        // default assumption
        let comes_from_history = false;

        // previous logic for live history mode (Alt/Meta+↑ then Enter without Tab)
        if (this.historyMode === 'all' || this.historyMode === 'local') {
            if (this.currentHistorySuggestion) {
                input = this.currentHistorySuggestion;
                comes_from_history = true;
            }
        } else if (this.historyMode === 'global') {
            if (this.currentHistorySuggestion) {
                input = this.currentHistorySet.getFullPath() + ' ' + this.currentHistorySuggestion;
                comes_from_history = true;
            }
        }

        // NEW: If we previously accepted via Tab, only keep "comes_from_history"
        // if the text is unchanged. If user edited it, treat as a fresh command.
        if (this._acceptedHistoryBuffer !== null) {
            if (this.input_field.value !== this._acceptedHistoryBuffer) {
                comes_from_history = false;  // user changed it → should be added to history
                console.log('User edited history buffer, treat as fresh command')
            } else {
                comes_from_history = true;   // unchanged → don't duplicate in history
                console.log('User did not edit history buffer, treat as history suggestion')
            }
            this._acceptedHistoryBuffer = null; // clear the buffer
        }

        if (comes_from_history && this.currentHistorySuggestion && this.currentHistorySet) {
            this._promoteHistoryEntry(this.currentHistorySuggestion, this.currentHistorySet);
        }

        this._exitHistoryMode();
        this._clearInputField();
        this._parseUserInput(input, comes_from_history);
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    _parseUserInput(command, comes_from_history = false) {

        // Parse some special commands
        if (command === '') {
            return;
        } else if (command === 'clear') {
            this.clear();
            return;
        } else if (command === 'help') {

        } else if (command === 'ch') {
            // Clear history
            this._clearHistory();
            this.print('History cleared.', 'green');
            return;

        } else if (command === 'exit' || command === 'close') {
            this.callbacks.get('close').call();
            return;
        } else if (command === 'max') {
            this.callbacks.get('maximize').call();
            return;
        }


        // Check if the command is a set
        const set = this._getSetFromUnformattedPath(command);

        if (set) {
            this.setCurrentCommandSet(set);
        }

        // Add it to the history. Only if it does not come from history or is a set change
        if (!comes_from_history && !set) {
            this._addToHistory({command: command, set: this.command_set});
        }

        this._printUserInput(command, this.command_set, null, 'cyan');
        this.on_screen_history.push({command: command, set: this.command_set});

        if (!set) {
            this.callbacks.get('command').call({command: command, set: this.command_set});
        }

        this._updateCommandHints();
        this._updateInputField();
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    _printUserInput(text, set, command = null, color = 'white') {
        // 1) timestamp
        const now = new Date();
        const hh = String(now.getHours()).padStart(2, '0');
        const mm = String(now.getMinutes()).padStart(2, '0');
        const ss = String(now.getSeconds()).padStart(2, '0');
        const ts = `[${hh}:${mm}:${ss}]`;

        // 2) path prompt → “[root] parent child …” → “~” for root
        let fullPath = set.getFullPath();
        const parts = fullPath.split(/\s+/);
        parts[0] = parts[0] === this.root_command_set.name ? '~' : parts[0];
        const tokenHTML = parts
            .map(tok => `<span class="user-prompt-token">${tok}</span>`)
            .join(`<span class="user-prompt-separator"></span>`);
        const promptHTML = `<span class="user-prompt-container">${tokenHTML}</span>`;

        // 3) optional “command” box (only if you passed a non‑null command)
        const esc = s => s
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;');
        let commandHTML = '';
        if (command != null && String(command).trim() !== '') {
            commandHTML = `<span class="user-command">${esc(command)}</span>`;
        }

        // 4) always show the raw text after
        const textHTML = `<span class="user-input-text" style="color:${getColor(color)}">> ${esc(text)}</span>`;

        // 5) assemble into a .terminal-line
        const lineEl = document.createElement('div');
        lineEl.classList.add('terminal-line');
        lineEl.innerHTML =
            `<span class="user-ts">${ts}</span> `
            + promptHTML
            + (commandHTML ? ` ${commandHTML}` : '')
            + ` ${textHTML}`;

        this.output_field.appendChild(lineEl);

        // 6) scroll lock
        const {scrollTop, clientHeight, scrollHeight} = this.output_field;
        if (scrollTop + clientHeight >= scrollHeight - 40) {
            this.output_field.scrollTop = scrollHeight;
        }
    }

    /* -------------------------------------------------------------------------------------------------------------- */

    /* HISTORY */
    _addToHistory(obj) {
        // obj = { command, set }
        const setPath = obj.set.getFullPath();

        // De-dupe against the most recent resolved entry (UI nicety)
        if (this.history.length > 0) {
            const last = this.history[this.history.length - 1];
            if (last.command === obj.command && last.set.getFullPath() === setPath) {
                return;
            }
        }

        // 1) Update resolved (in-memory) history used for the UI
        this.history.push({command: obj.command, set: obj.set});

        // 2) Update raw (persisted) history — this is the source of truth for storage
        if (!Array.isArray(this._rawHistory)) this._rawHistory = [];
        const lastRaw = this._rawHistory[this._rawHistory.length - 1];
        if (!lastRaw || lastRaw.command !== obj.command || lastRaw.setPath !== setPath) {
            this._rawHistory.push({command: obj.command, setPath});
        }

        this._persistHistory();
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    _getHistoryElements(prefix) {
        let entries = this.history;

        if (this.historyMode === 'local') {
            // Only include entries run in the same set we started browsing from
            entries = entries.filter(({set}) => set.getFullPath() === this.command_set.getFullPath());
        }
        // (you could special‑case global, or leave it as “all”)

        // Then always filter by the text prefix the user has typed
        if (prefix) {
            entries = entries.filter(({command}) => command.startsWith(prefix));
        }

        return entries.slice().reverse();
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    _startHistory(mode) {
        this.historyMode = mode;
        // this.historyPrefix = this.input_field.value;
        this.historyIndex = 0;
        this.historyIndicator.style.display = 'block';
        this._updateHistory()
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    _updateHistory(fromNav = false) {
        if (this.historyMode === null) return;

        // rebuild the list
        const historyElements = this._getHistoryElements(this.input_field.value);
        if (historyElements.length === 0) {
            this._exitHistoryMode();
            return;
        }

        if (!fromNav) {
            // ─── INPUT‑DRIVEN ────────────────────────────────────────
            // try to keep the old suggestion if it still exists
            if (this.currentHistorySuggestion) {
                const idx = historyElements.findIndex(
                    e => e.command === this.currentHistorySuggestion
                );
                this.historyIndex = idx !== -1 ? idx : 0;
            } else {
                // first time in history mode
                this.historyIndex = 0;
            }
        } else {
            // ─── NAVIGATION‑DRIVEN ────────────────────────────────────
            // keep whatever historyIndex you already have, but clamp it
            if (this.historyIndex < 0) {
                this.historyIndex = 0;
            } else if (this.historyIndex >= historyElements.length) {
                this.historyIndex = historyElements.length - 1;
            }
        }

        // now actually update the suggestion & set
        const {command, set} = historyElements[this.historyIndex];
        this.currentHistorySuggestion = command;
        this.currentHistorySet = set;

        // Update the indicator
        this._updateHistoryIndicator();

        this._updateInputField();
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    _navigateHistory(dir) {
        // If not in history mode return
        if (this.historyMode === null) return;

        this.historyIndex += dir;

        const historyElements = this._getHistoryElements(this.input_field.value);

        if (this.historyIndex < 0) {
            this._exitHistoryMode();
        } else if (this.historyIndex >= historyElements.length) {
            this.historyIndex = historyElements.length - 1;
        }
        this._updateHistory(true);
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    _exitHistoryMode() {
        this.historyMode = null;
        this.historyIndex = -1;
        // this.input_field.value = this.historyPrefix;
        this.currentHistorySuggestion = null;
        this.currentHistorySet = null;
        this.historyIndicator.style.display = 'none';
        this._updateInputField();
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    _clearHistory() {
        this.history = [];
        this.historyIndex = -1;
        this.historyMode = null;
        this.currentHistorySuggestion = null;
        this.currentHistorySet = null;

        this._wipePersistedHistory();
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    _updateHistoryIndicator() {
        if (!this.historyMode) return;

        // get the list of matching entries
        const entries = this._getHistoryElements(this.input_field.value);
        const total = entries.length;

        let pct = 0;
        if (total > 1) {
            pct = ((this.historyIndex + 1) / (total)) * 100;
        } else {
            // only one entry → full
            pct = 100;
        }
        this.historyIndicatorFill.style.height = `${pct}%`;
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    /** Accept exactly one more character from the current history suggestion. */
    _acceptNextHistoryChar() {
        // Only in history mode with an active suggestion
        if (!this.historyMode || !this.currentHistorySuggestion) return false;

        const {value, selectionStart, selectionEnd} = this.input_field;

        // Only act when the caret is a collapsed selection at the end (like a normal terminal)
        const atEnd = selectionStart === selectionEnd && selectionStart === value.length;
        if (!atEnd) return false;

        // Safety: ensure we’re extending a real prefix of the suggestion
        if (!this.currentHistorySuggestion.startsWith(value)) return false;

        // Grab the next character to commit
        const nextChar = this.currentHistorySuggestion.charAt(value.length);
        if (!nextChar) {
            // Already fully accepted; let default right-arrow behavior happen
            return false;
        }

        // Append that character to the real input
        this.input_field.value = value + nextChar;

        // Move caret to the new end
        const pos = this.input_field.value.length;
        this.input_field.setSelectionRange(pos, pos);

        // Recompute matches/suggestion based on the longer prefix and repaint
        this._updateHistory();        // keeps us in history mode, shrinks the ghost
        this._updateInputField();
        this._updateCommandHints();

        return true; // we handled the key
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    /** Move an existing {command,set} entry to the most-recent position (end of array). */
    _promoteHistoryEntry(command, set) {
        if (!command || !set) return;
        const setPath = set.getFullPath();

        // Promote in resolved history (UI)
        const idx = this.history.findIndex(h => h.command === command && h.set.getFullPath() === setPath);
        if (idx !== -1 && idx !== this.history.length - 1) {
            const [entry] = this.history.splice(idx, 1);
            this.history.push(entry);
        }

        // Promote in raw history (persisted)
        if (!Array.isArray(this._rawHistory)) this._rawHistory = [];
        const ridx = this._rawHistory.findIndex(h => h.command === command && h.setPath === setPath);
        if (ridx !== -1 && ridx !== this._rawHistory.length - 1) {
            const [entry] = this._rawHistory.splice(ridx, 1);
            this._rawHistory.push(entry);
            this._persistHistory();
        }
    }


    /* -------------------------------------------------------------------------------------------------------------- */
    _showHelpOverlay() {
        // Populate once
        if (!this.help_overlay.querySelector('.help-content')) {
            this.help_overlay.insertAdjacentHTML('beforeend', `
    <div class="help-content">
    
      <div class="help-section">
        <h2>Entering Commands</h2>
        <p>Type into the input and press <kbd>Enter</kbd> or click <span class="terminal-send-button">➡️</span>.</p>
      </div>
    
      <div class="help-section">
        <h2>Current Path</h2>
        <p>Your prompt shows where you are. By default you’ll see orange badges:</p>
        <div class="help-example">
          <span class="prompt-token">~</span>
          <span class="prompt-token">user</span>
          <span class="prompt-token">settings</span>
        </div>
        <p>To change directory, just type the path tokens (e.g. <code>user settings</code>) and press <kbd>Enter</kbd>.<br>
           Or click the <span class="prompt-token">~</span> badge in the hints box to jump back to the root.</p>
      </div>
    
      <div class="help-section">
        <h2>Hints Box Symbols</h2>
        <p>In the hints area you’ll see:</p>
        <div class="help-example">
          <span class="terminal-hint" style="color:orange">user</span>
          <span class="terminal-hint" style="color:cyan">list</span>
        </div>
        <div class="help-legend">
          <div class="help-legend-item set"><span></span>Command Set</div>
          <div class="help-legend-item command"><span></span>Command</div>
        </div>
      </div>
    
      <div class="help-section">
        <h2>Command Inputs</h2>
        <p>Required vs optional flags show up as colored badges:</p>
        <div class="help-example">
          <span class="input-hint required">--username, -u</span>
          <span class="input-hint optional">--role, -r</span>
        </div>
        <div class="help-legend">
          <div class="help-legend-item required"><span></span>Required</div>
          <div class="help-legend-item optional"><span></span>Optional</div>
        </div>
      </div>
    
      <div class="help-section">
        <h2>History Navigation</h2>
        <p>
          <kbd>↑</kbd> browse all commands.<br>
          <kbd>Alt+↑</kbd> global history (shows path).<br>
          <kbd>Meta+↑</kbd> local history in this set.<br>
          While browsing you’ll see <strong>🕒</strong> in the input; hit <kbd>Tab</kbd> or <kbd>Enter</kbd> to accept.<br>
          Press <kbd>Esc</kbd> to exit history mode.
        </p>
      </div>
    
      <div class="help-section">
        <h2>History Path Coloring</h2>
        <p>Prompt tokens change color by mode:</p>
        <div class="help-example">
          <span class="prompt-token">~</span><span class="prompt-token">logs</span>
          <span class="help-label">All history (orange)</span>
        </div>
        <div class="help-example history-global">
          <span class="prompt-token">~</span><span class="prompt-token">logs</span>
          <span class="help-label">Global history (green)</span>
        </div>
        <div class="help-example history-local">
          <span class="prompt-token">~</span><span class="prompt-token">logs</span>
          <span class="help-label">Local history (blue)</span>
        </div>
      </div>
    
      <div class="help-section">
        <h2>Special Commands</h2>
        <div class="help-legend">
          <div class="help-legend-item special"><span></span><code>clear</code> — clear the screen</div>
          <div class="help-legend-item special"><span></span><code>ch</code> — clear history</div>
        </div>
      </div>
    
    </div>
            `);
        }

        // Toggle overlays
        this.help_overlay.classList.toggle('active');
        this.settings_overlay.classList.remove('active');
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    _showSettingsOverlay() {

    }

    /* -------------------------------------------------------------------------------------------------------------- */
    _hideAllOverlays() {
        // Hide all overlays if applicable
        this.help_overlay.classList.remove('active');
        this.settings_overlay.classList.remove('active');
    }

    /* MISC */

    /* -------------------------------------------------------------------------------------------------------------- */
    _scrollDown() {
        // 6) scroll lock
        const {scrollTop, clientHeight, scrollHeight} = this.output_field;
        this.output_field.scrollTop = scrollHeight;
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    _handleKeyDown(event) {

        const key = event.key;

        switch (key) {
            case 'ArrowUp':
                event.preventDefault();
                if (event.altKey) {
                    if (this.historyMode === null && this.history.length > 0) {
                        this._startHistory('all');
                    } else if (this.historyMode) {
                        this._navigateHistory(1);
                    }
                } else if (event.shiftKey) {
                    if (this.historyMode === null && this.history.length > 0) {
                        this._startHistory('global')
                    } else if (this.historyMode) {
                        this._navigateHistory(1);
                    }
                } else {
                    if (this.historyMode === null && this.history.length > 0) {
                        this._startHistory('local');
                    } else if (this.historyMode) {
                        this._navigateHistory(1);
                    }
                }

                break;
            case 'ArrowDown':
                event.preventDefault();
                // Handle down arrow key
                if (event.altKey) {
                    if (this.historyMode) {
                        this._navigateHistory(-1);
                    }
                    return; // Prevent default behavior if needed
                } else {
                    // Normal down arrow behavior
                    if (this.historyMode) {
                        this._navigateHistory(-1);
                    }
                }
                break;
            case 'Enter':
                // Send the command
                this._onUserInputEvent();
                break;
            case 'Tab':
                // Prevent default tab behavior
                event.preventDefault();
                this._triggerAutocomplete();
                break;
            case 'Escape':
                // Clear the input field
                if (this.historyMode) {
                    this._exitHistoryMode();
                } else {
                    this._clearInputField();
                }
                this._hideAllOverlays();
                break;
            case 'ArrowRight': {
                if (this.historyMode && this.currentHistorySuggestion) {
                    const consumed = this._acceptNextHistoryChar();
                    if (consumed) {
                        event.preventDefault();  // we used the key to accept one char
                        return;
                    }
                }
                // otherwise, let the browser move the caret normally
                break;
            }
            default:
                break;
        }
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    _clearInputField() {
        this.input_field.value = '';
        this._updateInputField();
        this._updateCommandHints();
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    _getSetFromUnformattedPath(input) {
        const tokens = splitTokens(input);
        // start from current set
        let current = this.command_set;

        // nothing typed → just return current
        if (tokens.length === 0) {
            return current;
        }

        let idx = 0;
        const first = tokens[0];

        // handle leading root or parent nav
        if (first === '~' || first === '.') {
            current = this.root_command_set;
            idx = 1;
        } else if (first === '..') {
            if (!current.parent) return null;
            current = current.parent;
            idx = 1;
        }

        // traverse the rest
        for (let i = idx; i < tokens.length; i++) {
            const tok = tokens[i];
            if (tok === '~' || tok === '.') {
                current = this.root_command_set;
            } else if (tok === '..') {
                if (!current.parent) return null;
                current = current.parent;
            } else if (current.sets[tok]) {
                // descend into the named sub‑set
                current = current.sets[tok];
            } else {
                // neither nav nor a valid set name → fail
                return null;
            }
        }

        return current;
    }

    /* HINTS + AUTOCOMPLETE */

    /* -------------------------------------------------------------------------------------------------------------- */
    _handleCurrentInputFieldContent(event) {
        const input = event.target.value;
        // here we have to get the command hints for the current input
        this._updateCommandHints();
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    _updateInputField() {
        // 1) Render the left path column
        this._renderPathTokens();

        // 2) Escape user text
        const userText = this.input_field.value;
        const esc = s => s.replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;');
        const escapedUser = esc(userText);

        // 3) “Ghost” suggestion (history or autocomplete)
        let suggestionHTML = '';
        if (this.historyMode) {
            if (this.currentHistorySuggestion) {
                const rest = this.currentHistorySuggestion.slice(userText.length);
                suggestionHTML = `<span class="history-suggestion">${esc(rest)}</span>`;
            }
        } else {
            const toks = (userText.match(/(?:[^\s"]+|"[^"]*")+/g) || []);
            const complete = userText.endsWith(' ');
            const partial = complete ? '' : (toks[toks.length - 1] || '');
            if (this.currentSuggestion && partial.length > 0 && this.currentSuggestion.startsWith(partial)) {
                const rest = this.currentSuggestion.slice(partial.length);
                suggestionHTML = `<span class="suggestion-text">${esc(rest)}</span>`;
            }
        }

        // 4) Paint highlight layer with ONLY the input text + suggestion
        this.input_highlight.innerHTML = escapedUser + suggestionHTML;

        // 5) History mode classes for path coloring, etc.
        if (this.historyMode) {
            this.input_container.classList.add('history-command');
            this.input_container.classList.toggle('history-global', this.historyMode === 'global');
            this.input_container.classList.toggle('history-local', this.historyMode === 'local');
        } else {
            this.input_container.classList.remove('history-command', 'history-global', 'history-local');
        }
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    _showHints(hints) {
        if (typeof hints !== 'object' || !hints.sets || !hints.commands) {
            throw new Error('Invalid hints object');
        }
        this.hints_field.innerHTML = '';

        const allHints = [...hints.sets.map(s => ({type: 'set', name: s})),
            ...hints.commands.map(c => ({type: 'command', name: c}))];

        for (const hint of allHints) {
            const hintEl = document.createElement('div');
            hintEl.classList.add('terminal-hint');
            hintEl.textContent = hint.name;
            hintEl.style.color = hint.type === 'set' ? getColor('orange') : getColor('cyan');
            if (hint.name === '~') {
                // hintEl.style.paddingLeft = '15px'; // indent root set
                // hintEl.style.paddingRight = '15px'; // indent root set
                hintEl.style.fontWeight = 'bold'; // make root set bold
                hintEl.style.border = '1px solid orange'; // add a border for emphasis
            }

            this._attachHintHoverEvents(hintEl, hint.name);

            hintEl.addEventListener('click', (e) => {

                // Check if the hint name is "~" -> Go to root set
                if (hint.name === '~') {
                    this.setCurrentCommandSet(this.root_command_set);
                    return;
                }

                if (e.metaKey && hint.type === 'set') {
                    let targetSet = null;

                    // special names
                    if (hint.name === '~') {
                        targetSet = this.root_command_set;
                    } else if (hint.name === '..') {
                        targetSet = this.command_set.parent || this.command_set;
                    } else {
                        targetSet = this.command_set.sets[hint.name];
                    }

                    if (targetSet) {
                        this.setCurrentCommandSet(targetSet);
                        // optional: clear the input if you like
                        // this.clearInputField();
                    }
                    return; // skip the normal insertion logic
                }

                // grab current cursor & value
                const {value, selectionStart} = this.input_field;
                // figure out where this token starts
                const beforeCursor = value.slice(0, selectionStart);
                const lastSpace = beforeCursor.lastIndexOf(' ');
                const prefix = value.slice(0, lastSpace + 1);
                const suffix = value.slice(selectionStart);
                // insert the full hint.name + a space
                const insertion = hint.name + ' ';
                this.input_field.value = prefix + insertion + suffix;
                // move caret to just after it
                const newPos = (prefix + insertion).length;
                this.input_field.setSelectionRange(newPos, newPos);
                this.input_field.focus();
                // redraw
                this._updateCommandHints();
                this._updateInputField();
            });


            this.hints_field.appendChild(hintEl);
        }
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    _showCommandArguments(inputs) {
        if (typeof inputs !== 'object') {
            throw new Error('Invalid inputs object');
        }
        this.hints_field.innerHTML = '';

        // Check if inputs is empty
        if (Object.keys(inputs).length === 0) {
            const noInputs = document.createElement('div');
            noInputs.classList.add('no-inputs');
            noInputs.textContent = 'No inputs available';
            this.hints_field.appendChild(noInputs);
            return;
        }

        // turn into array and sort: required first (optional=false), then by position
        const inputArray = Object.values(inputs)
            .sort((a, b) => {
                if (a.optional === b.optional) {
                    return a.position - b.position;
                }
                return a.optional ? 1 : -1;
            });

        for (const input of inputArray) {
            const hintEl = document.createElement('div');
            hintEl.classList.add('input-hint', input.optional ? 'optional' : 'required');

            if (input.is_flag) {
                hintEl.classList.add('flag');
            }

            // show both short and long flags
            hintEl.textContent = `-${input.short_name}, --${input.name}`;
            // wire up hover to show full metadata
            this._attachCommandArgumentHoverEvents(hintEl, input);

            hintEl.addEventListener('click', () => {
                const {value, selectionStart} = this.input_field;
                const beforeCursor = value.slice(0, selectionStart);
                const lastSpace = beforeCursor.lastIndexOf(' ');
                const prefix = value.slice(0, lastSpace + 1);
                const suffix = value.slice(selectionStart);
                // ALWAYS use the long form here:
                const insertion = `--${input.name} `;
                this.input_field.value = prefix + insertion + suffix;
                const newPos = (prefix + insertion).length;
                this.input_field.setSelectionRange(newPos, newPos);
                this.input_field.focus();
                this._updateCommandHints();
                this._updateInputField();
            });

            this.hints_field.appendChild(hintEl);
        }
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    _getInputCommandHints(input) {
        const tokens = splitTokens(input);
        const completeToken = input.endsWith(' ');
        let current = this.command_set;
        let idx = 0;

        // Handle leading path tokens: ~, ., ..
        if (tokens[0] === '~') {
            current = this.root_command_set;
            idx++;
        } else if (tokens[0] === '.') {
            current = this.root_command_set;
            idx++;
        } else if (tokens[0] === '..') {
            if (current.parent) current = current.parent;
            idx++;
        }

        // Determine which tokens are “traversing” vs the final (possibly partial) token
        const traversing = completeToken
            ? tokens.slice(idx)
            : tokens.slice(idx, tokens.length - 1);
        const partial = completeToken
            ? ''
            : (tokens[tokens.length - 1] || '');

        // Walk down sets/commands until we either hit a command or exhaust the path
        let recognizedCommand = null;
        let invalidPath = false;
        for (const tok of traversing) {
            if (tok === '..') {
                if (current.parent) current = current.parent;
            } else if (current.sets[tok]) {
                current = current.sets[tok];
            } else if (current.commands[tok]) {
                recognizedCommand = current.commands[tok];
                break;
            } else {
                invalidPath = true;
                break;
            }
        }

        if (invalidPath && !recognizedCommand) {
            return {sets: [], commands: []};
        }

        // If we found a command, switch to showing its inputs
        if (recognizedCommand) {
            return {sets: [], commands: [], inputs: recognizedCommand.inputs};
        }

        // Otherwise, suggest sets (including special ~ and ..) plus commands
        const hints = {sets: [], commands: []};

        // parent and root

        if (!partial || '~'.startsWith(partial)) {
            hints.sets.push('~');
        }

        if (current.parent && current.parent instanceof TerminalCommandSet && (!partial || '..'.startsWith(partial))) {
            hints.sets.push('..');
        }

        // actual sets & commands
        for (const set of current.getPossibleSets(partial)) {
            hints.sets.push(set.name);
        }
        for (const cmd of current.getPossibleCommands(partial)) {
            hints.commands.push(cmd.name);
        }
        return hints;
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    _triggerAutocomplete() {
        // 1) If we're in history mode and have a suggestion, use that and exit history
        if (this.historyMode && this.currentHistorySuggestion) {
            // fill the input with the full history entry

            if (this.currentHistorySet) {
                this._promoteHistoryEntry(this.currentHistorySuggestion, this.currentHistorySet);
            }

            if (this.historyMode === 'global') {
                this.setCurrentCommandSet(this.currentHistorySet);
                this.input_field.value = this.currentHistorySuggestion;
                // this.input_field.value = this.currentHistorySet.getFullPath() + " " + this.currentHistorySuggestion;
            } else {
                this.input_field.value = this.currentHistorySuggestion;
            }
            this._acceptedHistoryBuffer = this.input_field.value;
            // leave history mode
            this._exitHistoryMode();
            // redraw hints & prompt
            this._updateCommandHints();
            this._updateInputField();
            return;
        }

        if (!this.currentSuggestion) {
            return;
        }

        // 2) Otherwise, do the normal autocomplete from this.currentSuggestion
        const {value, selectionStart, selectionEnd} = this.input_field;
        // split out what’s before the caret…
        const beforeCaret = value.slice(0, selectionStart);
        // find where the current token begins
        const lastSpaceIndex = beforeCaret.lastIndexOf(' ');
        const tokenStart = lastSpaceIndex + 1;
        // everything after the selection/caret
        const afterCaret = value.slice(selectionEnd);

        // build the new input with your suggestion
        const newValue =
            value.slice(0, tokenStart) +
            this.currentSuggestion +
            afterCaret;

        // write it back
        this.input_field.value = newValue;
        // place the cursor right after the inserted suggestion
        const newCursorPos = tokenStart + this.currentSuggestion.length;
        this.input_field.setSelectionRange(newCursorPos, newCursorPos);

        // re‑draw hints & prompt
        this._updateCommandHints();
        this._updateInputField();
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    _updateCommandHints() {
        const input = this.input_field.value;
        const hints = this._getInputCommandHints(input);

        const all = [...hints.sets, ...hints.commands];
        this.currentSuggestion =
            (input.length > 0 && all.length > 0)
                ? all[0]
                : null;

        // Check if "inputs" is not empty, then we have to show the inputs
        if (hints.inputs) {
            this._showCommandArguments(hints.inputs);
        } else {
            this._showHints(hints);
        }
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    _initializeHintHoverBox() {
        this.hint_hover_box = document.createElement('div');
        this.hint_hover_box.classList.add('terminal-hint-hover-box');
        this.hint_hover_box.textContent = 'Hint info'; // placeholder text
        this.container.appendChild(this.hint_hover_box);
        this.hint_hover_box.style.display = 'none';
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    _attachHintHoverEvents(hintEl, hintName) {
        hintEl.addEventListener('mouseenter', (e) => {
            if (this._onHintHover) {
                this.hint_hover_box.textContent = this._onHintHover(hintName) || 'Hint details...';
            }
            this.hint_hover_box.style.display = 'block';
            const rect = e.target.getBoundingClientRect();
            const tooltipHeight = this.hint_hover_box.offsetHeight;
            this.hint_hover_box.style.left = `${rect.left}px`;
            this.hint_hover_box.style.top = `${rect.top - tooltipHeight - 5}px`;
            this.hint_hover_box.classList.add('visible');
        });

        hintEl.addEventListener('mousemove', (e) => {
            const tooltipHeight = this.hint_hover_box.offsetHeight;
            this.hint_hover_box.style.left = `${e.pageX + 10}px`;
            this.hint_hover_box.style.top = `${e.pageY - tooltipHeight - 10}px`;
        });

        hintEl.addEventListener('mouseleave', () => {
            this.hint_hover_box.style.display = 'none';
            this.hint_hover_box.classList.remove('visible');
        });
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    _attachCommandArgumentHoverEvents(el, input) {
        el.addEventListener('mouseenter', (e) => {
            const box = this.hint_hover_box;
            // build structured HTML
            box.innerHTML = `
            <div class="input-hover-title">Input: ${input.name}</div>
            <div class="input-hover-row"><span class="input-hover-label">Short:</span> -${input.short_name}</div>
            <div class="input-hover-row"><span class="input-hover-label">Type:</span> ${input.type}</div>
            <div class="input-hover-row"><span class="input-hover-label">Required:</span> ${input.optional ? 'No' : 'Yes'}</div>
            <div class="input-hover-row"><span class="input-hover-label">Description:</span> ${input.description}</div>
            <div class="input-hover-row"><span class="input-hover-label">Flag:</span> ${input.is_flag ? 'Yes' : 'No'}</div>
        `;
            box.style.display = 'block';
            const rect = e.target.getBoundingClientRect();
            const tooltipHeight = box.offsetHeight;
            box.style.left = `${rect.left}px`;
            box.style.top = `${rect.top - tooltipHeight - 10}px`;
            box.classList.add('visible');
        });
        el.addEventListener('mousemove', (e) => {
            const box = this.hint_hover_box;
            const tooltipHeight = box.offsetHeight;
            box.style.left = `${e.pageX + 10}px`;
            box.style.top = `${e.pageY - tooltipHeight - 10}px`;
        });
        el.addEventListener('mouseleave', () => {
            const box = this.hint_hover_box;
            box.style.display = 'none';
            box.classList.remove('visible');
        });
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    _onHintHover(hintName) {
        return `Hint details for ${hintName}`
    }


    _renderPathTokens() {
        // Show absolute path if browsing global history
        const useSet = (this.historyMode === 'global' && this.currentHistorySet)
            ? this.currentHistorySet
            : this.command_set;

        const fullPath = useSet.getFullPath();
        const parts = fullPath.split(/\s+/);
        // Normalize root to "~"
        parts[0] = parts[0] === this.root_command_set.name ? '~' : parts[0];

        const html = parts
            .map(tok => `<span class="path-token" data-token="${tok}">${tok}</span>`)
            .join(`<span class="path-separator"></span>`);

        this.path_container.innerHTML = html;

        // Make tokens clickable
        const tokens = Array.from(this.path_container.querySelectorAll('.path-token'));
        tokens.forEach((el, idx) => {
            // remove any previous listeners by cloning to avoid stacking
            const clean = el.cloneNode(true);
            el.replaceWith(clean);

            clean.addEventListener('click', (e) => {
                e.preventDefault();
                e.stopPropagation();
                const targetPath = parts.slice(0, idx + 1).join(' ');
                const target = this._getSetFromUnformattedPath(targetPath);
                if (target) {
                    if (this.historyMode) this._exitHistoryMode();
                    this.setCurrentCommandSet(target);
                    this._updateCommandHints();
                    this._updateInputField();
                    this.input_field.focus();
                }
            });
        });
    }

    // -----------------------------------------------------------------------------------------------------------------
    inputFromExternal() {

    }


    /** Stable key for this terminal's history */
    _historyStorageKey() {
        // namespace with id so multiple terminals don't collide
        return `cli_terminal:${this.id}:history:v1`;
    }

    /** Save `this.history` to localStorage (command + set path only) */
    _persistHistory() {
        try {
            const key = this._historyStorageKey();

            // Merge with latest on disk in case another tab has written to it.
            const latest = getFromLocalStorage(key);
            const existing = Array.isArray(latest) ? latest : [];

            // Build a map (command+setPath) to keep uniqueness while preserving current order preference
            const toKey = (e) => `${e.command}@@${e.setPath}`;
            const map = new Map();

            // Start with disk entries
            for (const e of existing) {
                if (e && typeof e.command === 'string' && typeof e.setPath === 'string') {
                    map.set(toKey(e), e);
                }
            }
            // Then apply our raw history to become the “latest” ordering
            for (const e of (this._rawHistory || [])) {
                if (e && typeof e.command === 'string' && typeof e.setPath === 'string') {
                    map.delete(toKey(e));
                    map.set(toKey(e), {command: e.command, setPath: e.setPath});
                }
            }

            const merged = Array.from(map.values());
            writeToLocalStorage(key, merged);
        } catch (e) {
            console.error('Persist history failed:', e);
        }
    }


    /** Load history from localStorage and rehydrate set references */

    /** Load raw history from storage; do not drop unresolved entries */
    /** Load raw history from storage; do not drop unresolved entries */
    _loadHistory() {
        try {
            const raw = getFromLocalStorage(this._historyStorageKey());
            this._rawHistory = Array.isArray(raw) ? raw : [];
        } catch (e) {
            console.error('Load history failed:', e);
            this._rawHistory = [];
        }
        this._rehydrateHistory(); // build resolved history from raw
    }

    _rehydrateHistory() {
        try {
            // Optionally refresh raw history from disk before resolving (helps multi-tab)
            const latest = getFromLocalStorage(this._historyStorageKey());
            if (Array.isArray(latest)) {
                this._rawHistory = latest;
            }

            const resolved = [];
            for (const entry of (this._rawHistory || [])) {
                if (!entry || typeof entry !== 'object') continue;
                const {command, setPath} = entry;
                if (typeof command !== 'string' || typeof setPath !== 'string') continue;

                const set = this._getSetFromUnformattedPath(setPath);
                if (set) {
                    resolved.push({command, set});
                }
                // IMPORTANT: if not resolvable, do NOTHING — keep it in _rawHistory
            }

            this.history = resolved;

            // UI updates
            if (this._updateHistoryIndicator) this._updateHistoryIndicator();
            this._updateInputField();
            this._updateCommandHints();
        } catch (e) {
            console.error('Rehydrate history failed:', e);
        }
    }

    /** Wipe saved history (keep key but make it an empty array as requested) */
    _wipePersistedHistory() {
        writeToLocalStorage(this._historyStorageKey(), []);
        this._rawHistory = [];
    }


}