#!/usr/bin/env python3
import csv
import sys
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.absolute()
DATASET_DIR = PROJECT_ROOT / "datasets" / "fuel_captcha"
IMAGES_DIR = DATASET_DIR / "images"
LABELS_FILE = DATASET_DIR / "labels.csv"
STATE_FILE = DATASET_DIR / ".last_reviewed_index"

ones = ["", "یک", "دو", "سه", "چهار", "پنج", "شش", "هفت", "هشت", "نه"]
teens = ["ده", "یازده", "دوازده", "سیزده", "چهارده", "پانزده", "شانزده", "هفده", "هجده", "نوزده"]
tens = ["", "", "بیست", "سی", "چهل", "پنجاه", "شصت", "هفتاد", "هشتاد", "نود"]
hundreds = ["", "صد", "دویست", "سیصد", "چهارصد", "پانصد", "ششصد", "هفتصد", "هشتصد", "نهصد"]

def parse_under_1000(n: int) -> str:
    if n == 0:
        return ""
    parts = []
    h = n // 100
    remainder = n % 100
    if h > 0:
        parts.append(hundreds[h])
    if remainder > 0:
        if 10 <= remainder < 20:
            parts.append(teens[remainder - 10])
        else:
            t = remainder // 10
            u = remainder % 10
            if t > 0:
                parts.append(tens[t])
            if u > 0:
                parts.append(ones[u])
    return " و ".join([p for p in parts if p])

def num_to_persian_words(num: int) -> str:
    if num == 0:
        return "صفر"
    parts = []
    thousands = num // 1000
    remainder = num % 1000
    if thousands > 0:
        parts.append(parse_under_1000(thousands) + " هزار")
    if remainder > 0:
        parts.append(parse_under_1000(remainder))
    return " و ".join(parts)

def main():
    if not LABELS_FILE.exists():
        print(f"❌ labels.csv not found at {LABELS_FILE}")
        return

    # Read current labels
    rows = []
    with open(LABELS_FILE, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)

    # Read last reviewed state
    last_reviewed = 0
    if STATE_FILE.exists():
        try:
            last_reviewed = int(STATE_FILE.read_text().strip())
        except ValueError:
            pass

    print("====================================================")
    print("      CAPTCHA LABEL CORRECTION TOOL (Interactive)   ")
    print("====================================================")
    print("Controls:")
    print("  - Type the correct digits (e.g. 38741) and press Enter.")
    print("  - Just press Enter to skip/keep current label.")
    print("  - Type 'q' and press Enter to save progress & exit.")
    print("====================================================\n")

    if last_reviewed > 0:
        print(f"🔄 Resuming from last progress: image #{last_reviewed + 1}\n")

    try:
        for i, row in enumerate(rows):
            # Skip reviewed images
            if i < last_reviewed:
                continue

            filename = row["filename"]
            curr_words = row["words"]
            curr_digits = row["digits"]
            img_path = IMAGES_DIR / filename

            if not img_path.exists():
                print(f"⚠️ Image not found: {filename}")
                last_reviewed = i + 1
                continue

            print(f"[{i+1}/{len(rows)}] Image: {filename}")
            print(f"  Current Words:  '{curr_words}'")
            print(f"  Current Digits: {curr_digits}")

            # Open image in macOS Preview
            subprocess.Popen(["open", str(img_path)])

            # Wait for user input
            try:
                user_input = input("  Enter correct digits (or press Enter to skip, 'q' to quit): ").strip()
            except KeyboardInterrupt:
                break

            if user_input.lower() == 'q':
                print("\nSaving progress and quitting...")
                break

            if user_input:
                try:
                    num_val = int(user_input)
                    new_words = num_to_persian_words(num_val)
                    row["words"] = new_words
                    row["digits"] = str(num_val)
                    print(f"  ✏️ Updated to: '{new_words}' -> {num_val}\n")
                except ValueError:
                    print("  ❌ Invalid input (must be digits only or 'q'). Skipping.\n")
            else:
                print("  ⏭️ Skipped (no changes).\n")

            # Update progress state
            last_reviewed = i + 1
            STATE_FILE.write_text(str(last_reviewed))

    finally:
        # Save updated labels back to CSV
        with open(LABELS_FILE, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["index", "filename", "words", "digits"])
            writer.writeheader()
            for row in rows:
                writer.writerow(row)
        print("💾 All progress saved to labels.csv!")

if __name__ == "__main__":
    main()
