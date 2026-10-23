import argparse
import asyncio
import json
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from ..mind.lawful import lawful
from ..mind.llama import LlamaServerMind
from ..mind.profile import ModelProfile
from .context import context_from
from .model import ModelReader
from .request import ACTIONS, KINDS, BadRequest, from_dict
from .resolve import Reading
from .understanding import MODEL_LEADS, RULES_FIRST, Understanding

HERE = Path(__file__).resolve().parent
EVAL_SET = HERE / "eval_set.jsonl"
SETS = {
    "main": EVAL_SET,
    "holdout": HERE / "eval_holdout.jsonl",
    "fresh": HERE / "eval_fresh.jsonl",
    "things": HERE / "eval_things.jsonl",
    "things_fresh": HERE / "eval_things_fresh.jsonl",
    "alive": HERE / "eval_alive.jsonl",
    "alive_fresh": HERE / "eval_alive_fresh.jsonl",
    "flex": HERE / "eval_flex.jsonl",
}
NUMBER_SLOTS = ("metres", "degrees", "seconds")
NUMBERS = frozenset(NUMBER_SLOTS + ("in_s", "every_s", "minutes", "level", "every_weeks", "month_day", "times", "repeat"))
TARGET_KINDS = frozenset({"check", "watch"})
TALK = frozenset({"chat", "other"})
STRUCTURE = ("when", "on", "while", "if")
LABELS = frozenset({"name"})
STOP_WORDS = frozenset(
    "a an the to is are be it its that this of for and or my your me you i we us our they them their he him his she her will would please just so then "
    "says said say tell remind about at on in".split()
)
LONG_WAIT_S = 120.0
TURN_DEG = {"little": 30.0, "lot": 135.0, "": 90.0}


def load(path: Path = EVAL_SET) -> list[dict]:
    items = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            items.append(json.loads(line))
    return items


LOOSE = frozenset({"thing", "what", "place", "target"})
EVERY_DAY = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def _loose(expected, got) -> bool:
    return _same(expected, got) or (bool(content(got)) and text_matches(expected, got))


def _same(expected, got) -> bool:
    if isinstance(expected, (int, float)) and not isinstance(expected, bool):
        try:
            got = float(got or 0)
        except (TypeError, ValueError):
            return False
        return abs(got - expected) <= max(0.2 * abs(expected), 0.01)
    return str(expected).strip().lower() == str(got or "").strip().lower()


def _stem(word: str) -> str:
    for end in ("ing", "ed", "es", "s"):
        if word.endswith(end) and len(word) - len(end) >= 3:
            return word[: -len(end)]
    return word


def content(text) -> set:
    words = re.findall(r"[a-z0-9]+", str(text or "").lower().replace("'", ""))
    return {_stem(w) for w in words if w not in STOP_WORDS}


def text_matches(expected, got) -> bool:
    want = content(expected)
    if not want:
        return True
    have = content(got)
    return len(want & have) * 3 >= 2 * len(want)


def _expand(steps: list[dict]) -> list[dict]:
    out = []
    for step in steps:
        step = dict(step)
        repeat = int(step.pop("repeat", 1) or 1)
        if step.get("kind") == "turn" and repeat > 1:
            base = float(step.get("degrees") or (180.0 if step.get("way") == "around" else TURN_DEG.get(step.get("amount", ""), 90.0)))
            if base * repeat <= 720:
                step["degrees"] = base * repeat
                step.pop("amount", None)
                repeat = 1
        if step.get("kind") == "if":
            step["then"] = _expand(step.get("then") or [])
            step["else"] = _expand(step.get("else") or [])
        out.extend([step] * repeat)
    return out


def _target(step: dict) -> dict:
    if step.get("kind") in TARGET_KINDS:
        step = dict(step)
        target = step.pop("thing", "") or step.pop("place", "") or step.pop("who", "")
        step.pop("thing", None)
        step.pop("place", None)
        step.pop("who", None)
        if target:
            step["target"] = target
    return step


