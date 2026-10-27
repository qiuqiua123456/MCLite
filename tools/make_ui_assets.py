"""把 ComfyUI 出的原图裁成界面里直接能用的尺寸。

Tk 只能读 PNG，而且运行期不做缩放/合成（不引入 Pillow），所以圆角、
左侧压暗、右侧淡出这些都在这里一次性烤进图里。

用法：python tools/make_ui_assets.py
输入：assets/ui/raw/*.png    输出：assets/ui/*.png
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "assets" / "ui" / "raw"
OUT = ROOT / "assets" / "ui"

PAGE_BG = (237, 244, 253)          # theme["pcl"]["bg"]
CARD_BG = (255, 255, 255)

HERO_W, HERO_H = 820, 104
HERO_RADIUS = 14


def cover(img: Image.Image, size: tuple[int, int]) -> Image.Image:
    """按 cover 方式裁剪缩放。"""
    tw, th = size
    sw, sh = img.size
    scale = max(tw / sw, th / sh)
    nw, nh = max(tw, round(sw * scale)), max(th, round(sh * scale))
    resized = img.resize((nw, nh), Image.LANCZOS)
    left = (nw - tw) // 2
    top = int((nh - th) * 0.42)
    return resized.crop((left, top, left + tw, top + th))


def scrim(img: Image.Image, color: tuple[int, int, int],
          strength: float = 0.94, solid_fraction: float = 0.24,
          fade_fraction: float = 0.42) -> Image.Image:
    """左侧压一层蓝色渐变，保证白字读得清。

    solid_fraction 范围内几乎不透明，往右 fade_fraction 宽度内衰减到 0。
    """
    w, h = img.size
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    solid = max(1, int(w * solid_fraction))
    fade = max(1, int(w * fade_fraction))
    top = int(255 * strength)
    for x in range(min(w, solid + fade)):
        if x < solid:
            a = top
        else:
            t = (x - solid) / fade
            a = int(top * (1 - t) ** 1.7)
        if a > 0:
            draw.line([(x, 0), (x, h)], fill=color + (a,))
    soft = overlay.filter(ImageFilter.GaussianBlur(6))
    out = img.convert("RGBA")
    out.alpha_composite(soft)
    return out.convert("RGB")


def fade_right(img: Image.Image, color: tuple[int, int, int], span: int = 220) -> Image.Image:
    """右侧淡出到页面底色：窗口比图更宽时不会露出硬边。"""
    w, h = img.size
    span = min(span, w)
    out = img.convert("RGBA")
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    for i in range(span):
        a = int(255 * (i / span) ** 1.6)
        draw.line([(w - span + i, 0), (w - span + i, h)], fill=color + (a,))
    out.alpha_composite(overlay)
    return out.convert("RGB")


def rounded(img: Image.Image, radius: int, fill: tuple[int, int, int]) -> Image.Image:
    """四角涂成页面底色，视觉上就是圆角。"""
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (0, 0, img.size[0] - 1, img.size[1] - 1), radius=radius, fill=255)
    bg = Image.new("RGB", img.size, fill)
    bg.paste(img, (0, 0), mask)
    return bg


def hero() -> None:
    src = Image.open(RAW / "hero-home.png").convert("RGB")
    canvas = cover(src, (HERO_W, HERO_H))
    canvas = scrim(canvas, (7, 52, 108), 0.94, 0.24, 0.42)
    canvas = fade_right(canvas, PAGE_BG, 340)
    canvas = rounded(canvas, HERO_RADIUS, PAGE_BG)
    canvas.save(OUT / "hero.png", optimize=True)
    print("hero.png", canvas.size)


def empty(name: str, size: int, out: str) -> None:
    src = Image.open(RAW / f"{name}.png").convert("RGB")
    img = Image.new("RGB", src.size, CARD_BG)   # 白底插画放在白卡片上
    img.paste(src, (0, 0))
    img = img.resize((size, size), Image.LANCZOS)
    img.save(OUT / out, optimize=True)
    print(out, img.size)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    hero()
    empty("empty-versions", 168, "empty-versions.png")
    empty("empty-mods", 152, "empty-mods.png")
    empty("empty-search", 148, "empty-search.png")


if __name__ == "__main__":
    main()
