import { Joystick, JoystickManager } from './joystick.js';

export class JoystickTester {
  /**
   * @param {Object} opts
   * @param {HTMLElement} opts.container - where to render
   * @param {JoystickManager|null} [opts.manager=null] - if null, a new manager is created
   * @param {string} [opts.mapping='steamdeck'] - mapping passed to Joystick instances
   * @param {number} [opts.deadzone=0.12] - deadzone for Joystick instances
   * @param {boolean} [opts.showToolbar=true] - show rescan/rumble controls
   * @param {string} [opts.title='Joystick Tester'] - header title
   */
  constructor(opts = {}) {
    const {
      container,
      manager = null,
      mapping = 'steamdeck',
      deadzone = 0.12,
      showToolbar = true,
      title = 'Joystick Tester',
    } = opts;

    if (!container) throw new Error('JoystickTester requires { container }');

    this.container = container;
    this.manager = manager || new JoystickManager();
    this._ownsManager = !manager;
    this.mapping = mapping;
    this.deadzone = deadzone;
    this.showToolbar = showToolbar;
    this.title = title;

    /** @type {Map<number, Joystick>} */
    this.joysticks = new Map();
    /** @type {Map<number, HTMLButtonElement>} */
    this.tabs = new Map();
    this.activeIndex = null;

    this._buildShell();
    this._wireManager();
  }

  // ---------- Public API ----------

  rescan() { this.manager.rescan(); }

  async rumbleAll(durationMs = 80, strong = 0.8, weak = 0.6) {
    for (const js of this.joysticks.values()) {
      await js.rumble(durationMs, strong, weak);
    }
  }

  destroy() {
    for (const js of this.joysticks.values()) js.destroy();
    this.joysticks.clear();
    this.tabs.clear();
    this.container.innerHTML = '';
    if (this._ownsManager && this.manager.stop) this.manager.stop();
  }

  // ---------- Internals ----------

  _buildShell() {
    this.container.innerHTML = `
      <div class="jt-root">
        <header class="jt-header">
          <h1 class="jt-title">${this.title} <span class="jt-accent">UI</span></h1>
          ${this.showToolbar ? `
          <div class="jt-actions">
            <button class="jt-btn" id="jt-rescan">Rescan</button>
            <button class="jt-btn jt-primary" id="jt-rumble">Rumble</button>
          </div>` : ``}
        </header>
        <main class="jt-main">
          <div class="jt-status">
            <span id="jt-dot" class="jt-dot"></span>
            <span id="jt-status">Waiting for a controller… Press any button.</span>
          </div>

          <div id="jt-tabs" class="jt-tabs" hidden></div>
          <div id="jt-panels" class="jt-panels"></div>

          <p class="jt-muted jt-footnote">Tip: If nothing appears on Steam Deck, ensure your browser can read <code>/run/udev</code> (Flatpak override) and use a user gesture first.</p>
        </main>
      </div>
    `;

    this.el = {
      panels: this.container.querySelector('#jt-panels'),
      tabs: this.container.querySelector('#jt-tabs'),
      dot: this.container.querySelector('#jt-dot'),
      status: this.container.querySelector('#jt-status'),
      rescan: this.container.querySelector('#jt-rescan'),
      rumble: this.container.querySelector('#jt-rumble'),
    };

    if (this.el.rescan) this.el.rescan.addEventListener('click', () => this.rescan());
    if (this.el.rumble) this.el.rumble.addEventListener('click', () => this.rumbleAll());
  }

