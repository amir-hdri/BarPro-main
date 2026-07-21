#!/usr/bin/env python3
import csv
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.automation.captcha.persian_number_parser import num_to_persian_words

LABELS_FILE = PROJECT_ROOT / "datasets" / "fuel_captcha" / "labels.csv"
BACKUP_FILE = PROJECT_ROOT / "datasets" / "fuel_captcha" / "labels.csv.bak"


def main():
    if not LABELS_FILE.exists():
        print(f"❌ Error: labels.csv not found at {LABELS_FILE}")
        return

    # Backup the original labels.csv first
    import shutil

    shutil.copy2(LABELS_FILE, BACKUP_FILE)
    print(f"📦 Created backup of labels.csv at {BACKUP_FILE}")

    # Read existing rows
    rows = []
    with open(LABELS_FILE, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        for row in reader:
            rows.append(row)

    # Correct words column based on digits
    corrected_count = 0
    for idx, row in enumerate(rows):
        digits_str = row.get("digits", "").strip()
        if not digits_str:
            print(f"⚠️ Warning: Empty digits at index {row.get('index')}, skipping.")
            continue

        try:
            digits_val = int(digits_str)
        except ValueError:
            print(f"❌ Error: Non-numeric digits '{digits_str}' at index {row.get('index')}, skipping.")
            continue

        correct_words = num_to_persian_words(digits_val)
        original_words = row.get("words", "")

        if correct_words != original_words:
            row["words"] = correct_words
            corrected_count += 1
            if corrected_count <= 10:
                print(f"✏️ Corrected Row {idx+2} ({row['filename']}): '{original_words}' -> '{correct_words}'")

    print(f"✨ Corrected {corrected_count} rows out of {len(rows)} total rows.")

    # Save the corrected labels back to CSV
    with open(LABELS_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"💾 Corrected labels successfully written to {LABELS_FILE}")


if __name__ == "__main__":
    main()
