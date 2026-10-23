import argparse
import asyncio
import json
import sys
import time
from datetime import datetime
from pathlib import Path

from ..understand.eval import mind_for
from .book import Book
from .dream import default_ground
from .write import Task, Writer, asked_span

TASKS = Path(__file__).with_name("eval_tasks.jsonl")
BAR = 0.7
PIXEL_READ = (20.0, 40.0)
PIXEL_WRITE = (3.5, 6.0)
START = datetime(2026, 10, 21, 7, 30)
FIRST = {"alex": "Alex", "ina": "Ina", "sam": "Sam", "mo": "Mo"}


class NoStore:
    def read(self, name, default=None):
        return default

    def write(self, name, data, keep_backup=True):
        return None

    def read_bytes(self, name, default=b""):
        return default

    def write_bytes(self, name, data):
        return None

    def remove(self, name):
        return None


class NoClock:
    def now(self):
        return START.timestamp()


def load(path: Path = TASKS) -> list[dict]:
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def task_of(item: dict) -> Task:
    if item.get("own"):
        return Task(item["words"])
    name = item["for"]
    ground = default_ground(name)
    return Task(item["words"], name, FIRST.get(name, name.title()), ground.tier(name) or "trusted", asked_span(item["words"]))


def pixel_minutes(history: list) -> tuple[float, float]:
    fresh = 0
    written = 0
    before = 0
    for index, item in enumerate(history):
        prompt = int(item.get("prompt_tokens") or 0)
        done = int(item.get("completion_tokens") or 0)
        fresh += prompt if index == 0 else max(0, prompt - before)
        before = prompt + done
        written += done
    low = fresh / PIXEL_READ[1] + written / PIXEL_WRITE[1]
    high = fresh / PIXEL_READ[0] + written / PIXEL_WRITE[0]
    return low / 60.0, high / 60.0


async def run(args: argparse.Namespace) -> int:
    mind = mind_for(args.main, "conscious", "")
    if not await mind.ready():
        print(f"no llama-server answers at {args.main}")
        return 2
    writer = Writer(lambda: mind, Book(NoStore(), NoClock()), wait_s=args.wait, seed=args.seed)
    items = load(Path(args.set) if args.set else TASKS)
    if args.only:
        wanted = set(args.only.split(","))
        items = [item for item in items if item["id"] in wanted]
    results = []
    began = time.monotonic()
    for item in items:
        task = task_of(item)
        ground = default_ground(task.for_name)
        start = time.monotonic()
        written = await writer.write(task, ground, START)
        took = time.monotonic() - start
        low, high = pixel_minutes(written.history)
        result = {
            "id": item["id"],
            "own": task.own,
            "valid_first": written.valid_first,
            "valid": written.valid,
            "dreamed": written.dream_passed,
            "calls": written.calls,
            "minutes": round(took / 60.0, 2),
            "pixel_minutes_estimate": [round(low, 1), round(high, 1)],
            "prompt_tokens": [h.get("prompt_tokens") for h in written.history],
            "completion_tokens": [h.get("completion_tokens") for h in written.history],
            "errors": written.errors[:4],
            "failed": written.failed,
        }
        if args.show:
            result["history"] = [{k: v for k, v in h.items() if k != "source"} for h in written.history]
            result["source"] = written.source or (written.history[-1].get("source") if written.history else "")
        results.append(result)
        print(json.dumps(result, ensure_ascii=False), flush=True)
    await mind.close()
    total = len(results)
    first = sum(1 for r in results if r["valid_first"])
    valid = sum(1 for r in results if r["valid"])
    dreamed = sum(1 for r in results if r["dreamed"])
    minutes = (time.monotonic() - began) / 60.0
    lows = sorted(r["pixel_minutes_estimate"][0] for r in results)
    highs = sorted(r["pixel_minutes_estimate"][1] for r in results)
    rate = dreamed / total if total else 0.0
    print(f"valid at first {first} of {total}; valid after fixes {valid}; passed the dream {dreamed} ({rate:.0%}, the bar is {BAR:.0%}); {minutes:.1f} minutes on this machine in all")
    if lows:
        print(f"Pixel 6 Pro estimate (the plan's ruler: reading 20 to 40 tokens a second, writing 3.5 to 6): median {lows[len(lows) // 2]} to {highs[len(highs) // 2]} minutes a program, slowest {lows[-1]} to {highs[-1]}")
    if args.save:
        Path(args.save).write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in results) + "\n", encoding="utf-8")
    return 0 if rate >= BAR else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m pebble.script.eval", description="Ask a real model to write Pebble script for the 40 eval tasks, and score how many are valid at first, valid after fixes and pass their dream run")
    parser.add_argument("--main", default="http://127.0.0.1:8080", help="llama-server URL of the main model")
    parser.add_argument("--set", default="", help="a JSON lines file of tasks (default: eval_tasks.jsonl)")
    parser.add_argument("--only", default="", help="task ids, comma separated")
    parser.add_argument("--wait", type=float, default=240.0, help="how long to wait for each writing call")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--show", action="store_true", help="print each script and its rounds")
    parser.add_argument("--save", default="", help="write every result to this JSON lines file")
    return asyncio.run(run(parser.parse_args(argv)))


if __name__ == "__main__":
    sys.exit(main())
