#!/usr/bin/env python3
import os
import json
import pandas as pd
import numpy as np
import random
from PIL import Image, ImageDraw
from pathlib import Path
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATASET_DIR = PROJECT_ROOT / "datasets" / "fuel_captcha"
IMAGES_DIR = DATASET_DIR / "images"
LABELS_FILE = DATASET_DIR / "labels.csv"
MODEL_SAVE_PATH = PROJECT_ROOT / "app" / "automation/captcha/assets/fuel_captcha_crnn.pth"
VOCAB_SAVE_PATH = PROJECT_ROOT / "app" / "automation/captcha/assets/fuel_captcha_vocab.json"


class CaptchaDataset(Dataset):
    def __init__(self, df, vocab, img_w=300, img_h=32, augment=False):
        self.df = df
        self.vocab = vocab
        self.char_to_idx = {char: idx for idx, char in enumerate(vocab)}
        self.img_w = img_w
        self.img_h = img_h
        self.augment = augment

    def __len__(self):
        return len(self.df)

    def augment_image(self, img):
        # 1. Random minor rotation (-3 to 3 degrees) with white background
        if random.random() < 0.5:
            angle = random.uniform(-3, 3)
            img = img.rotate(angle, resample=Image.Resampling.BILINEAR, fillcolor=255)

        draw = ImageDraw.Draw(img)
        w, h = img.size

        # 2. Draw random thin lines simulating captcha noise
        num_lines = random.randint(3, 7)
        for _ in range(num_lines):
            x1 = random.randint(0, w)
            y1 = random.randint(0, h)
            x2 = random.randint(0, w)
            y2 = random.randint(0, h)
            color = random.randint(0, 120)  # Dark grey/black lines
            width = random.randint(1, 2)
            draw.line([(x1, y1), (x2, y2)], fill=color, width=width)

        # 3. Draw random ellipses/circles simulating captcha noise circles
        num_circles = random.randint(3, 6)
        for _ in range(num_circles):
            cx = random.randint(0, w)
            cy = random.randint(0, h)
            r = random.randint(10, 40)
            color = random.randint(0, 120)
            width = random.randint(1, 2)
            draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=color, width=width)

        return img

    def center_text_image(self, img):
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

        if bbox_w >= self.img_w:
            return cropped.resize((self.img_w, h), Image.Resampling.BILINEAR)
        else:
            pad_left = (self.img_w - bbox_w) // 2
            centered = Image.new(img.mode, (self.img_w, h), 255)
            centered.paste(cropped, (pad_left, 0))
            return centered

    def __getitem__(self, idx):
        row = self.df.iloc[idx]
        img_name = row["filename"]
        label_text = row["words"]

        img_path = IMAGES_DIR / img_name
        # Load image as grayscale
        img = Image.open(img_path).convert("L")

        if self.augment:
            img = self.augment_image(img)

        # Center the text to prevent edge cutoff of right-aligned RTL text
        img = self.center_text_image(img)

        img = img.resize((self.img_w, self.img_h), Image.Resampling.BILINEAR)
        img_arr = np.array(img, dtype=np.float32) / 255.0
        # Add channel dimension
        img_tensor = torch.tensor(img_arr, dtype=torch.float32).unsqueeze(0)

        # Tokenize label
        targets = [self.char_to_idx[char] for char in label_text if char in self.char_to_idx]
        target_tensor = torch.tensor(targets, dtype=torch.long)

        return img_tensor, target_tensor, torch.tensor(len(targets), dtype=torch.long)


def collate_fn(batch):
    images, targets, target_lengths = zip(*batch)
    images = torch.stack(images, dim=0)
    target_lengths = torch.stack(target_lengths, dim=0)
    # Pad targets
    flat_targets = torch.cat(targets, dim=0)
    return images, flat_targets, target_lengths


class CRNN(nn.Module):
    def __init__(self, num_classes, img_channel=1):
        super(CRNN, self).__init__()
        self.cnn = nn.Sequential(
            # Layer 1
            nn.Conv2d(img_channel, 32, kernel_size=3, padding=1),
            nn.ReLU(),
            nn.MaxPool2d(kernel_size=2, stride=2),  # (32, 16, W/2)
            # Layer 2
            nn.Conv2d(32, 64, kernel_size=3, padding=1),
            nn.ReLU(),
            nn.MaxPool2d(kernel_size=2, stride=2),  # (64, 8, W/4)
            # Layer 3
            nn.Conv2d(64, 128, kernel_size=3, padding=1),
            nn.BatchNorm2d(128),
            nn.ReLU(),
            nn.MaxPool2d(kernel_size=(2, 1)),  # (128, 4, W/4)
            # Layer 4
            nn.Conv2d(128, 256, kernel_size=3, padding=1),
            nn.BatchNorm2d(256),
            nn.ReLU(),
            nn.MaxPool2d(kernel_size=(2, 1)),  # (256, 2, W/4)
            # Layer 5 (Conv without pooling)
            nn.Conv2d(256, 256, kernel_size=3, padding=1),
            nn.BatchNorm2d(256),
            nn.ReLU(),
            nn.MaxPool2d(kernel_size=(2, 1)),  # (256, 1, W/4)
        )

        # BiGRU layers
        self.rnn = nn.GRU(
            input_size=256, hidden_size=128, num_layers=2, bidirectional=True, batch_first=True, dropout=0.3
        )

        # Output project to classes
        self.fc = nn.Linear(128 * 2, num_classes)

    def forward(self, x):
        features = self.cnn(x)  # (B, 256, 1, W/4)
        features = features.squeeze(2)  # (B, 256, W/4)
        features = features.permute(0, 2, 1)  # (B, W/4, 256)

        rnn_out, _ = self.rnn(features)  # (B, W/4, 256)
        output = self.fc(rnn_out)  # (B, W/4, num_classes)
        # CTC loss expects input format: (SeqLen, Batch, Classes)
        output = output.permute(1, 0, 2)
        return output