  _wireManager() {
    // new_joystick: build panel + tab and start a Joystick for it
    this.manager.callbacks.get('new_joystick').register((info) => {
      this._createPanelAndTab(info);

      const js = new Joystick({
        index: info.index,
        mapping: this.mapping,
        deadzone: this.deadzone,
      });
      this.joysticks.set(info.index, js);

      // Keep status in sync
      js.callbacks.get('connected').register(() => this._updateStatus());
      js.callbacks.get('disconnected').register(() => this._updateStatus());

      // Live updates
      js.callbacks.get('tick').register(({ axes, buttons }) => {
        this._updateAxes(info.index, axes);
        this._updateSticks(info.index, axes);
        this._updateButtons(info.index, buttons);
      });

      // Edge logs
      js.callbacks.get('button').register((e) => {
        if (e.type === 'down') console.log(`#${info.index} DOWN`, e.index, e.name ?? '');
        if (e.type === 'up')   console.log(`#${info.index} UP`,   e.index, e.name ?? '');
      });

      this._updateStatus();
    });

    // joystick_disconnected: remove panel + tab
    this.manager.callbacks.get('joystick_disconnected').register((info) => {
      this.joysticks.get(info.index)?.destroy();
      this.joysticks.delete(info.index);
      this._removePanelAndTab(info.index);
      this._updateStatus();
    });

    // scan_complete: render any missing and ensure one is active
    this.manager.callbacks.get('scan_complete').register((list) => {
      this._updateStatus(list.length);
      for (const info of list) {
        if (!document.getElementById(`jt-card-${info.index}`)) {
          this.manager.callbacks.get('new_joystick').call(info);
        }
      }
      if (this.activeIndex == null && list.length) {
        this._activate(list[0].index);
      }
    });

    // initial scan
    this.manager.rescan();
  }

  _updateStatus(explicitCount) {
    const count = explicitCount != null ? explicitCount : this.manager.listConnected().length;
    if (this.el.dot) this.el.dot.classList.toggle('on', count > 0);
    if (this.el.status) {
      this.el.status.textContent = count
        ? `${count} controller${count > 1 ? 's' : ''} connected.`
        : 'No controller found. Press any button or click Rescan.';
    }
    this._updateTabsVisibility();
  }

  _updateTabsVisibility() {
    if (!this.el.tabs) return;
    const showTabs = this.tabs.size > 1;
    this.el.tabs.hidden = !showTabs;
  }

  _shorten(str, max = 40) {
    if (typeof str !== 'string') return String(str ?? '');
    return str.length > max ? (str.slice(0, max - 1) + '…') : str;
  }

  _sanitizeName(id) {
    try {
      return id.replace(/$begin:math:text$(.*?)$end:math:text$/g, '').trim();
    } catch {
      return String(id ?? '').trim();
    }
  }

  _createPanelAndTab(info) {
    const { index, id, mapping, axes, buttons } = info;

    // Tab
    const tab = document.createElement('button');
    tab.className = 'jt-tab';
    tab.id = `jt-tab-${index}`;
    tab.type = 'button';
    const label = `#${index} — ${this._shorten(this._sanitizeName(id))}`;
    tab.textContent = label;
    tab.addEventListener('click', () => this._activate(index));
    this.el.tabs.appendChild(tab);
    this.tabs.set(index, tab);

    // Panel / card
    const card = document.createElement('div');
    card.className = 'jt-card';
    card.id = `jt-card-${index}`;
    card.innerHTML = `
      <h2 class="jt-h2">#${index} — ${this._sanitizeName(id)}</h2>
      <div class="jt-meta">
        <div>Mapping: <code>${mapping || 'none'}</code></div>
        <div>Buttons: <b id="jt-btnCount-${index}">${buttons}</b></div>
        <div>Axes: <b id="jt-axCount-${index}">${axes}</b></div>
      </div>

      <div class="jt-section">
        <div class="jt-sticks">
          <div class="jt-stick">
            <div class="jt-pad"><div class="jt-dot2" id="jt-ls-${index}"></div></div>
            <div class="jt-caption"><span>Left stick</span><span class="jt-muted"><code>axes 0/1</code></span></div>
          </div>
          <div class="jt-stick">
            <div class="jt-pad"><div class="jt-dot2" id="jt-rs-${index}"></div></div>
            <div class="jt-caption"><span>Right stick</span><span class="jt-muted"><code>axes 2/3</code></span></div>
          </div>
        </div>
      </div>

      <!-- Buttons are now directly under sticks -->
      <div class="jt-section">
        <h3 class="jt-h3">Buttons</h3>
        <div class="jt-buttons" id="jt-btns-${index}"></div>
      </div>

      <!-- Axes come after buttons -->
      <div class="jt-section">
        <h3 class="jt-h3">Axes</h3>
        <div class="jt-axes" id="jt-axes-${index}"></div>
      </div>
    `;
    this.el.panels.appendChild(card);

    // Axes rows
    const axesEl = card.querySelector(`#jt-axes-${index}`);
    for (let i = 0; i < axes; i++) {
      const row = document.createElement('div');
      row.className = 'jt-axis';
      row.innerHTML = `
        <div class="jt-label"><span>Axis ${i}</span><span id="jt-axv-${index}-${i}">0.000</span></div>
        <div class="jt-bar">
          <div class="jt-zero"></div>
          <div class="jt-thumb" id="jt-axt-${index}-${i}"></div>
        </div>
      `;
      axesEl.appendChild(row);
    }

    // Buttons grid
    const btnsEl = card.querySelector(`#jt-btns-${index}`);
    for (let i = 0; i < buttons; i++) {
      const el = document.createElement('div');
      el.className = 'jt-btncell';
      el.id = `jt-btn-${index}-${i}`;
      el.textContent = i;
      el.style.setProperty('--val', 0);
      btnsEl.appendChild(el);
    }

    // If nothing active yet, activate this one
    if (this.activeIndex == null) this._activate(index);
    this._updateTabsVisibility();
  }

