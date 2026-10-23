import argparse
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
WORK = HERE / "export" / "work"
NLTK = HERE / "export" / "nltk_data"
BRAIN_MODELS = HERE.parent / "brain" / "pebble" / "eyes" / "models"
ASSETS = "https://github.com/ultralytics/assets/releases/download/v8.4.0"
LICENCE = "AGPL-3.0 (YOLOE, THU-MIG/yoloe; Ultralytics)"
SOURCES = {
    "yoloe-26n-seg-pf.pt": "ae805a9ac11c85214588b32da8248d68a516e1d071465e1e86a03cbfadb66ba7",
    "yoloe-26s-seg-pf.pt": "01605da3f2e0e5325df45d5f5eef8e40b5b5c7d085399be3c33ac638258b150a",
}

PHYSICAL = {"artifact.n.01", "food.n.01", "food.n.02", "plant.n.02", "animal.n.01", "plant_part.n.01", "fruit.n.01", "vegetable.n.01"}
NOT_AT_HOME = {
    "person.n.01", "body_part.n.01", "building.n.01", "room.n.01", "housing.n.01", "facility.n.01", "location.n.01",
    "geological_formation.n.01", "body_of_water.n.01", "land.n.04", "self-propelled_vehicle.n.01", "aircraft.n.01",
    "vessel.n.02", "train.n.01", "public_transport.n.01", "weapon.n.01", "weaponry.n.01", "establishment.n.04",
    "structure.n.01", "way.n.06", "material.n.01", "substance.n.01", "spacecraft.n.01", "bridge.n.01",
}
HOME_MAMMALS = {
    "dog.n.01", "cat.n.01", "rodent.n.01", "lagomorph.n.01", "bovine.n.01", "sheep.n.01", "goat.n.01", "swine.n.01",
    "equine.n.01", "domestic_animal.n.01", "ferret.n.02", "hedgehog.n.02",
}
ALLOW = {
    "door", "window", "stairs", "staircase", "fireplace", "shelf", "bookshelf", "cupboard", "curtain", "rug", "carpet", "mat", "blanket",
    "pillow", "cushion", "towel", "painting", "picture frame", "poster", "mirror", "plant pot", "flower pot", "scissors", "knife", "candle",
}
GENERIC = {
    "product", "object", "item", "thing", "gadget", "device", "equipment", "machine", "tool", "accessory", "container", "furniture", "food",
    "dish", "meal", "fruit", "vegetable", "plant", "animal", "pet", "toy", "decoration", "art", "artwork", "design", "pattern", "logo",
    "sign", "symbol", "text", "label", "screen", "display", "board", "panel", "frame", "box", "case", "cover", "top", "bottom", "base",
    "part", "piece", "set", "model", "figure", "image", "picture", "photo", "photograph", "illustration", "drawing", "cartoon",
    "rendering", "graphic", "close-up", "beast", "creature", "fauna", "carnivore", "mammal", "invertebrate", "marine invertebrate",
    "marine mammal", "artifact", "article", "material", "media", "home", "decor", "home decor", "collection", "kit", "pack", "package",
    "vehicle", "land vehicle", "instrument", "hardware", "fixture", "utensil", "appliance", "home appliance", "vessel", "unit",
}
NONSENSE = {
    "action film", "animation film", "comedy film", "drama film", "horror film", "science fiction film", "documentary", "tv genre",
    "appointment", "baby", "baby shower", "charity", "client", "call", "coach", "gang", "gathering", "graduate", "guard", "guide", "job",
    "kiss", "leader", "nanny", "painter", "queen", "rapper", "royal", "sailor", "soldier", "spectator", "supporter", "worker", "lumberjack",
    "diver", "conductor", "bishop", "medical staff", "motorcycle racer", "head coach", "baseball pitcher", "shooting basketball guard",
    "adult", "twin", "bite", "crack", "cut", "dance", "drag", "drive", "flip", "mess", "mix", "pull", "push", "read", "release", "shake",
    "washing", "wear", "writing", "play baseball", "play basketball", "play football", "play volleyball", "playing chess", "bike ride",
    "boat ride", "horse ride", "picnic", "shopping", "shipping", "stunt", "scene", "scenery", "landscape", "panorama", "winter scene",
    "street scene", "still life", "evening light", "morning light", "mountain landscape", "nativity scene", "castle", "big ben",
    "prague castle", "manhattan", "galaxy", "nebula", "elevation map", "floor plan", "medical image", "website", "icon", "app icon",
    "number icon", "vector icon", "clip art", "line art", "art vector illustration", "vector cartoon illustration", "cartoon illustration",
    "fashion illustration", "watercolor illustration", "font", "motif", "polka dot", "stripe", "plaid", "monochrome", "khaki", "teal",
    "transparency", "project picture", "publicity portrait", "couple photo", "family photo", "group photo", "team photo", "wedding photo",
    "id photo", "file photo", "old photo", "snapshot", "portrait", "video", "audio", "copy", "publication", "super bowl", "football match",
    "football college game", "game", "emergency", "diet", "fashion", "assembly", "assembly line", "array", "system", "grid", "plan",
    "triangle", "sphere", "cylinder", "cube", "spiral", "loop", "strip", "surface", "water surface", "forest floor", "floor", "glass floor",
    "kitchen floor", "tile flooring", "hardwood floor", "wood floor", "dance floor", "ceiling", "roof", "tile roof", "building facade",
    "facade", "cornice", "siding", "pavement", "tarmac", "curb", "manhole", "manhole cover", "power line", "telegraph pole", "street light",
    "lamp post", "stop light", "traffic cone", "hydrant", "flag pole", "lightning rod", "wind turbine", "windmill", "water tower", "turbine",
    "dam", "satellite", "rocket", "submarine", "schooner", "arm", "back", "face", "head", "jaw", "leg", "limb", "lap", "neck", "nose",
    "shoulder", "skin", "toe", "vein", "rib", "freckle", "tattoo", "braid", "lash", "crop", "pasture", "plain", "landing", "mine",
    "excavation", "archaelogical excavation", "pool", "puddle", "reef", "shore", "inlet", "tide pool", "sea ice", "iceberg", "mound",
    "moat", "quarry", "reservoir", "track", "race track", "railroad", "train track", "rail", "airport runway", "construction site",
    "cinema", "store", "storefront", "shopfront", "pet store", "fabric store", "sushi bar", "delicatessen", "information desk",
    "reception", "stage", "catwalk", "carousel", "ferris wheel", "amusement ride", "chairlift", "ski lift", "elevator", "escalator",
    "oilrig", "loading dock", "dock", "deck", "boat deck", "landing deck", "platform", "scaffold", "space station", "space shuttle",
    "bomber", "plane", "boat", "inflatable boat", "swan boat", "fish boat", "raft", "car", "truck", "lorry", "van", "sedan", "convertible",
    "concept car", "muscle car", "monster truck", "family car", "emergency vehicle", "food truck", "decker bus", "bus", "city bus",
    "tour bus", "railcar", "train car", "cabin car", "trailer", "stagecoach", "chariot", "rickshaw", "sidecar", "harvester", "excavator",
    "steam engine", "transporter", "cargo", "drive", "electric chair", "coffin", "bomb", "cannon", "spear", "shield", "armor",
    "chain mail", "bulletproof vest", "gasmask", "handcuff", "pall", "pulpit", "throne", "altar", "crucifix", "bible", "tee",
    "underdrawers", "screenshot", "selfie", "bomb", "cigarette case", "condom", "syringe", "urinal", "bedpan", "crown", "tiara",
}

