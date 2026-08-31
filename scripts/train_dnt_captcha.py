#!/usr/bin/env python3
"""
Train a PyTorch CRNN (CNN + Bidirectional GRU + CTC Loss) model for DNT Captcha.
Solves wave-distorted Persian number words with high accuracy.
"""

import os
import json
import random
import csv
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw

import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATASET_DIR = Path(os.getenv("DATASET_DIR", str(PROJECT_ROOT / "datasets" / "dnt_captcha")))
IMAGES_DIR = DATASET_DIR / "images"
LABELS_FILE = DATASET_DIR / "labels.csv"
MODEL_SAVE_PATH = Path(os.getenv("MODEL_SAVE_PATH", str(PROJECT_ROOT / "app" / "automation/captcha/assets/dnt_captcha_crnn.pth")))
VOCAB_SAVE_PATH = Path(os.getenv("VOCAB_SAVE_PATH", str(PROJECT_ROOT / "app" / "automation/captcha/assets/dnt_captcha_vocab.json")))

os.makedirs(MODEL_SAVE_PATH.parent, exist_ok=True)


class CRNN(nn.Module):
    def __init__(self, num_classes: int, img_channel: int = 1):
        super().__init__()
        self.cnn = nn.Sequential(
            nn.Conv2d(img_channel, 32, kernel_size=3, padding=1),
            nn.BatchNorm2d(32),
            nn.ReLU(),
            nn.MaxPool2d(kernel_size=2, stride=2),  # (H/2, W/2) -> (18, 120)

            nn.Conv2d(32, 64, kernel_size=3, padding=1),
            nn.BatchNorm2d(64),
            nn.ReLU(),
            nn.MaxPool2d(kernel_size=2, stride=2),  # (H/4, W/4) -> (9, 60)

            nn.Conv2d(64, 128, kernel_size=3, padding=1),
            nn.BatchNorm2d(128),
            nn.ReLU(),
            nn.MaxPool2d(kernel_size=(2, 1)),       # (4, 60)

            nn.Conv2d(128, 256, kernel_size=3, padding=1),
            nn.BatchNorm2d(256),
            nn.ReLU(),
            nn.MaxPool2d(kernel_size=(2, 1)),       # (2, 60)

            nn.Conv2d(256, 256, kernel_size=(2, 1)), # (1, 60)
            nn.BatchNorm2d(256),
            nn.ReLU(),
        )

        self.rnn = nn.GRU(
            input_size=256,
            hidden_size=128,
            num_layers=2,
            bidirectional=True,
            batch_first=True,
            dropout=0.25,
        )

        self.fc = nn.Linear(128 * 2, num_classes)

    def forward(self, x):
        features = self.cnn(x)          # [B, 256, 1, W_seq]
        features = features.squeeze(2)  # [B, 256, W_seq]
        features = features.permute(0, 2, 1)  # [B, W_seq, 256]

        rnn_out, _ = self.rnn(features) # [B, W_seq, 256]
        output = self.fc(rnn_out)       # [B, W_seq, num_classes]
        output = output.permute(1, 0, 2)  # [W_seq, B, num_classes] (for CTC)
        return output


class DntCaptchaDataset(Dataset):
    def __init__(self, records: list[dict[str, str]], vocab: list[str], img_w: int = 240, img_h: int = 36, augment: bool = False):
        self.records = records
        self.vocab = vocab
        # Index 0 is reserved for CTC blank token
        self.char_to_idx = {char: idx + 1 for idx, char in enumerate(vocab)}
        self.img_w = img_w
        self.img_h = img_h
        self.augment = augment

    def __len__(self):
        return len(self.records)

    def augment_image(self, img: Image.Image) -> Image.Image:
        draw = ImageDraw.Draw(img)
        w, h = img.size

        # Add random light noise dots/lines
        if random.random() < 0.6:
            for _ in range(random.randint(2, 6)):
                x1, y1 = random.randint(0, w), random.randint(0, h)
                x2, y2 = random.randint(0, w), random.randint(0, h)
                draw.line([(x1, y1), (x2, y2)], fill=random.randint(120, 200), width=1)
        return img

    def __getitem__(self, idx):
        row = self.records[idx]
        filename = row["filename"]
        words = str(row["words"])

        img_path = IMAGES_DIR / filename
        img = Image.open(img_path).convert("L")

        if self.augment:
            img = self.augment_image(img)

        img = img.resize((self.img_w, self.img_h), Image.Resampling.BILINEAR)
        img_arr = np.array(img, dtype=np.float32) / 255.0
        # Normalize: zero mean, unit variance
        img_arr = (img_arr - 0.5) / 0.5
        img_tensor = torch.tensor(img_arr, dtype=torch.float32).unsqueeze(0)

        targets = [self.char_to_idx[c] for c in words if c in self.char_to_idx]
        target_tensor = torch.tensor(targets, dtype=torch.long)

        return img_tensor, target_tensor, torch.tensor(len(targets), dtype=torch.long), words