def canon(reading: dict) -> dict:
    extra = {key: reading[key] for key in ("ask", "speaker", "too_much") if key in reading}
    body = {key: value for key, value in reading.items() if key not in extra}
    try:
        body = from_dict(body).as_dict()
    except BadRequest:
        pass
    if body.get("kind") == "if":
        body["then"] = [_target(step) for step in _expand(body.get("then") or [])]
        body["else"] = [_target(step) for step in _expand(body.get("else") or [])]
    else:
        then = body.pop("then", []) or []
        chain = _expand([body] + list(then))
        body = dict(chain[0])
        if len(chain) > 1:
            body["then"] = chain[1:]
        body = _target(body)
        if body.get("then"):
            body["then"] = [_target(step) for step in body["then"]]
    return {**body, **extra}


def _cond_matches(expected: dict, got: dict) -> list[str]:
    if not isinstance(got, dict):
        return [f"condition {got!r} != {expected!r}"]
    for join in ("all", "any"):
        if join in expected:
            parts = got.get(join)
            if not isinstance(parts, list) or len(parts) != len(expected[join]):
                return [f"condition {json.dumps(got)} != {json.dumps(expected)}"]
            return _unordered(expected[join], parts, _cond_matches, "condition part")
    if "not" in expected:
        if "not" not in got:
            return [f"condition {json.dumps(got)} != {json.dumps(expected)}"]
        return _cond_matches(expected["not"], got["not"])
    if "state" not in got or got.get("state") != expected.get("state"):
        return [f"state {got.get('state', json.dumps(got))!r} != {expected.get('state')!r}"]
    misses = []
    for key, value in expected.items():
        if key in ("state",) or key in LABELS:
            continue
        if key == "is":
            continue
        if key in LOOSE and _loose(value, got.get(key)):
            continue
        if not _same(value, got.get(key, 0 if key in NUMBERS else "")):
            misses.append(f"{expected['state']}.{key} {got.get(key)!r} != {value!r}")
    if expected.get("state") == "result" and (expected.get("is") or "yes") != (got.get("is") or "yes"):
        misses.append(f"result.is {got.get('is') or 'yes'!r} != {expected.get('is') or 'yes'!r}")
    return misses


def _unordered(expected: list, got: list, match, what: str) -> list[str]:
    left = list(got)
    misses = []
    for want in expected:
        found = next((item for item in left if not match(want, item)), None)
        if found is None:
            misses.append(f"no {what} like {json.dumps(want)}")
        else:
            left.remove(found)
    return misses


def _trigger_matches(expected: dict, got) -> list[str]:
    if not isinstance(got, dict):
        return [f"event {got!r} != {json.dumps(expected)}"]
    if "first_of" in expected:
        items = got.get("first_of")
        if not isinstance(items, list) or len(items) != len(expected["first_of"]):
            return [f"event {json.dumps(got)} != {json.dumps(expected)}"]
        return _unordered(expected["first_of"], items, _trigger_matches, "event")
    if got.get("event") != expected.get("event"):
        return [f"event {got.get('event', json.dumps(got))!r} != {expected.get('event')!r}"]
    misses = []
    for key, value in expected.items():
        if key == "event":
            continue
        if key in LOOSE and _loose(value, got.get(key)):
            continue
        if not _same(value, got.get(key, 0 if key in NUMBERS else "")):
            misses.append(f"event.{key} {got.get(key)!r} != {value!r}")
    return misses


def _when_matches(expected: dict, got) -> list[str]:
    if not isinstance(got, dict):
        return [f"when {got!r} != {json.dumps(expected)}"]
    misses = []
    if got.get("every_s") == 86400 and not got.get("from") and not got.get("days"):
        got = {**{k: v for k, v in got.items() if k != "every_s"}, "days": EVERY_DAY}
    for key, value in expected.items():
        have = got.get(key)
        if key == "days":
            if sorted(value) != sorted(have or []):
                misses.append(f"when.days {have!r} != {value!r}")
        elif not _same(value, have if have is not None else (0 if key in NUMBERS else "")):
            misses.append(f"when.{key} {have!r} != {value!r}")
    return misses


