import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

from .address import ADDRESSED, LABELS, OVERHEARD, Room, decide
from .words import name_at

SCENES = Path(__file__).resolve().parent / "eval_scenes.jsonl"
SECONDS_PER_CHAR = 0.065


@dataclass(frozen=True)
class Scored:
    scene: str
    who: str
    say: str
    expect: tuple
    got: str
    score: float
    reasons: tuple

    @property
    def right(self) -> bool:
        return self.got in self.expect

    @property
    def false_reply(self) -> bool:
        return self.got == ADDRESSED and ADDRESSED not in self.expect

    @property
    def missed(self) -> bool:
        return self.expect == (ADDRESSED,) and self.got == OVERHEARD


def load(path: Path = SCENES) -> list[dict]:
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def run_scene(scene: dict, name: str = "Pebble") -> list[Scored]:
    room = Room(name)
    people = set(scene.get("people") or [])
    t = 0.0
    out = []
    for line in scene["lines"]:
        t += float(line.get("gap", 3.0))
        people |= set(line.get("enter") or [])
        people -= set(line.get("leave") or [])
        who, say = line["who"], line["say"]
        if who == "pebble":
            room.spoke(t, line.get("to"), bool(line.get("asked")))
            t += len(say) * SECONDS_PER_CHAR
            continue
        look = line.get("look")
        keyword = bool(name_at(say, name)) and line.get("kw", True)
        names = tuple(sorted(p for p in people if p != who))
        cues = room.cues(t, who, say, keyword, len(people | {who}), looking=True if look == "me" else (False if look in ("away", "other") else None), at_other=look == "other", on_phone=bool(line.get("phone")), names=names, busy=bool(line.get("doing", scene.get("doing"))))
        verdict = decide(cues)
        room.heard(t, who, verdict, say)
        expect = tuple(str(line["expect"]).split("|"))
        out.append(Scored(scene["scene"], who, say, expect, verdict.label, verdict.score, verdict.reasons))
        t += len(say) * SECONDS_PER_CHAR
    return out


def evaluate(path: Path = SCENES) -> list[Scored]:
    results = []
    for scene in load(path):
        results.extend(run_scene(scene))
    return results


def report(results: list[Scored]) -> dict:
    total = len(results)
    right = sum(r.right for r in results)
    confusion = {want: {got: 0 for got in LABELS} for want in LABELS}
    for r in results:
        confusion[r.expect[0]][r.got] += 1
    return {
        "lines": total,
        "scenes": len({r.scene for r in results}),
        "right": right,
        "accuracy": round(right / total, 3) if total else 0.0,
        "false_replies": sum(r.false_reply for r in results),
        "missed": sum(r.missed for r in results),
        "confusion": confusion,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m pebble.conversation.eval", description="Score who-is-being-talked-to on the scripted scenes.")
    parser.add_argument("--scenes", default=str(SCENES))
    parser.add_argument("--wrong", action="store_true", help="list the lines it got wrong")
    args = parser.parse_args(argv)
    results = evaluate(Path(args.scenes))
    summary = report(results)
    print(f"{summary['lines']} lines in {summary['scenes']} scenes: {summary['right']} right ({100 * summary['accuracy']:.1f} %), {summary['false_replies']} false replies, {summary['missed']} missed")
    print("expected (first choice) -> got:")
    for want, row in summary["confusion"].items():
        print(f"  {want:10s} " + "  ".join(f"{got} {count}" for got, count in row.items()))
    if args.wrong:
        for r in results:
            if not r.right:
                print(f"- [{r.scene}] {r.who}: \"{r.say}\" expected {'/'.join(r.expect)}, got {r.got} ({r.score:+.1f}: {'; '.join(r.reasons[:3])})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
