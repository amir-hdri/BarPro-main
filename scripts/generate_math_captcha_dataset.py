#!/usr/bin/env python3
"""Generate 2,000 synthetic math captcha samples matching UTCMS visual style.

Supports 1-digit and 2-digit operands with addition (+) and subtraction (-).
Outputs:
  - datasets/math_captcha/images/captcha_XXXX.png (2000 images)
  - datasets/math_captcha/labels.json
  - datasets/math_captcha/labels.csv
  - datasets/math_captcha/math_captchas_2000.tar.gz (single archive)
"""

from __future__ import annotations

import csv
import json
import math
import os
import random
import tarfile
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_ROOT / "datasets" / "math_captcha"
IMAGES_DIR = OUTPUT_DIR / "images"

# Primary fonts matching UTCMS captcha typography
FONT_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Times New Roman Bold Italic.ttf",
    "/System/Library/Fonts/Supplemental/Times New Roman Bold.ttf",
    "/System/Library/Fonts/Supplemental/Georgia Bold Italic.ttf",
    "/System/Library/Fonts/Supplemental/Georgia Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold Italic.ttf",
    "/System/Library/Fonts/Supplemental/Trebuchet MS Bold Italic.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif-BoldItalic.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]

AVAILABLE_FONTS = [f for f in FONT_CANDIDATES if os.path.exists(f)]
if not AVAILABLE_FONTS:
    # Fallback to system search
    for p in ["/System/Library/Fonts/Supplemental", "/Library/Fonts", "/usr/share/fonts"]:
        if os.path.isdir(p):
            for fname in os.listdir(p):
                if any(k in fname.lower() for k in ["times", "georgia", "arial", "dejavu"]) and fname.endswith((".ttf", ".otf")):
                    AVAILABLE_FONTS.append(os.path.join(p, fname))


def _draw_spline_or_line(draw: ImageDraw.ImageDraw, width: int = 150, height: int = 50) -> None:
    """Draw a thin curved or straight interference line across the captcha."""
    color = (random.randint(90, 180), random.randint(90, 180), random.randint(90, 180))
    if random.random() < 0.6:
        # Wavy sine/bezier curve
        points = []
        y_start = random.randint(5, height - 10)
        freq = random.uniform(0.02, 0.05)
        amp = random.uniform(3, 8)
        phase = random.uniform(0, math.pi * 2)
        for x in range(0, width, 4):
            y = int(y_start + amp * math.sin(freq * x + phase))
            y = max(2, min(height - 3, y))
            points.append((x, y))
        for i in range(len(points) - 1):
            draw.line([points[i], points[i + 1]], fill=color, width=1)
    else:
        # Straight / diagonal line
        start = (random.randint(0, 30), random.randint(5, height - 5))
        end = (random.randint(width - 35, width), random.randint(5, height - 5))
        draw.line([start, end], fill=color, width=1)


