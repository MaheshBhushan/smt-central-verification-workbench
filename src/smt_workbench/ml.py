"""Real OpenCV features and sklearn classifier; all source data is synthetic."""
import json
from pathlib import Path
import cv2
import joblib
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, confusion_matrix, classification_report
from sklearn.model_selection import GroupShuffleSplit
from .synthetic import LABELS

FEATURE_NAMES = ["gray_mean", "gray_std", "dark_fraction", "edge_fraction", "laplacian_variance", "height_mm", "volume_mm3"]


def features(path, measurement):
    image = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if image is None:
        raise ValueError("image is not a readable PNG")
    return [float(image.mean()), float(image.std()), float((image < 25).mean()),
            float((cv2.Canny(image, 60, 140) > 0).mean()), float(cv2.Laplacian(image, cv2.CV_64F).var()),
            measurement["height_mm"], measurement["volume_mm3"]]


def train(root: Path, manifest: dict, model_path: Path):
    rows = manifest["records"]
    groups = [r["board_id"] for r in rows]
    x = np.array([features(root / r["image_path"], r) for r in rows])
    y = np.array([r["label"] for r in rows])
    train_idx, test_idx = next(GroupShuffleSplit(n_splits=1, test_size=0.25, random_state=41).split(x, y, groups))
    model = RandomForestClassifier(n_estimators=80, max_depth=6, random_state=41, n_jobs=1)
    model.fit(x[train_idx], y[train_idx])
    predicted = model.predict(x[test_idx])
    report = {"synthetic_only": True, "seed": manifest["seed"], "split": "board-group held-out 25%",
              "train_boards": sorted({groups[i] for i in train_idx}), "test_boards": sorted({groups[i] for i in test_idx}),
              "train_samples": len(train_idx), "test_samples": len(test_idx),
              "accuracy": float(accuracy_score(y[test_idx], predicted)), "labels": list(LABELS),
              "confusion_matrix": confusion_matrix(y[test_idx], predicted, labels=LABELS).tolist(),
              "classification_report": classification_report(y[test_idx], predicted, zero_division=0, output_dict=True),
              "feature_names": FEATURE_NAMES, "feature_importance": dict(zip(FEATURE_NAMES, model.feature_importances_.tolist())),
              "limitations": "Generated defect patterns are intentionally separable. No plant accuracy claim."}
    model_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({"model": model, "report": report, "version": "synthetic-rf-v1"}, model_path)
    model_path.with_suffix(".json").write_text(json.dumps(report, indent=2))
    return report


def load_predictor(path: Path):
    # Only load the model produced locally by the trusted train command; pickle is executable.
    artifact = joblib.load(path)
    model = artifact["model"]

    def predict(image_path, measurement):
        probabilities = model.predict_proba([features(image_path, measurement)])[0]
        index = int(np.argmax(probabilities))
        return {"label": str(model.classes_[index]), "confidence": float(probabilities[index]),
                "probabilities": dict(zip(model.classes_.tolist(), probabilities.tolist())),
                "model_version": artifact["version"], "synthetic_only": True}
    return predict
