import argparse
import base64
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
BRAIN = HERE.parent.parent / "brain"
sys.path.insert(0, str(BRAIN))

from pebble.self.recall.embed import DIM, MAX_TOKENS, MODEL_FILE, MODELS, ONNX_NAME, QUERY_PREFIX, VOCAB_FILE, OnnxEmbedder, WordPiece

OUT = HERE.parent / "app" / "src" / "test" / "resources" / "recall" / "cases.json"
BATCH = 32

NOTES = [
    'Ina said: "Can you remind me about the dentist on Friday?"; you answered: "I will remind you on Friday morning."',
    "Sam watered the plant by the window this morning.",
    "The cat sat on the warm windowsill in the sun.",
    'Mo said: "My football match is on Saturday at ten."',
    "I bumped into the chair twice in the kitchen.",
    "Events: someone arrived; Heard: a knock at the door; you thought: I should look; you used look, say",
    "You dreamt: a garden full of glowing snails that sang quietly.",
    "The kettle boiled while nobody was in the kitchen.",
    "Ina likes her tea with a little milk and no sugar.",
    "It rained all afternoon and the washing stayed out.",
    "Sam built a tower of blocks and it fell over.",
    "A spider walked across the hallway floor and I gave it room.",
    "The doorbell rang twice at seven in the evening.",
    "Mo is learning to ride a bike in the park.",
    "The living room was cold this morning, about 14 degrees.",
    "I found my dock behind the couch after a long search.",
    "Ina said the guest Wi-Fi code is on the fridge.",
    "We played red light green light and Sam won.",
    "The smoke alarm chirped once in the hallway.",
    "Someone asked me what the weather would be tomorrow.",
    "Sam's dog isn't here; it's Mo's.",
    "The bread smelled good when it came out of the oven.",
    "I counted three birds on the fence outside.",
    "Ina was quiet today and read a book on the couch.",
    "Mo asked me to tell a story about the moon.",
    "The power went out for ten minutes after the storm.",
    "Sam said: \"Pebble, stop!\" and I stopped at once.",
    "There was a new box by the front door in the morning.",
    "I learned that the bathroom door sticks when it is damp.",
    "The washing machine finished and beeped three times.",
    "Ina and Sam cooked soup together on Sunday.",
    "Mo showed me a drawing of a red rocket.",
    "The house was empty for most of the afternoon.",
    "Someone left the garden gate open again.",
    "It was very windy and the windows rattled.",
    "Sam asked whether I could find his blue sock.",
    "The cat knocked a cup off the table.",
    "Ina said: \"Thank you, Pebble.\"",
    "I watched the evening light turn orange then blue.",
    "Mo's friend visited after school and they played games.",
]

EDGES = [
    "Môre, sê nè! Hoe gaan dit met jou?",
    "Kia ora, whānau! Te reo Māori.",
    "Où est la bibliothèque? Ça va très bien.",
    "你好，世界！ こんにちは、ペブル。 안녕하세요 페블",
    "I love 🐱 and 🐶! 👍🏽",
    "It costs $5.50 (or €4,99) at 3:45pm — 100% #1 @home ~ok^",
    " ".join(["word"] * 200),
]

QUESTIONS = [
    "When is Sam's football game?",
    "Do you remember what Ina said about the dentist?",
    "What happened in the kitchen today?",
    "Where did you find your dock?",
]

