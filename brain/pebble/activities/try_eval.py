import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

from ..people.trust import TRUSTED
from ..understand.eval import mind_for
from .card import Body, Card, request_of
from .gate import Asker, Situation, decide
from .skills import same
from .trying import ANOTHER_ASK, PLAN_IT, Loop, Planner, asking

SET = Path(__file__).with_name("eval_try.jsonl")
TRIES_MOST = 5
PLACES = ("kitchen", "lounge", "bathroom", "bedroom", "hallway")
PEOPLE = ("ina", "sam", "mo")
ASKER = Asker("ina", "Ina", TRUSTED)


def load(path: Path = SET) -> list[dict]:
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def wanted(steps: list, want) -> bool:
    if want == "cant" or not steps:
        return False
    names = [step["do"] for step in steps]
    if any(name not in names for name in want.get("all", [])):
        return False
    if want.get("any") and not any(name in names for name in want["any"]):
        return False
    return not any(name in names for name in want.get("none", []))


def refused(steps: list) -> int:
    count = 0
    situation = Situation(later=True, places_known=frozenset(PLACES))
    for step in steps:
        request = request_of(step)
        if request is not None and not decide(request, ASKER, situation).yes:
            count += 1
    return count


async def score(planner: Planner, card: Card, item: dict) -> dict:
    loop = Loop(item["text"], item["text"], ASKER, "heard")
    out = {"id": item["id"], "text": item["text"], "tries": 0, "yes": False, "first_valid": None, "cant": False, "refused": 0, "repeats": 0, "seconds": []}
    ask = PLAN_IT
    while out["tries"] < TRIES_MOST:
        start = time.monotonic()
        planned = await planner.ask(card, asking(loop, "Ina", ask), seed=len(loop.tries))
        out["seconds"].append(round(time.monotonic() - start, 2))
        if out["first_valid"] is None:
            out["first_valid"] = bool(planned.steps) and not planned.errors
        if planned.cant:
            out["cant"] = True
            out["why"] = planned.cant
            break
        if not planned.steps:
            out["failed"] = planned.failed or "no steps"
            break
        if same(planned.steps, loop.tries):
            out["repeats"] += 1
        out["tries"] += 1
        out["refused"] += refused(planned.steps)
        good = wanted(planned.steps, item["want"])
        loop.tries.append({"steps": planned.steps, "answer": "yes" if good else "no", "answer_kind": "yes" if good else "no"})
        if good:
            out["yes"] = True
            break
        ask = ANOTHER_ASK
    out["plans"] = [t["steps"] for t in loop.tries]
    out["right"] = out["cant"] if item["want"] == "cant" else out["yes"]
    return out


async def run(args: argparse.Namespace) -> int:
    mind = mind_for(args.main, "conscious", "")
    if not await mind.ready():
        print(f"no llama-server answers at {args.main}")
        return 2
    planner = Planner(lambda: mind, wait_s=args.wait)
    card = Card(Body(places=PLACES, people=PEOPLE))
    results = []
    for item in load(Path(args.set) if args.set else SET):
        result = await score(planner, card, item)
        results.append(result)
        print(json.dumps({k: v for k, v in result.items() if k != "plans"}), flush=True)
        if args.show:
            for number, steps in enumerate(result["plans"], 1):
                print(f"   try {number}: {json.dumps(steps, separators=(',', ':'))}", flush=True)
    await mind.close()
    right = sum(1 for r in results if r["right"])
    plans = [r for r in results if not r["cant"]]
    valid = sum(1 for r in plans if r["first_valid"])
    tries = [r["tries"] for r in results if r["yes"]]
    seconds = sorted(s for r in results for s in r["seconds"])
    print(f"right {right} of {len(results)}; first plan valid {valid} of {len(plans)} planned; tries until yes {sum(tries)} over {len(tries)} ({(sum(tries) / len(tries)) if tries else 0:.1f} each); gate refusals in plans {sum(r['refused'] for r in results)}; repeated plans {sum(r['repeats'] for r in results)}; seconds a plan median {seconds[len(seconds) // 2] if seconds else 0}, slowest {seconds[-1] if seconds else 0}")
    if args.save:
        Path(args.save).write_text("\n".join(json.dumps(r) for r in results) + "\n", encoding="utf-8")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m pebble.activities.try_eval", description="Ask a real model to plan new things for the wheeled body, with a stand-in person who says yes when the plan has what the request needs")
    parser.add_argument("--main", default="http://127.0.0.1:8080", help="llama-server URL of the main model")
    parser.add_argument("--set", default="", help="a JSON lines file of requests (default: eval_try.jsonl)")
    parser.add_argument("--wait", type=float, default=60.0, help="how long to wait for each plan")
    parser.add_argument("--show", action="store_true", help="print every plan")
    parser.add_argument("--save", default="", help="write every result to this JSON lines file")
    return asyncio.run(run(parser.parse_args(argv)))


if __name__ == "__main__":
    sys.exit(main())
