import argparse
import asyncio
import json
import re
import statistics
import sys
import tempfile
import time
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from types import MethodType

from ..body.profile import resolve_profile
from ..mind.base import Mind, MindReply
from ..mind.budget import BUDGET_LOG, FOLD, REPLY_TRIM, guarded, note_event
from ..mind.lawful import lawful
from ..mind.llama import LlamaServerMind
from ..mind.profile import ModelProfile
from ..mind.prompt import ROOM, redact
from ..people.trust import FRIEND, TRUSTED
from ..self.recall.board import Note, block, fit
from ..self.recall.core import TALK, _short
from ..self.recall.embed import embedder_from
from ..self.recall.stream import HOUR_S, RECENCY, importance, shown, visible
from ..self.recall.vectors import cosines, spread
from ..sim.scene import Who

SET = Path(__file__).with_name("eval_fold.jsonl")
AT = datetime(2026, 10, 21, 15, 0, tzinfo=timezone.utc)
TIERS = {"Ina": TRUSTED, "Sam": FRIEND, "Mo": TRUSTED}
MODES = ("old", "new", "picks")
QUICK_S = 2.0
PAUSE_S = 7.0
PAUSE_EVERY = 6
BEFORE_PROBE_S = 8.0
REPLY_TOKENS = 90
SETTLE_S = 30.0
TIMING_CYCLES = 5
BEFORE_KEEP = ("Events:", "Heard:", "Note:")
BEFORE_DEEP = "You thought back (from your own memory; what others said stays their words): "


def load(path: Path = SET) -> tuple[list, list[dict]]:
    filler, scenes = [], []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        if item["kind"] == "filler":
            filler = item["lines"]
        else:
            scenes.append(item)
    return filler, scenes


class Canned(Mind):
    def __init__(self, inner: Mind, warms: bool = True):
        self.inner = inner
        self.name = inner.name
        self.replies: list[str] = []
        self.warms = warms
        self.firsts: list[float] = []

    async def chat(self, messages, tools=None, purpose="turn", max_tokens=None, options=None):
        if purpose == "reply" and self.replies:
            return MindReply(self.replies.pop(0))
        return await self.inner.chat(messages, tools=tools, purpose=purpose, max_tokens=max_tokens, options=options)

    async def stream(self, messages, purpose="turn", max_tokens=None, options=None, tools=None):
        if purpose == "reply" and self.replies:
            yield self.replies.pop(0)
            return
        extra = {"tools": tools} if tools else {}
        async for piece in self.inner.stream(messages, purpose=purpose, max_tokens=max_tokens, options=options, **extra):
            yield piece

    async def warm(self, messages, tools=None, purpose="warm"):
        if not self.warms:
            return True
        return await self.inner.warm(messages, tools=tools, purpose=purpose)

    async def ready(self):
        return await self.inner.ready()

    async def sees(self):
        return await self.inner.sees()

    def give_way(self) -> int:
        return self.inner.give_way()

    async def close(self):
        await self.inner.close()


def _before_from_turn(self, turn: dict):
    audience = tuple(str(a) for a in turn.get("audience") or ())
    at = turn.get("t")
    heard_from = turn.get("by")
    lines, thought, tools, asked, label = [], "", [], "", ""
    private = False
    for message in turn.get("messages") or []:
        if message.get("private"):
            private = True
        content = redact(message).get("content") or ""
        role = message.get("role")
        if role == "user":
            for line in content.splitlines():
                found = TALK.match(line.strip())
                if found:
                    label, asked = found.group("who"), found.group("said")
                elif line.startswith(BEFORE_KEEP):
                    lines.append(line.strip())
        elif role == "assistant":
            if content.strip() and not thought:
                thought = content.strip()
            for call in message.get("tool_calls") or []:
                tools.append(str((call.get("function") or {}).get("name") or "?"))
    if asked or heard_from:
        text = self.quote(label or "Someone", asked) + (f'; you answered: "{_short(thought, 80)}"' if thought else "")
        shared = bool(turn.get("shared")) and bool(heard_from) and not private
        return self.stream.add(text, "said", by="person", who=heard_from, tier=turn.get("tier"), about=(heard_from,) if heard_from else (), mark="private", audience=audience, weight=importance("said", people=1), at=at, shared=shared)
    parts = list(lines)
    if thought:
        parts.append(f"you thought: {_short(thought, 100)}")
    if tools:
        parts.append("you used " + ", ".join(dict.fromkeys(tools)))
    if not parts:
        return None
    heard = any(line.startswith("Heard:") for line in lines)
    return self.stream.add("; ".join(parts), "happened", mark="private" if (private or heard) else "", audience=audience, weight=importance("happened", people=len(audience)), at=at)