  _removePanelAndTab(index) {
    const card = document.getElementById(`jt-card-${index}`);
    if (card) card.remove();

    const tab = this.tabs.get(index) || document.getElementById(`jt-tab-${index}`);
    if (tab) tab.remove();
    this.tabs.delete(index);

    // If it was the active one, activate another if present
    if (this.activeIndex === index) {
      const remaining = Array.from(this.tabs.keys());
      this.activeIndex = null;
      if (remaining.length) this._activate(remaining[0]);
    }
    this._updateTabsVisibility();
  }

  _activate(index) {
    // tabs
    for (const [i, btn] of this.tabs.entries()) {
      if (!btn) continue;
      btn.classList.toggle('active', i === index);
    }
    // cards
    const allCards = this.el.panels.querySelectorAll('.jt-card');
    allCards.forEach(c => c.classList.remove('active'));
    const card = document.getElementById(`jt-card-${index}`);
    if (card) card.classList.add('active');

    this.activeIndex = index;
  }

  _fmt(n) { return (Math.abs(n) < 1e-3 ? 0 : n).toFixed(3); }

  _updateAxes(index, axes) {
    for (let i = 0; i < axes.length; i++) {
      const v = axes[i];
      const num = document.getElementById(`jt-axv-${index}-${i}`);
      const thumb = document.getElementById(`jt-axt-${index}-${i}`);
      if (num) num.textContent = this._fmt(v);
      if (thumb) thumb.style.left = `calc(50% + ${v * 50}%)`;
    }
  }

  _updateSticks(index, axes) {
    const ls = document.getElementById(`jt-ls-${index}`);
    const rs = document.getElementById(`jt-rs-${index}`);
    const clamp = (n, min, max) => (n < min ? min : n > max ? max : n);

    if (ls) {
      const x = clamp(axes[0] ?? 0, -1, 1);
      const y = clamp(axes[1] ?? 0, -1, 1);
      ls.style.left = `calc(50% + ${x * 50}%)`;
      ls.style.top  = `calc(50% + ${y * 50}%)`;
    }
    if (rs) {
      const x = clamp(axes[2] ?? 0, -1, 1);
      const y = clamp(axes[3] ?? 0, -1, 1);
      rs.style.left = `calc(50% + ${x * 50}%)`;
      rs.style.top  = `calc(50% + ${y * 50}%)`;
    }
  }

  _updateButtons(index, buttons) {
    for (let i = 0; i < buttons.length; i++) {
      const el = document.getElementById(`jt-btn-${index}-${i}`);
      if (!el) continue;
      const b = buttons[i];
      const val = typeof b.value === 'number' ? b.value : (b.pressed ? 1 : 0);
      el.style.setProperty('--val', val);
      if (b.pressed || val > 0.15) el.classList.add('active'); else el.classList.remove('active');
    }
    // If button count changes, rebuild grid
    const countEl = document.getElementById(`jt-btnCount-${index}`);
    if (countEl && Number(countEl.textContent) !== buttons.length) {
      countEl.textContent = buttons.length;
      const holder = document.querySelector(`#jt-btns-${index}`);
      holder.innerHTML = '';
      for (let i = 0; i < buttons.length; i++) {
        const el = document.createElement('div');
        el.className = 'jt-btncell';
        el.id = `jt-btn-${index}-${i}`;
        el.textContent = i;
        holder.appendChild(el);
      }
    }
  }
}