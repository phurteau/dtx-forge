"""Generate the DTXScribe app icon: a falling-note-lane chart motif (the DTX gameplay
chart) in the app's signature accent green. Renders at 4x for clean anti-aliasing, then
writes a multi-resolution .ico plus a browser favicon.

Run from anywhere:  python tools/make_icon.py
Outputs into the repo's assets/:
  assets/icon.ico       (16/24/32/48/64/128/256 - the exe + window icon)
  assets/favicon.png     (32px - the browser-UI favicon)
  assets/icon-256.png    (preview)

Requires Pillow (pip install pillow).
"""
import os
import struct
import io
from PIL import Image, ImageDraw

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(REPO, "assets")
os.makedirs(ASSETS, exist_ok=True)

S = 256          # target size
SS = 4           # supersample factor

ACC   = (3, 120, 0)       # accent green (border/lane tint)
ACC2  = (18, 210, 10)     # brighter hero green for chips
BRITE = (120, 255, 80)    # judgement-line glow green
BG1   = (13, 22, 14)      # near-black, slight green (top)
BG2   = (3, 6, 4)         # near-black (bottom)
WHITE = (242, 250, 242)


def render(size_ss):
    """Render the icon at size_ss pixels (coords are authored in a 256-unit space)."""
    img = Image.new("RGBA", (size_ss, size_ss), (0, 0, 0, 0))
    u = size_ss / 256.0

    # rounded tile with a vertical dark gradient
    tile = Image.new("RGBA", (size_ss, size_ss), (0, 0, 0, 0))
    td = ImageDraw.Draw(tile)
    for y in range(size_ss):
        f = y / size_ss
        c = tuple(int(BG1[i] + (BG2[i] - BG1[i]) * f) for i in range(3)) + (255,)
        td.line([(0, y), (size_ss, y)], fill=c)
    mask = Image.new("L", (size_ss, size_ss), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, size_ss - 1, size_ss - 1],
                                           radius=int(54 * u), fill=255)
    img.paste(tile, (0, 0), mask)
    d = ImageDraw.Draw(img)

    # inner accent border ring
    d.rounded_rectangle([int(6 * u), int(6 * u), int(250 * u), int(250 * u)],
                        radius=int(50 * u), outline=ACC, width=max(1, int(4 * u)))

    # three note lanes (chunky, dim)
    lane_xs = [int(74 * u), int(128 * u), int(182 * u)]
    lane_w = int(40 * u)
    top, bot = int(34 * u), int(222 * u)
    for lx in lane_xs:
        d.rounded_rectangle([lx - lane_w // 2, top, lx + lane_w // 2, bot],
                            radius=int(12 * u), fill=(255, 255, 255, 20))

    # bold, sparse, brand-green note chips at staggered heights
    chip_h = int(26 * u)
    chip_w = int(38 * u)
    chips = [
        (0, int(66 * u), ACC2), (0, int(126 * u), ACC2),
        (1, int(52 * u), WHITE), (1, int(112 * u), ACC2),
        (2, int(88 * u), ACC2), (2, int(148 * u), WHITE),
    ]
    for li, yc, col in chips:
        lx = lane_xs[li]
        d.rounded_rectangle([lx - chip_w // 2, yc - chip_h // 2,
                             lx + chip_w // 2, yc + chip_h // 2],
                            radius=int(7 * u), fill=col)

    # bright judgement line low in the frame (thick, layered glow)
    jy = int(190 * u)
    for gw, ga in ((int(16 * u), 45), (int(9 * u), 90)):
        d.rectangle([int(50 * u), jy - gw, int(206 * u), jy + gw],
                    fill=(BRITE[0], BRITE[1], BRITE[2], ga))
    d.rectangle([int(48 * u), jy - int(3 * u), int(208 * u), jy + int(3 * u)], fill=BRITE)
    return img


def main():
    big = render(S * SS).resize((S, S), Image.LANCZOS)
    big.save(os.path.join(ASSETS, "icon-256.png"))
    big.resize((32, 32), Image.LANCZOS).save(os.path.join(ASSETS, "favicon.png"))

    # multi-res .ico - pack per-size crisp PNG frames manually (Pillow's ICO API can't
    # embed independent frames). Modern .ico allows each frame to be a PNG blob.
    sizes = [16, 24, 32, 48, 64, 128, 256]
    blobs = []
    for sz in sizes:
        fr = render(sz * SS).resize((sz, sz), Image.LANCZOS)
        b = io.BytesIO(); fr.save(b, format="PNG"); blobs.append(b.getvalue())
    ico = io.BytesIO()
    ico.write(struct.pack("<HHH", 0, 1, len(sizes)))
    offset = 6 + 16 * len(sizes)
    for sz, blob in zip(sizes, blobs):
        w = h = 0 if sz >= 256 else sz          # 256 is encoded as 0
        ico.write(struct.pack("<BBBBHHII", w, h, 0, 0, 1, 32, len(blob), offset))
        offset += len(blob)
    for blob in blobs:
        ico.write(blob)
    with open(os.path.join(ASSETS, "icon.ico"), "wb") as f:
        f.write(ico.getvalue())

    print("wrote assets/icon.ico, assets/favicon.png, assets/icon-256.png")


if __name__ == "__main__":
    main()
