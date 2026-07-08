#!/usr/bin/env python3
"""
Semi-Automatic Labeling Tool for Fuel Captcha Dataset (Matplotlib version)
==========================================================================
Shows each unlabeled captcha image with the model's prediction using matplotlib.
Input is via terminal:
  - Press Enter to accept the prediction
  - Type the correct number to override
  - Type 's' to skip
  - Type 'q' to quit and save

Progress is automatically saved to labels.csv after each label.
"""
import os
import sys
import json
import csv
from pathlib import Path
from PIL import Image
import numpy as np
import matplotlib
matplotlib.use('TkAgg')  # Try TkAgg first, fall back to macosx
import matplotlib.pyplot as plt

import os
import sys
import json
import csv
from pathlib import Path

# 1. Setup paths and load project environment variables first
PROJECT_ROOT = Path(__file__).resolve().parent.parent
env_file = PROJECT_ROOT / ".env"
if env_file.exists():
    with open(env_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                parts = line.split("=", 1)
                if len(parts) == 2:
                    k, v = parts[0].strip(), parts[1].strip().strip("'\"")
                    if k:
                        os.environ[k] = v

# Ensure required config defaults are populated
if "HEADLESS" not in os.environ:
    os.environ["HEADLESS"] = "true"

# 2. Define dataset-specific paths
DATASET_DIR = PROJECT_ROOT / "datasets" / "fuel_captcha"
IMAGES_DIR = DATASET_DIR / "images"
LABELS_FILE = DATASET_DIR / "labels.csv"
MODEL_PATH = PROJECT_ROOT / "app" / "automation" / "captcha" / "assets" / "fuel_captcha_crnn.pth"
VOCAB_PATH = PROJECT_ROOT / "app" / "automation" / "captcha" / "assets" / "fuel_captcha_vocab.json"

# 3. Import numpy, PIL, and matplotlib
import numpy as np
from PIL import Image
import matplotlib.pyplot as plt


# 4. Import torch and project dependencies
try:
    import torch
    import torch.nn as nn
except ImportError:
    print("❌ PyTorch is required. Install it first.")
    sys.exit(1)

sys.path.insert(0, str(PROJECT_ROOT))
from app.automation.captcha.persian_number_parser import persian_words_to_number




class CRNN(nn.Module):
    def __init__(self, num_classes, img_channel=1):
        super(CRNN, self).__init__()
        self.cnn = nn.Sequential(
            nn.Conv2d(img_channel, 32, kernel_size=3, padding=1),
            nn.ReLU(),
            nn.MaxPool2d(kernel_size=2, stride=2),
            nn.Conv2d(32, 64, kernel_size=3, padding=1),
            nn.ReLU(),
            nn.MaxPool2d(kernel_size=2, stride=2),
            nn.Conv2d(64, 128, kernel_size=3, padding=1),
            nn.BatchNorm2d(128),
            nn.ReLU(),
            nn.MaxPool2d(kernel_size=(2, 1)),
            nn.Conv2d(128, 256, kernel_size=3, padding=1),
            nn.BatchNorm2d(256),
            nn.ReLU(),
            nn.MaxPool2d(kernel_size=(2, 1)),
            nn.Conv2d(256, 256, kernel_size=3, padding=1),
            nn.BatchNorm2d(256),
            nn.ReLU(),
            nn.MaxPool2d(kernel_size=(2, 1))
        )
        self.rnn = nn.GRU(
            input_size=256, hidden_size=128, num_layers=2,
            bidirectional=True, batch_first=True, dropout=0.3
        )
        self.fc = nn.Linear(128 * 2, num_classes)

    def forward(self, x):
        features = self.cnn(x)
        features = features.squeeze(2)
        features = features.permute(0, 2, 1)
        rnn_out, _ = self.rnn(features)
        output = self.fc(rnn_out)
        output = output.permute(1, 0, 2)
        return output


def center_text_image(img, target_w=300):
    arr = np.array(img)
    h, w = arr.shape
    col_mins = np.min(arr, axis=0)
    non_white_cols = np.where(col_mins < 240)[0]
    if len(non_white_cols) == 0:
        return img
    left_bound = non_white_cols[0]
    right_bound = non_white_cols[-1]
    bbox_w = right_bound - left_bound + 1
    cropped = img.crop((left_bound, 0, right_bound + 1, h))
    if bbox_w >= target_w:
        return cropped.resize((target_w, h), Image.Resampling.BILINEAR)
    pad_left = (target_w - bbox_w) // 2
    centered = Image.new(img.mode, (target_w, h), 255)
    centered.paste(cropped, (pad_left, 0))
    return centered


def predict_image(model, vocab, img_path, device):
    img = Image.open(img_path).convert('L')
    img = center_text_image(img, 300)
    img_resized = img.resize((300, 32), Image.Resampling.BILINEAR)
    img_arr = np.array(img_resized, dtype=np.float32) / 255.0
    tensor = torch.tensor(img_arr, dtype=torch.float32).unsqueeze(0).unsqueeze(0).to(device)
    with torch.no_grad():
        outputs = model(tensor)
    outputs = outputs.permute(1, 0, 2)
    preds = torch.softmax(outputs, dim=-1)
    max_idx = torch.argmax(preds, dim=-1)[0]
    chars = []
    prev = -1
    for idx in max_idx:
        val = idx.item()
        if val != len(vocab) and val != prev:
            chars.append(vocab[val])
        prev = val
    words = "".join(chars).strip()
    digits = persian_words_to_number(words) if words else ""
    return words, digits


def load_existing_labels():
    labeled = set()
    if LABELS_FILE.exists():
        with open(LABELS_FILE, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                labeled.add(row["filename"])
    return labeled


def get_next_index():
    if not LABELS_FILE.exists():
        return 1
    with open(LABELS_FILE, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        next(reader)
        max_idx = 0
        for row in reader:
            try:
                max_idx = max(max_idx, int(row[0]))
            except (ValueError, IndexError):
                pass
    return max_idx + 1


def save_label(index, filename, words, digits):
    file_exists = LABELS_FILE.exists()
    with open(LABELS_FILE, "a", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["index", "filename", "words", "digits"])
        writer.writerow([index, filename, words, digits])


def main():
    print("=" * 60)
    print("  ابزار لیبل‌زنی نیمه‌خودکار کپچای استعلام سوخت")
    print("=" * 60)
    print()
    print("🔄 بارگذاری مدل...")

    with open(VOCAB_PATH, "r", encoding="utf-8") as f:
        vocab = json.load(f)

    device = torch.device("cpu")
    model = CRNN(len(vocab) + 1)
    checkpoint = torch.load(MODEL_PATH, map_location=device, weights_only=True)
    model.load_state_dict(checkpoint)
    model.to(device)
    model.eval()
    print("✅ مدل بارگذاری شد.")

    # Find unlabeled images
    labeled = load_existing_labels()
    all_images = sorted([f for f in os.listdir(IMAGES_DIR) if f.endswith(".png")])
    unlabeled = [f for f in all_images if f not in labeled]

    total_all = len(all_images)
    total_labeled = len(labeled)
    total_unlabeled = len(unlabeled)

    print(f"📊 کل: {total_all} | لیبل‌دار: {total_labeled} | بدون لیبل: {total_unlabeled}")
    print()
    print("راهنما:")
    print("  Enter  = تأیید پیش‌بینی مدل")
    print("  عدد    = تصحیح با عدد درست")
    print("  s      = رد شدن (skip)")
    print("  q      = خروج و ذخیره")
    print("-" * 60)

    if not unlabeled:
        print("🎉 همه تصاویر لیبل‌دار هستند!")
        return

    next_idx = get_next_index()
    labeled_count = 0
    accepted_count = 0

    # Setup matplotlib for interactive display
    plt.ion()
    fig, ax = plt.subplots(1, 1, figsize=(10, 3))
    fig.patch.set_facecolor('#1a1a2e')

    for i, filename in enumerate(unlabeled):
        img_path = IMAGES_DIR / filename

        # Predict
        words, digits = predict_image(model, vocab, img_path, device)

        # Show image in matplotlib
        ax.clear()
        img_display = Image.open(img_path).convert('RGB')
        ax.imshow(np.array(img_display), aspect='auto')
        ax.set_title(
            f"[{i+1}/{total_unlabeled}] {filename}    |    Model: {digits}",
            fontsize=14, color='white', fontweight='bold'
        )
        ax.axis('off')
        fig.canvas.draw()
        fig.canvas.flush_events()
        plt.pause(0.1)

        # Terminal input
        acc_pct = (accepted_count / labeled_count * 100) if labeled_count > 0 else 0
        print(f"\n📷 [{i+1}/{total_unlabeled}] {filename}")
        print(f"   پیش‌بینی: {words}")
        print(f"   عدد: {digits}")
        print(f"   [لیبل‌زده: {labeled_count} | دقت مدل: {acc_pct:.0f}%]")

        user_input = input("   ▶ Enter=تأیید / عدد=تصحیح / s=رد / q=خروج: ").strip()

        if user_input.lower() == 'q':
            print(f"\n💾 خروج. {labeled_count} لیبل جدید ذخیره شد.")
            break
        elif user_input.lower() == 's':
            print(f"   ⏭ رد شد.")
            continue
        elif user_input == '':
            # Accept model prediction
            if not digits:
                print("   ⚠ مدل پیش‌بینی ندارد. عدد صحیح را وارد کنید:")
                user_input = input("   ▶ عدد: ").strip()
                if not user_input.isdigit():
                    print("   ⏭ رد شد.")
                    continue
                final_digits = user_input
            else:
                final_digits = digits
                accepted_count += 1
        else:
            if not user_input.isdigit():
                print("   ⚠ فقط عدد مجاز است! رد شد.")
                continue
            final_digits = user_input

        save_label(next_idx, filename, words, final_digits)
        next_idx += 1
        labeled_count += 1

        status = "✅ تأیید" if user_input == '' else f"✏️ {digits} → {final_digits}"
        print(f"   💾 ذخیره: {filename} = {final_digits} ({status})")

    plt.ioff()
    plt.close()

    print()
    print("=" * 60)
    print(f"✅ پایان! {labeled_count} لیبل جدید اضافه شد.")
    if labeled_count > 0:
        acc = accepted_count / labeled_count * 100
        print(f"📊 دقت مدل (بدون تصحیح): {acc:.1f}%")
    print(f"📁 فایل ذخیره: {LABELS_FILE}")
    print(f"📊 کل لیبل‌ها اکنون: {total_labeled + labeled_count}")
    print("=" * 60)


if __name__ == "__main__":
    main()