def collate_fn(batch):
    images, targets, target_lengths, words = zip(*batch)
    images = torch.stack(images, dim=0)
    target_lengths = torch.stack(target_lengths, dim=0)
    flattened_targets = torch.cat(targets, dim=0)
    return images, flattened_targets, target_lengths, words


def decode_predictions(preds, vocab: list[str]):
    # preds: [W_seq, B, num_classes]
    preds = preds.permute(1, 0, 2)  # [B, W_seq, num_classes]
    argmax_preds = torch.argmax(preds, dim=2).detach().cpu().numpy()

    decoded_strings = []
    for seq in argmax_preds:
        decoded_chars = []
        prev_idx = 0
        for idx in seq:
            if idx != 0 and idx != prev_idx:
                if idx - 1 < len(vocab):
                    decoded_chars.append(vocab[idx - 1])
            prev_idx = idx
        decoded_strings.append("".join(decoded_chars))
    return decoded_strings


def train(epochs: int = 50, batch_size: int = 32, lr: float = 1e-3):
    if not LABELS_FILE.exists():
        print(f"Error: {LABELS_FILE} not found. Please run generate_dnt_captcha_dataset.py first.")
        return

    records = []
    with open(LABELS_FILE, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            records.append(r)
    print(f"Loaded {len(records)} samples from {LABELS_FILE}")

    # Build vocabulary from all unique characters in labels
    unique_chars = sorted(list(set("".join([str(r["words"]) for r in records]))))
    print(f"Vocabulary ({len(unique_chars)} chars): {''.join(unique_chars)}")

    with open(VOCAB_SAVE_PATH, "w", encoding="utf-8") as f:
        json.dump(unique_chars, f, ensure_ascii=False, indent=2)
    print(f"Saved vocabulary to {VOCAB_SAVE_PATH}")

    # Split Train (90%) and Val (10%)
    val_size = max(50, int(len(records) * 0.1))
    train_records = records[:-val_size]
    val_records = records[-val_size:]

    train_dataset = DntCaptchaDataset(train_records, unique_chars, augment=True)
    val_dataset = DntCaptchaDataset(val_records, unique_chars, augment=False)

    train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True, collate_fn=collate_fn)
    val_loader = DataLoader(val_dataset, batch_size=batch_size, shuffle=False, collate_fn=collate_fn)

    # Blank token at index 0 -> num_classes = len(vocab) + 1
    num_classes = len(unique_chars) + 1
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Using training device: {device}")

    model = CRNN(num_classes=num_classes).to(device)
    ctc_loss = nn.CTCLoss(blank=0, zero_infinity=True)
    optimizer = optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)
    scheduler = optim.lr_scheduler.ReduceLROnPlateau(optimizer, mode="max", factor=0.5, patience=3)

    best_val_acc = 0.0

    for epoch in range(1, epochs + 1):
        model.train()
        total_loss = 0.0

        for images, targets, target_lengths, _ in train_loader:
            images = images.to(device)
            targets = targets.to(device)
            target_lengths = target_lengths.to(device)

            optimizer.zero_grad()
            preds = model(images)  # [W_seq, B, num_classes]
            log_probs = nn.functional.log_softmax(preds, dim=2)

            input_lengths = torch.full((images.size(0),), preds.size(0), dtype=torch.long, device=device)
            loss = ctc_loss(log_probs, targets, input_lengths, target_lengths)

            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=5.0)
            optimizer.step()

            total_loss += loss.item()

        avg_loss = total_loss / len(train_loader)

        # Validation
        model.eval()
        correct = 0
        total = 0

        with torch.no_grad():
            for images, _, _, words in val_loader:
                images = images.to(device)
                preds = model(images)
                decoded = decode_predictions(preds, unique_chars)

                for pred_text, true_text in zip(decoded, words):
                    if pred_text.strip() == str(true_text).strip():
                        correct += 1
                    total += 1

        val_acc = correct / total if total > 0 else 0.0
        scheduler.step(val_acc)

        print(f"Epoch {epoch:02d}/{epochs:02d} | Loss: {avg_loss:.4f} | Val Exact Accuracy: {val_acc * 100:.2f}% ({correct}/{total})")

        if val_acc > best_val_acc or epoch == epochs:
            best_val_acc = max(best_val_acc, val_acc)
            torch.save(model.state_dict(), MODEL_SAVE_PATH)
            print(f"  ⭐ Saved best model ({best_val_acc * 100:.2f}%) to {MODEL_SAVE_PATH}")

    print(f"\n🎉 Training complete! Best validation exact-match accuracy: {best_val_acc * 100:.2f}%")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--epochs", type=int, default=35)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--lr", type=float, default=1e-3)
    args = parser.parse_args()
    train(epochs=args.epochs, batch_size=args.batch_size, lr=args.lr)