UNKNOWN_TO_WORDNET = {
    "American shorthair": ("cat", True, 14), "english shorthair": ("cat", True, 14), "bichon": ("dog", True, 14),
    "pitbull": ("dog", True, 14), "shiba inu": ("dog", True, 14), "koi": ("koi", True, 12), "bento": ("bento box", False, 9),
    "binocular": ("binoculars", False, 10), "barbie": ("doll", False, 9), "smartphone": ("smartphone", False, 11),
    "iphone": ("smartphone", False, 11), "ipad": ("tablet computer", False, 11), "dishsoap": ("dish soap", False, 8),
    "droplight": ("hanging lamp", False, 9), "flip-flop": ("flip-flop", False, 9), "flipchart": ("flipchart", False, 9),
    "foosball": ("table football", False, 9), "hoodie": ("hoodie", False, 10), "hoverboard": ("hoverboard", False, 10),
    "humidifier": ("humidifier", False, 9), "longboard": ("longboard", False, 10), "mandarine": ("mandarin", False, 10),
    "motherboard": ("circuit board", False, 10), "nightstand": ("bedside table", False, 10), "pitaya": ("dragon fruit", False, 10),
    "starfruit": ("star fruit", False, 10), "t-shirt": ("t-shirt", False, 10), "tatami": ("tatami mat", False, 9),
    "tong": ("tongs", False, 9), "totoro": ("soft toy", False, 9), "gundam": ("toy robot", False, 9), "ultraman": ("action figure", False, 9),
    "wetsuit": ("wetsuit", False, 10), "whiteboard": ("whiteboard", False, 9), "Wii": ("game console", False, 10),
    "clothe": ("clothes", False, 7), "baby clothe": ("baby clothes", False, 8), "baozi": ("bun", False, 8), "zongzi": ("rice dumpling", False, 9),
    "toy": ("toy", False, 8), "toy car": ("toy car", False, 10), "plug": ("plug", False, 9), "power plugs and sockets": ("plug socket", False, 9),
    "socket": ("socket", False, 9),
}
RENAME = {
    "tong": "tongs", "t shirt": "t-shirt", "hair drier": "hair dryer", "dinning table": "dining table", "icecream": "ice cream",
    "teddy": "teddy bear", "crapper": "toilet", "mac": "computer", "remote": "remote control", "refrigerator": "fridge",
    "donut": "doughnut", "cellphone": "mobile phone", "tv cabinet": "tv stand",
}


