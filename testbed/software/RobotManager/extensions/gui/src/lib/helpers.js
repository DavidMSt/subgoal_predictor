export function rad2deg(rad) {
    return rad * 180 / Math.PI;
}

export function deg2rad(deg) {
    return deg * Math.PI / 180;
}

export function shadeColor(color, percent) {
    // very minimal RGB-only implementation:
    const num = parseInt(color.slice(1), 16), amt = Math.round(2.55 * percent), R = (num >> 16) + amt,
        G = (num >> 8 & 0x00FF) + amt, B = (num & 0x0000FF) + amt;
    return '#' + (0x1000000 + (R < 255 ? R < 1 ? 0 : R : 255) * 0x10000 + (G < 255 ? G < 1 ? 0 : G : 255) * 0x100 + (B < 255 ? B < 1 ? 0 : B : 255)).toString(16).slice(1);
}

/**
 * Lighten/darken an RGB(A) color given as 0–1 floats, mirroring shadeColor's logic.
 * @param {number[]} rgba - [r,g,b] or [r,g,b,a], each 0..1
 * @param {number} percent - amount to shift, e.g. -100..100 (but any number works; result is clamped)
 * @returns {number[]} New array with components still in 0..1. Alpha (if present) is preserved.
 */
export function shadeColorArray(rgba, percent) {
    // Match the original's rounding: Math.round(2.55 * percent) on 0–255 channels
    // → convert to 0–1 by dividing by 255.
    const delta = Math.round(2.55 * percent) / 255;

    const clamp01 = (x) => (x < 0 ? 0 : x > 1 ? 1 : x);

    const r = clamp01(rgba[0] + delta);
    const g = clamp01(rgba[1] + delta);
    const b = clamp01(rgba[2] + delta);

    // Preserve alpha if provided
    return rgba.length > 3 ? [r, g, b, rgba[3]] : [r, g, b];
}


export function getColor(color) {

    if (typeof color === 'string') {
        if (color === 'inherit') {
            return 'inherit';
        }
    }

    const color_array = _getColor(color);
    return `rgba(${color_array.r}, ${color_array.g}, ${color_array.b}, ${color_array.a})`;
}

function _getColor(color) {
    if (Array.isArray(color)) {
        // Python-style [r, g, b] or [r, g, b, a] with 0–1 values
        const [r, g, b, a = 1] = color;
        return {
            r: Math.round(r * 255),
            g: Math.round(g * 255),
            b: Math.round(b * 255),
            a: a
        };
    } else if (typeof color === 'string') {
        if (color === 'transparent') {
            return {r: 0, g: 0, b: 0, a: 0};
        }

        if (color.startsWith('#')) {

            let r, g, b, a = 1;
            if (color.length === 4) {
                // #rgb shorthand
                r = parseInt(color[1] + color[1], 16);
                g = parseInt(color[2] + color[2], 16);
                b = parseInt(color[3] + color[3], 16);
            } else if (color.length === 7) {
                // #rrggbb
                r = parseInt(color.slice(1, 3), 16);
                g = parseInt(color.slice(3, 5), 16);
                b = parseInt(color.slice(5, 7), 16);
            }
            return {r, g, b, a};
        } else if (color.startsWith('rgb')) {
            const match = color.match(/rgba?\(([^)]+)\)/);
            if (match) {
                const parts = match[1].split(',').map(x => parseFloat(x.trim()));
                const [r, g, b, a = 1] = parts;
                return {r, g, b, a};
            }
        } else {
            // Assume it's a named color. Any way to convert named colors to RGB?
            const namedColors = {
                black: {r: 0, g: 0, b: 0, a: 1},
                white: {r: 255, g: 255, b: 255, a: 1},
                red: {r: 255, g: 0, b: 0, a: 1},
                green: {r: 0, g: 128, b: 0, a: 1},
                blue: {r: 0, g: 0, b: 255, a: 1},
                yellow: {r: 255, g: 255, b: 0, a: 1},
                cyan: {r: 0, g: 255, b: 255, a: 1},
                magenta: {r: 255, g: 0, b: 255, a: 1},
                gray: {r: 128, g: 128, b: 128, a: 1},
                lightgray: {r: 211, g: 211, b: 211, a: 1},
                darkgray: {r: 169, g: 169, b: 169, a: 1},
                orange: {r: 255, g: 165, b: 0, a: 1},
                pink: {r: 255, g: 192, b: 203, a: 1},
                purple: {r: 128, g: 0, b: 128, a: 1},
                brown: {r: 165, g: 42, b: 42, a: 1},
            };

            const namedColor = namedColors[color.toLowerCase()];
            if (namedColor) {
                return namedColor;
            }
        }
    }

    throw new Error('Unsupported color format: ' + color);
}

