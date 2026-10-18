import io
import threading
from functools import lru_cache

import torch
from PIL import Image, UnidentifiedImageError
from torchvision.ops import nms
from transformers import pipeline

MODEL_ID = "google/owlv2-base-patch16-ensemble"
NMS_IOU_THRESHOLD = 0.5
DEFAULT_THRESHOLD = 0.3
MIN_THRESHOLD = 0.05
MAX_THRESHOLD = 0.9

# Keys are model prompts and must stay in English (OWLv2 is trained on English text).
FURNITURE_LABELS = {
    "cabinet": "alacena",
    "mirror": "espejo",
    "under counter": "bajo mesada",
    "kitchen faucet": "griferia cocina",
    "water heater": "termotanque",
    "thermos": "termo",
    "tiled floor": "ceramico",
    "window": "ventana",
    "door": "puerta",
}

_inference_lock = threading.Lock()


class InvalidImageError(ValueError):
    pass


def select_device():
    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


@lru_cache(maxsize=1)
def get_detector():
    return pipeline("zero-shot-object-detection", model=MODEL_ID, device=select_device())


def load_image(data: bytes) -> Image.Image:
    try:
        return Image.open(io.BytesIO(data)).convert("RGB")
    except (UnidentifiedImageError, OSError) as error:
        raise InvalidImageError("Unsupported or corrupted image file") from error


def clamp_threshold(value: float | None) -> float:
    if value is None:
        return DEFAULT_THRESHOLD
    return max(MIN_THRESHOLD, min(MAX_THRESHOLD, value))


def _suppress_overlaps(detections):
    if not detections:
        return []
    boxes = torch.tensor(
        [[d["box"]["xmin"], d["box"]["ymin"], d["box"]["xmax"], d["box"]["ymax"]] for d in detections],
        dtype=torch.float32,
    )
    scores = torch.tensor([d["score"] for d in detections], dtype=torch.float32)
    keep = nms(boxes, scores, NMS_IOU_THRESHOLD)
    return [detections[i] for i in keep.tolist()]


def detect_objects(image: Image.Image, threshold: float = DEFAULT_THRESHOLD) -> list[dict]:
    with _inference_lock:
        detections = get_detector()(
            image, candidate_labels=list(FURNITURE_LABELS), threshold=threshold
        )
    detections = _suppress_overlaps(detections)
    return sorted(
        (
            {
                "code": d["label"],
                "label": FURNITURE_LABELS[d["label"]],
                "confidence": round(float(d["score"]), 3),
                "box": {k: int(d["box"][k]) for k in ("xmin", "ymin", "xmax", "ymax")},
            }
            for d in detections
        ),
        key=lambda o: o["confidence"],
        reverse=True,
    )