def wordnet():
    import nltk

    nltk.data.path.insert(0, str(NLTK))
    try:
        from nltk.corpus import wordnet as wn

        wn.synsets("cup")
    except LookupError:
        nltk.download("wordnet", download_dir=str(NLTK), quiet=True)
        from nltk.corpus import wordnet as wn
    return wn


def closure(synset) -> set[str]:
    names: set[str] = set()
    for path in synset.hypernym_paths():
        names.update(s.name() for s in path)
    return names


def judge(wn, raw: str):
    if raw in UNKNOWN_TO_WORDNET:
        label, animal, depth = UNKNOWN_TO_WORDNET[raw]
        return {"raw": raw, "label": label, "animal": animal, "depth": depth}
    name = " ".join(raw.lower().split())
    if any(ch.isdigit() for ch in name) or name in GENERIC or name in NONSENSE:
        return None
    synsets = wn.synsets(name.replace(" ", "_").replace("-", "_"), pos=wn.NOUN)
    guessed = False
    if not synsets and " " in name:
        synsets = wn.synsets(name.split()[-1], pos=wn.NOUN)
        guessed = True
    if not synsets:
        return None
    alive = not guessed or name.split()[0] in {"baby", "pet", "house", "domestic", "young", "little", "small"}
    for synset in synsets[:4]:
        up = closure(synset)
        if not up & PHYSICAL:
            continue
        if name not in ALLOW:
            if up & NOT_AT_HOME and not {"food.n.01", "food.n.02", "animal.n.01", "plant.n.02"} & up:
                return None
            if "mammal.n.01" in up and not up & HOME_MAMMALS:
                return None
        return {"raw": raw, "label": RENAME.get(name, name), "animal": alive and "animal.n.01" in up, "depth": synset.min_depth() + int(guessed)}
    return None


def coco_depths(wn) -> dict[str, int]:
    sys.path.insert(0, str(HERE.parent / "brain"))
    from pebble.eyes.labels import COCO

    depths = {}
    for label in sorted({v for v in COCO.values() if v}):
        synsets = wn.synsets(label.replace(" ", "_"), pos=wn.NOUN) or wn.synsets(label.split()[-1], pos=wn.NOUN)
        physical = [s for s in synsets[:4] if closure(s) & PHYSICAL]
        depths[label] = (physical or synsets)[0].min_depth() if synsets else 6
    return depths