export function setOpacity(color, opacity, multiply = false) {
    const { r, g, b, a } = _getColor(color);
    const clamp01 = (x) => (x < 0 ? 0 : x > 1 ? 1 : x);

    const nextA = multiply ? clamp01(a * opacity) : clamp01(opacity);

    return `rgba(${r}, ${g}, ${b}, ${nextA})`;
}

export function interpolateColors(color1, color2, fraction) {
    const c1 = _getColor(color1);
    const c2 = _getColor(color2);

    const r = Math.round(c1.r + (c2.r - c1.r) * fraction);
    const g = Math.round(c1.g + (c2.g - c1.g) * fraction);
    const b = Math.round(c1.b + (c2.b - c1.b) * fraction);
    const a = c1.a + (c2.a - c1.a) * fraction;

    return `rgba(${r}, ${g}, ${b}, ${a.toFixed(3)})`;
}


export function simulateSine(widget, {
    min, max, periodMs, offset = (min + max) / 2, amp = (max - min) / 2
}) {
    let start = performance.now();

    function step(now) {
        const t = (now - start) % periodMs;
        const theta = (2 * Math.PI * t) / periodMs;
        const value = offset + amp * Math.sin(theta);
        widget.update({value});
        requestAnimationFrame(step);
    }

    requestAnimationFrame(step);
}

export function stripId(path, targetId) {
    // Remove leading/trailing slashes
    path = path.replace(/^\/+|\/+$/g, '');
    const parts = path.split('/');

    const index = parts.indexOf(targetId);
    if (index === -1) {
        return null;
    }

    return parts.slice(index + 1).join('/');
}


export function removeLeadingAndTrailingSlashes(path) {
    return path.replace(/^\/+|\/+$/g, '');
}

export function splitPath(path) {
    // Trim leading/trailing slashes, then split on '/'
    const trimmed = path.replace(/^\/+|\/+$/g, '');
    if (trimmed === '') {
        return ["", ""];
    }
    const parts = trimmed.split('/');
    const first = parts[0];
    const remainder = parts.slice(1).join('/');
    return [first, remainder];
}


function normalizePath(path) {
    return path
        .split('/')                 // split into parts
        .filter(Boolean)           // remove empty strings (from leading/trailing slashes)
        .join('/');                // re-join normalized parts
}

export function isObject(parent, child) {
    const normalizedParent = normalizePath(parent);
    const normalizedChild = normalizePath(child);

    // If child is shorter than parent, it can't be a subpath
    if (normalizedChild.length < normalizedParent.length) return false;

    // Same path
    if (normalizedChild === normalizedParent) return true;

    // Check if child starts with parent + a separating slash
    return normalizedChild.startsWith(normalizedParent + '/');
}


export class Callbacks {
    constructor() {
        this._callbacks = {};
    }

    add(name) {
        if (!this._callbacks[name]) {
            this._callbacks[name] = new CallbackList();
        }
        return this._callbacks[name];
    }

    get(name) {
        return this._callbacks[name];
    }
}

class CallbackList {
    constructor() {
        this._list = [];
    }

    register(fn) {
        if (typeof fn === 'function') this._list.push(fn);
    }

    call(...args) {
        for (const fn of this._list) {
            fn(...args);
        }
    }
}


/* ================================================================================================================== */
export function writeToLocalStorage(key, value) {
    try {
        localStorage.setItem(key, JSON.stringify(value));
    } catch (e) {
        console.error('Failed to store to localStorage:', e);
    }
}

/* ================================================================================================================== */
export function getFromLocalStorage(key) {
    try {
        const value = localStorage.getItem(key);
        return value ? JSON.parse(value) : null;
    } catch (e) {
        console.error('Failed to retrieve from localStorage:', e);
        return null;
    }
}

/* ================================================================================================================== */
export function removeFromLocalStorage(key) {
    try {
        localStorage.removeItem(key);
    } catch (e) {
        console.error('Failed to remove from localStorage:', e);
    }
}

/* ================================================================================================================== */
export function existsInLocalStorage(key) {
    try {
        return localStorage.getItem(key) !== null;
    } catch (e) {
        console.error('Failed to check existence in localStorage:', e);
        return false;
    }
}


/* ================================================================================================================== */
export function getVerticalFittingFontSize(textElement, container, padding_vertical = 0, max_font_size = 100, min_font_size = 10) {
    const containerHeight = container.clientHeight - 2 * padding_vertical;
    let fontSize = max_font_size;

    const testFits = (size) => {
        textElement.style.fontSize = size + 'px';
        const {height} = textElement.getBoundingClientRect();
        return height <= containerHeight;
    };

    let low = min_font_size;
    let high = max_font_size;
    let bestFit = min_font_size;

    while (low <= high) {
        const mid = Math.floor((low + high) / 2);
        if (testFits(mid)) {
            bestFit = mid;
            low = mid + 1;
        } else {
            high = mid - 1;
        }
    }

    textElement.style.fontSize = bestFit + 'px';
    return bestFit;
}

