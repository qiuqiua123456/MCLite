"""把截图的上半部分裁出来放大，确认页签行是否真的画出来了。"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

src = Path(sys.argv[1])
out = Path(sys.argv[2])
top = int(sys.argv[3]) if len(sys.argv) > 3 else 40
bottom = int(sys.argv[4]) if len(sys.argv) > 4 else 140

img = Image.open(src)
box = img.crop((0, top, img.width, bottom))
scale = 2
box = box.resize((box.width * scale, box.height * scale), Image.LANCZOS)

# 在顶部画一条参考刻度，方便换算原图坐标
from PIL import ImageDraw
d = ImageDraw.Draw(box)
for x in range(0, box.width, 100):
    d.line([(x, 0), (x, 8)], fill=(255, 0, 0))
    d.text((x + 3, 2), str(x // scale), fill=(255, 0, 0))

box.save(out)
print(f"saved -> {out}  ({box.width}x{box.height})  source band y={top}..{bottom}")
