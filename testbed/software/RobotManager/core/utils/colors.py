from __future__ import annotations
import colorsys
from typing import Union, Tuple, List, Literal, Sequence, Optional, Any, Mapping, Iterable, Dict

import seaborn as sns
import matplotlib.colors as mcolors

from dataclasses import dataclass
from enum import Enum
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple
import random

BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
RED = (255, 0, 0)
GREEN = (0, 255, 0)
BLUE = (0, 0, 255)
YELLOW = (255, 255, 0)
CYAN = (0, 255, 255)
MAGENTA = (255, 0, 255)
GREY = (128, 128, 128)
LIGHT_GREY = (192, 192, 192)

# Dark colors
DARK_RED = (139, 0, 0)
DARK_GREEN = (0, 100, 0)
DARK_BLUE = (0, 0, 139)
DARK_YELLOW = (204, 204, 0)
DARK_CYAN = (0, 139, 139)
DARK_MAGENTA = (139, 0, 139)
DARK_PURPLE = (128, 0, 128)
DARK_ORANGE = (255, 140, 0)
DARK_BROWN = (139, 69, 19)
DARK_GREY = (100, 100, 100)

# Light colors
LIGHT_RED = (255, 99, 71)
LIGHT_GREEN = (144, 238, 144)
LIGHT_BLUE = (173, 216, 230)
LIGHT_YELLOW = (255, 255, 224)
LIGHT_CYAN = (224, 255, 255)
LIGHT_MAGENTA = (255, 0, 255)
LIGHT_PURPLE = (218, 112, 214)
LIGHT_ORANGE = (255, 165, 0)
LIGHT_BROWN = (205, 133, 63)

# Medium colors
MEDIUM_RED = (220, 20, 60)
MEDIUM_GREEN = (60, 179, 113)
MEDIUM_BLUE = (0, 0, 205)
MEDIUM_YELLOW = (255, 255, 0)
MEDIUM_CYAN = (0, 255, 255)
MEDIUM_MAGENTA = (255, 0, 255)
MEDIUM_PURPLE = (147, 112, 219)
MEDIUM_ORANGE = (255, 165, 0)
MEDIUM_BROWN = (165, 42, 42)


# --- tiny helpers (standalone so the class is self-contained) ---
def _hex_to_rgb01(hex_str: str) -> Tuple[float, float, float]:
    s = hex_str.lstrip("#")
    if len(s) == 3:  # #rgb
        r, g, b = (int(c * 2, 16) for c in s)
    elif len(s) == 6:  # #rrggbb
        r, g, b = (int(s[i:i + 2], 16) for i in (0, 2, 4))
    else:
        raise ValueError(f"Bad hex color: {hex_str}")
    return r / 255.0, g / 255.0, b / 255.0


def _rgb01_to_hex(rgb: Sequence[float]) -> str:
    r, g, b = [max(0, min(255, int(round(c * 255)))) for c in rgb[:3]]
    return f"#{r:02x}{g:02x}{b:02x}"


# ---------- small helpers ----------
def _hex_to_rgb01(hex_str: str) -> Tuple[float, float, float]:
    s = hex_str.lstrip("#")
    if len(s) == 3:
        r, g, b = (int(c * 2, 16) for c in s)
    elif len(s) == 6:
        r, g, b = (int(s[i:i + 2], 16) for i in (0, 2, 4))
    else:
        raise ValueError(f"Bad hex color: {hex_str}")
    return (r / 255.0, g / 255.0, b / 255.0)


def _rgb01_to_hex(rgb: Sequence[float]) -> str:
    r, g, b = [max(0, min(255, int(round(c * 255)))) for c in rgb[:3]]
    return f"#{r:02x}{g:02x}{b:02x}"


def _normalize(s: str) -> str:
    return "".join(ch for ch in s.lower() if ch.isalnum())