/* ================================================================================================================== */
export function getVerticalFittingFontSizeSingleContainer(textElement, padding_vertical = 0, max_font_size = 100, min_font_size = 10) {
    // Get container height
    const containerHeight = textElement.clientHeight - 2 * padding_vertical;

    // Create a clone for measuring
    const clone = textElement.cloneNode(true);
    clone.style.visibility = 'hidden';
    clone.style.position = 'absolute';
    clone.style.height = 'auto';
    clone.style.width = textElement.clientWidth + 'px';
    clone.style.whiteSpace = 'nowrap'; // prevent line wrapping
    document.body.appendChild(clone);

    const testFits = (size) => {
        clone.style.fontSize = size + 'px';
        return (clone.getBoundingClientRect().height - 0) <= containerHeight;
    };

    let low = min_font_size;
    let high = max_font_size;
    let bestFit = min_font_size;

    while (low <= high) {
        const mid = Math.floor((low + high) / 2);
        if (testFits(mid)) {
            bestFit = mid;
            low = mid + 1;
        } else {
            high = mid - 1;
        }
    }

    document.body.removeChild(clone);
    textElement.style.fontSize = bestFit + 'px';
    return bestFit;
}

export function getFittingFontSizeSingleContainer(
    textElement,
    padding_vertical = 0,
    padding_horizontal = 0,
    max_font_size = 100,
    min_font_size = 10
) {

    // Check if textElement has .clientHeight
    if (!textElement) {
        return;
    }

    if (max_font_size < min_font_size) {
        console.warn('max_font_size must be greater than min_font_size. I swap it for you ...');
        [min_font_size, max_font_size] = [max_font_size, min_font_size];
    }


    const containerHeight = textElement.clientHeight - 2 * padding_vertical;
    const containerWidth = textElement.clientWidth - 2 * padding_horizontal;


    const clone = textElement.cloneNode(true);
    clone.style.visibility = 'hidden';
    clone.style.position = 'absolute';
    clone.style.height = 'auto';
    clone.style.width = 'auto'; // Important for accurate horizontal measurement
    clone.style.whiteSpace = 'nowrap'; // prevent wrapping
    clone.style.padding = '0'; // eliminate any padding interference
    clone.style.margin = '0';
    clone.style.boxSizing = 'content-box';

    document.body.appendChild(clone);

    const testFits = (size) => {
        clone.style.fontSize = size + 'px';
        const rect = clone.getBoundingClientRect();
        return rect.height <= containerHeight && rect.width <= containerWidth;
    };

    let low = min_font_size;
    let high = max_font_size;
    let bestFit = min_font_size;

    while (low <= high) {
        const mid = Math.floor((low + high) / 2);
        if (testFits(mid)) {
            bestFit = mid;
            low = mid + 1;
        } else {
            high = mid - 1;
        }
    }

    document.body.removeChild(clone);
    textElement.style.fontSize = bestFit + 'px';
    return bestFit;
}


/* ------------------------------------------------------------------------------------------------------------------ */
export function stringifyObject(obj, pretty = false, indent = 2) {
    try {
        // JSON.stringify handles most objects, but can't handle circular refs
        return JSON.stringify(obj, getCircularReplacer(), pretty ? indent : 0);
    } catch (e) {
        // Fallback: use util.inspect in Node.js
        if (typeof require === 'function') {
            try {
                const util = require('util');
                return util.inspect(obj, {depth: null, colors: false});
            } catch (_) {
                return String(obj);
            }
        }
        return String(obj);
    }
}

// Helper to deal with circular references
function getCircularReplacer() {
    const seen = new WeakSet();
    return function (key, value) {
        if (typeof value === 'object' && value !== null) {
            if (seen.has(value)) return '[Circular]';
            seen.add(value);
        }
        return value;
    };
}




export function formatNumberWithIncrement(number, increment, method = "round") {
  if (increment <= 0) {
    throw new Error("Increment must be a positive number");
  }

  // Determine decimal precision of the increment
  const incrementStr = increment.toString();
  const decimals = incrementStr.includes(".")
    ? incrementStr.split(".")[1].length
    : 0;

  const scale = Math.pow(10, decimals);

  // Scale values to integers to avoid floating point issues
  const scaledNumber = Math.round(number * scale);
  const scaledIncrement = Math.round(increment * scale);

  let adjusted;
  switch (method) {
    case "floor":
      adjusted =
        Math.floor(scaledNumber / scaledIncrement) * scaledIncrement;
      break;
    case "ceil":
      adjusted =
        Math.ceil(scaledNumber / scaledIncrement) * scaledIncrement;
      break;
    case "round":
    default:
      adjusted =
        Math.round(scaledNumber / scaledIncrement) * scaledIncrement;
      break;
  }

  // Scale back down and format with fixed decimals
  return (adjusted / scale).toFixed(decimals);
}