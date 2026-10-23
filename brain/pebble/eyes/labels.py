COCO_NAMES = (
    "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train", "truck", "boat", "traffic light",
    "fire hydrant", "stop sign", "parking meter", "bench", "bird", "cat", "dog", "horse", "sheep", "cow",
    "elephant", "bear", "zebra", "giraffe", "backpack", "umbrella", "handbag", "tie", "suitcase", "frisbee",
    "skis", "snowboard", "sports ball", "kite", "baseball bat", "baseball glove", "skateboard", "surfboard", "tennis racket", "bottle",
    "wine glass", "cup", "fork", "knife", "spoon", "bowl", "banana", "apple", "sandwich", "orange",
    "broccoli", "carrot", "hot dog", "pizza", "donut", "cake", "chair", "couch", "potted plant", "bed",
    "dining table", "toilet", "tv", "laptop", "mouse", "remote", "keyboard", "cell phone", "microwave", "oven",
    "toaster", "sink", "refrigerator", "book", "clock", "vase", "scissors", "teddy bear", "hair drier", "toothbrush",
)
PERSON = 0
RENAMED = {
    "handbag": "bag",
    "sports ball": "ball",
    "tennis racket": "racket",
    "wine glass": "glass",
    "donut": "doughnut",
    "potted plant": "plant",
    "dining table": "table",
    "mouse": "computer mouse",
    "remote": "remote control",
    "cell phone": "phone",
    "refrigerator": "fridge",
    "hair drier": "hair dryer",
}
NOT_AT_HOME = {
    "person", "motorcycle", "airplane", "bus", "train", "truck", "boat", "traffic light", "fire hydrant", "stop sign",
    "parking meter", "elephant", "bear", "zebra", "giraffe", "skis", "snowboard", "kite", "baseball bat", "baseball glove",
    "surfboard",
}
COCO = {raw: (None if raw in NOT_AT_HOME else RENAMED.get(raw, raw)) for raw in COCO_NAMES}
COCO_ANIMALS = {"bird", "cat", "dog", "horse", "sheep", "cow"}


def coco_label(index: int) -> tuple[str | None, bool]:
    if not 0 <= index < len(COCO_NAMES):
        return None, False
    raw = COCO_NAMES[index]
    return COCO[raw], raw in COCO_ANIMALS