def _before_recall(self, query, audience, now, most=3, weights=None, here=(), skip=(), related=None, kinds=None):
    weights = weights or {}
    here = set(here or ())
    found = [r for r in self.records.values() if r.id not in skip and visible(r, audience, now) and (kinds is None or r.kind in kinds)]
    if not found:
        return []
    relevance = [0.0] * len(found)
    if query:
        rows = [self.vectors.get(r.id) for r in found]
        known = [n for n, row in enumerate(rows) if row is not None]
        scores = cosines(query, [rows[n] for n in known])
        for n, score in zip(known, scores):
            relevance[n] = score
        if related is not None:
            best = max(scores) if scores else 0.0
            keep = [n for n in known if relevance[n] >= related and relevance[n] >= best - 0.15]
            found = [found[n] for n in keep]
            relevance = [relevance[n] for n in keep]
            if not found:
                return []
    recency = [RECENCY ** (max(0.0, now - (r.recalled_t or r.t)) / HOUR_S) for r in found]
    weight = [float(r.importance) for r in found]
    lift = [1.0 if here & (set(r.about) | ({r.who} if r.who else set())) else 0.0 for r in found]
    totals = [
        float(weights.get("recency", 1.0)) * a + float(weights.get("importance", 1.0)) * b + float(weights.get("relevance", 1.0)) * c + float(weights.get("people", 1.0)) * d
        for a, b, c, d in zip(spread(recency), spread(weight), spread(relevance), lift)
    ]
    return sorted(zip(found, totals), key=lambda pair: (-pair[1], -pair[0].t))[:most]


async def _before_think_back(self, text: str, audience: frozenset, here=(), now: float | None = None) -> list[str]:
    now = self.clock.now() if now is None else now
    query = await self.vector(text)
    if query is None:
        return []
    ranked = self.stream.recall(query, audience, now, most=3, weights=self.weights(), here=here, related=self.related())
    notes = fit([Note(shown(r), "memory", r) for r, _ in ranked])
    self.stream.touch([n.record for n in notes if n.record is not None], now)
    return [n.text for n in notes]


async def _before_reply_path(self, observation: str, stage: str, values_text: str, people: str, room: int, at: str) -> int:
    system = self.builder.system_text(stage, values_text, self.history.summary, people)
    if not self.history.needs_compaction(self._fixed_tokens(system, [{"role": "user", "content": observation}])):
        return 0
    result = await self.history.compact(self.mind, at)
    note_event(self.store, self.clock, FOLD, where="reply", turns=result.folded)
    return result.folded


def as_before(life) -> None:
    recall = life.memory.recall
    recall._from_turn = MethodType(_before_from_turn, recall)
    recall.stream.recall = MethodType(_before_recall, recall.stream)
    recall.think_back = MethodType(_before_think_back, recall)
    life.memory.deep_line = lambda notes: block([Note(n) for n in notes], BEFORE_DEEP)
    life.before = True
    history = life.p.history
    history.mover = recall.from_turns
    history.talker = lambda: None
    turns = life.p.turns
    turns.card = lambda kind: ""
    turns.after_reply = None
    turns._trim_for_reply = MethodType(_before_reply_path, turns)
    turns.matched = lambda kind="reply": " ".join(part for part in (life.later.matched(), life.matched(kind)) if part)
    life.folding.tick = lambda: None
    life.commands.card = lambda: ""
    life.commands.on_refused = None


def profile_for(url: str, picks: bool = False) -> ModelProfile:
    data = json.loads(Path(resolve_profile("gemma4_e4b", "model")).read_text(encoding="utf-8"))
    data["endpoint"] = url
    profile = ModelProfile.from_dict(data)
    return replace(profile, fold_picks=True) if picks else profile


async def staged(root: Path, url: str, mode: str, people: list[str], embedder, warms: bool = True, readings: dict | None = None):
    from ..life.scene import LaterScene

    profile = profile_for(url, mode == "picks")
    whos = [Who(name, TIERS.get(name, FRIEND), 1300.0 + 200.0 * n, 300.0 * n) for n, name in enumerate(people)]
    play = LaterScene(root, whos, AT, readings or {})
    play.scene.extra = {"embedder": embedder}
    await play.setup()
    life = play.life
    store, clock = play.scene.store, play.scene.clock
    inner = LlamaServerMind(profile)
    real = lawful(guarded(inner, profile, store, clock, inner.base))
    canned = Canned(real, warms)
    await canned.ready()
    life.p.history.profile = profile
    life.p.turns.mind = canned
    life.p.mind = canned
    life._mind_ready = True
    if mode == "old":
        as_before(life)
    return play, canned