# ---------- Enum with autocompletion ----------
class NamedColor(Enum):
    # Grays
    BLACK = (0.0, 0.0, 0.0)
    WHITE = (1.0, 1.0, 1.0)
    GREY = _hex_to_rgb01("#808080")
    LIGHTGREY = _hex_to_rgb01("#d3d3d3")
    DARKGREY = _hex_to_rgb01("#646464")

    # Core hues + nice designer names
    RED = _hex_to_rgb01("#ff0000")
    CRIMSON = _hex_to_rgb01("#dc143c")
    SALMON = _hex_to_rgb01("#fa8072")
    CORAL = _hex_to_rgb01("#ff7f50")
    ORANGE = _hex_to_rgb01("#ffa500")
    DARKORANGE = _hex_to_rgb01("#ff8c00")
    AMBER = _hex_to_rgb01("#ffc107")
    GOLD = _hex_to_rgb01("#ffd700")
    YELLOW = _hex_to_rgb01("#ffff00")
    OLIVE = _hex_to_rgb01("#808000")
    LIME = _hex_to_rgb01("#32cd32")
    LIGHTGREEN = _hex_to_rgb01("#90ee90")
    FOREST = _hex_to_rgb01("#228b22")
    EMERALD = _hex_to_rgb01("#2ecc71")
    JADE = _hex_to_rgb01("#00a86b")
    MINT = _hex_to_rgb01("#98ff98")
    AQUAMARINE = _hex_to_rgb01("#7fffd4")
    TEAL = _hex_to_rgb01("#008080")
    TURQUOISE = _hex_to_rgb01("#40e0d0")
    CYAN = _hex_to_rgb01("#00ffff")
    SKY = _hex_to_rgb01("#87ceeb")
    DEEPSKY = _hex_to_rgb01("#00bfff")
    DODGERBLUE = _hex_to_rgb01("#1e90ff")
    CORNFLOWER = _hex_to_rgb01("#6495ed")
    ROYALBLUE = _hex_to_rgb01("#4169e1")
    BLUE = _hex_to_rgb01("#0000ff")
    NAVY = _hex_to_rgb01("#000080")
    INDIGO = _hex_to_rgb01("#4b0082")
    PURPLE = _hex_to_rgb01("#800080")
    VIOLET = _hex_to_rgb01("#8a2be2")
    ORCHID = _hex_to_rgb01("#da70d6")
    PLUM = _hex_to_rgb01("#dda0dd")
    MAGENTA = _hex_to_rgb01("#ff00ff")
    FUCHSIA = _hex_to_rgb01("#ff00ff")
    LAVENDER = _hex_to_rgb01("#e6e6fa")
    LILAC = _hex_to_rgb01("#c8a2c8")
    BROWN = _hex_to_rgb01("#8b4513")
    CHOCOLATE = _hex_to_rgb01("#d2691e")
    TAN = _hex_to_rgb01("#d2b48c")
    BEIGE = _hex_to_rgb01("#f5f5dc")
    IVORY = _hex_to_rgb01("#fffff0")

    # Convenience “dark* / light*”
    DARKRED = _hex_to_rgb01("#8b0000")
    DARKGREEN = _hex_to_rgb01("#006400")
    DARKBLUE = _hex_to_rgb01("#00008b")
    DARKCYAN = _hex_to_rgb01("#008b8b")
    DARKMAGENTA = _hex_to_rgb01("#8b008b")
    DARKPURPLE = _hex_to_rgb01("#800080")
    DARKBROWN = _hex_to_rgb01("#8b4513")
    LIGHTRED = _hex_to_rgb01("#ff6347")
    LIGHTBLUE = _hex_to_rgb01("#add8e6")
    LIGHTCYAN = _hex_to_rgb01("#e0ffff")
    LIGHTMAGENTA = _hex_to_rgb01("#ff77ff")
    LIGHTPURPLE = _hex_to_rgb01("#da70d6")
    LIGHTORANGE = _hex_to_rgb01("#ffb347")
    LIGHTBROWN = _hex_to_rgb01("#cd853f")

    # ---- convenience properties / helpers ----
    @property
    def rgb(self) -> Tuple[float, float, float]:
        return self.value

    @property
    def hex(self) -> str:
        return _rgb01_to_hex(self.value)

    def as_tuple(self) -> Tuple[float, float, float]:
        return self.value

    # Aliases (string forms) → Enum
    _ALIASES: Mapping[str, "NamedColor"] = {}

    @classmethod
    def _build_aliases(cls) -> None:
        if cls._ALIASES:
            return
        # Normalize enum names and popular spellings
        for member in cls:
            cls._ALIASES[_normalize(member.name)] = member
            cls._ALIASES[_normalize(member.name.lower())] = member
        # manual common aliases / synonyms
        manual: Dict[str, NamedColor] = {
            "grey": cls.GREY,
            "lightgrey": cls.LIGHTGREY,
            "darkgrey": cls.DARKGREY,
            "light_green": cls.LIGHTGREEN,
            "light-green": cls.LIGHTGREEN,
            "seafoam": cls.EMERALD,  # pick your preferred mapping
            "rebeccapurple": cls.PURPLE,  # easy extension point
            "blueviolet": cls.VIOLET,
            "deep_sky": cls.DEEPSKY,
            "dodger-blue": cls.DODGERBLUE,
        }
        for k, v in manual.items():
            cls._ALIASES[_normalize(k)] = v

    @classmethod
    def from_name(cls, name: str) -> "NamedColor":
        cls._build_aliases()
        key = _normalize(name)
        if key in cls._ALIASES:
            return cls._ALIASES[key]
        # try exact enum member name
        try:
            return cls[name.upper()]
        except KeyError:
            # nice error with available names
            choices = ", ".join(m.name.lower() for m in cls)
            raise KeyError(f"Unknown color '{name}'. Try one of: {choices}") from None

    @classmethod
    def list(cls) -> List["NamedColor"]:
        return list(cls)

    @classmethod
    def random(cls, seed: Optional[int] = None) -> "NamedColor":
        rng = random.Random(seed)
        return rng.choice(list(cls))


