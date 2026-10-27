"""用本机 ComfyUI（Qwen-Image 2.1 int8）为 MCLite 1.5 生成界面素材。

用法：python tools/gen_ui.py tools/ui_jobs.json
输出：assets/ui/<name>.png
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.parse
import urllib.request

BASE = "http://127.0.0.1:8188"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "assets", "ui")


def api(path, data=None):
    url = BASE + path
    if data is None:
        with urllib.request.urlopen(url, timeout=120) as r:
            return json.loads(r.read())
    req = urllib.request.Request(url, data=json.dumps(data).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())


def build(prompt, negative, width, height, steps=25, seed=0, cfg=1.0, prefix="mclite"):
    return {
        "451": {"class_type": "UNETLoader", "inputs": {
            "unet_name": "qwen_image_2.1_int8_convrot.safetensors", "weight_dtype": "default"}},
        "480": {"class_type": "QwenImage21Cache", "inputs": {
            "model": ["451", 0], "device": "auto", "dtype": "default"}},
        "453": {"class_type": "CLIPLoader", "inputs": {
            "clip_name": "qwen3vl_8b_int8_convrot.safetensors", "type": "qwen_image", "device": "default"}},
        "454": {"class_type": "VAELoader", "inputs": {"vae_name": "qwen_image_2.1_vae_bf16.safetensors"}},
        "452": {"class_type": "TextEncodeQwenImage21", "inputs": {
            "clip": ["453", 0], "prompt": prompt, "negative_prompt": negative,
            "resolution": 1024, "vae": ["454", 0]}},
        "456": {"class_type": "EmptyLatentImage", "inputs": {"width": width, "height": height, "batch_size": 1}},
        "458": {"class_type": "KSampler", "inputs": {
            "model": ["480", 0], "positive": ["452", 0], "negative": ["452", 1],
            "latent_image": ["456", 0], "seed": seed, "steps": steps, "cfg": cfg,
            "sampler_name": "euler", "scheduler": "simple", "denoise": 1.0}},
        "457": {"class_type": "VAEDecode", "inputs": {"samples": ["458", 0], "vae": ["454", 0]}},
        "461": {"class_type": "SaveImage", "inputs": {"images": ["457", 0], "filename_prefix": prefix}},
    }


def run(job, name):
    os.makedirs(OUT, exist_ok=True)
    t0 = time.time()
    pid = api("/prompt", {"prompt": job, "client_id": "mclite-ui"})["prompt_id"]
    print("queued", name, pid, flush=True)
    while True:
        hist = api("/history/" + pid)
        if pid in hist:
            break
        time.sleep(3)
    dest = None
    for out in hist[pid]["outputs"].values():
        for img in out.get("images", []):
            q = urllib.parse.urlencode({"filename": img["filename"],
                                        "subfolder": img.get("subfolder", ""),
                                        "type": img["type"]})
            with urllib.request.urlopen(BASE + "/view?" + q) as r:
                data = r.read()
            dest = os.path.join(OUT, name + ".png")
            with open(dest, "wb") as fh:
                fh.write(data)
    print("done %s in %.0fs -> %s" % (name, time.time() - t0, dest), flush=True)
    return dest


if __name__ == "__main__":
    spec = json.load(open(sys.argv[1], encoding="utf-8"))
    for item in spec:
        run(build(item["prompt"], item.get("negative", "text, watermark, letters, logo, signature"),
                  item["width"], item["height"], item.get("steps", 25),
                  item.get("seed", 42), item.get("cfg", 1.0), "mclite-ui/" + item["name"]),
            item["name"])
