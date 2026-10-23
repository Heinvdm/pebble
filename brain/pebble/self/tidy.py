import asyncio
import json
import logging
import re

from ..mind.base import CallOptions, MindInterrupted, MindUnavailable
from ..mind.select import unknown_names
from .notes import Notes
from .recall.vectors import cosines, pack

log = logging.getLogger(__name__)

SAME = 0.9
NEAREST = 10
TIDY_MOST = 5
TIDY_IMPORTANCE = 4
SYSTEM = (
    "You keep a few short notes for yourself, {name}: lasting facts about your home, the people in it and your days. "
    "You see your notes and one new memory. Choose one small change: add a note, update one, delete one that is wrong or no longer true, or none. "
    "Never rewrite everything. A note is one plain sentence of at most 25 words. What someone else said stays their words: write 'Sam said ...', never as your own belief. "
    'Reply with JSON only, like {{"op": "add", "text": "..."}} or {{"op": "update", "id": "n3", "text": "..."}} or {{"op": "delete", "id": "n3"}} or {{"op": "none"}}.'
)
GRAMMAR = (
    'root ::= "{" space "\\"op\\":" space op ( "," space "\\"id\\":" space string )? ( "," space "\\"text\\":" space string )? space "}"\n'
    'op ::= "\\"add\\"" | "\\"update\\"" | "\\"delete\\"" | "\\"none\\""\n'
    'string ::= "\\"" [^"\\\\\\n]* "\\""\n'
    'space ::= " "?'
)


def parse(text: str) -> dict:
    found = re.search(r"\{.*\}", text or "", re.DOTALL)
    if not found:
        return {"op": "none"}
    try:
        value = json.loads(found.group(0))
    except ValueError:
        return {"op": "none"}
    return value if isinstance(value, dict) else {"op": "none"}


async def nearest(notes: Notes, embedder, text: str) -> list[tuple[str, str, float | None]]:
    if not notes.items:
        return []
    texts = [item["text"] for item in notes.items]
    try:
        rows = await asyncio.to_thread(embedder.embed, texts + [text], False)
    except Exception as error:
        log.warning("could not turn the notes into numbers: %s", error)
        rows = []
    if len(rows or []) != len(texts) + 1:
        return [(item["id"], item["text"], None) for item in notes.items[-NEAREST:]]
    scores = cosines(rows[-1], [pack(row) for row in rows[:-1]])
    ranked = sorted(zip(notes.items, scores), key=lambda pair: -pair[1])[:NEAREST]
    return [(item["id"], item["text"], score) for item, score in ranked]


async def tidy(notes: Notes, stream, embedder, mind, known=None, most: int = TIDY_MOST) -> dict:
    fresh = sorted((r for r in stream.records.values() if r.t > notes.tidied_t and r.mark == "" and r.importance >= TIDY_IMPORTANCE and r.kind in ("happened", "fact", "feeling", "dream")), key=lambda r: r.t)
    report: dict = {"looked": 0, "changed": [], "refused": [], "unranked": 0}
    if mind is None:
        return report
    for record in fresh[:most]:
        near = await nearest(notes, embedder, record.text)
        ranked = all(score is not None for _, _, score in near)
        twin = near[0][0] if near and ranked and near[0][2] >= SAME else None
        shown = "\n".join(f"{note_id}: {text}" for note_id, text, _ in near) or "(none yet)"
        messages = [
            {"role": "system", "content": SYSTEM.format(name=notes.name)},
            {"role": "user", "content": f"Your notes:\n{shown}\n\nNew memory: {record.text}\n\nOne change, as JSON:"},
        ]
        try:
            reply = await mind.chat(messages, purpose="summary", max_tokens=90, options=CallOptions(kind="steady", grammar=GRAMMAR))
        except MindInterrupted:
            break
        except MindUnavailable as error:
            report["error"] = str(error)
            break
        report["looked"] += 1
        report["unranked"] += 0 if ranked else 1
        notes.tidied_t = record.t
        op = parse(reply.text)
        strange = unknown_names(str(op.get("text") or ""), known() if known is not None else (), record.text, notes.name) if op.get("op") in ("add", "update") else []
        if strange:
            report["refused"].append({"ok": False, "op": op.get("op"), "error": "it names someone or something you don't know: " + ", ".join(strange)})
            continue
        result = notes.apply(op, twin, record.id)
        if result.get("ok") and result.get("op") != "none":
            report["changed"].append(result)
        elif not result.get("ok"):
            report["refused"].append(result)
    notes.save()
    return report