# ---------- Frozen dataclass with autocompleted attributes ----------
# (Access like: COLORS.emerald, COLORS.lightgreen, ...)

@dataclass(frozen=True)
class Colors:
    # Keep names lowercase to feel natural when used as attributes
    black: Tuple[float, float, float] = NamedColor.BLACK.rgb
    white: Tuple[float, float, float] = NamedColor.WHITE.rgb
    grey: Tuple[float, float, float] = NamedColor.GREY.rgb
    lightgrey: Tuple[float, float, float] = NamedColor.LIGHTGREY.rgb
    darkgrey: Tuple[float, float, float] = NamedColor.DARKGREY.rgb

    red: Tuple[float, float, float] = NamedColor.RED.rgb
    crimson: Tuple[float, float, float] = NamedColor.CRIMSON.rgb
    salmon: Tuple[float, float, float] = NamedColor.SALMON.rgb
    coral: Tuple[float, float, float] = NamedColor.CORAL.rgb
    orange: Tuple[float, float, float] = NamedColor.ORANGE.rgb
    darkorange: Tuple[float, float, float] = NamedColor.DARKORANGE.rgb
    amber: Tuple[float, float, float] = NamedColor.AMBER.rgb
    gold: Tuple[float, float, float] = NamedColor.GOLD.rgb
    yellow: Tuple[float, float, float] = NamedColor.YELLOW.rgb
    olive: Tuple[float, float, float] = NamedColor.OLIVE.rgb
    lime: Tuple[float, float, float] = NamedColor.LIME.rgb
    lightgreen: Tuple[float, float, float] = NamedColor.LIGHTGREEN.rgb
    forest: Tuple[float, float, float] = NamedColor.FOREST.rgb
    emerald: Tuple[float, float, float] = NamedColor.EMERALD.rgb
    jade: Tuple[float, float, float] = NamedColor.JADE.rgb
    mint: Tuple[float, float, float] = NamedColor.MINT.rgb
    aquamarine: Tuple[float, float, float] = NamedColor.AQUAMARINE.rgb
    teal: Tuple[float, float, float] = NamedColor.TEAL.rgb
    turquoise: Tuple[float, float, float] = NamedColor.TURQUOISE.rgb
    cyan: Tuple[float, float, float] = NamedColor.CYAN.rgb
    sky: Tuple[float, float, float] = NamedColor.SKY.rgb
    deepsky: Tuple[float, float, float] = NamedColor.DEEPSKY.rgb
    dodgerblue: Tuple[float, float, float] = NamedColor.DODGERBLUE.rgb
    cornflower: Tuple[float, float, float] = NamedColor.CORNFLOWER.rgb
    royalblue: Tuple[float, float, float] = NamedColor.ROYALBLUE.rgb
    blue: Tuple[float, float, float] = NamedColor.BLUE.rgb
    navy: Tuple[float, float, float] = NamedColor.NAVY.rgb
    indigo: Tuple[float, float, float] = NamedColor.INDIGO.rgb
    purple: Tuple[float, float, float] = NamedColor.PURPLE.rgb
    violet: Tuple[float, float, float] = NamedColor.VIOLET.rgb
    orchid: Tuple[float, float, float] = NamedColor.ORCHID.rgb
    plum: Tuple[float, float, float] = NamedColor.PLUM.rgb
    magenta: Tuple[float, float, float] = NamedColor.MAGENTA.rgb
    fuchsia: Tuple[float, float, float] = NamedColor.FUCHSIA.rgb
    lavender: Tuple[float, float, float] = NamedColor.LAVENDER.rgb
    lilac: Tuple[float, float, float] = NamedColor.LILAC.rgb
    brown: Tuple[float, float, float] = NamedColor.BROWN.rgb
    chocolate: Tuple[float, float, float] = NamedColor.CHOCOLATE.rgb
    tan: Tuple[float, float, float] = NamedColor.TAN.rgb
    beige: Tuple[float, float, float] = NamedColor.BEIGE.rgb
    ivory: Tuple[float, float, float] = NamedColor.IVORY.rgb

    darkred: Tuple[float, float, float] = NamedColor.DARKRED.rgb
    darkgreen: Tuple[float, float, float] = NamedColor.DARKGREEN.rgb
    darkblue: Tuple[float, float, float] = NamedColor.DARKBLUE.rgb
    darkcyan: Tuple[float, float, float] = NamedColor.DARKCYAN.rgb
    darkmagenta: Tuple[float, float, float] = NamedColor.DARKMAGENTA.rgb
    darkpurple: Tuple[float, float, float] = NamedColor.DARKPURPLE.rgb
    darkbrown: Tuple[float, float, float] = NamedColor.DARKBROWN.rgb
    lightred: Tuple[float, float, float] = NamedColor.LIGHTRED.rgb
    lightblue: Tuple[float, float, float] = NamedColor.LIGHTBLUE.rgb
    lightcyan: Tuple[float, float, float] = NamedColor.LIGHTCYAN.rgb
    lightmagenta: Tuple[float, float, float] = NamedColor.LIGHTMAGENTA.rgb
    lightpurple: Tuple[float, float, float] = NamedColor.LIGHTPURPLE.rgb
    lightorange: Tuple[float, float, float] = NamedColor.LIGHTORANGE.rgb
    lightbrown: Tuple[float, float, float] = NamedColor.LIGHTBROWN.rgb


