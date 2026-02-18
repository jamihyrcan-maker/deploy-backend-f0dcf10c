from __future__ import annotations

import json
import os
import time
import urllib.request
from typing import Any, Dict, List, Tuple

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont


BASE = os.getenv("SIM_VIDEO_BASE", "http://127.0.0.1:9001").rstrip("/")
OUT_MP4 = os.getenv("SIM_VIDEO_OUT", "simulator/sim_test.mp4")
SECONDS = int(os.getenv("SIM_VIDEO_SECONDS", "30"))
FPS = int(os.getenv("SIM_VIDEO_FPS", "10"))
WIDTH = int(os.getenv("SIM_VIDEO_WIDTH", "960"))
HEIGHT = int(os.getenv("SIM_VIDEO_HEIGHT", "540"))
MAX_QUEUE = int(os.getenv("SIM_VIDEO_MAX_QUEUE", "20"))


def fetch_json(path: str) -> Dict[str, Any]:
    url = BASE + path
    with urllib.request.urlopen(url, timeout=10) as resp:
        raw = resp.read().decode("utf-8", "ignore")
    return json.loads(raw)


def color_for_kind(kind: str) -> Tuple[int, int, int]:
    if kind == "KITCHEN":
        return (217, 72, 15)
    if kind == "OPERATOR":
        return (240, 140, 0)
    if kind == "CHARGING":
        return (47, 158, 68)
    return (42, 111, 219)


def draw_frame(state: Dict[str, Any], queue: Dict[str, Any]) -> np.ndarray:
    map_obj = state.get("map", {})
    w = float(map_obj.get("width", 20))
    h = float(map_obj.get("height", 12))

    img = Image.new("RGB", (WIDTH, HEIGHT), (247, 247, 247))
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default()

    # layout
    map_w = int(WIDTH * 0.72)
    map_h = HEIGHT - 20
    map_x0 = 10
    map_y0 = 10

    # background
    draw.rectangle([map_x0, map_y0, map_x0 + map_w, map_y0 + map_h], outline=(50, 50, 50), width=2)

    # grid
    for gx in range(int(w) + 1):
        x = map_x0 + int(gx * map_w / w)
        draw.line([x, map_y0, x, map_y0 + map_h], fill=(220, 220, 220))
    for gy in range(int(h) + 1):
        y = map_y0 + int(gy * map_h / h)
        draw.line([map_x0, y, map_x0 + map_w, y], fill=(220, 220, 220))

    # POIs
    for p in state.get("pois", []):
        coord = p.get("coordinate") or [0, 0]
        px = map_x0 + int(float(coord[0]) * map_w / w)
        py = map_y0 + int(float(coord[1]) * map_h / h)
        c = color_for_kind(p.get("kind", "TABLE"))
        draw.ellipse([px - 5, py - 5, px + 5, py + 5], fill=c, outline=(0, 0, 0))
        draw.text((px + 6, py - 8), p.get("name", ""), fill=(0, 0, 0), font=font)

    # Robots
    for r in state.get("robots", []):
        rx = map_x0 + int(float(r.get("x", 0)) * map_w / w)
        ry = map_y0 + int(float(r.get("y", 0)) * map_h / h)
        draw.ellipse([rx - 6, ry - 6, rx + 6, ry + 6], fill=(0, 0, 0))
        label = f"{r.get('robotId')} {r.get('battery', 0)}%"
        draw.text((rx + 8, ry + 8), label, fill=(0, 0, 0), font=font)

    # Queue panel
    qx0 = map_x0 + map_w + 10
    qy0 = map_y0
    draw.rectangle([qx0, qy0, WIDTH - 10, map_y0 + map_h], outline=(50, 50, 50), width=2)
    draw.text((qx0 + 8, qy0 + 6), "Queue (top items)", fill=(0, 0, 0), font=font)

    stats = queue.get("stats")
    if stats:
        draw.text((qx0 + 8, qy0 + 22), f"Stats: {stats}", fill=(0, 0, 0), font=font)

    items = queue.get("queue", []) if queue.get("ok") else []
    y = qy0 + 40
    for item in items[:MAX_QUEUE]:
        line = f"#{item.get('task_id')} {item.get('title')} ({item.get('task_type')})"
        draw.text((qx0 + 8, y), line, fill=(0, 0, 0), font=font)
        y += 14

    draw.text((qx0 + 8, map_y0 + map_h - 16), time.strftime("%Y-%m-%d %H:%M:%S"), fill=(0, 0, 0), font=font)

    return cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)


def main() -> int:
    total_frames = SECONDS * FPS
    writer = cv2.VideoWriter(
        OUT_MP4,
        cv2.VideoWriter_fourcc(*"mp4v"),
        FPS,
        (WIDTH, HEIGHT),
    )

    for _ in range(total_frames):
        state = fetch_json("/sim/state")
        queue = fetch_json("/sim/queue")
        frame = draw_frame(state, queue)
        writer.write(frame)
        time.sleep(1.0 / FPS)

    writer.release()
    print("Saved:", OUT_MP4)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