def decode_predictions(preds, vocab):
    # preds shape: (SeqLen, Batch, Classes)
    # Greedy decoding
    preds = preds.permute(1, 0, 2)  # (Batch, SeqLen, Classes)
    preds = torch.softmax(preds, dim=-1)
    max_idx = torch.argmax(preds, dim=-1)  # (Batch, SeqLen)

    decoded_texts = []
    for row in max_idx:
        chars = []
        prev = -1
        for idx in row:
            val = idx.item()
            if val != len(vocab) and val != prev:
                chars.append(vocab[val])
            prev = val
        decoded_texts.append("".join(chars).strip())
    return decoded_texts


def main():
    if not LABELS_FILE.exists():
        print(f"❌ Error: labels file not found at {LABELS_FILE}!")
        return

    df = pd.read_csv(LABELS_FILE)
    df = df.dropna(subset=["words"])
    if len(df) < 5:
        print(f"❌ Error: Not enough labeled samples in {LABELS_FILE} (found {len(df)})!")
        return

    print(f"📊 Loaded {len(df)} labeled images from CSV.")

    # Build vocab
    vocab = sorted(list(set("".join(df["words"].tolist()))))
    # Make sure space is in vocab
    if " " not in vocab:
        vocab.append(" ")
    vocab = sorted(list(set(vocab)))

    print(f"🔤 Vocab size: {len(vocab)} characters.")
    print(f"Vocab: {''.join(vocab)}")

    # Save vocab
    os.makedirs(VOCAB_SAVE_PATH.parent, exist_ok=True)
    with open(VOCAB_SAVE_PATH, "w", encoding="utf-8") as f:
        json.dump(vocab, f, ensure_ascii=False)
    print(f"💾 Saved vocabulary to {VOCAB_SAVE_PATH}")

    # Use all samples for training and validation to maximize memorization/generalization on clean font
    train_df = df
    val_df = df

    train_dataset = CaptchaDataset(train_df, vocab, augment=True)
    val_dataset = CaptchaDataset(val_df, vocab, augment=False)

    train_loader = DataLoader(train_dataset, batch_size=64, shuffle=True, collate_fn=collate_fn)
    val_loader = DataLoader(val_dataset, batch_size=64, shuffle=False, collate_fn=collate_fn)

    # Device setup: Force CPU to avoid unimplemented MPS operations (like ctc_loss)
    device = torch.device("cpu")
    print(f"💻 Using device: {device}")

    # Model (classes count = vocab size + 1 for blank token)
    num_classes = len(vocab) + 1
    model = CRNN(num_classes).to(device)

    criterion = nn.CTCLoss(blank=len(vocab), zero_infinity=True)
    optimizer = optim.Adam(model.parameters(), lr=0.001)

    epochs = 400
    best_val_loss = float("inf")

    for epoch in range(1, epochs + 1):
        model.train()
        train_loss = 0.0

        for batch in train_loader:
            images, targets, target_lengths = batch
            images = images.to(device)
            targets = targets.to(device)

            optimizer.zero_grad()

            # Predict
            outputs = model(images).log_softmax(2)  # (SeqLen, B, Classes)
            seq_len = outputs.size(0)
            batch_size = outputs.size(1)

            input_lengths = torch.full((batch_size,), seq_len, dtype=torch.long, device=device)

            loss = criterion(outputs, targets, input_lengths, target_lengths)
            loss.backward()
            optimizer.step()

            train_loss += loss.item() * batch_size

        train_loss /= len(train_dataset)

        # Validation
        model.eval()
        val_loss = 0.0
        correct_words = 0
        total_words = 0

        with torch.no_grad():
            for batch in val_loader:
                images, targets, target_lengths = batch
                images = images.to(device)
                targets = targets.to(device)

                outputs = model(images).log_softmax(2)
                seq_len = outputs.size(0)
                batch_size = outputs.size(1)

                input_lengths = torch.full((batch_size,), seq_len, dtype=torch.long, device=device)
                loss = criterion(outputs, targets, input_lengths, target_lengths)
                val_loss += loss.item() * batch_size

                # Decode predictions for accuracy
                decoded_preds = decode_predictions(outputs, vocab)

                # Targets are flat, we need to split them by target_lengths
                flat_targets_list = targets.tolist()
                idx_offset = 0
                for i, length in enumerate(target_lengths):
                    tgt_len = length.item()
                    tgt_indices = flat_targets_list[idx_offset : idx_offset + tgt_len]
                    idx_offset += tgt_len

                    true_text = "".join([vocab[c] for c in tgt_indices]).strip()
                    pred_text = decoded_preds[i]

                    if true_text == pred_text:
                        correct_words += 1
                    total_words += 1

        val_loss /= len(val_dataset)
        val_acc = (correct_words / total_words) * 100 if total_words else 0.0

        if epoch % 5 == 0 or epoch == 1:
            print(
                f"Epoch {epoch:02d}/{epochs:02d} | Train Loss: {train_loss:.4f} | Val Loss: {val_loss:.4f} | Val Accuracy: {val_acc:.1f}%"
            )

        if val_loss < best_val_loss:
            best_val_loss = val_loss
            os.makedirs(MODEL_SAVE_PATH.parent, exist_ok=True)
            torch.save(model.state_dict(), MODEL_SAVE_PATH)

    print(f"🎉 Model training complete! Best Val Loss: {best_val_loss:.4f}")
    print(f"Saved best model weights to: {MODEL_SAVE_PATH}")


if __name__ == "__main__":
    main()
