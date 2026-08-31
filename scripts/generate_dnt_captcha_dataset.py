#!/usr/bin/env python3
"""
Generate synthetic training dataset for DNT Captcha (Persian number words).
Replicates DNT Captcha rendering: Persian text, wave distortion, background noise.
"""

import os
import random
import math
import csv
import numpy as np
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATASET_DIR = Path(os.getenv("DATASET_DIR", str(PROJECT_ROOT / "datasets" / "dnt_captcha")))
IMAGES_DIR = DATASET_DIR / "images"
LABELS_FILE = DATASET_DIR / "labels.csv"

os.makedirs(IMAGES_DIR, exist_ok=True)

ones = ["", "یک", "دو", "سه", "چهار", "پنج", "شش", "هفت", "هشت", "نه"]
teens = ["ده", "یازده", "دوازده", "سیزده", "چهارده", "پانزده", "شانزده", "هفده", "هجده", "نوزده"]
tens = ["", "", "بیست", "سی", "چهل", "پنجاه", "شصت", "هفتاد", "هشتاد", "نود"]
hundreds_variants = [
    ["", "صد", "دویست", "سیصد", "چهارصد", "پانصد", "ششصد", "هفتصد", "هشتصد", "نهصد"],
    ["", "یکصد", "دویست", "سیصد", "چهارصد", "پانصد", "ششصد", "هفتصد", "هشتصد", "نهصد"],
]

def num_to_persian_words(n: int, use_yek_sad: bool = True) -> str:
    h_list = hundreds_variants[1] if use_yek_sad else hundreds_variants[0]
    
    def parse_under_1000(val: int) -> str:
        if val == 0:
            return ""
        parts = []
        h = val // 100
        rem = val % 100
        if h > 0:
            parts.append(h_list[h])
        if rem > 0:
            if 10 <= rem < 20:
                parts.append(teens[rem - 10])
            else:
                t = rem // 10
                u = rem % 10
                if t > 0:
                    parts.append(tens[t])
                if u > 0:
                    parts.append(ones[u])
        return " و ".join(parts)

    thousands = n // 1000
    remainder = n % 1000
    parts = []
    if thousands > 0:
        parts.append(parse_under_1000(thousands) + " هزار")
    if remainder > 0:
        parts.append(parse_under_1000(remainder))
    return " و ".join(parts)


def apply_wave_distortion(img: Image.Image, amplitude: float = 4.0, period: float = 60.0) -> Image.Image:
    """Apply vertical sine wave distortion matching DNT Captcha."""
    arr = np.array(img)
    h, w = arr.shape[:2]
    out = np.full_like(arr, 255)
    
    phase = random.uniform(0, 2 * math.pi)
    amp = random.uniform(amplitude * 0.7, amplitude * 1.3)
    per = random.uniform(period * 0.8, period * 1.2)
    
    for x in range(w):
        offset = int(amp * math.sin(2 * math.pi * x / per + phase))
        for y in range(h):
            src_y = y - offset
            if 0 <= src_y < h:
                out[y, x] = arr[src_y, x]
                
    return Image.fromarray(out)


def get_available_fonts():
    # Common system Persian / Arabic TrueType fonts
    font_candidates = [
        "/tmp/fonts/Tahoma.ttf",
        "/tmp/fonts/Arial.ttf",
        "/usr/share/fonts/truetype/custom/Tahoma.ttf",
        "/usr/share/fonts/truetype/custom/Arial.ttf",
        "/System/Library/Fonts/Supplemental/Tahoma.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/Library/Fonts/Tahoma.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ]
    valid = []
    for fc in font_candidates:
        if os.path.exists(fc):
            valid.append(fc)
    return valid


def render_captcha_image(text: str, font_paths: list[str], target_w: int = 240, target_h: int = 36) -> Image.Image:
    # 1. Base canvas
    img = Image.new("L", (target_w + 40, target_h + 20), color=255)
    draw = ImageDraw.Draw(img)
    
    font_size = random.randint(13, 16)
    font = None
    if font_paths:
        fp = random.choice(font_paths)
        try:
            font = ImageFont.truetype(fp, font_size)
        except Exception:
            font = ImageFont.load_default()
    else:
        font = ImageFont.load_default()

    # Draw background wave band
    band_color = random.randint(215, 235)
    draw.rectangle([0, 6, target_w + 40, target_h + 14], fill=band_color)

    # Draw text in black/dark gray
    text_color = random.randint(10, 45)
    
    # Measure text bounding box
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    
    start_x = max(5, (target_w + 40 - text_w) // 2 + random.randint(-5, 5))
    start_y = max(4, (target_h + 20 - text_h) // 2 + random.randint(-2, 2))
    
    draw.text((start_x, start_y), text, font=font, fill=text_color)
    
    # 2. Apply sine wave distortion
    distorted = apply_wave_distortion(img, amplitude=random.uniform(3.0, 5.5), period=random.uniform(50.0, 80.0))
    
    # 3. Crop / resize to target size
    cropped = distorted.crop((20, 10, target_w + 20, target_h + 10))
    return cropped


def generate_dataset(count: int = 8000):
    print(f"Generating {count} synthetic DNT Captchas...")
    font_paths = get_available_fonts()
    print(f"Available fonts: {font_paths}")

    records = []
    
    for i in range(1, count + 1):
        # 80% 6-digit (100,000 to 999,999), 20% 5-digit (10,000 to 99,999)
        if random.random() < 0.85:
            num = random.randint(100000, 999999)
        else:
            num = random.randint(10000, 99999)
            
        use_yek_sad = random.random() < 0.75
        words = num_to_persian_words(num, use_yek_sad=use_yek_sad)
        
        img = render_captcha_image(words, font_paths)
        filename = f"syn_captcha_{i:05d}.png"
        filepath = IMAGES_DIR / filename
        img.save(filepath)
        
        records.append({
            "filename": filename,
            "number": str(num),
            "words": words,
        })
        
        if i % 1000 == 0 or i == count:
            print(f"  Generated {i}/{count} images...")

    with open(LABELS_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["filename", "number", "words"])
        writer.writeheader()
        writer.writerows(records)
    print(f"✅ Generated {len(records)} synthetic samples with labels saved to {LABELS_FILE}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=8000)
    args = parser.parse_args()
    generate_dataset(args.count)
