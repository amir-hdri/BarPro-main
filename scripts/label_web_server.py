#!/usr/bin/env python3
"""
Web-Based Interactive Labeling Tool for Fuel Captcha - Dual Screen Edition
=========================================================================
Supports two views:
1. http://localhost:8080/mac  -> Displays the big image on the Mac screen.
2. http://<mac_ip>:8080/       -> Serves a touch-friendly remote keypad on iPhone.
"""

import os
import sys
import json
import csv
import socket
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib.parse
from PIL import Image
import numpy as np

# Load environment first
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

if "HEADLESS" not in os.environ:
    os.environ["HEADLESS"] = "true"

# Define paths
DATASET_DIR = PROJECT_ROOT / "datasets" / "fuel_captcha"
IMAGES_DIR = DATASET_DIR / "images"
LABELS_FILE = DATASET_DIR / "labels.csv"
MODEL_PATH = PROJECT_ROOT / "app" / "automation/captcha/assets/fuel_captcha_crnn.pth"
VOCAB_PATH = PROJECT_ROOT / "app" / "automation/captcha/assets/fuel_captcha_vocab.json"

try:
    import torch
    import torch.nn as nn
except ImportError:
    print("❌ PyTorch is required. Install it first.")
    sys.exit(1)

sys.path.insert(0, str(PROJECT_ROOT))
from app.automation.captcha.persian_number_parser import persian_words_to_number, num_to_persian_words


def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        IP = s.getsockname()[0]
    except Exception:
        IP = "127.0.0.1"
    finally:
        s.close()
    return IP


# --- Helper to standardize Persian/Arabic digits to English digits ---
def standardize_digits(text: str) -> str:
    persian_to_english = {
        "۰": "0",
        "۱": "1",
        "۲": "2",
        "۳": "3",
        "۴": "4",
        "۵": "5",
        "۶": "6",
        "۷": "7",
        "۸": "8",
        "۹": "9",
        "٠": "0",
        "١": "1",
        "٢": "2",
        "٣": "3",
        "٤": "4",
        "٥": "5",
        "٦": "6",
        "٧": "7",
        "٨": "8",
        "٩": "9",
    }
    for p_dig, e_dig in persian_to_english.items():
        text = text.replace(p_dig, e_dig)
    return text