# Make a module-level instance for attribute autocompletion:
COLORS = Colors()

# Optional: ergonomic helpers that also benefit from Enum typing
ColorTuple = Tuple[float, float, float]


def color_get(name_or_member: str | NamedColor) -> ColorTuple:
    if isinstance(name_or_member, NamedColor):
        return name_or_member.rgb
    return NamedColor.from_name(name_or_member).rgb


def color_hex(name_or_member: str | NamedColor) -> str:
    return _rgb01_to_hex(color_get(name_or_member))


def rgb_to_hex(rgb):
    """
    Convert a list of RGB(A) values (0–1 floats) to a hex HTML color.
    Examples:
      rgb_to_hex([0.5, 0.2, 0.8])       -> "#8033cc"
      rgb_to_hex([0.5, 0.2, 0.8, 0.3])  -> "#8033cc4d"
    """

    def clamp(x):
        return max(0, min(x, 1))

    if rgb is None:
        return None

    if len(rgb) == 3 or len(rgb) == 4:
        # clamp & scale
        comps = [int(clamp(c) * 255) for c in rgb]
        # format RGB
        hex_str = "#{:02x}{:02x}{:02x}".format(*comps[:3])
        # if alpha present, append as two hex digits
        if len(comps) == 4:
            hex_str += "{:02x}".format(comps[3])
        return hex_str

    # fallback on bad input
    return "#FFFFFF"


