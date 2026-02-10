from pathlib import Path
import cv2
import numpy as np


def preprocess_image(input_path: Path, output_path: Path, fast_mode: bool = True):
    img = cv2.imread(str(input_path))
    if img is None:
        raise ValueError("Corrupted or unreadable image")

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    denoised = cv2.fastNlMeansDenoising(gray, None, 12, 7, 21)
    enhanced = cv2.equalizeHist(denoised)
    _, th = cv2.threshold(enhanced, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    if fast_mode:
        h, w = th.shape[:2]
        scale = 1400 / max(h, w) if max(h, w) > 1400 else 1.0
        if scale < 1.0:
            th = cv2.resize(th, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(output_path), th):
        raise RuntimeError("Failed to write preprocessed image")
