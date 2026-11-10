"""Header-only detection of animated images (GIF, WebP, APNG).

The detector reads container headers and skips pixel data. It never decodes a frame, never raises, and
bounds both the number of container blocks it walks and the bytes it moves past. Anything it cannot
prove animated (other formats, unreadable files, truncated headers) is "not animated".
"""

from __future__ import annotations

import struct
from pathlib import Path
from typing import BinaryIO

# Extensions of the containers this module understands (``.png`` covers APNG).
ANIMATABLE_EXTENSIONS = frozenset({".gif", ".webp", ".png"})

_MAX_GIF_SCAN_BYTES = 64 * 1024 * 1024  # a first frame larger than this is not walked further
_MAX_CHUNKS = 512  # PNG / WebP chunk walk bound
_READ_BUFFER = 64 * 1024


def _read_exact(fp: BinaryIO, size: int) -> bytes | None:
    data = fp.read(size)
    return data if len(data) == size else None


def _skip(fp: BinaryIO, size: int, end: int) -> bool:
    """Move forward ``size`` bytes; ``False`` when that runs past the end of the file."""
    target = fp.tell() + size
    if target > end:
        return False
    fp.seek(target)
    return True


def _gif_is_animated(fp: BinaryIO, end: int) -> bool:
    """True once a second Image Descriptor follows the first image's data."""
    header = _read_exact(fp, 13)  # signature + logical screen descriptor
    if header is None:
        return False
    flags = header[10]
    if flags & 0x80 and not _skip(fp, 3 * (2 << (flags & 0x07)), end):
        return False
    frames = 0
    start = fp.tell()
    while fp.tell() - start < _MAX_GIF_SCAN_BYTES:
        introducer = fp.read(1)
        if not introducer:
            return False
        marker = introducer[0]
        if marker == 0x21:  # extension: label byte, then data sub-blocks
            if not fp.read(1):
                return False
        elif marker == 0x2C:  # image descriptor
            frames += 1
            if frames > 1:
                return True
            descriptor = _read_exact(fp, 9)
            if descriptor is None:
                return False
            if descriptor[8] & 0x80 and not _skip(fp, 3 * (2 << (descriptor[8] & 0x07)), end):
                return False
            if not fp.read(1):  # LZW minimum code size
                return False
        else:  # trailer (0x3B) or garbage
            return False
        while True:  # data sub-blocks: length byte, payload; a zero length ends the run
            length = fp.read(1)
            if not length:
                return False
            if length[0] == 0:
                break
            if not _skip(fp, length[0], end):
                return False
    return False


def _webp_is_animated(fp: BinaryIO, end: int) -> bool:
    header = _read_exact(fp, 12)
    if header is None or header[:4] != b"RIFF" or header[8:12] != b"WEBP":
        return False
    for _ in range(_MAX_CHUNKS):
        chunk = _read_exact(fp, 8)
        if chunk is None:
            return False
        tag = chunk[:4]
        size = struct.unpack("<I", chunk[4:])[0]
        if tag == b"VP8X":
            flags = fp.read(1)
            if not flags:
                return False
            if flags[0] & 0x02:
                return True
            if not _skip(fp, size - 1 + (size & 1), end):
                return False
            continue
        if tag in (b"ANIM", b"ANMF"):
            return True
        if tag in (b"VP8 ", b"VP8L"):  # still image data: no animation chunk can follow
            return False
        if not _skip(fp, size + (size & 1), end):
            return False
    return False


def _png_is_animated(fp: BinaryIO, end: int) -> bool:
    if _read_exact(fp, 8) != b"\x89PNG\r\n\x1a\n":
        return False
    for _ in range(_MAX_CHUNKS):
        chunk = _read_exact(fp, 8)
        if chunk is None:
            return False
        length, tag = struct.unpack(">I4s", chunk)
        if tag == b"acTL":
            return True
        if tag in (b"IDAT", b"IEND") or length > 0x7FFFFFFF:
            return False
        if not _skip(fp, length + 4, end):  # data + CRC
            return False
    return False


def sniff_animated(fp: BinaryIO) -> bool:
    """Whether the container read from ``fp`` holds more than one frame; never raises."""
    try:
        end = fp.seek(0, 2)
        fp.seek(0)
        magic = fp.read(4)
        fp.seek(0)
        if magic == b"GIF8":
            return _gif_is_animated(fp, end)
        if magic == b"RIFF":
            return _webp_is_animated(fp, end)
        if magic == b"\x89PNG":
            return _png_is_animated(fp, end)
    except (OSError, ValueError, struct.error):
        return False
    return False


def detect_animated_file(path: str | Path) -> bool | None:
    """Return whether the file is an animated image, or ``None`` when it cannot be opened (unknown)."""
    try:
        with open(path, "rb", buffering=_READ_BUFFER) as fp:
            return sniff_animated(fp)
    except OSError:
        return None