def random_color(len=3):
    if len == 3:
        return [random.random(), random.random(), random.random()]
    elif len == 4:
        return [random.random(), random.random(), random.random(), random.random()]
    else:
        return None


_PREDEFINED_PALETTES = {
    "muted": sns.color_palette("muted"),  # ~8 colors
    "pastel": sns.color_palette("pastel"),  # ~8 colors
    "dark": sns.color_palette("dark"),  # ~8 colors
    "bright": sns.color_palette("bright"),  # ~8 colors
    "colorblind": sns.color_palette("colorblind"),  # ~8 colors
    "deep": sns.color_palette("deep"),  # ~8 colors
    # ... you can add more, e.g.:
    # "cubehelix":    sns.color_palette("cubehelix", 8),
    # "viridis":      sns.color_palette("viridis",   8),
    # "inferno":      sns.color_palette("inferno",   8),
    # "cividis":      sns.color_palette("cividis",   8),
}


def get_palette(name, n_colors=8):
    """
    Return a list of `n_colors` float‐RGB tuples in [0,1].
    Examples:
      get_palette("muted", 5)   → 5 “muted” colors
      get_palette("bright", 10) → 10 “bright” colors
    If `name` is not found, raises KeyError.
    """
    if name not in _PREDEFINED_PALETTES:
        raise KeyError(f"Palette '{name}' is not defined. Available: {list(_PREDEFINED_PALETTES.keys())}")
    # Seaborn will automatically cycle/ interpolate if you ask for > base size.
    return sns.color_palette(name, n_colors)


def get_color_from_palette(name, n_colors, index):
    if name not in _PREDEFINED_PALETTES:
        raise KeyError(f"Palette '{name}' is not defined. Available: {list(_PREDEFINED_PALETTES.keys())}")
    return _PREDEFINED_PALETTES[name][index % n_colors]


def get_palette_hex(name, n_colors=8):
    """
    Same as get_palette(), but each color is converted to a hex string "#RRGGBB".
    """
    float_list = get_palette(name, n_colors)
    # rgb_to_hex expects a list [r,g,b] in floats 0..1
    return [rgb_to_hex(color) for color in float_list]


def random_color_from_palette(name):
    """
    Return one random float‐RGB tuple from the named palette (using its standard size).
    """
    base = _PREDEFINED_PALETTES.get(name)
    if base is None:
        raise KeyError(f"Palette '{name}' is not defined.")
    return random.choice(base)


def random_color_from_palette_hex(name):
    """
    Return one random color from the named palette, as "#RRGGBB".
    """
    c = random_color_from_palette(name)
    return rgb_to_hex(c)


def get_shaded_color(base_color: str | tuple[float, float, float] | list[float],
                     total_steps: int,
                     index: int) -> tuple:
    """
    Return an RGBA color with increasing alpha (transparency) based on index.

    Args:
        base_color (str | list | tuple): Base color (name, hex, or RGB [0-1]).
        total_steps (int): Total number of curves.
        index (int): Current index (0-based).

    Returns:
        tuple: RGBA color (r, g, b, a)
    """
    if isinstance(base_color, (list, tuple)):
        rgb = tuple(base_color)
    else:
        rgb = mcolors.to_rgb(base_color)

    if total_steps <= 1:
        alpha = 1.0
    else:
        alpha = 0.2 + 0.8 * index / (total_steps - 1)  # from 0.2 to 1.0

    return (*rgb, alpha)


from typing import List

Color = List[float]
Mode = Literal["interpolate", "add", "multiply", "screen", "overlay", "darken", "lighten"]