def observation_of(play, name: str, text: str, board: str, deep: list[str]) -> tuple[str, list]:
    life = play.life
    local = play.scene.clock.local()
    person = life.company.book.find(name.lower())
    alone = person.id if person is not None else None
    lines, private = [], []
    if board and (not deep or getattr(life, "before", False)):
        lines.append(board)
        private.append({"to": alone or ROOM, "text": board})
    lines.append(f"It is {local:%A} {local:%H:%M}; your battery is at 80%.")
    lines.append(f"Answer {name} out loud now.")
    lines.append(f'{name} is talking to you: "{text}"')
    if deep:
        block = life.memory.deep_line(deep)
        lines.append(block)
        private.append({"to": alone or ROOM, "text": block})
    return "\n".join(lines), private


async def quiet_down(life, limit_s: float = SETTLE_S) -> None:
    end = time.monotonic() + limit_s
    while time.monotonic() < end:
        memory = [getattr(life.memory, "_task", None), getattr(life.memory, "_refresh", None)]
        busy = [task for task in list(life.folding.tasks) + list(life.commands.tasks) + memory if task is not None and not task.done()]
        if not busy:
            return
        await asyncio.wait(busy, timeout=max(0.0, end - time.monotonic()))


async def talk(play, canned: Canned, name: str, text: str, reply: str | None, gap: float, warm_first: bool = False) -> tuple[str, float | None]:
    scene, life = play.scene, play.life
    await scene.say(name, text)
    await quiet_down(life)
    if reply is None:
        await scene.run(gap)
        await quiet_down(life)
        return "", None
    memory = life.memory
    audience = memory.audience()
    board = memory.board_text(audience)
    deep = await memory.think_back(text, audience) if memory.remembering(text) else []
    observation, private = observation_of(play, name, text, board, deep)
    person = life.company.book.find(name.lower())
    if warm_first:
        partial = " ".join(text.split()[:-1])
        early, early_private = observation_of(play, name, partial, board, deep)
        await life.warm_reply(early, early_private, "warm")
    if reply:
        canned.replies.append(reply)
    start = time.monotonic()
    first, pieces = None, []
    async for piece in life.reply(observation, private, REPLY_TOKENS, speaker=person.id if person else None):
        if first is None:
            first = time.monotonic() - start
        pieces.append(piece)
    said = " ".join("".join(pieces).split())
    life.reply_done(said)
    await scene.run(gap)
    await quiet_down(life)
    return said, first


def events(play) -> list[dict]:
    return [line for line in play.scene.store.read_lines(BUDGET_LOG) if isinstance(line, dict) and line.get("event")]


async def play_scene(item: dict, filler: list, offset: int, url: str, mode: str, embedder, show: bool) -> dict:
    with tempfile.TemporaryDirectory(prefix="pebble-fold-") as folder:
        play, canned = await staged(Path(folder) / "self", url, mode, item["people"], embedder, warms=False, readings=item.get("readings"))
        try:
            main = item["people"][0]
            for name, text, reply in item["lines"]:
                await talk(play, canned, name, text, reply, PAUSE_S)
            for n in range(int(item.get("filler", 40))):
                say, answer = filler[(offset + n) % len(filler)]
                await talk(play, canned, main, say, answer, PAUSE_S if (n + 1) % PAUSE_EVERY == 0 else QUICK_S)
            await play.scene.run(BEFORE_PROBE_S)
            await quiet_down(play.life)
            name, text = item["probe"]
            said, _ = await talk(play, canned, name, text, "", QUICK_S)
            right = re.search(item["good"], said, re.IGNORECASE) is not None
            happened = events(play)
            folds = sum(1 for e in happened if e["event"] == FOLD)
            trims = sum(1 for e in happened if e["event"] == REPLY_TRIM)
            out = {"id": item["id"], "kind": item["kind"], "mode": mode, "right": right, "said": said, "folds": folds, "reply_path": sum(1 for e in happened if e["event"] == FOLD and e.get("where") == "reply"), "trims": trims}
            life = play.life
            if item.get("item"):
                out["kept"] = any(item["item"] in (it.words or "").lower() for it in life.later.agenda.waiting())
            if item.get("open"):
                out["kept"] = any(item["open"] in p["text"].lower() for p in getattr(getattr(life, "taskcard", None), "promises", []) or [])
            if show:
                print(json.dumps(out), flush=True)
            return out
        finally:
            await play.life.folding.close()
            await play.close()


