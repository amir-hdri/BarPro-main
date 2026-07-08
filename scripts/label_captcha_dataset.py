#!/usr/bin/env python3
"""
Interactive labeling tool for the fuel CAPTCHA dataset.

Usage:
  python3 label_captcha_dataset.py                    # Label unlabeled images
  python3 label_captcha_dataset.py --stats             # Show labeling stats
  python3 label_captcha_dataset.py --export-tfds       # Export to TFDS format
"""

import csv
import json
import sys
import argparse
from pathlib import Path

from PIL import Image

DATASET_DIR = Path(__file__).resolve().parent.parent / "datasets" / "fuel_captcha"
IMAGES_DIR = DATASET_DIR / "images"
LABELS_FILE = DATASET_DIR / "labels.csv"
TFDS_DIR = DATASET_DIR / "tfds"


def load_labels() -> dict[int, str]:
    labels = {}
    if LABELS_FILE.exists():
        with open(LABELS_FILE, "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            next(reader, None)
            for row in reader:
                if len(row) >= 2:
                    labels[int(row[0])] = row[1]
    return labels


def save_labels(labels: dict[int, str]):
    with open(LABELS_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["index", "label"])
        for idx in sorted(labels):
            writer.writerow([idx, labels[idx]])
    print(f"  ✅ Labels saved to {LABELS_FILE}")


def verify_all_images_exist() -> list[int]:
    existing = set()
    for p in IMAGES_DIR.glob("captcha_*.png"):
        try:
            idx = int(p.stem.split("_")[1])
            existing.add(idx)
        except (IndexError, ValueError):
            pass
    return sorted(existing)


def show_stats():
    labels = load_labels()
    all_indices = verify_all_images_exist()
    labeled = sum(1 for i in all_indices if i in labels)
    unlabeled = len(all_indices) - labeled
    print(f"Total images:     {len(all_indices)}")
    print(f"Labeled:          {labeled}")
    print(f"Unlabeled:        {unlabeled}")
    print(f"Progress:         {labeled}/{len(all_indices)} ({100 * labeled // len(all_indices)}%)")
    if labels:
        label_values = list(labels.values())
        lengths = [len(v) for v in label_values]
        print(f"Label length min: {min(lengths)}, max: {max(lengths)}, avg: {sum(lengths)/len(lengths):.1f}")
        print(f"Unique labels:    {len(set(label_values))}")


def interactive_label():
    labels = load_labels()
    all_indices = verify_all_images_exist()
    unlabeled = [i for i in all_indices if i not in labels]

    if not unlabeled:
        print("✅ All images are already labeled!")
        return

    print(f"📝 Interactive labeling: {len(unlabeled)} unlabeled images remaining")
    print(f"   Enter the CAPTCHA text (digits only) or:")
    print(f"   's' = skip, 'q' = save & quit, 'u' = undo last")
    print()

    last_labeled = []

    for idx in unlabeled:
        img_path = IMAGES_DIR / f"captcha_{idx:04d}.png"
        img = Image.open(img_path)

        print(f"[{idx}/{len(all_indices)}] Image captcha_{idx:04d}.png ({img.size[0]}x{img.size[1]})")
        print(f"   Press 'v' to view in Finder, or enter label: ", end="", flush=True)

        label = sys.stdin.readline().strip()

        if label == "q":
            save_labels(labels)
            print("Exiting.")
            return
        elif label == "s":
            continue
        elif label == "u":
            if last_labeled:
                undone = last_labeled.pop()
                del labels[undone]
                print(f"   ↩️  Undone captcha_{undone:04d}.png")
            else:
                print("   Nothing to undo.")
            continue
        elif label == "v":
            import subprocess
            subprocess.run(["open", "-R", str(img_path)])
            print(f"   (Finder opened) Enter label: ", end="", flush=True)
            label = sys.stdin.readline().strip()
            if label == "q":
                save_labels(labels)
                return
            if label in ("s", "u"):
                continue

        if label:
            labels[idx] = label
            last_labeled.append(idx)
            auto_save_count = 50
            if len(last_labeled) % auto_save_count == 0:
                save_labels(labels)
                print(f"   🔄 Auto-saved ({len(labels)} labels)")

    save_labels(labels)
    print("\n🎉 All images labeled!")


def test_model_on_dataset():
    """Run the Keras model on dataset to see current accuracy."""
    try:
        import keras
        import numpy as np
        import tensorflow as tf
    except ImportError:
        print("TensorFlow/Keras not available")
        return

    labels = load_labels()
    if not labels:
        print("No labels available. Label some images first.")
        return

    model_path = Path(__file__).resolve().parent.parent / "persian_number_ocr.keras"
    if not model_path.exists():
        print(f"Model not found: {model_path}")
        return

    print(f"Loading model: {model_path}")
    model = keras.models.load_model(str(model_path), compile=False)

    CHARS = [str(d) for d in range(10)]
    BLANK_INDEX = 10
    correct = 0
    total = 0
    results = []

    for idx in sorted(labels):
        true_label = labels[idx]
        img_path = IMAGES_DIR / f"captcha_{idx:04d}.png"
        if not img_path.exists():
            continue

        img = Image.open(img_path).convert("RGB")
        img_resized = img.resize((180, 25))
        img_array = np.expand_dims(np.array(img_resized, dtype=np.float32) / 255.0, axis=0)

        pred = model.predict(img_array, verbose=0)
        pred_time_major = tf.transpose(pred, perm=[1, 0, 2])
        input_len = np.ones(pred.shape[0]) * pred.shape[1]
        decoded, _ = tf.nn.ctc_greedy_decoder(
            pred_time_major,
            sequence_length=tf.cast(input_len, tf.int32),
            blank_index=BLANK_INDEX
        )
        dense_decoded = tf.sparse.to_dense(decoded[0], default_value=-1).numpy()
        digits = [CHARS[int(c)] for c in dense_decoded[0] if c != -1]
        predicted = "".join(digits)[::-1]

        is_correct = predicted == true_label
        if is_correct:
            correct += 1
        total += 1
        results.append((idx, true_label, predicted, is_correct))
        if not is_correct and total <= 20:
            print(f"  captcha_{idx:04d}: true={true_label}, pred={predicted} ❌")
        elif is_correct and correct <= 3:
            print(f"  captcha_{idx:04d}: true={true_label}, pred={predicted} ✅")

    accuracy = correct / total * 100 if total else 0
    print(f"\n{'='*50}")
    print(f"Model accuracy: {correct}/{total} = {accuracy:.1f}%")
    print(f"{'='*50}")

    wrong_results = [(i, t, p) for i, t, p, c in results if not c]
    if wrong_results:
        print(f"\nWrong predictions sample (first 10):")
        for i, t, p in wrong_results[:10]:
            print(f"  captcha_{i:04d}: true='{t}' pred='{p}' (len {len(p)})")


def export_tfds():
    labels = load_labels()
    if not labels:
        print("No labels available. Label images first.")
        return

    (TFDS_DIR / "images").mkdir(parents=True, exist_ok=True)
    records = []

    for idx in sorted(labels):
        src = IMAGES_DIR / f"captcha_{idx:04d}.png"
        if not src.exists():
            continue
        dst = TFDS_DIR / "images" / f"captcha_{idx:04d}.png"
        dst.write_bytes(src.read_bytes())
        records.append({
            "image": f"captcha_{idx:04d}.png",
            "label": labels[idx],
        })

    with open(TFDS_DIR / "_dataset.json", "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

    print(f"Exported {len(records)} labeled images to {TFDS_DIR}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CAPTCHA Dataset Labeling Tool")
    parser.add_argument("--stats", action="store_true", help="Show labeling stats")
    parser.add_argument("--test-model", action="store_true", help="Test Keras model on labeled data")
    parser.add_argument("--export-tfds", action="store_true", help="Export to TFDS format")
    args = parser.parse_args()

    if args.stats:
        show_stats()
    elif args.test_model:
        test_model_on_dataset()
    elif args.export_tfds:
        export_tfds()
    else:
        interactive_label()