# --- CRNN Architecture ---
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
            nn.MaxPool2d(kernel_size=(2, 1)),
        )
        self.rnn = nn.GRU(
            input_size=256, hidden_size=128, num_layers=2, bidirectional=True, batch_first=True, dropout=0.3
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
    img = Image.open(img_path).convert("L")
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
    words = words.replace("یکصد", "صد")
    digits = persian_words_to_number(words) if words else ""
    return words, digits


def load_existing_labels():
    labeled = {}
    if LABELS_FILE.exists():
        with open(LABELS_FILE, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                labeled[row["filename"]] = {"words": row["words"], "digits": row["digits"]}
    return labeled


def get_next_index():
    if not LABELS_FILE.exists():
        return 1
    with open(LABELS_FILE, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        try:
            next(reader)
        except StopIteration:
            return 1
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


# Global state
MODEL = None
VOCAB = []
DEVICE = torch.device("cpu")


def init_model():
    global MODEL, VOCAB
    with open(VOCAB_PATH, "r", encoding="utf-8") as f:
        VOCAB = json.load(f)
    MODEL = CRNN(len(VOCAB) + 1)
    checkpoint = torch.load(MODEL_PATH, map_location=DEVICE, weights_only=True)
    MODEL.load_state_dict(checkpoint)
    MODEL.to(DEVICE)
    MODEL.eval()


# --- Page 1: iPhone Keypad View ---
IPHONE_PAGE = """
<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>کیپد همراه کپچا</title>
    <link href="https://fonts.googleapis.com/css2?family=Vazirmatn:wght@400;700&display=swap" rel="stylesheet">
    <style>
        * {
            box-sizing: border-box;
            font-family: 'Vazirmatn', sans-serif;
            margin: 0;
            padding: 0;
        }
        body {
            background: #0f172a;
            color: #f8fafc;
            min-height: 100vh;
            min-height: -webkit-fill-available;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: flex-start;
            padding: 10px;
            overflow-x: hidden;
            overflow-y: auto;
        }
        .container {
            width: 100%;
            max-width: 450px;
            display: flex;
            flex-direction: column;
            min-height: 100vh;
            min-height: -webkit-fill-available;
            justify-content: flex-start;
            padding-bottom: 15px;
        }
        h1 {
            font-size: 1.3rem;
            text-align: center;
            color: #38bdf8;
            margin-bottom: 10px;
        }
        .stats {
            display: flex;
            justify-content: space-between;
            font-size: 0.85rem;
            color: #94a3b8;
            margin-bottom: 10px;
        }
        .input-display {
            width: 100%;
            height: 70px;
            background: #020617;
            border: 2px solid #334155;
            border-radius: 16px;
            font-size: 2.2rem;
            color: #00ff88;
            text-align: center;
            direction: ltr; /* English Left-to-Right layout */
            font-family: monospace, sans-serif;
            font-weight: bold;
            outline: none;
            display: flex;
            align-items: center;
            justify-content: center;
            margin-bottom: 15px;
            letter-spacing: 2px;
        }
        .keypad {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 12px;
            flex-grow: 1;
            margin-bottom: 15px;
            direction: ltr; /* Force Left-to-Right grid layout for numbers */
        }
        .btn {
            background: #1e293b;
            border: 1px solid rgba(255, 255, 255, 0.05);
            color: #f8fafc;
            font-size: 1.8rem;
            font-weight: bold;
            border-radius: 16px;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.2);
            -webkit-tap-highlight-color: transparent;
            touch-action: manipulation; /* Disable double-tap zoom */
            height: 60px; /* Consistent touch height */
        }
        .btn:active {
            background: #334155;
            transform: scale(0.95);
        }
        .btn-clear {
            background: #7f1d1d;
            color: #fca5a5;
            font-size: 1.1rem;
            touch-action: manipulation;
        }
        .btn-clear:active {
            background: #991b1b;
        }
        .btn-skip {
            background: #374151;
            color: #d1d5db;
            font-size: 1.1rem;
            touch-action: manipulation;
        }
        .btn-skip:active {
            background: #4b5563;
        }
        .bottom-actions {
            display: flex;
            gap: 12px;
            margin-bottom: 5px;
        }
        .btn-submit {
            flex: 2;
            height: 60px;
            background: #059669;
            border: none;
            color: #ffffff;
            font-size: 1.5rem;
            font-weight: bold;
            border-radius: 16px;
            box-shadow: 0 4px 10px rgba(5, 150, 105, 0.3);
            display: flex;
            align-items: center;
            justify-content: center;
            -webkit-tap-highlight-color: transparent;
            touch-action: manipulation; /* Disable double-tap zoom */
        }
        .btn-submit:active {
            background: #047857;
            transform: scale(0.95);
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>کیپد کنترل از راه دور</h1>
        
        <div class="stats">
            <span id="stat-progress">در حال اتصال...</span>
            <span>کیپد همراه</span>
        </div>
        
        <div class="image-box" style="
            background: #020617;
            border: 2px solid #334155;
            border-radius: 16px;
            padding: 12px;
            margin-bottom: 12px;
            display: flex;
            align-items: center;
            justify-content: center;
            min-height: 80px;
        ">
            <img id="captcha-img" src="" alt="کپچا" style="
                max-width: 100%;
                height: 40px;
                object-fit: contain;
                border-radius: 8px;
                image-rendering: pixelated;
                transform: scale(1.6);
            ">
        </div>
        
        <input type="text" class="input-display" id="input-val" readonly placeholder="Captcha code">
        
        <div class="keypad">
            <button class="btn btn-number" onclick="pressKey('1')">1</button>
            <button class="btn btn-number" onclick="pressKey('2')">2</button>
            <button class="btn btn-number" onclick="pressKey('3')">3</button>
            <button class="btn btn-number" onclick="pressKey('4')">4</button>
            <button class="btn btn-number" onclick="pressKey('5')">5</button>
            <button class="btn btn-number" onclick="pressKey('6')">6</button>
            <button class="btn btn-number" onclick="pressKey('7')">7</button>
            <button class="btn btn-number" onclick="pressKey('8')">8</button>
            <button class="btn btn-number" onclick="pressKey('9')">9</button>
            <button class="btn btn-clear" onclick="clearInput()">پاک کردن</button>
            <button class="btn btn-number" onclick="pressKey('0')">0</button>
            <button class="btn btn-skip" onclick="skip()">رد کردن</button>
        </div>
        
        <div class="bottom-actions">
            <button class="btn-submit" style="background:#10b981" onclick="submit()">ثبت و ذخیره</button>
            <button class="btn-submit" style="background:#ef4444; flex:1.2; font-size:1.1rem" onclick="finishSession()">پایان و ذخیره نهایی</button>
        </div>
    </div>

    <script>
        // Retrieve or generate a unique client ID
        let clientId = localStorage.getItem("fuel_captcha_client_id");
        if (!clientId) {
            clientId = "user_" + Math.random().toString(36).substring(2, 10);
            localStorage.setItem("fuel_captcha_client_id", clientId);
        }

        let currentFilename = "";
        let modelDigits = "";
        let modelWords = "";

        async function loadNext() {
            try {
                const res = await fetch(`/api/next_info?clientId=${clientId}`);
                const data = await res.json();
                
                if (data.finished) {
                    alert("تمام تصاویر لیبل‌زنی شدند!");
                    return;
                }
                
                if (data.filename !== currentFilename) {
                    currentFilename = data.filename;
                    modelDigits = data.model_digits || "";
                    modelWords = data.model_words || "";
                    document.getElementById("input-val").value = "";
                    document.getElementById("captcha-img").src = `/image/${currentFilename}?t=${Date.now()}`;
                }
                
                const total = data.total;
                const labeled = data.labeled;
                const unlabeled = data.unlabeled;
                document.getElementById("stat-progress").innerText = `فایل ${labeled + 1} از ${total} (باقیمانده: ${unlabeled})`;
                
            } catch (err) {
                console.error(err);
            }
        }

        function pressKey(num) {
            const input = document.getElementById("input-val");
            input.value += num;
        }

        function clearInput() {
            document.getElementById("input-val").value = "";
        }

        async function submit() {
            if (!currentFilename) return;
            const val = document.getElementById("input-val").value.trim();
            if (!val) return;
            
            try {
                const isModelCorrect = (val === modelDigits);
                
                await fetch("/api/submit", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        clientId: clientId,
                        filename: currentFilename,
                        digits: val,
                        words: modelWords,
                        is_correct: isModelCorrect
                    })
                });
                
                loadNext();
            } catch (err) {
                console.error(err);
            }
        }

        function skip() {
            // Tell the server we skipped this one to show next
            fetch(`/api/skip?filename=${currentFilename}&clientId=${clientId}`).then(loadNext);
        }

        function finishSession() {
            document.body.innerHTML = `
                <div style="
                    display: flex;
                    flex-direction: column;
                    align-items: center;
                    justify-content: center;
                    height: 100vh;
                    text-align: center;
                    padding: 20px;
                    background: #0f172a;
                    color: #00ff88;
                ">
                    <h1 style="font-size: 2rem; margin-bottom: 20px; color: #10b981;">🎉 خسته نباشید!</h1>
                    <p style="font-size: 1.2rem; color: #f8fafc; margin-bottom: 30px;">
                        تمام پیشرفت شما تا این لحظه در فایل <b>labels.csv</b> ذخیره شده است.
                    </p>
                    <p style="font-size: 1rem; color: #94a3b8;">
                        حالا می‌توانید صفحات مرورگر (آیفون و مک) را ببندید.
                    </p>
                </div>
            `;
        }

        // Initial load
        loadNext();
    </script>
</body>
</html>
"""

# --- Page 2: Mac Display View ---
MAC_PAGE = """
<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>نمایشگر بزرگ کپچا (اتاق فرمان مک)</title>
    <link href="https://fonts.googleapis.com/css2?family=Vazirmatn:wght@400;700&display=swap" rel="stylesheet">
    <style>
        * {
            box-sizing: border-box;
            font-family: 'Vazirmatn', sans-serif;
            margin: 0;
            padding: 0;
        }
        body {
            background: #0b0f19;
            color: #f8fafc;
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: flex-start;
            padding: 30px;
        }
        .container {
            width: 100%;
            max-width: 1200px;
            background: rgba(22, 30, 49, 0.7);
            backdrop-filter: blur(16px);
            border: 1px solid rgba(255, 255, 255, 0.05);
            border-radius: 32px;
            padding: 30px;
            box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.7);
        }
        h1 {
            font-size: 1.8rem;
            margin-bottom: 20px;
            background: linear-gradient(90deg, #38bdf8, #818cf8);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            font-weight: 700;
            text-align: center;
        }
        .progress-bar {
            width: 100%;
            height: 10px;
            background: #1e293b;
            border-radius: 5px;
            margin-bottom: 15px;
            overflow: hidden;
        }
        .progress-fill {
            height: 100%;
            background: linear-gradient(90deg, #38bdf8, #6366f1);
            width: 0%;
            transition: width 0.3s ease;
        }
        .stats {
            display: flex;
            justify-content: space-between;
            font-size: 1rem;
            color: #94a3b8;
            margin-bottom: 25px;
        }
        .nodes-title {
            font-size: 1.2rem;
            color: #f8fafc;
            margin-bottom: 15px;
            font-weight: bold;
            border-right: 4px solid #38bdf8;
            padding-right: 10px;
        }
        .grid-container {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
            gap: 20px;
            margin-bottom: 25px;
        }
        .session-card {
            background: rgba(30, 41, 59, 0.6);
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 20px;
            padding: 20px;
            display: flex;
            flex-direction: column;
            align-items: center;
            box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.3);
            transition: all 0.3s ease;
        }
        .session-card:hover {
            transform: translateY(-4px);
            border-color: rgba(56, 189, 248, 0.4);
            box-shadow: 0 15px 25px -5px rgba(0, 0, 0, 0.5);
        }
        .session-header {
            width: 100%;
            display: flex;
            justify-content: space-between;
            font-size: 0.8rem;
            color: #94a3b8;
            margin-bottom: 12px;
            border-bottom: 1px solid rgba(255, 255, 255, 0.05);
            padding-bottom: 8px;
        }
        .session-node {
            font-weight: bold;
            color: #38bdf8;
        }
        .session-image-container {
            background: #020617;
            padding: 12px;
            border-radius: 12px;
            width: 100%;
            display: flex;
            justify-content: center;
            align-items: center;
            margin-bottom: 12px;
            min-height: 60px;
        }
        .session-image {
            max-width: 100%;
            height: 35px;
            image-rendering: pixelated;
            transform: scale(1.4);
            object-fit: contain;
        }
        .session-info {
            text-align: center;
        }
        .session-digits {
            font-size: 1.6rem;
            color: #00ff88;
            font-weight: bold;
            font-family: monospace;
            letter-spacing: 2px;
        }
        .session-words {
            font-size: 0.85rem;
            color: #94a3b8;
            margin-top: 4px;
        }
        .no-nodes {
            grid-column: 1 / -1;
            text-align: center;
            padding: 40px;
            color: #64748b;
            background: rgba(30, 41, 59, 0.3);
            border-radius: 20px;
            border: 1px dashed rgba(255, 255, 255, 0.05);
            font-size: 1.1rem;
        }
        .instructions {
            margin-top: 30px;
            font-size: 0.95rem;
            color: #64748b;
            line-height: 1.6;
            text-align: center;
        }
        .ip-box {
            display: inline-block;
            background: #1e293b;
            padding: 6px 14px;
            border-radius: 8px;
            color: #38bdf8;
            font-weight: bold;
            margin-top: 10px;
            font-family: monospace;
            font-size: 1rem;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>اتاق کنترل لیبل‌زنی همزمان</h1>
        
        <div class="progress-bar">
            <div class="progress-fill" id="progress-fill"></div>
        </div>
        
        <div class="stats">
            <span id="stat-progress">در حال دریافت آمار...</span>
            <span id="stat-active-count">دستگاه‌های فعال: 0</span>
        </div>

        <div class="nodes-title">وضعیت زنده دستگاه‌ها</div>
        <div class="grid-container" id="nodes-grid">
            <div class="no-nodes">در حال انتظار برای اتصال موبایل‌ها...</div>
        </div>
        
        <div class="instructions">
            موبایل‌ها را به شبکه وای‌فای مشابه وصل کنید و آدرس زیر را در مرورگر آن‌ها باز کنید تا هر کدام تصویر متفاوتی را حل کنند:
            <br>
            <span class="ip-box" id="mac-ip-address">http://IP:8080/</span>
        </div>
    </div>

    <script>
        async function checkUpdate() {
            try {
                const res = await fetch("/api/active_sessions");
                const data = await res.json();
                
                const total = data.total || 0;
                const labeled = data.labeled || 0;
                const unlabeled = data.unlabeled || 0;
                const pct = total > 0 ? (labeled / total * 100) : 0;
                
                document.getElementById("progress-fill").style.width = `${pct}%`;
                document.getElementById("stat-progress").innerText = `پیشرفت کل: ${labeled} از ${total} (باقیمانده: ${unlabeled})`;
                
                const sessions = data.sessions || [];
                document.getElementById("stat-active-count").innerText = `دستگاه‌های فعال: ${sessions.length}`;
                
                const grid = document.getElementById("nodes-grid");
                if (sessions.length === 0) {
                    grid.innerHTML = '<div class="no-nodes">هیچ موبایلی متصل نیست. لطفاً آدرس پایین صفحه را در گوشی باز کنید.</div>';
                } else {
                    grid.innerHTML = sessions.map(s => {
                        const shortId = s.clientId.startsWith("user_") ? s.clientId.substring(5) : s.clientId;
                        return `
                            <div class="session-card">
                                <div class="session-header">
                                    <span class="session-node">کاربر ${shortId}</span>
                                    <span class="session-ip">${s.ip}</span>
                                </div>
                                <div class="session-image-container">
                                    <img class="session-image" src="/image/${s.filename}" alt="کپچا">
                                </div>
                                <div class="session-info">
                                    <div class="session-digits">${s.digits || "---"}</div>
                                    <div class="session-words">${s.words || "در حال تایپ..."}</div>
                                </div>
                            </div>
                        `;
                    }).join('');
                }
                
                document.getElementById("mac-ip-address").innerText = "http://" + window.location.hostname + ":8080/";
                
            } catch (err) {
                console.error(err);
            }
        }

        setInterval(checkUpdate, 500);
        checkUpdate();
    </script>
</body>
</html>
"""

# Global memory state for multi-device collaboration
CLIENT_ASSIGNMENTS = {}  # { clientId: filename }
CLIENT_LAST_SEEN = {}  # { clientId: timestamp }
CLIENT_IP_MAP = {}  # { clientId: ip_address }


def cleanup_inactive_clients():
    import time

    now = time.time()
    inactive_threshold = 20.0  # 20 seconds timeout
    inactive_clients = [
        cid for cid, last_seen in list(CLIENT_LAST_SEEN.items()) if now - last_seen > inactive_threshold
    ]
    for cid in inactive_clients:
        CLIENT_ASSIGNMENTS.pop(cid, None)
        CLIENT_LAST_SEEN.pop(cid, None)
        CLIENT_IP_MAP.pop(cid, None)


class WebLabelHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        return

    def do_GET(self):
        parsed_path = urllib.parse.urlparse(self.path)
        path = parsed_path.path

        if path == "/" or path == "/index.html":
            # Serve the iPhone View
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(IPHONE_PAGE.encode("utf-8"))

        elif path == "/mac" or path == "/mac.html":
            # Serve the Mac View
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(MAC_PAGE.encode("utf-8"))

        elif path.startswith("/image/"):
            filename = urllib.parse.unquote(path.split("/")[-1])
            img_path = IMAGES_DIR / filename
            if img_path.exists():
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.end_headers()
                with open(img_path, "rb") as f:
                    self.wfile.write(f.read())
            else:
                self.send_error(404, "Image not found")

        elif path == "/api/next_info" or path == "/api/current_info":
            # Extract client ID
            import time

            query_params = urllib.parse.parse_qs(parsed_path.query)
            client_id = query_params.get("clientId", ["default"])[0]

            # Store client IP
            client_ip = self.headers.get("X-Forwarded-For", self.client_address[0])
            CLIENT_IP_MAP[client_id] = client_ip
            CLIENT_LAST_SEEN[client_id] = time.time()

            cleanup_inactive_clients()

            labeled = load_existing_labels()
            all_images = sorted([f for f in os.listdir(IMAGES_DIR) if f.endswith(".png")])
            unlabeled_current = [f for f in all_images if f not in labeled]

            total = len(all_images)
            total_labeled = len(labeled)
            total_unlabeled = len(unlabeled_current)

            if total_unlabeled == 0:
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"finished": True}).encode("utf-8"))
                return

            # Get assignment
            target_fn = CLIENT_ASSIGNMENTS.get(client_id)
            if not target_fn or target_fn not in unlabeled_current:
                # Find an unassigned image
                assigned_files = set(CLIENT_ASSIGNMENTS.values())
                unassigned_files = [f for f in unlabeled_current if f not in assigned_files]
                if unassigned_files:
                    target_fn = unassigned_files[0]
                else:
                    target_fn = unlabeled_current[0]
                CLIENT_ASSIGNMENTS[client_id] = target_fn

            img_path = IMAGES_DIR / target_fn
            words, digits = predict_image(MODEL, VOCAB, img_path, DEVICE)

            response_data = {
                "filename": target_fn,
                "model_words": words,
                "model_digits": digits,
                "total": total,
                "labeled": total_labeled,
                "unlabeled": total_unlabeled,
            }

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(response_data).encode("utf-8"))

        elif path == "/api/active_sessions":
            import time

            cleanup_inactive_clients()
            labeled = load_existing_labels()
            all_images = sorted([f for f in os.listdir(IMAGES_DIR) if f.endswith(".png")])
            unlabeled_current = [f for f in all_images if f not in labeled]

            sessions = []
            for cid, fn in list(CLIENT_ASSIGNMENTS.items()):
                if fn in unlabeled_current:
                    img_path = IMAGES_DIR / fn
                    words, digits = predict_image(MODEL, VOCAB, img_path, DEVICE)
                    sessions.append(
                        {
                            "clientId": cid,
                            "ip": CLIENT_IP_MAP.get(cid, "Unknown"),
                            "filename": fn,
                            "words": words,
                            "digits": digits,
                        }
                    )

            response_data = {
                "sessions": sessions,
                "total": len(all_images),
                "labeled": len(labeled),
                "unlabeled": len(unlabeled_current),
            }

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(response_data).encode("utf-8"))

        elif path.startswith("/api/skip"):
            query_params = urllib.parse.parse_qs(parsed_path.query)
            client_id = query_params.get("clientId", ["default"])[0]

            CLIENT_ASSIGNMENTS.pop(client_id, None)
            cleanup_inactive_clients()

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"success": True}).encode("utf-8"))

        else:
            self.send_error(404, "Not found")

    def do_POST(self):
        parsed_path = urllib.parse.urlparse(self.path)
        if parsed_path.path == "/api/submit":
            content_length = int(self.headers["Content-Length"])
            body = self.rfile.read(content_length)
            data = json.loads(body.decode("utf-8"))

            client_id = data.get("clientId", "default")
            filename = data["filename"]
            raw_digits = standardize_digits(data["digits"].strip())
            words = data["words"]

            if not raw_digits.isdigit():
                parsed = persian_words_to_number(raw_digits)
                if parsed and parsed != "0":
                    digits = parsed
                else:
                    digits = raw_digits
            else:
                digits = raw_digits

            # Reconstruct words from digits to ensure 100% consistency and clean spelling
            try:
                words = num_to_persian_words(int(digits))
            except ValueError:
                words = raw_digits

            # Save label
            next_idx = get_next_index()
            save_label(next_idx, filename, words, digits)
            print(f"✅ Saved by {client_id}: {filename} = {digits} ({words})")

            # Reset active assignment for this client
            CLIENT_ASSIGNMENTS.pop(client_id, None)
            cleanup_inactive_clients()

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"success": True}).encode("utf-8"))
        else:
            self.send_error(404, "Not found")


def main():
    print("=" * 60)
    print("  ابزار لیبل‌زنی دوصفحه‌ای تحت وب (مک + آیفون)")
    print("=" * 60)
    print("🔄 بارگذاری مدل...")
    init_model()
    print("✅ مدل بارگذاری شد.")

    local_ip = get_local_ip()
    server_address = ("", 8080)
    httpd = HTTPServer(server_address, WebLabelHandler)

    print()
    print("🚀 سرور وب با موفقیت فعال شد!")
    print(f"🖥 آدرس نمایشگر مک:  http://localhost:8080/mac")
    print(f"📱 آدرس کیپد آیفون:  http://{local_ip}:8080/")
    print("   (هر دو دستگاه باید به یک مودم/وای‌فای وصل باشند)")
    print("   برای خروج، در ترمینال Ctrl+C را فشار دهید.")
    print("-" * 60)

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n👋 سرور متوقف شد.")


if __name__ == "__main__":
    main()