async def run_set(url: str, modes: list[str], only: list[str], show: bool, save: str) -> dict:
    filler, scenes = load()
    if only:
        scenes = [s for s in scenes if s["id"] in only]
    embedder = embedder_from("auto")
    results = []
    for mode in modes:
        for n, item in enumerate(scenes):
            results.append(await play_scene(item, filler, n * 7, url, mode, embedder, show))
    if save:
        Path(save).write_text("\n".join(json.dumps(r) for r in results) + "\n", encoding="utf-8")
    summary = {}
    for mode in modes:
        mine = [r for r in results if r["mode"] == mode]
        kinds = {}
        for r in mine:
            kinds.setdefault(r["kind"], [0, 0])
            kinds[r["kind"]][0] += r["right"]
            kinds[r["kind"]][1] += 1
        kept = [r["kept"] for r in mine if "kept" in r]
        summary[mode] = {
            "right": sum(r["right"] for r in mine),
            "of": len(mine),
            "kinds": {k: f"{a}/{b}" for k, (a, b) in kinds.items()},
            "folds": [r["folds"] for r in mine],
            "reply_path_folds": sum(r["reply_path"] for r in mine),
            "reply_trims": sum(r["trims"] for r in mine),
            "promises_kept": f"{sum(kept)}/{len(kept)}",
        }
    return summary


async def timing(url: str, mode: str, cycles: int, embedder, show: bool) -> dict:
    filler, _ = load()
    with tempfile.TemporaryDirectory(prefix="pebble-fold-time-") as folder:
        play, canned = await staged(Path(folder) / "self", url, mode, ["Ina"], embedder, warms=True)
        life = play.life
        history, turns = life.p.history, life.p.turns
        due_s, calm_s, folded = [], [], []
        n = 0
        try:
            for _ in range(cycles):
                for _ in range(400):
                    local = play.scene.clock.local()
                    stage, values = life.stage(local), life.p.books.values.describe()
                    people = life.company.prompt_text(play.scene.clock.now(), play.scene.clock.local)
                    system = turns.builder.system_text(stage, values, history.summary, people)
                    fixed = turns._fixed_tokens(system, [{"role": "user", "content": "x" * 600}])
                    if history.needs_compaction(fixed) if mode == "old" else turns.fold_due(stage, values, people):
                        break
                    say, answer = filler[n % len(filler)]
                    n += 1
                    await talk(play, canned, "Ina", say, answer, QUICK_S)
                before = history.compactions
                await play.scene.run(PAUSE_S)
                await quiet_down(life)
                quiet = history.compactions - before
                for _ in range(2):
                    say, _ = filler[n % len(filler)]
                    n += 1
                    before = history.compactions
                    _, first = await talk(play, canned, "Ina", say, "", QUICK_S, warm_first=True)
                    during = history.compactions - before
                    (due_s if during or quiet else calm_s).append(first)
                    folded.append({"quiet": quiet, "reply": during, "s": round(first, 3)})
                    quiet = 0
                if show:
                    print(json.dumps({"mode": mode, "replies": folded[-2:]}), flush=True)
            happened = events(play)
            return {
                "mode": mode,
                "window": history.profile.window(),
                "due_median_s": round(statistics.median(due_s), 3) if due_s else None,
                "calm_median_s": round(statistics.median(calm_s), 3) if calm_s else None,
                "due_s": [round(x, 3) for x in due_s],
                "calm_s": [round(x, 3) for x in calm_s],
                "folded_each": folded,
                "folds": sum(1 for e in happened if e["event"] == FOLD),
                "reply_path_folds": sum(1 for e in happened if e["event"] == FOLD and e.get("where") == "reply"),
                "reply_trims": sum(1 for e in happened if e["event"] == REPLY_TRIM),
            }
        finally:
            await play.life.folding.close()
            await play.close()


async def main_async(args) -> int:
    if args.timing:
        embedder = embedder_from("auto")
        for mode in [m for m in args.modes.split(",") if m in ("old", "new")]:
            print(json.dumps(await timing(args.main, mode, args.cycles, embedder, args.show)), flush=True)
        return 0
    summary = await run_set(args.main, [m for m in args.modes.split(",") if m in MODES], [s for s in args.only.split(",") if s], args.show, args.save)
    print(json.dumps(summary, indent=1), flush=True)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m pebble.conversation.eval_fold", description="Talk scenes that pass the compaction point, scored with a real model: is something from early on still used right afterwards?")
    parser.add_argument("--main", default="http://127.0.0.1:8080", help="llama-server URL of the main model")
    parser.add_argument("--modes", default="old,new,picks", help="which folds to score: old (before piece 13), new, picks (new with its own picks)")
    parser.add_argument("--only", default="", help="comma separated scene ids")
    parser.add_argument("--timing", action="store_true", help="time replies with and without a compaction due, instead of scoring")
    parser.add_argument("--cycles", type=int, default=TIMING_CYCLES)
    parser.add_argument("--show", action="store_true")
    parser.add_argument("--save", default="", help="write every result to this JSON lines file")
    return asyncio.run(main_async(parser.parse_args(argv)))


if __name__ == "__main__":
    sys.exit(main())
