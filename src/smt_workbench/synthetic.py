"""Seeded fictional AOI crops and independent synthetic 3D measurements."""
import hashlib
import json
from pathlib import Path
import cv2
import numpy as np

LABELS = ("false_call", "real_defect")


def generate(root: Path, *, boards=120, seed=17, prefix="training"):
    rng = np.random.default_rng(seed)
    records = []
    folder = root / prefix
    folder.mkdir(parents=True, exist_ok=True)
    for board in range(boards):
        board_offset = rng.normal(0, 3)
        for site in range(2):
            label = LABELS[int(rng.integers(0, 2))]
            image = np.clip(rng.normal(43 + board_offset, 6, (96, 128, 3)), 0, 255).astype(np.uint8)
            cv2.rectangle(image, (27, 25), (101, 71), (76, 85, 80), -1)
            cv2.rectangle(image, (35, 35), (93, 61), (150, 150, 150), -1)
            for x in (23, 99):
                for y in (31, 47, 63):
                    cv2.rectangle(image, (x, y), (x + 7, y + 6), (210, 215, 220), -1)
            if label == "real_defect":
                x = int(rng.integers(46, 80))
                cv2.line(image, (x, 30), (x + 5, 68), (8, 10, 9), int(rng.integers(3, 8)))
                height = float(rng.normal(0.85, 0.12))
                volume = float(rng.normal(0.24, 0.035))
            else:
                cv2.circle(image, (int(rng.integers(44, 85)), 43), 3, (220, 220, 220), -1)
                height = float(rng.normal(0.48, 0.065))
                volume = float(rng.normal(0.14, 0.02))
            name = f"{prefix}/{board:05d}-U{site + 1}.png"
            if not cv2.imwrite(str(root / name), image):
                raise OSError("failed to write synthetic image")
            records.append({"board_id": f"{prefix}-{board:05d}", "site_id": f"U{site + 1}",
                            "image_path": name, "sha256": hashlib.sha256((root / name).read_bytes()).hexdigest(),
                            "height_mm": max(0.01, height), "volume_mm3": max(0.01, volume), "label": label})
    manifest = {"seed": seed, "synthetic": True, "boards": boards, "records": records}
    (folder / "manifest.json").write_text(json.dumps(manifest, indent=2))
    return manifest