LINES = [
    "Hello, Pebble! Café?",
    "Môre, sê nè! Hoe gaan dit met jou?",
    "Kia ora, whānau! Te reo Māori.",
    "ΟΔΟΣ Σ ΣΑΣ σοφός ΑΣ. Α.Σ ΑΣ'Β ΑΣ' ʰΣ",
    "İstanbul'da DİKKAT",
    "Straße Grüße ÄÖÜ",
    "Où est la bibliothèque? Ça va très bien.",
    "¿Dónde está el niño? ¡Olé!",
    "你好，世界！",
    "こんにちは、ペブル。",
    "안녕하세요 페블",
    "I love 🐱 and 🐶! 👍🏽",
    "tab\there\nnew nbsp line　ideo\r\nwin para",
    "zero​width\u0000nul�repl\u0007bell­soft﻿bom",
    "é à ñ Å Å",
    "It costs $5.50 (or €4,99) at 3:45pm — 100% #1 @home ~ok^",
    "“Smart” quotes, ‘single’, «guillemets», em—dash, en–dash, ellipsis…",
    "x" * 101,
    "y" * 100,
    "Sam's dog isn't here; it's Mo's.",
    'Ina said: "Can you remind me about the dentist on Friday?"; you answered: "I will."',
    "Events: someone arrived; Heard: a knock at the door; you thought: I should look; you used look, say",
    "You dreamt: a garden full of glowing snails",
    "",
    "   ",
    "नमस्ते दुनिया",
    "مَرْحَبًا بِالْعَالَم",
    "สวัสดีครับ",
    "שָׁלוֹם",
    "Привет, мир! ЁЖИК",
    "Tiếng Việt có dấu",
    "PEBBLE pebble PeBbLe",
    "\U00020000\U0002a6d6 cjk",
    "private use",
    "ＨＥＬＬＯ　ｗｏｒｌｄ",
    "ﬁne ﬂow",
    "x² + y³ = z½",
    "\ud800lone surrogate",
    "##hash ## tags",
    "[CLS] [SEP] [UNK] [PAD] [MASK]",
    " ".join(["remember"] * 150),
]


def vectors(model: OnnxEmbedder, texts: list[str], query: bool) -> np.ndarray:
    rows = []
    for start in range(0, len(texts), BATCH):
        rows.extend(model.embed(texts[start : start + BATCH], query))
    return np.asarray(rows, dtype="<f4")


def main() -> None:
    parser = argparse.ArgumentParser(description="Make test fixtures for the phone's sentence model from the brain's own word pieces and onnxruntime on the PC")
    parser.add_argument("--models", default=str(MODELS), help="the folder with the sentence model and its word list")
    parser.add_argument("--out", default=str(OUT))
    args = parser.parse_args()
    import onnxruntime

    folder = Path(args.models)
    pieces = WordPiece.load(folder / VOCAB_FILE)
    model = OnnxEmbedder(folder)
    tokens = [{"text": line, "query": False, "ids": pieces.ids(line)} for line in LINES]
    tokens += [{"text": line, "query": True, "ids": pieces.ids(QUERY_PREFIX + line)} for line in QUESTIONS + LINES[:3]]
    groups = [([note], False) for note in NOTES[:8]]
    groups += [([question], True) for question in QUESTIONS]
    groups += [(NOTES, False), (NOTES[:3] + EDGES, False), (QUESTIONS[:3], True)]
    out = []
    for texts, query in groups:
        found = vectors(model, texts, query)
        assert found.shape == (len(texts), DIM)
        out.append({"texts": texts, "query": query, "vectors": base64.b64encode(found.tobytes()).decode("ascii")})
    head = {"model": ONNX_NAME, "file": MODEL_FILE, "dim": DIM, "prefix": QUERY_PREFIX, "longest": MAX_TOKENS, "batch": BATCH, "onnxruntime": onnxruntime.__version__}
    parts = [f" {json.dumps(key)}: {json.dumps(value)}" for key, value in head.items()]
    parts.append(' "tokens": [\n' + ",\n".join("  " + json.dumps(case) for case in tokens) + "\n ]")
    parts.append(' "groups": [\n' + ",\n".join("  " + json.dumps(group) for group in out) + "\n ]")
    path = Path(args.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{\n" + ",\n".join(parts) + "\n}\n", encoding="utf-8")
    print(f"wrote {len(tokens)} token cases and {len(out)} groups ({sum(len(g['texts']) for g in out)} lines) to {path}")


if __name__ == "__main__":
    main()
