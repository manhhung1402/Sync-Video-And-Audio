"""Generate a Windows ICO with uncompressed DIB entries for Tk and Explorer."""

from __future__ import annotations

import struct
from pathlib import Path

from PIL import Image


SIZES = (16, 24, 32, 48, 64, 128, 256)


def dib_entry(image: Image.Image, size: int) -> bytes:
    rgba = image.resize((size, size), Image.Resampling.LANCZOS).convert("RGBA")
    pixels = rgba.load()
    xor_rows = []
    and_rows = []
    row_bytes = ((size + 31) // 32) * 4
    for y in range(size - 1, -1, -1):
        xor_rows.append(
            b"".join(bytes((pixels[x, y][2], pixels[x, y][1], pixels[x, y][0], pixels[x, y][3])) for x in range(size))
        )
        mask = bytearray(row_bytes)
        for x in range(size):
            if pixels[x, y][3] < 128:
                mask[x // 8] |= 1 << (7 - x % 8)
        and_rows.append(bytes(mask))
    header = struct.pack(
        "<IiiHHIIiiII",
        40,
        size,
        size * 2,
        1,
        32,
        0,
        size * size * 4,
        0,
        0,
        0,
        0,
    )
    return header + b"".join(xor_rows) + b"".join(and_rows)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    source = Image.open(root / "assets" / "logo.png").convert("RGBA")
    background = Image.new("RGBA", source.size, (25, 211, 197, 255))
    source = Image.alpha_composite(background, source)
    source.resize((64, 64), Image.Resampling.LANCZOS).save(root / "assets" / "logo-taskbar.png")
    entries = [dib_entry(source, size) for size in SIZES]
    directory_size = 6 + 16 * len(entries)
    offset = directory_size
    directory = [struct.pack("<HHH", 0, 1, len(entries))]
    payload = []
    for size, entry in zip(SIZES, entries, strict=True):
        directory.append(
            struct.pack(
                "<BBBBHHII",
                size if size < 256 else 0,
                size if size < 256 else 0,
                0,
                0,
                1,
                32,
                len(entry),
                offset,
            )
        )
        payload.append(entry)
        offset += len(entry)
    (root / "assets" / "logo.ico").write_bytes(b"".join(directory + payload))


if __name__ == "__main__":
    main()
