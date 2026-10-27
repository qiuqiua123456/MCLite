"""生成应用图标 assets/icon.ico（无需外部素材）。"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def rounded(size: int, radius: int, color, bg=(0, 0, 0, 0)) -> Image.Image:
    img = Image.new("RGBA", (size, size), bg)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, size - 1, size - 1), radius=radius, fill=color)
    return img


def main() -> int:
    out = Path(__file__).resolve().parent.parent / "assets" / "icon.ico"
    out.parent.mkdir(parents=True, exist_ok=True)

    size = 256
    img = rounded(size, 56, (59, 142, 234, 255))

    # 白色 M
    d = ImageDraw.Draw(img)
    font = None
    for name in ("arialbd.ttf", "seguibl.ttf", "segoeuib.ttf"):
        try:
            font = ImageFont.truetype(name, 168)
            break
        except OSError:
            continue
    if font is None:
        font = ImageFont.load_default()
    text = "M"
    box = d.textbbox((0, 0), text, font=font)
    tw, th = box[2] - box[0], box[3] - box[1]
    d.text(((size - tw) / 2 - box[0], (size - th) / 2 - box[1]), text,
           font=font, fill=(255, 255, 255, 255))

    sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    img.save(out, format="ICO", sizes=sizes)
    print("saved ->", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
