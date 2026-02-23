// joystick.js
import { Callbacks } from "./helpers.js";

/** Name → index maps for convenience */
export const MAPPINGS = {
  standard: {
    axes: { left_x: 0, left_y: 1, right_x: 2, right_y: 3 },
    buttons: {
      a: 0, b: 1, x: 2, y: 3,
      l1: 4, r1: 5, l2: 6, r2: 7,
      select: 8, start: 9, l3: 10, r3: 11,
      dpad_up: 12, dpad_down: 13, dpad_left: 14, dpad_right: 15,
      home: 16,
    },
  },
  steamdeck: {
    axes: { left_x: 0, left_y: 1, right_x: 2, right_y: 3 },
    buttons: {
      a: 0, b: 1, x: 2, y: 3,
      l1: 4, r1: 5, l2: 6, r2: 7,
      select: 8, start: 9, l3: 10, r3: 11,
      dpad_up: 12, dpad_down: 13, dpad_left: 14, dpad_right: 15,
      home: 16,
    },
  },
};

/**
 * Joystick: wraps one specific Gamepad (by index) with polling, deadzone,
 * edge events for buttons, and optional axis events.
 */
export class Joystick {
  /**
   * @param {Object} opts
   * @param {number} opts.index - Gamepad.index to bind to (required)
   * @param {number} [opts.deadzone=0.15]
   * @param {string|Object} [opts.mapping="standard"]
   * @param {number} [opts.changeThreshold=0.015]
   * @param {boolean} [opts.emitAxis=true] - whether to emit 'axis' events
   */
  constructor(opts = {}) {
    if (typeof opts.index !== "number") {
      throw new Error("Joystick requires opts.index (Gamepad.index).");
    }

    const {
      index,
      deadzone = 0.15,
      mapping = "standard",
      changeThreshold = 0.015,
      emitAxis = true,
    } = opts;

    this.index = index;
    this._deadzone = deadzone;
    this._changeThreshold = changeThreshold;
    this._emitAxis = emitAxis;

    this.callbacks = new Callbacks();
    this.callbacks.add("connected");
    this.callbacks.add("disconnected");
    this.callbacks.add("button"); // {index, name?, type:'down'|'up'|'change', value, pressed, ts}
    this.callbacks.add("axis");   // {index, name?, value, ts}
    this.callbacks.add("tick");   // {axes, buttons, ts}

    this._mapping = { axes: {}, buttons: {} };
    this.setMapping(mapping);

    this._raf = null;
    this._axesPrev = [];
    this._buttonsPrev = [];

    // Bindings
    this._onDisconnect = this._onDisconnect.bind(this);
    this._tick = this._tick.bind(this);

    window.addEventListener("gamepaddisconnected", this._onDisconnect);

    // If already present, announce connected
    const gp = this._gamepad();
    if (gp) {
      this.callbacks.get("connected").call(this._describe(gp));
      this._raf = requestAnimationFrame(this._tick);
    }
  }

  /** Stop polling & listeners. */
  destroy() {
    if (this._raf) cancelAnimationFrame(this._raf);
    this._raf = null;
    window.removeEventListener("gamepaddisconnected", this._onDisconnect);
    this._axesPrev = [];
    this._buttonsPrev = [];
  }

  /** Is the bound gamepad currently connected? */
  isConnected() { return !!this._gamepad(); }

  /** Deadzone getter/setter */
  setDeadzone(dz = 0.15) { this._deadzone = Math.max(0, Math.min(0.95, Number(dz))); }
  getDeadzone() { return this._deadzone; }

  /** Change mapping at runtime (string key or custom object). */
  setMapping(mapping) {
    if (typeof mapping === "string" && MAPPINGS[mapping]) {
      this._mapping = structuredClone(MAPPINGS[mapping]);
    } else if (mapping && typeof mapping === "object") {
      this._mapping = {
        axes: { ...(mapping.axes || {}) },
        buttons: { ...(mapping.buttons || {}) },
      };
    } else {
      this._mapping = structuredClone(MAPPINGS.standard);
    }
  }