def getColorGradient(color1: Color, color2: Color, num_colors: int) -> List[Color]:
    """
    Linearly interpolate between color1 and color2 (0–1 RGB or RGBA lists/tuples),
    returning `num_colors` colors including both endpoints.

    - If num_colors <= 0 → []
    - If num_colors == 1 → [color1 (trimmed to common channel length)]
    - Supports RGB or RGBA; uses the common channel count (min length).
    """
    if num_colors <= 0:
        return []

    length = min(len(color1), len(color2))
    c1 = list(color1[:length])
    c2 = list(color2[:length])

    if num_colors == 1:
        return [c1]

    out = []
    for i in range(num_colors):
        t = i / (num_colors - 1)
        out.append(mix_colors(c1, c2, mode="interpolate", t=t))
    return out


def clamp(value: float, min_val: float = 0.0, max_val: float = 1.0) -> float:
    return max(min_val, min(max_val, value))


def mix_colors(color1: Color, color2: Color, mode: Mode = "interpolate", t: float = 0.5) -> Color:
    length = min(len(color1), len(color2))
    c1 = color1[:length]
    c2 = color2[:length]

    def interp(a, b):
        return (1 - t) * a + t * b

    mixed = []

    for i in range(length):
        a = c1[i]
        b = c2[i]

        if mode == "interpolate":
            val = interp(a, b)
        elif mode == "add":
            val = clamp(a + b)
        elif mode == "multiply":
            val = a * b
        elif mode == "screen":
            val = 1 - (1 - a) * (1 - b)
        elif mode == "overlay":
            val = 2 * a * b if a < 0.5 else 1 - 2 * (1 - a) * (1 - b)
        elif mode == "darken":
            val = min(a, b)
        elif mode == "lighten":
            val = max(a, b)
        else:
            raise ValueError(f"Unsupported mode: {mode}")

        mixed.append(clamp(val))

    return mixed


# --------------------------------------------------------------------------------------
# New color utilities: lighten, darken, (de)saturate, hue shift, and a generic adjuster
# --------------------------------------------------------------------------------------

def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def _to_rgba01(color: Union[str, Sequence[float]]) -> Tuple[float, float, float, float]:
    """
    Normalize a color to RGBA in 0–1 floats.
    Accepts:
      - Matplotlib color strings (names, "C0", "tab:blue", "#RRGGBB", "#RRGGBBAA")
      - RGB or RGBA sequences in 0–1 floats or 0–255 ints
    """
    if isinstance(color, str):
        # mcolors.to_rgba handles hex, names, "C0", etc.
        r, g, b, a = mcolors.to_rgba(color)
        return (_clamp01(r), _clamp01(g), _clamp01(b), _clamp01(a))

    if isinstance(color, (list, tuple)):
        if len(color) not in (3, 4):
            raise ValueError("Color tuple/list must have length 3 (RGB) or 4 (RGBA).")
        vals = list(color)
        # Detect 0–255 integers
        if any(v > 1.0 for v in vals):
            # Assume 0–255 range
            vals = [v / 255.0 for v in vals]
        # Pad alpha if missing
        if len(vals) == 3:
            vals.append(1.0)
        r, g, b, a = vals[:4]
        return (_clamp01(float(r)), _clamp01(float(g)), _clamp01(float(b)), _clamp01(float(a)))

    raise TypeError(f"Unsupported color type: {type(color)}")


def _rgb01_to_hls(r: float, g: float, b: float) -> Tuple[float, float, float]:
    # colorsys uses HLS order (note: not HSL)
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    return h, l, s


def _hls_to_rgb01(h: float, l: float, s: float) -> Tuple[float, float, float]:
    r, g, b = colorsys.hls_to_rgb(h, l, s)
    return _clamp01(r), _clamp01(g), _clamp01(b)