def prune(model, keep: list[int]) -> None:
    import torch
    import torch.nn as nn

    index = torch.tensor(keep, dtype=torch.long)
    head = model.model.model[-1]
    for name in ("lrpc", "one2one_lrpc"):
        for lrpc in getattr(head, name, None) or []:
            vocab = lrpc.vocab
            if isinstance(vocab, nn.Linear):
                small = nn.Linear(vocab.in_features, len(keep))
            else:
                small = nn.Conv2d(vocab.in_channels, len(keep), 1)
            small.weight.data = vocab.weight.data[index].clone()
            small.bias.data = vocab.bias.data[index].clone()
            lrpc.vocab = small
    head.nc = len(keep)
    if hasattr(head, "no"):
        head.no = head.nc + head.reg_max * 4
    names = {i: model.names[k] for i, k in enumerate(keep)}
    model.model.names = names


def sha256(path: Path) -> str:
    sha = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            sha.update(chunk)
    return sha.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="Export YOLOE prompt-free (built-in vocabulary) to ONNX for Pebble's slow lane, with the vocabulary cut down to things found in a home.")
    parser.add_argument("--model", default="yoloe-26s-seg-pf.pt")
    parser.add_argument("--imgsz", type=int, default=320)
    parser.add_argument("--out", default=str(BRAIN_MODELS))
    parser.add_argument("--name", default="objects")
    parser.add_argument("--full", action="store_true", help="keep all 4585 classes (no home vocabulary)")
    args = parser.parse_args()

    import onnx
    import ultralytics
    from ultralytics import YOLOE

    out = Path(args.out).resolve()
    WORK.mkdir(parents=True, exist_ok=True)
    os.chdir(WORK)
    wn = wordnet()
    model = YOLOE(args.model)
    pinned = SOURCES.get(args.model)
    if pinned and sha256(WORK / args.model) != pinned:
        print(f"{args.model} does not match its pinned SHA-256; delete it from {WORK} and run again", file=sys.stderr)
        return 1
    names = [model.names[i] for i in range(len(model.names))]
    judged = [None if args.full else judge(wn, raw) for raw in names]
    if args.full:
        judged = [{"raw": raw, "label": raw.lower(), "animal": False, "depth": 6} for raw in names]
    keep = [i for i, item in enumerate(judged) if item]
    classes = [judged[i] for i in keep]
    print(f"vocabulary: {len(names)} built-in names, {len(keep)} kept for a home")
    if not args.full:
        prune(model, keep)
    exported = Path(model.export(format="onnx", imgsz=args.imgsz, opset=17, simplify=True, dynamic=False))
    out.mkdir(parents=True, exist_ok=True)
    onnx_path = out / f"{args.name}.onnx"
    graph = onnx.load(str(exported))
    first = graph.graph.output[0].name
    trimmed = WORK / "trimmed.onnx"
    onnx.utils.extract_model(str(exported), str(trimmed), [graph.graph.input[0].name], [first])
    shutil.move(str(trimmed), onnx_path)
    channels = onnx.load(str(onnx_path)).graph.output[0].type.tensor_type.shape.dim[1].dim_value
    if channels != 4 + len(classes) + 32:
        print(f"unexpected output layout: {channels} channels for {len(classes)} classes", file=sys.stderr)
        return 1
    source = WORK / args.model
    vocab = {
        "model": args.model,
        "licence": LICENCE,
        "source": f"{ASSETS}/{args.model}",
        "source_sha256": sha256(source) if source.exists() else None,
        "ultralytics": ultralytics.__version__,
        "imgsz": args.imgsz,
        "layout": {"boxes": 4, "classes": len(classes), "mask": 32, "anchors_last": True, "scores": "probability"},
        "classes": classes,
        "coco_depth": coco_depths(wn),
    }
    vocab_path = out / f"{args.name}_vocab.json"
    vocab_path.write_text(json.dumps(vocab, indent=1, ensure_ascii=False), encoding="utf-8")
    for path in (onnx_path, vocab_path):
        print(f'{path.name}: {path.stat().st_size} bytes, SHA-256 {sha256(path)}')
    return 0


if __name__ == "__main__":
    sys.exit(main())