def _steps_match(name: str, wanted: list, have: list) -> list[str]:
    if len(wanted) != len(have):
        return [f"{name} has {len(have)} steps, wanted {len(wanted)}"]
    misses = []
    for want, step in zip(wanted, have):
        misses.extend(f"{name}: {miss}" for miss in _match(want, step))
    return misses


def _match(expected: dict, got: dict) -> list[str]:
    if expected.get("kind") in TALK and got.get("kind") in TALK:
        got = {**got, "kind": expected.get("kind")}
    if expected.get("kind") != got.get("kind"):
        return [f"kind {got.get('kind')} != {expected.get('kind')}"]
    misses = []
    for key, value in expected.items():
        if key in ("kind", "then", "else") or key in STRUCTURE:
            continue
        if key == "name" and expected.get("kind") == "check":
            continue
        if key == "text":
            if not text_matches(value, got.get("text")):
                misses.append(f"text {got.get('text')!r} != {value!r}")
            continue
        if key == "until" and isinstance(value, dict):
            misses.extend(_trigger_matches(value, got.get("until")))
            continue
        if key == "target" and _loose(value, got.get("target")):
            continue
        if not _same(value, got.get(key, 0 if key in NUMBERS else "")):
            misses.append(f"{key} {got.get(key)!r} != {value!r}")
    for key in STRUCTURE:
        if key in expected:
            if key not in got:
                misses.append(f"no {key}, wanted {json.dumps(expected[key])}")
            elif key == "when":
                misses.extend(_when_matches(expected[key], got[key]))
            elif key == "on":
                misses.extend(_trigger_matches(expected[key], got[key]))
            else:
                misses.extend(_cond_matches(expected[key], got[key]))
        elif key in got:
            misses.append(f"unexpected {key} {json.dumps(got[key])}")
    if "repeat" in got and "repeat" not in expected:
        misses.append(f"unexpected repeat {got['repeat']}")
    misses.extend(_steps_match("then", expected.get("then") or [], got.get("then") or []))
    if expected.get("kind") == "if" or got.get("kind") == "if":
        misses.extend(_steps_match("else", expected.get("else") or [], got.get("else") or []))
    return misses


def step_matches(expected: dict, got: dict) -> list[str]:
    return _match(canon(expected), canon(got))


def fired(reading: dict) -> bool:
    return reading.get("kind") in ACTIONS and not reading.get("ask")