  /** Vibrate if supported. */
  async rumble(durationMs = 60, strong = 0.5, weak = 0.5) {
    const act = this._gamepad()?.vibrationActuator;
    if (!act?.playEffect) return false;
    try {
      await act.playEffect("dual-rumble", {
        duration: Math.max(1, durationMs | 0),
        startDelay: 0,
        strongMagnitude: this._clamp01(strong),
        weakMagnitude: this._clamp01(weak),
      });
      return true;
    } catch { return false; }
  }

  /** Axes helpers */
  getAxes() {
    const gp = this._gamepad();
    if (!gp) return [];
    return gp.axes.map(v => this._applyDeadzone(v));
  }
  getAxis(identifier) {
    const gp = this._gamepad();
    if (!gp) return 0;
    const idx = typeof identifier === "number" ? identifier : this._mapping.axes[identifier];
    if (idx == null) return 0;
    return this._applyDeadzone(gp.axes[idx] ?? 0);
  }

  /** Buttons helpers */
  getButtons() {
    const gp = this._gamepad();
    if (!gp) return [];
    return gp.buttons.map(b => ({ value: Number(b.value ?? (b.pressed ? 1 : 0)), pressed: !!b.pressed }));
  }
  getButton(identifier) {
    const gp = this._gamepad();
    if (!gp) return { value: 0, pressed: false };
    const idx = typeof identifier === "number" ? identifier : this._mapping.buttons[identifier];
    if (idx == null) return { value: 0, pressed: false };
    const b = gp.buttons[idx];
    return { value: Number(b?.value ?? (b?.pressed ? 1 : 0)), pressed: !!b?.pressed };
  }

  /** Info helpers */
  getType() { return this._gamepad()?.mapping || "unknown"; }
  getInfo() {
    const gp = this._gamepad();
    if (!gp) {
      return { connected: false, index: this.index, id: null, mapping: null, axes: [], buttons: [] };
    }
    return {
      connected: true,
      index: gp.index,
      id: gp.id,
      mapping: gp.mapping || null,
      axes: this.getAxes(),
      buttons: this.getButtons(),
    };
  }

  // ---- internals ----
  _tick() {
    const gp = this._gamepad();
    const ts = performance.now();

    if (!gp) {
      // Disconnected mid-frame: we'll be told via event too.
      this._raf = requestAnimationFrame(this._tick);
      return;
    }

    // Axes
    const axesNow = gp.axes.map(v => this._applyDeadzone(v));
    if (!this._axesPrev.length) this._axesPrev = Array(axesNow.length).fill(0);

    if (this._emitAxis) {
      axesNow.forEach((v, i) => {
        const prev = this._axesPrev[i] ?? 0;
        if (Math.abs(v - prev) >= this._changeThreshold) {
          const name = this._axisName(i);
          this.callbacks.get("axis").call({ index: i, name, value: v, ts });
        }
      });
    }
    this._axesPrev = axesNow;

    // Buttons
    const buttonsNow = gp.buttons.map(b => ({
      value: Number(b.value ?? (b.pressed ? 1 : 0)),
      pressed: !!b.pressed,
    }));
    if (!this._buttonsPrev.length) this._buttonsPrev = buttonsNow.map(b => ({ ...b }));

    buttonsNow.forEach((b, i) => {
      const p = this._buttonsPrev[i] || { value: 0, pressed: false };
      const name = this._buttonName(i);
      if (b.pressed && !p.pressed) {
        this.callbacks.get("button").call({ index: i, name, type: "down", value: b.value, pressed: b.pressed, ts });
      } else if (!b.pressed && p.pressed) {
        this.callbacks.get("button").call({ index: i, name, type: "up", value: b.value, pressed: b.pressed, ts });
      } else if (Math.abs(b.value - p.value) >= this._changeThreshold) {
        this.callbacks.get("button").call({ index: i, name, type: "change", value: b.value, pressed: b.pressed, ts });
      }
    });
    this._buttonsPrev = buttonsNow;

    this.callbacks.get("tick").call({ axes: axesNow, buttons: buttonsNow, ts });
    this._raf = requestAnimationFrame(this._tick);
  }