def adjust_color(color: Union[str, Sequence[float]],
                 *,
                 l_factor: Optional[float] = None,
                 s_factor: Optional[float] = None,
                 h_shift_deg: Optional[float] = None,
                 alpha: Optional[float] = None) -> Tuple[float, float, float, float]:
    """
    Generic color adjustment in HLS space.

    Args:
        color: Any Matplotlib color (name/hex/"C0"/RGB/RGBA in 0–1 or 0–255).
        l_factor: Multiplicative factor for lightness (L). 1.0 = unchanged.
                  e.g., 1.15 to lighten ~15%, 0.85 to darken ~15%.
        s_factor: Multiplicative factor for saturation (S). 1.0 = unchanged.
        h_shift_deg: Add degrees to hue (wraps around), e.g., +30 rotates hue by 30°.
        alpha: If set, replace the alpha channel (0–1).

    Returns:
        (r, g, b, a) with components in [0, 1].
    """
    r, g, b, a = _to_rgba01(color)
    h, l, s = _rgb01_to_hls(r, g, b)

    if l_factor is not None:
        l = _clamp01(l * l_factor)
    if s_factor is not None:
        s = _clamp01(s * s_factor)
    if h_shift_deg is not None:
        h = (h + (h_shift_deg / 360.0)) % 1.0
    if alpha is not None:
        a = _clamp01(alpha)

    r2, g2, b2 = _hls_to_rgb01(h, l, s)
    return (r2, g2, b2, a)


def lighten_color(color: Union[str, Sequence[float]], amount: float = 0.2) -> Tuple[float, float, float]:
    """
    Lighten a color by increasing HLS lightness toward 1.0.

    amount: in [0,1]. 0 = no change, 1 = white.
    Implementation: L' = L + amount * (1 - L)
    """
    r, g, b, a = _to_rgba01(color)
    h, l, s = _rgb01_to_hls(r, g, b)
    l = _clamp01(l + amount * (1.0 - l))
    r2, g2, b2 = _hls_to_rgb01(h, l, s)
    return (r2, g2, b2)


def darken_color(color: list | tuple | Any, amount: float = 0.2) -> tuple:
    """
    Darken a color by reducing HLS lightness toward 0.0.

    amount: in [0,1]. 0 = no change, 1 = black.
    Implementation: L' = L * (1 - amount)
    """
    r, g, b, a = _to_rgba01(color)
    h, l, s = _rgb01_to_hls(r, g, b)
    l = _clamp01(l * (1.0 - amount))
    r2, g2, b2 = _hls_to_rgb01(h, l, s)
    return r2, g2, b2


def saturate_color(color: Union[str, Sequence[float]], amount: float = 0.2) -> Tuple[float, float, float]:
    """
    Increase color saturation in HLS space.

    amount: in [0,1]. 0 = no change, 1 = fully saturated.
    Implementation: S' = S + amount * (1 - S)
    """
    r, g, b, a = _to_rgba01(color)
    h, l, s = _rgb01_to_hls(r, g, b)
    s = _clamp01(s + amount * (1.0 - s))
    r2, g2, b2 = _hls_to_rgb01(h, l, s)
    return (r2, g2, b2)


def desaturate_color(color: Union[str, Sequence[float]], amount: float = 0.2) -> Tuple[float, float, float]:
    """
    Reduce color saturation in HLS space.

    amount: in [0,1]. 0 = no change, 1 = grayscale.
    Implementation: S' = S * (1 - amount)
    """
    r, g, b, a = _to_rgba01(color)
    h, l, s = _rgb01_to_hls(r, g, b)
    s = _clamp01(s * (1.0 - amount))
    r2, g2, b2 = _hls_to_rgb01(h, l, s)
    return (r2, g2, b2)


def shift_hue(color: Union[str, Sequence[float]], degrees: float) -> Tuple[float, float, float]:
    """
    Rotate hue by a given number of degrees (positive = clockwise).

    Example: shift_hue("#1f77b4", 30)
    """
    r, g, b, a = _to_rgba01(color)
    h, l, s = _rgb01_to_hls(r, g, b)
    h = (h + degrees / 360.0) % 1.0
    r2, g2, b2 = _hls_to_rgb01(h, l, s)
    return (r2, g2, b2)


