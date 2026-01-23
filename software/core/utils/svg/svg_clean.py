#!/usr/bin/env python3
from __future__ import annotations

import re
import hashlib
from pathlib import Path


# =========================
# Byte-level helpers
# =========================

def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()

def read_bytes(path: Path) -> bytes:
    return path.read_bytes()

def write_bytes(path: Path, data: bytes) -> None:
    path.write_bytes(data)

def try_decode_utf8(data: bytes) -> str:
    # Strict decode so we *don’t* silently corrupt content.
    # If this fails, you can still do a pure byte copy.
    return data.decode("utf-8", errors="strict")

def encode_utf8(text: str) -> bytes:
    return text.encode("utf-8")


# =========================
# String-level fixes (only run if enabled)
# =========================

_INVALID_XML_10 = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F]")

def remove_invalid_xml_chars(text: str) -> tuple[str, int]:
    return _INVALID_XML_10.subn("", text)

def repair_unclosed_attribute_quotes(text: str) -> tuple[str, int]:
    out = []
    in_tag = False
    quote_char: str | None = None
    fixes = 0

    i = 0
    n = len(text)
    while i < n:
        ch = text[i]

        if not in_tag:
            if ch == "<":
                in_tag = True
            out.append(ch)
            i += 1
            continue

        if quote_char is None:
            if ch == ">":
                in_tag = False
            elif ch in ('"', "'"):
                quote_char = ch
            out.append(ch)
            i += 1
            continue

        if ch == quote_char:
            quote_char = None
            out.append(ch)
            i += 1
            continue

        if ch == "<":
            out.append(quote_char)   # insert missing closing quote
            fixes += 1
            quote_char = None
            out.append(ch)
            i += 1
            continue

        out.append(ch)
        i += 1

    return "".join(out), fixes

def strip_prefixed_attributes(text: str, prefixes: list[str]) -> tuple[str, int]:
    total = 0
    for p in prefixes:
        pat = re.compile(
            rf'(\s+){re.escape(p)}:[\w.\-]+=(".*?"|\'.*?\')',
            re.DOTALL,
        )
        text, n = pat.subn(r"\1", text)
        total += n
    return text, total


# =========================
# Main
# =========================

def fix_svg_bytesafe(
    input_svg: Path,
    output_svg: Path,
    *,
    strip_inkscape: bool = False,
    strip_sodipodi: bool = False,
    strip_ns4: bool = False,
    remove_ctrl_chars: bool = False,
    fix_quotes: bool = False,
) -> None:
    original = read_bytes(input_svg)

    # If *no* transformations enabled, do a pure byte copy.
    if not any([strip_inkscape, strip_sodipodi, strip_ns4, remove_ctrl_chars, fix_quotes]):
        write_bytes(output_svg, original)
        print("SVG copied byte-for-byte (no transforms enabled)")
        print("  Input :", input_svg)
        print("  Output:", output_svg)
        print("  SHA256 in :", sha256_bytes(original))
        print("  SHA256 out:", sha256_bytes(read_bytes(output_svg)))
        return

    # Otherwise, we must decode. Do it STRICTLY to avoid silent layout corruption.
    try:
        text = try_decode_utf8(original)
    except UnicodeDecodeError as e:
        raise RuntimeError(
            "Input SVG is not valid UTF-8, but the file header likely claims UTF-8.\n"
            "Refusing to decode with replacement because that can change text layout.\n"
            f"Decode error: {e}\n"
            "You can still run with all transforms disabled to do a byte-for-byte copy."
        ) from e

    removed_ctrl = 0
    quote_fixes = 0
    stripped = 0

    if remove_ctrl_chars:
        text, removed_ctrl = remove_invalid_xml_chars(text)

    if fix_quotes:
        text, quote_fixes = repair_unclosed_attribute_quotes(text)

    prefixes = []
    if strip_inkscape:
        prefixes.append("inkscape")
    if strip_sodipodi:
        prefixes.append("sodipodi")
    if strip_ns4:
        prefixes.append("ns4")

    if prefixes:
        text, stripped = strip_prefixed_attributes(text, prefixes)

    out_bytes = encode_utf8(text)
    write_bytes(output_svg, out_bytes)

    print("SVG repair complete (byte-safe mode)")
    print("  Input :", input_svg)
    print("  Output:", output_svg)
    print("  Control chars removed:", removed_ctrl)
    print("  Inserted missing quotes:", quote_fixes)
    if prefixes:
        print("  Stripped attributes:", stripped, f"({', '.join(prefixes)})")
    print("  SHA256 in :", sha256_bytes(original))
    print("  SHA256 out:", sha256_bytes(out_bytes))
    print("  Size in/out:", len(original), "->", len(out_bytes))


if __name__ == "__main__":
    INPUT_SVG = Path(r"/Users/lehmann/Desktop/figures.svg")
    OUTPUT_SVG = Path(r"/Users/lehmann/Desktop/figures_fixed.svg")

    # IMPORTANT:
    # If you set all of these False, the script performs a byte-for-byte copy.
    fix_svg_bytesafe(
        INPUT_SVG,
        OUTPUT_SVG,
        strip_inkscape=True,
        strip_sodipodi=False,
        strip_ns4=False,
        remove_ctrl_chars=False,
        fix_quotes=False,
    )