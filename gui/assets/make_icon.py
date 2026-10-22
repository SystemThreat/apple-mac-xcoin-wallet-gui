#!/usr/bin/env python3
"""Draw the app icon from the official xCoin mark: the black Ӿ in an acid lime circle (xcoin.svg of
xcoinproject.com, same 1024-unit geometry), with a thin black rim so it holds on any wallpaper.

    python3 gui/assets/make_icon.py      (no dependencies)

Writes xid-wallet.png (512 px) and xid-wallet.ico (16 to 256 px, each size drawn on its own, not scaled
down from one bitmap) next to this file.
"""
import struct, zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
LIME, INK = (0xC7, 0xFF, 0x2E), (0x0B, 0x0C, 0x08)
R, RIM = 480, 32                       # circle radius and rim width, in the SVG's 1024 units
GLYPH = [(763.030, 782.000), (631.529, 782.000), (511.816, 595.247), (391.734, 782.000), (260.970, 782.000),
         (422.675, 535.206), (322.484, 535.206), (322.484, 466.693), (423.780, 466.693), (278.282, 242.000),
         (405.731, 242.000), (514.026, 415.492), (620.111, 242.000), (746.454, 242.000), (602.430, 466.693),
         (702.252, 466.693), (702.252, 535.206), (599.115, 535.206)]
EDGES = list(zip(GLYPH, GLYPH[1:] + GLYPH[:1]))
ICO_SIZES = (16, 20, 24, 32, 40, 48, 64, 96, 128, 256)


def spans(y):
    """The glyph's inside on the horizontal line at y, as (x0, x1) pairs (even-odd rule)."""
    xs = sorted(x0 + (y - y0) * (x1 - x0) / (y1 - y0) for (x0, y0), (x1, y1) in EDGES if (y0 <= y) != (y1 <= y))
    return list(zip(xs[0::2], xs[1::2]))


def render(n):
    """n x n RGBA rows (bytes), each pixel the average of ss x ss samples."""
    ss = 8 if n <= 64 else 4
    unit = 1024 / (n * ss)
    rows = []
    for py in range(n):
        acc = [[0.0, 0.0, 0.0, 0] for _ in range(n)]          # premultiplied r, g, b and covered samples
        for sy in range(ss):
            y = (py * ss + sy + 0.5) * unit
            inside, dy2 = spans(y), (y - 512) ** 2
            for px in range(n):
                a = acc[px]
                for sx in range(ss):
                    x = (px * ss + sx + 0.5) * unit
                    d2 = (x - 512) ** 2 + dy2
                    if d2 > R * R: continue
                    c = INK if d2 > (R - RIM) ** 2 or any(x0 <= x < x1 for x0, x1 in inside) else LIME
                    a[0] += c[0]; a[1] += c[1]; a[2] += c[2]; a[3] += 1
        row = bytearray()
        for r, g, b, k in acc:
            row += bytes((round(r / k), round(g / k), round(b / k), round(255 * k / ss / ss))) if k else bytes(4)
        rows.append(bytes(row))
    return rows


def png(rows):
    n = len(rows)
    chunk = lambda tag, data: struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", n, n, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"".join(b"\0" + r for r in rows), 9)) + chunk(b"IEND", b""))


def dib(rows):
    """A classic 32-bit icon bitmap: BGRA bottom-up, then an empty AND mask (the alpha channel decides)."""
    n = len(rows)
    pixels = b"".join(bytes(v for i in range(0, len(r), 4) for v in (r[i + 2], r[i + 1], r[i], r[i + 3])) for r in reversed(rows))
    mask = bytes(((n + 31) // 32) * 4 * n)
    return struct.pack("<IiiHHIIiiII", 40, n, 2 * n, 1, 32, 0, len(pixels) + len(mask), 0, 0, 0, 0) + pixels + mask


def ico(images):
    """256 px as PNG, smaller sizes as bitmaps: the layout every Windows shell and .NET icon loader reads."""
    head = struct.pack("<HHH", 0, 1, len(images))
    offset, entries, blobs = len(head) + 16 * len(images), b"", b""
    for n, rows in images:
        blob = png(rows) if n >= 256 else dib(rows)
        entries += struct.pack("<BBBBHHII", n % 256, n % 256, 0, 0, 1, 32, len(blob), offset)
        blobs += blob; offset += len(blob)
    return head + entries + blobs


if __name__ == "__main__":
    (HERE / "xid-wallet.png").write_bytes(png(render(512)))
    (HERE / "xid-wallet.ico").write_bytes(ico([(n, render(n)) for n in ICO_SIZES]))
    print("wrote", HERE / "xid-wallet.png", "and", HERE / "xid-wallet.ico")