# Convenience: make N subtle variants for “iteration 2” lines in plots
def variants(color: Union[str, Sequence[float]],
             *,
             n: int = 3,
             lighten_by: float = 0.15,
             saturate_by: float = 0.10) -> List[Tuple[float, float, float]]:
    """
    Generate `n` slight variations of a base color, useful for secondary/iterative curves.
    Returns RGB in 0–1.

    Strategy: progressively lighten + saturate a touch.
    """
    r, g, b, _ = _to_rgba01(color)
    out = []
    for i in range(n):
        t = 0 if n <= 1 else i / (n - 1)
        # ease-in a bit on both
        li = lighten_by * (0.6 * t + 0.4 * (t ** 2))
        si = saturate_by * (0.5 * t + 0.5 * (t ** 2))
        c = lighten_color((r, g, b), li)
        c = saturate_color(c, si)
        out.append(c)
    return out


# -------------------------
# Progression color helpers
# -------------------------

def _interp(a: float, b: float, t: float) -> float:
    return (1 - t) * a + t


def _interp_color_rgb(c1: Color, c2: Color, t: float) -> Color:
    length = min(len(c1), len(c2), 4)
    return [
        _clamp01((1 - t) * c1[i] + t * c2[i])
        for i in range(min(length, 3))
    ] + ([_clamp01((1 - t) * c1[3] + t * c2[3])] if length >= 4 else [])


# 1) Multi-hue spiral with rising brightness (HSV)
def get_progression_colors_multi_hue(n: int,
                                     cycles: float = 2.5,
                                     start_h: float = 0.0,
                                     s: float = 0.8,
                                     v_min: float = 0.35,
                                     v_max: float = 0.9) -> List[Color]:
    """
    Generates n colors by cycling the hue 'cycles' times while ramping value (brightness).
    Great for 20–30 trials: adjacent colors jump around the wheel but overall get brighter.
    """
    if n <= 0:
        return []
    if n == 1:
        h = start_h % 1.0
        r, g, b = colorsys.hsv_to_rgb(h, s, v_max)
        return [[r, g, b]]
    out = []
    for i in range(n):
        t = i / (n - 1)
        h = (start_h + cycles * t) % 1.0
        v = _interp(v_min, v_max, t)
        r, g, b = colorsys.hsv_to_rgb(h, s, v)
        out.append([r, g, b])
    return out


# 2) Segmented interpolation across multiple anchors
def get_segmented_progression_colors(n: int,
                                     anchors: Sequence[Color],
                                     gamma: float = 1.0) -> List[Color]:
    """
    Interpolates across a list of anchor colors (RGB 0–1) to produce n ordered colors.
    'gamma' > 1 biases toward anchors; gamma < 1 densifies the middle.
    Example anchors: [[0,0,0.8],[0,0.6,0.3],[0.9,0.5,0.0],[0.8,0.0,0.0]]
    """
    if n <= 0:
        return []
    if n == 1 or len(anchors) == 1:
        return [list(anchors[0])]

    # Normalize anchors lengths to 3
    anchors = [list(a[:3]) for a in anchors]

    out = []
    m = len(anchors) - 1
    for i in range(n):
        t = i / (n - 1)
        # gamma shaping (monotonic)
        if gamma != 1.0:
            t = t ** gamma
        # Which segment?
        seg = min(int(t * m), m - 1)
        local_start = seg / m
        local_end = (seg + 1) / m
        u = 0.0 if local_end == local_start else (t - local_start) / (local_end - local_start)
        c = _interp_color_rgb(anchors[seg], anchors[seg + 1], u)
        out.append(c)
    return out


# 3) Cycle a qualitative palette while ramping lightness (HLS)
def get_palette_cycling_with_lightness(n: int,
                                       base_palette: Sequence[Color],
                                       l_min: float = 0.38,
                                       l_max: float = 0.82) -> List[Color]:
    """
    Repeats a provided palette (e.g., sns.color_palette('colorblind', 8)), but
    gradually increases lightness across indices to suggest progression.
    """
    if n <= 0:
        return []
    k = len(base_palette)
    if k == 0:
        return []

    out = []
    for i in range(n):
        t = 0 if n == 1 else i / (n - 1)
        l_target = (1 - t) * l_min + t * l_max
        r0, g0, b0 = base_palette[i % k][:3]
        h, l, s = colorsys.rgb_to_hls(r0, g0, b0)
        r, g, b = colorsys.hls_to_rgb(h, l_target, s)
        out.append([_clamp01(r), _clamp01(g), _clamp01(b)])
    return out
