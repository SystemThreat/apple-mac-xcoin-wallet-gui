#!/usr/bin/env python3
"""Draw the macOS app icon: the official xCoin mark (the black Ӿ glyph) on an acid lime squircle, on Apple's icon
grid (1024 px canvas, 824 px body with continuous superellipse corners, soft shadow), then pack xid-wallet.icns.

    python3 gui/assets/make_mac_icon.py      (macOS: needs Google Chrome for drawing, iconutil and sips, which ship with macOS)

The glyph is the official xCoin mark's outline, in the 1024-unit geometry of xcoin.svg (xcoinproject.com).
"""
import math, subprocess, tempfile, shutil
from pathlib import Path
GLYPH = [(763.030, 782.000), (631.529, 782.000), (511.816, 595.247), (391.734, 782.000), (260.970, 782.000),
         (422.675, 535.206), (322.484, 535.206), (322.484, 466.693), (423.780, 466.693), (278.282, 242.000),
         (405.731, 242.000), (514.026, 415.492), (620.111, 242.000), (746.454, 242.000), (602.430, 466.693),
         (702.252, 466.693), (702.252, 535.206), (599.115, 535.206)]

HERE = Path(__file__).resolve().parent
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


def squircle(cx, cy, half, n=5.0, steps=720):
    """A superellipse |x|^n + |y|^n = half^n: the continuous corner of macOS icons."""
    pts = []
    for i in range(steps):
        t = 2 * math.pi * i / steps
        c, s = math.cos(t), math.sin(t)
        pts.append((cx + half * math.copysign(abs(c) ** (2 / n), c), cy + half * math.copysign(abs(s) ** (2 / n), s)))
    return "M" + " L".join(f"{x:.2f},{y:.2f}" for x, y in pts) + "Z"


def svg():
    body = squircle(512, 512, 412)                       # 824 px body, 100 px margin: Apple's grid
    scale, off = 0.78, 512 * (1 - 0.78)                  # the glyph, centred, at 78% of the canvas units
    glyph = "M" + " L".join(f"{off + x * scale:.2f},{off + y * scale:.2f}" for x, y in GLYPH) + "Z"
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1024" height="1024" viewBox="0 0 1024 1024">
  <defs>
    <linearGradient id="lime" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#d8ff5c"/><stop offset="1" stop-color="#b9f21a"/></linearGradient>
    <filter id="shadow" x="-20%" y="-20%" width="140%" height="140%"><feDropShadow dx="0" dy="10" stdDeviation="12" flood-color="#000" flood-opacity=".32"/></filter>
  </defs>
  <path d="{body}" fill="url(#lime)" filter="url(#shadow)"/>
  <path d="{body}" fill="none" stroke="#0b0c08" stroke-opacity=".18" stroke-width="3"/>
  <path d="{glyph}" fill="#0b0c08"/>
</svg>'''


def main():
    tmp = Path(tempfile.mkdtemp())
    try:
        (tmp / "icon.html").write_text(f'<html><body style="margin:0;background:transparent">{svg()}</body></html>')
        png = HERE / "xid-wallet-mac-1024.png"
        subprocess.run([CHROME, "--headless=new", "--hide-scrollbars", "--default-background-color=00000000",
                        "--window-size=1024,1024", f"--screenshot={png}", (tmp / "icon.html").as_uri()],
                       check=True, capture_output=True)
        iconset = tmp / "xid-wallet.iconset"; iconset.mkdir()
        for size in (16, 32, 128, 256, 512):
            for mul, suffix in ((1, ""), (2, "@2x")):
                px = size * mul
                subprocess.run(["sips", "-z", str(px), str(px), str(png), "--out", str(iconset / f"icon_{size}x{size}{suffix}.png")],
                               check=True, capture_output=True)
        subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(HERE / "xid-wallet.icns")], check=True)
        print("wrote", png.name, "and xid-wallet.icns")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