  _onDisconnect(e) {
    if (e.gamepad.index !== this.index) return;
    this.callbacks.get("disconnected").call(this._describe(e.gamepad));
  }

  _pads() { return navigator.getGamepads ? Array.from(navigator.getGamepads()) : []; }
  _gamepad() { return this._pads()[this.index] || null; }

  _applyDeadzone(v) {
    const dz = this._deadzone;
    if (Math.abs(v) <= dz) return 0;
    const sign = Math.sign(v);
    const mag = (Math.abs(v) - dz) / (1 - dz);
    return sign * this._clamp01(mag);
  }

  _clamp01(n) { return Math.min(1, Math.max(0, Number(n))); }
  _axisName(i) { for (const [name, idx] of Object.entries(this._mapping.axes)) if (idx === i) return name; }
  _buttonName(i) { for (const [name, idx] of Object.entries(this._mapping.buttons)) if (idx === i) return name; }
  _describe(gp) { return { index: gp.index, id: gp.id, mapping: gp.mapping || null, buttons: gp.buttons.length, axes: gp.axes.length }; }
}

/**
 * JoystickManager: watches for gamepads, emits simplified info when
 * new ones appear or known ones disconnect. You can then create
 * Joystick instances with the supplied index.
 */
export class JoystickManager {
  /**
   * @param {Object} [opts]
   * @param {boolean} [opts.autoStart=true]
   */
  constructor(opts = {}) {
    const { autoStart = true } = opts;

    this.callbacks = new Callbacks();
    this.callbacks.add("new_joystick");         // { index, id, mapping, buttons, axes }
    this.callbacks.add("joystick_disconnected"); // { index, id, mapping, buttons, axes }
    this.callbacks.add("scan_complete");        // [{...}, ...]

    this._known = new Map(); // index -> last describe()
    this._onConnect = this._onConnect.bind(this);
    this._onDisconnect = this._onDisconnect.bind(this);

    if (autoStart) this.start();
  }

  start() {
    window.addEventListener("gamepadconnected", this._onConnect);
    window.addEventListener("gamepaddisconnected", this._onDisconnect);
    this.rescan();
  }

  stop() {
    window.removeEventListener("gamepadconnected", this._onConnect);
    window.removeEventListener("gamepaddisconnected", this._onDisconnect);
    this._known.clear();
  }

  /** Manually rescan current pads and emit 'new_joystick' for newly discovered ones. */
  rescan() {
    const found = this._pads().filter(Boolean);
    const announced = [];
    for (const gp of found) {
      if (!this._known.has(gp.index)) {
        const info = this._describe(gp);
        this._known.set(gp.index, info);
        this.callbacks.get("new_joystick").call(info);
        announced.push(info);
      }
    }
    // Remove any that disappeared since last scan
    for (const idx of Array.from(this._known.keys())) {
      if (!found.find(g => g.index === idx)) {
        const info = this._known.get(idx);
        this._known.delete(idx);
        this.callbacks.get("joystick_disconnected").call(info);
      }
    }
    this.callbacks.get("scan_complete").call(this.listConnected());
  }

  /** Return a snapshot of currently connected pads (from last rescan/connection). */
  listConnected() { return Array.from(this._known.values()); }

  /** Convenience: get current Gamepad info by index (if known). */
  getByIndex(index) { return this._known.get(index) || null; }

  // ---- internals ----
  _onConnect(e) {
    const info = this._describe(e.gamepad);
    this._known.set(info.index, info);
    this.callbacks.get("new_joystick").call(info);
  }

  _onDisconnect(e) {
    const info = this._known.get(e.gamepad.index) || this._describe(e.gamepad);
    this._known.delete(e.gamepad.index);
    this.callbacks.get("joystick_disconnected").call(info);
  }

  _pads() { return navigator.getGamepads ? Array.from(navigator.getGamepads()) : []; }
  _describe(gp) { return { index: gp.index, id: gp.id, mapping: gp.mapping || null, buttons: gp.buttons.length, axes: gp.axes.length }; }
}