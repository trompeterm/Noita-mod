"""Read Noita's save00/mod_settings.bin, where ModSettingSet() values are persisted.

Layout (worked out from real files; little-endian header, big-endian body):
    u32 compressed_size, u32 uncompressed_size, then the body, FastLZ-compressed
    unless both sizes are equal.
    body: u64 count, then per entry:
        u32 name_len, name, u32 current_type, u32 next_type, current value, next value
    value types: 0 none (no bytes), 1 bool (1 byte), 2 number (f64), 3 string (u32 len + bytes)
"""

from __future__ import annotations

import os
import struct
from pathlib import Path

Value = bool | float | str | None


def default_mod_settings_path() -> Path:
    base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")).parent
    return base / "LocalLow" / "Nolla_Games_Noita" / "save00" / "mod_settings.bin"


def fastlz_decompress(data: bytes, expected_size: int) -> bytes:
    # FastLZ picks level 2 for inputs over 64 KiB, e.g. once many rooms are exported.
    level = (data[0] >> 5) + 1
    if level not in (1, 2):
        raise ValueError(f"Unsupported FastLZ level {level}")
    out = bytearray()
    ip = 1
    ctrl = data[0] & 31
    while True:
        if ctrl >= 32:
            length = (ctrl >> 5) - 1
            ofs = (ctrl & 31) << 8
            ref = len(out) - ofs - 1
            if length == 6:
                if level == 1:
                    length += data[ip]
                    ip += 1
                else:
                    while True:
                        code = data[ip]
                        ip += 1
                        length += code
                        if code != 255:
                            break
            code = data[ip]
            ip += 1
            ref -= code
            if level == 2 and code == 255 and ofs == 31 << 8:  # far match: 16-bit distance
                ref = len(out) - ((data[ip] << 8) + data[ip + 1]) - 8191 - 1
                ip += 2
            if ref < 0:
                raise ValueError("Corrupt FastLZ stream (reference before start)")
            for i in range(length + 3):  # byte by byte: matches may overlap
                out.append(out[ref + i])
        else:
            out += data[ip:ip + ctrl + 1]
            ip += ctrl + 1
        if ip >= len(data):
            break
        ctrl = data[ip]
        ip += 1
    if len(out) != expected_size:
        raise ValueError(f"FastLZ size mismatch: got {len(out)}, expected {expected_size}")
    return bytes(out)


def parse_mod_settings(raw: bytes) -> dict[str, Value]:
    """Current value of every setting (the value the running game sees)."""
    compressed, uncompressed = struct.unpack_from("<II", raw, 0)
    body = raw[8:8 + compressed]
    if compressed != uncompressed:
        body = fastlz_decompress(body, uncompressed)
    pos = 0

    def take(n: int) -> bytes:
        nonlocal pos
        if pos + n > len(body):
            raise ValueError("Truncated mod settings file")
        chunk = body[pos:pos + n]
        pos += n
        return chunk

    def value(kind: int) -> Value:
        if kind == 0:
            return None
        if kind == 1:
            return take(1) != b"\0"
        if kind == 2:
            return struct.unpack(">d", take(8))[0]
        if kind == 3:
            (length,) = struct.unpack(">I", take(4))
            return take(length).decode("utf-8", "replace")
        raise ValueError(f"Unknown mod setting value type {kind}")

    (count,) = struct.unpack(">Q", take(8))
    settings: dict[str, Value] = {}
    for _ in range(count):
        (name_len,) = struct.unpack(">I", take(4))
        name = take(name_len).decode("utf-8", "replace")
        current_type, next_type = struct.unpack(">II", take(8))
        settings[name] = value(current_type)
        value(next_type)
    return settings


def read_mod_settings(path: Path | None = None) -> dict[str, Value]:
    return parse_mod_settings((path or default_mod_settings_path()).read_bytes())