@dataclass
class Score:
    total: int = 0
    right: int = 0
    core_total: int = 0
    core_right: int = 0
    not_command_total: int = 0
    false_fires: list = field(default_factory=list)
    misses: list = field(default_factory=list)
    groups: dict = field(default_factory=dict)
    seconds: float = 0.0
    times: list = field(default_factory=list)
    asked_model: int = 0

    def add(self, item: dict, got: dict, misses: list[str]) -> None:
        ok = not misses
        self.total += 1
        self.right += ok
        group = self.groups.setdefault(item.get("group", "?"), [0, 0])
        group[0] += 1
        group[1] += ok
        if item.get("core"):
            self.core_total += 1
            self.core_right += ok
        if item.get("group") in ("not_command", "never"):
            self.not_command_total += 1
            if fired(got):
                self.false_fires.append((item["id"], item["text"], got))
        if misses:
            self.misses.append((item["id"], item["text"], item.get("expect"), got, misses))

    @property
    def accuracy(self) -> float:
        return self.right / self.total if self.total else 0.0

    @property
    def core_accuracy(self) -> float:
        return self.core_right / self.core_total if self.core_total else 0.0

    def timing(self) -> str:
        if not self.times:
            return ""
        ordered = sorted(self.times)
        middle = ordered[len(ordered) // 2]
        high = ordered[min(len(ordered) - 1, int(round(0.95 * (len(ordered) - 1))))]
        return f"time: {self.seconds:.1f} s ({self.seconds / max(1, self.total):.2f} s a line; median {middle:.2f} s, 95% within {high:.2f} s; the model read {self.asked_model} of {self.total})"

    def report(self, label: str, show: int = 40) -> str:
        lines = [
            f"{label}: {self.right}/{self.total} right ({self.accuracy:.1%}); core {self.core_right}/{self.core_total} ({self.core_accuracy:.1%}); "
            f"commands fired on the {self.not_command_total} not-a-command lines: {len(self.false_fires)}",
            "by group: " + ", ".join(f"{name} {ok}/{n}" for name, (n, ok) in sorted(self.groups.items())),
        ]
        if self.seconds:
            lines.append(self.timing())
        for ident, text, got in self.false_fires:
            lines.append(f"  FIRED #{ident} {text!r} -> {json.dumps(got)}")
        for ident, text, expected, got, misses in self.misses[:show]:
            lines.append(f"  #{ident} {text!r}: {'; '.join(misses)} | got {json.dumps(got)} | want {json.dumps(expected)}")
        return "\n".join(lines)


async def score(items: list[dict], reader) -> Score:
    result = Score()
    loop = asyncio.get_running_loop()
    start = loop.time()
    for item in items:
        ctx = context_from(item.get("context"))
        began = time.perf_counter()
        reading = await reader(item["text"], ctx)
        result.times.append(time.perf_counter() - began)
        if reading.source not in ("rules", "household"):
            result.asked_model += 1
        got = reading.as_dict()
        result.add(item, got, step_matches(item["expect"], got) + _extra(item["expect"], got) + _ranges(item.get("ranges"), got))
    result.seconds = loop.time() - start
    return result


def _ranges(ranges: dict | None, got: dict) -> list[str]:
    misses = []
    for key, (low, high) in (ranges or {}).items():
        try:
            value = float(got.get(key) or 0)
        except (TypeError, ValueError):
            value = 0.0
        if not low <= value <= high:
            misses.append(f"{key} {got.get(key)!r} not within {low} to {high}")
    return misses


def _extra(expected: dict, got: dict) -> list[str]:
    misses = []
    for key in ("ask", "speaker", "too_much"):
        if key not in expected and got.get(key):
            misses.append(f"unexpected {key} {got.get(key)!r}")
    return misses


def rules_reader():
    understanding = Understanding()

    async def read(text, ctx) -> Reading:
        return await understanding.read(text, ctx)

    return read


def model_reader(reader: ModelReader, label: str):
    understanding = Understanding(reader, MODEL_LEADS)

    async def read(text, ctx) -> Reading:
        modelled = await reader.read(text, ctx, (label,))
        if modelled is None:
            return Reading(from_dict({"kind": "other"}), source="none")
        return understanding.from_model(modelled, ctx, text)

    return read


def pipeline_reader(reader: ModelReader, mode: str = MODEL_LEADS, wait_s: float | None = LONG_WAIT_S):
    understanding = Understanding(reader, mode)

    async def read(text, ctx) -> Reading:
        return await understanding.read(text, ctx, wait_s)

    return read


def chooser_for(count: int):
    if count <= 0:
        return None
    from ..self.recall.embed import embedder_from
    from .examples import Chooser

    return Chooser(embedder_from("auto"), count)


def mind_for(url: str, label: str, model: str):
    data = {"name": label, "endpoint": url, "model": model, "tools": False, "max_reply_tokens": 200, "timeout_s": 120}
    return lawful(LlamaServerMind(ModelProfile.from_dict(data)))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m pebble.understand.eval", description="Score the request interpreters on the evaluation set")
    parser.add_argument("--set", default="all", help="main, holdout, fresh, things, things_fresh, alive, alive_fresh, flex, all (default) or a path to a JSON lines file")
    parser.add_argument("--sub", default=None, help="llama-server URL of the small subconscious model, e.g. http://127.0.0.1:8081")
    parser.add_argument("--main", default=None, help="llama-server URL of the main model, e.g. http://127.0.0.1:8080")
    parser.add_argument("--pipeline", action="store_true", help="also score the full pipeline (the front door, then the models)")
    parser.add_argument("--mode", choices=(MODEL_LEADS, RULES_FIRST, "both"), default=MODEL_LEADS, help="which pipeline to score with --pipeline")
    parser.add_argument("--wait", type=float, default=LONG_WAIT_S, help="how long the pipeline waits for the model before the rules stand (Pebble waits 3 s)")
    parser.add_argument("--readers", default="rules,model,pipeline", help="which readers to score, comma separated (rules, model, pipeline)")
    parser.add_argument("--only", choices=("all", "core", "not_command"), default="all")
    parser.add_argument("--show", type=int, default=40, help="how many misses to list")
    parser.add_argument("--save", default=None, help="write every reading to this JSON lines file")
    parser.add_argument("--examples", type=int, default=0, help="add this many examples chosen by meaning to each reading (the profile's reader_examples)")
    return parser


def chosen_sets(name: str) -> list[tuple[str, Path]]:
    if name == "all":
        return [(label, path) for label, path in SETS.items() if path.exists()]
    names = [part.strip() for part in name.split(",") if part.strip()]
    if all(part in SETS for part in names):
        return [(part, SETS[part]) for part in names]
    return [(Path(name).stem, Path(name))]


async def run(args: argparse.Namespace) -> int:
    minds = []
    if args.sub:
        minds.append(("subconscious", args.sub, mind_for(args.sub, "subconscious", "lfm2.5-230m")))
    if args.main:
        minds.append(("conscious", args.main, mind_for(args.main, "conscious", "")))
    ready = []
    for label, url, mind in minds:
        if await mind.ready():
            ready.append((label, mind))
        else:
            print(f"{label} at {url} is not ready (no /health ok); skipped")
    reader = ModelReader(ready, chooser=chooser_for(args.examples))
    readers = {part.strip() for part in args.readers.split(",")}
    modes = (MODEL_LEADS, RULES_FIRST) if args.mode == "both" else (args.mode,)
    saved = open(args.save, "a", encoding="utf-8") if args.save else None
    for set_name, path in chosen_sets(args.set):
        items = load(path)
        if args.only == "core":
            items = [i for i in items if i.get("core")]
        elif args.only == "not_command":
            items = [i for i in items if i.get("group") in ("not_command", "never")]
        bad = [i["id"] for i in items if i["expect"].get("kind") not in KINDS]
        if bad:
            print(f"{set_name}: items with an unknown kind: {bad}")
            return 2
        print(f"== {set_name} ({path.name}, {len(items)} lines)", flush=True)
        runs = []
        if "rules" in readers:
            runs.append(("rules", rules_reader()))
        if "model" in readers:
            runs.extend((label, model_reader(reader, label)) for label, _ in ready)
        if ("pipeline" in readers or args.pipeline) and ready:
            runs.extend((f"pipeline {mode}", pipeline_reader(reader, mode, args.wait)) for mode in modes)
        for label, read in runs:
            result = await score(items, read)
            print(result.report(label, args.show), flush=True)
            if saved is not None:
                saved.write(json.dumps({"set": set_name, "reader": label, "right": result.right, "total": result.total, "false": len(result.false_fires), "seconds": round(result.seconds, 2), "asked_model": result.asked_model, "times": [round(t, 3) for t in result.times], "misses": [[m[0], m[4]] for m in result.misses]}) + "\n")
                saved.flush()
    if saved is not None:
        saved.close()
    for _, _, mind in minds:
        await mind.close()
    return 0


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(run(build_parser().parse_args(argv)))


if __name__ == "__main__":
    sys.exit(main())