def generate_single_captcha(index: int) -> dict:
    """Generate one math captcha image and its metadata."""
    op = random.choice(["+", "-"])
    if op == "+":
        # Variations: 1d+1d (25%), 2d+1d (35%), 1d+2d (15%), 2d+2d (25%)
        pattern = random.choices(["1d+1d", "2d+1d", "1d+2d", "2d+2d"], weights=[0.25, 0.35, 0.15, 0.25])[0]
        if pattern == "1d+1d":
            left = random.randint(0, 9)
            right = random.randint(0, 9)
        elif pattern == "2d+1d":
            left = random.randint(10, 99)
            right = random.randint(0, 9)
        elif pattern == "1d+2d":
            left = random.randint(0, 9)
            right = random.randint(10, 99)
        else:
            left = random.randint(10, 50)
            right = random.randint(10, 50)
        answer = left + right
        expr = f"{left} + {right}"
    else:
        # Subtraction: always non-negative answer
        pattern = random.choices(["1d-1d", "2d-1d", "2d-2d"], weights=[0.3, 0.5, 0.2])[0]
        if pattern == "1d-1d":
            left = random.randint(1, 9)
            right = random.randint(0, left)
        elif pattern == "2d-1d":
            left = random.randint(10, 99)
            right = random.randint(0, 9)
        else:
            left = random.randint(20, 99)
            right = random.randint(10, left)
        answer = left - right
        # In UTCMS, subtraction appears as "54 - 9" or "54-9"
        sep = " - " if random.random() < 0.8 else "-"
        expr = f"{left}{sep}{right}"

    width, height = 150, 50
    img = Image.new("RGB", (width, height), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)

    # Typography
    font_path = random.choice(AVAILABLE_FONTS) if AVAILABLE_FONTS else None
    font_size = random.randint(26, 30)
    try:
        font = ImageFont.truetype(font_path, font_size) if font_path else ImageFont.load_default()
    except Exception:
        font = ImageFont.load_default()

    # Calculate text bounding box to center horizontally
    bbox = draw.textbbox((0, 0), expr, font=font)
    t_width = bbox[2] - bbox[0]
    t_height = bbox[3] - bbox[1]

    # Jitter position
    x_offset = max(5, (width - t_width) // 2 + random.randint(-6, 6))
    y_offset = max(4, (height - t_height) // 2 + random.randint(-4, 4))

    # Text color: dark / near-black
    text_color = (random.randint(0, 20), random.randint(0, 20), random.randint(0, 20))
    draw.text((x_offset, y_offset), expr, font=font, fill=text_color)

    # Draw 2-3 interference lines
    for _ in range(random.randint(2, 3)):
        _draw_spline_or_line(draw, width=width, height=height)

    # Convert to NumPy for noise and morphology
    arr = np.array(img)

    # Add salt and pepper noise
    num_pepper = random.randint(120, 250)
    for _ in range(num_pepper):
        ry = random.randint(0, height - 1)
        rx = random.randint(0, width - 1)
        arr[ry, rx] = [random.randint(0, 40), random.randint(0, 40), random.randint(0, 40)]

    num_salt = random.randint(40, 90)
    for _ in range(num_salt):
        ry = random.randint(0, height - 1)
        rx = random.randint(0, width - 1)
        arr[ry, rx] = [255, 255, 255]

    # Optional slight erosion or dilation
    if random.random() < 0.2:
        k = np.ones((2, 2), np.uint8)
        arr = cv2.erode(arr, k, iterations=1)

    result_img = Image.fromarray(arr)
    filename = f"captcha_{index:04d}.png"
    filepath = IMAGES_DIR / filename
    result_img.save(filepath, "PNG")

    return {
        "id": f"captcha_{index:04d}",
        "filename": filename,
        "expression": expr,
        "canonical_expression": f"{left} {op} {right}",
        "answer": str(answer),
        "operator": op,
        "left_operand": left,
        "right_operand": right,
        "font": Path(font_path).name if font_path else "default",
    }


def main():
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    count = 2000
    print(f"Generating {count} math captcha samples in {IMAGES_DIR}...")
    print(f"Available fonts ({len(AVAILABLE_FONTS)}): {[Path(f).name for f in AVAILABLE_FONTS[:5]]}")

    random.seed(42)
    np.random.seed(42)

    metadata = []
    for i in range(1, count + 1):
        item = generate_single_captcha(i)
        metadata.append(item)
        if i % 250 == 0:
            print(f"  Progress: {i}/{count} ({i * 100 // count}%)")

    # Save JSON labels
    json_path = OUTPUT_DIR / "labels.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)
    print(f"Saved JSON labels to {json_path}")

    # Save CSV labels
    csv_path = OUTPUT_DIR / "labels.csv"
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "id",
                "filename",
                "expression",
                "canonical_expression",
                "answer",
                "operator",
                "left_operand",
                "right_operand",
                "font",
            ],
        )
        writer.writeheader()
        writer.writerows(metadata)
    print(f"Saved CSV labels to {csv_path}")

    # Create single tar.gz archive
    archive_path = OUTPUT_DIR / "math_captchas_2000.tar.gz"
    print(f"Archiving dataset to {archive_path}...")
    with tarfile.open(archive_path, "w:gz") as tar:
        tar.add(IMAGES_DIR, arcname="images")
        tar.add(json_path, arcname="labels.json")
        tar.add(csv_path, arcname="labels.csv")

    archive_size_mb = archive_path.stat().st_size / (1024 * 1024)
    print(f"Dataset generation complete! Archive size: {archive_size_mb:.2f} MB")
    print(f"Archive path: {archive_path}")


if __name__ == "__main__":
    main()
