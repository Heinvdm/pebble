import argparse
import asyncio
import json
import math
import statistics
import sys
import tempfile
import time
from pathlib import Path

from ..people.trust import CHILD, FRIEND, TRUSTED
from ..sim.scene import Who
from ..sim.world import SimThing
from .book import SLOT
from .induce import Inducer, made_from, values_seen
from .replay import gap_to_path
from .scene import carry, drive, face, press, quiet, scatter, settle, staged, tidy

SET = Path(__file__).with_name("eval_sessions.jsonl")
HOUSE = {"Ina": (TRUSTED, 1.6, 0.9), "Mo": (TRUSTED, 1.6, -0.9), "Sam": (CHILD, 0.5, 1.6), "Alex": (FRIEND, 0.5, -1.6)}
START = (2.2, 0.0, 0.0)
ROUTE_GAP_M = 0.2
SPOT_GAP_M = 0.5
ASKS = ("Like this?", "I couldn't do all of it just now. Like this?", "Did I get the way right?")


def load(path: Path = SET) -> list[dict]:
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def loose(step: dict) -> str:
    if step.get("do") == "request":
        request = step.get("request") or {}
        target = request.get("place") or request.get("thing") or request.get("who") or ""
        return f"{request.get('kind')}:{'{}' if SLOT.fullmatch(str(target)) else target}"
    target = step.get("way") or step.get("expression") or ""
    return f"{step.get('do')}:{target}"


def activity_sigs(pairs: list) -> list[str]:
    out = []
    for activity, _ in pairs:
        if activity.kind in ("try_new",) and getattr(activity, "steps", None) is not None:
            for step in activity.steps:
                out.extend([loose(step)] * max(1, int(step.get("repeat", 1))))
            continue
        if activity.kind in ("drive", "copy_me", "follow"):
            continue
        request = activity.request
        target = request.place or request.thing or request.who or (request.way if request.kind in ("turn", "move") else "")
        out.append(f"{request.kind}:{target}")
    return out


def expanded(steps: list) -> list[str]:
    out = []
    for step in steps:
        out.extend([loose(step)] * max(1, int(step.get("repeat", 1)) if step.get("do") != "request" else 1))
    return out


def matches(entry, expect: dict) -> bool:
    if entry is None or entry.kind != expect["kind"]:
        return False
    if expect.get("steps") is not None:
        got = [loose(step) for step in entry.steps]
        if got != expect["steps"]:
            return False
    if expect.get("slots") is not None:
        values = [v for items in entry.slots.values() for v in items]
        if sorted(values) != sorted(expect["slots"]):
            return False
    return True


class Run:
    def __init__(self, play, mind, session: dict):
        self.play = play
        self.mind = mind
        self.session = session
        self.teacher = session["teacher"]
        self.questions = 0
        self.replays: list = []
        self.tracks: list = []
        self.seconds: list = []
        self.problems: list = []
        self.questions_before = len([r for r in play.records() if r["kind"] == "teach_question"])

    @property
    def life(self):
        return self.play.life

    @property
    def teaching(self):
        return self.play.life.teaching

    def history(self) -> list:
        return list(self.life.commands.runner.history)

    async def say(self, text: str, who: str | None = None) -> None:
        scene = self.play.scene
        before = self.history()
        asked_before = len(self.play.said())
        sampling = []
        started = time.perf_counter()
        await scene.say(who or self.teacher, text)
        self.seconds.append(time.perf_counter() - started)
        end = scene.clock.monotonic() + 400.0
        await scene.run(0.5)
        while scene.clock.monotonic() < end and not quiet(self.play):
            pose = scene.world.pose
            sampling.append((pose.x / 1000.0, pose.y / 1000.0))
            await scene.run(0.5)
        new = [pair for pair in self.history() if all(pair is not old for old in before)]
        said = self.play.said()[asked_before:]
        if any(line in ASKS for line in said):
            self.replays.append(new)
            self.tracks.append(sampling)
        self.questions = len([r for r in self.play.records() if r["kind"] == "teach_question"]) - self.questions_before

    async def act(self, action: dict) -> None:
        scene = self.play.scene
        world = scene.world
        if "say" in action:
            await self.say(action["say"], action.get("who"))
        elif "pad" in action:
            x, y, seconds = action["pad"]
            await drive(self.play, x, y, seconds)
        elif "tilt" in action:
            await press(self.play, {"kind": "tilt", "way": action["tilt"]})
        elif "face" in action:
            await press(self.play, {"kind": "face", "expression": action["face"]})
        elif "walk" in action:
            scene.walk(action.get("who") or self.teacher, *[tuple(p) for p in action["walk"]], speed_mm_s=float(action.get("speed") or 120.0))
            await scene.run(float(action.get("run") or 60.0))
        elif "position" in action:
            name, x, y = action["position"]
            person = world.person(name.lower())
            person.x, person.y, person.route = x * 1000.0, y * 1000.0, []
            await scene.run(1.0)
        elif "carry" in action:
            await carry(self.play, *action["carry"])
        elif "place" in action:
            face(self.play, *action["place"])
            await scene.run(1.0)
        elif "scatter" in action:
            spec = action["scatter"]
            self.scattered = getattr(self, "scattered", []) + scatter(self.play, tuple(spec["near"]), spec["count"], spec["seed"])
            await scene.run(1.0)
        elif "tidy" in action:
            tidy(self.play, getattr(self, "scattered", []))
            self.scattered = []
            await scene.run(1.0)
        elif "put" in action:
            spec = action["put"]
            thing = world.thing(spec["name"])
            if thing is None:
                thing = SimThing(spec["name"], 0.0, 0.0, width_mm=300.0 if spec["name"] != "door" else 800.0, depth_mm=200.0, height_mm=200.0 if spec["name"] != "door" else 1900.0, slow=spec["name"], print_id=spec["print"], track=700 + len(world.things))
                world.things.append(thing)
            thing.print_id = spec["print"]
            thing.home = True
            thing.x, thing.y = spec["at"][0] * 1000.0, spec["at"][1] * 1000.0
            await scene.run(1.0)
        elif "take" in action:
            thing = world.thing(action["take"])
            if thing is not None:
                world.things.remove(thing)
        elif "gesture" in action:
            spec = action["gesture"]
            person = world.person((spec.get("who") or self.teacher).lower())
            if "arm" in spec:
                person.arm, person.arm_side = spec["arm"], "right"
            if "turn" in spec:
                person.facing = math.atan2(person.y, person.x - 1000.0) if spec["turn"] else None
            if "posture" in spec:
                person.posture = spec["posture"]
            if "nod" in spec:
                person.nod = bool(spec["nod"])
            await scene.run(float(spec.get("run") or 2.0))
        elif "leave" in action:
            scene.leave(action["leave"])
        elif "arrive" in action:
            name, x, y = action["arrive"]
            scene.arrive(name, x, y)
        elif "skip" in action:
            await self.play.skip(float(action["skip"]))
        elif "seen" in action:
            for _ in range(int(action["seen"])):
                self.play.seen()
                await scene.run(1.0)
            await settle(self.play)
        elif "sound" in action:
            self.life.later.sound(action["sound"])
            await scene.run(2.0)
            await settle(self.play)

    async def probe(self, entry) -> tuple[bool, list]:
        notes = []
        ok = True
        for action in self.session.get("probe") or []:
            if "is" in action:
                found = self.teaching.concepts.find(action["is"])
                answer = await self.teaching.concepts.is_this(found) if found is not None else "missing"
                notes.append(f"is {action['is']}: {answer}")
                ok = ok and answer == action["want"]
                continue
            if "want_run" in action:
                ran = activity_sigs(self.since_probe)
                want = action["want_run"]
                notes.append(f"ran {ran}")
                ok = ok and ran[: len(want)] == want
                continue
            if "say" in action and ("want" in action or "near" in action):
                before = self.history()
                await self.say(action["say"])
                new = [pair for pair in self.history() if all(pair is not old for old in before)]
                if "want" in action:
                    ran = activity_sigs(new)
                    notes.append(f"ran {ran}")
                    ok = ok and ran[: len(action["want"])] == action["want"]
                if "near" in action:
                    pose = self.play.scene.world.pose
                    gap = math.hypot(pose.x / 1000.0 - action["near"][0], pose.y / 1000.0 - action["near"][1])
                    notes.append(f"gap {gap:.2f}")
                    ok = ok and gap <= SPOT_GAP_M
                continue
            if any(key in action for key in ("leave", "skip", "arrive", "seen", "sound")) and not hasattr(self, "since_probe_start"):
                self.since_probe_start = self.history()
            await self.act(action)
            self.since_probe = [pair for pair in self.history() if all(pair is not old for old in getattr(self, "since_probe_start", []))]
        return ok, notes


def reset(play, present=()) -> None:
    scene = play.scene
    for person in scene.world.people:
        home = HOUSE.get(person.name.title())
        if home is not None:
            person.home, person.x, person.y, person.route = person.name.title() in present, home[1] * 1000.0, home[2] * 1000.0, []
            person.arm, person.facing, person.posture, person.nod = "down", None, None, False
    for name in ("cat", "plant pot"):
        thing = scene.world.thing(name)
        if thing is not None:
            thing.home = False
    face(play, *START)


async def run_session(play, mind, session: dict, captured: list) -> dict:
    run = Run(play, mind, session)
    result = {"id": session["id"], "kind": session["kind"], "way": session["way"], "learned_in": None, "replay": None, "new": None, "question_ok": None, "asked": False, "notes": []}
    expect = session["expect"]
    teaching = play.life.teaching
    entry = None
    present = set(session.get("present") or []) | {session["teacher"]}
    for number, lesson in enumerate(session["lessons"], 1):
        reset(play, present)
        await play.scene.run(1.0)
        for action in lesson:
            await run.act(action)
        await settle(play, 60.0)
        entry = teaching.book.get(expect["name"]) or teaching._named(expect["name"])
        if result["learned_in"] is None and matches(entry, expect):
            result["learned_in"] = number
    probe_ok, notes = (True, [])
    if session.get("probe"):
        probe_ok, notes = await run.probe(entry)
        result["notes"] += notes
    if result["learned_in"] is not None and not probe_ok:
        result["learned_in"] = None
    result["learned"] = result["learned_in"] is not None and result["learned_in"] <= 2
    if session.get("replay", True) and session["kind"] not in ("concept", "word", "spot", "habit"):
        if session["kind"] == "route":
            points = entry.points if entry is not None else []
            track = [p for p in (run.tracks[-1] if run.tracks else []) if points]
            moving = track[2:] if len(track) > 2 else track
            worst = max((gap_to_path(x, y, points) for x, y in moving), default=math.inf) if points else math.inf
            result["replay"] = worst <= ROUTE_GAP_M
            result["route_gap_m"] = round(worst, 3) if math.isfinite(worst) else None
        else:
            shown = list((entry.examples[-1].get("steps") if entry is not None and entry.examples else []) or [])
            replayed = activity_sigs(run.replays[-1]) if run.replays else []
            result["replay"] = bool(replayed) and replayed == expanded(shown)
            if not result["replay"]:
                result["notes"].append(f"replayed {replayed} shown {expanded(shown)}")
    if session.get("new"):
        before = run.history()
        await run.say(session["new"]["say"])
        new = [pair for pair in run.history() if all(pair is not old for old in before)]
        ran = activity_sigs(new)
        want = session["new"]["want"]
        result["new"] = ran[: len(want)] == want
        result["notes"].append(f"new value ran {ran}")
    result["asked"] = run.questions > 0
    result["question_ok"] = result["asked"] == bool(session.get("question"))
    result["wanted_question"] = bool(session.get("question"))
    result["entry"] = {"kind": entry.kind, "steps": [loose(s) for s in entry.steps], "slots": entry.slots} if entry is not None else None
    result["replay_s"] = [round(t, 3) for t in teaching.timings[-3:]]
    return result


async def run(sessions: list[dict], echo: bool = False, captured: list | None = None, root: Path | None = None) -> list[dict]:
    people = [Who(name, tier, x * 1000.0, y * 1000.0) for name, (tier, x, y) in HOUSE.items()]
    holder = None
    if root is None:
        holder = tempfile.TemporaryDirectory(prefix="pebble-teach-eval-", ignore_cleanup_errors=True)
        root = Path(holder.name)
    results = []
    play, mind = await staged(root / "self", echo, people, looks=["toys and clothes on the floor"])
    captured = captured if captured is not None else []
    teaching = play.life.teaching
    real_ask = teaching.inducer.ask
    state: dict = {}

    async def ask(text, card, known=(), seed=None, kinds=()):
        session = state.get("session") or {}
        captured.append({"session": session.get("id"), "expect": session.get("expect"), "kinds": tuple(kinds), "text": text, "card": card, "known": list(known), "examples": [list(e) for e in (teaching.making.examples if teaching.making is not None else [])], "name": teaching.making.name if teaching.making is not None else ""})
        return await real_ask(text, card, known, seed, kinds)

    teaching.inducer.ask = ask
    try:
        for session in sessions:
            state["session"] = session
            result = await run_session(play, mind, session, captured)
            results.append(result)
            if echo:
                print(json.dumps(result), flush=True)
    finally:
        await play.close()
        if holder is not None:
            holder.cleanup()
    return results


def summary(results: list[dict]) -> dict:
    replays = [r for r in results if r["replay"] is not None]
    news = [r for r in results if r["new"] is not None]
    routes = [r["route_gap_m"] for r in results if r.get("route_gap_m") is not None]
    return {
        "sessions": len(results),
        "learned": sum(1 for r in results if r["learned"]),
        "learned_in_one": sum(1 for r in results if r["learned_in"] == 1),
        "replay": [sum(1 for r in replays if r["replay"]), len(replays)],
        "routes_worst_m": max(routes) if routes else None,
        "new_values": [sum(1 for r in news if r["new"]), len(news)],
        "one_question": [sum(1 for r in results if r["question_ok"]), len(results)],
        "asked_when_needed": [sum(1 for r in results if r["asked"] and r["question_ok"]), sum(1 for r in results if r.get("wanted_question"))],
        "asked_needlessly": sum(1 for r in results if r["asked"] and not r.get("wanted_question")),
    }


async def real(captured: list[dict], url: str, wait: float) -> dict:
    from ..understand.eval import mind_for

    mind = mind_for(url, "conscious", "")
    if not await mind.ready():
        raise SystemExit(f"no llama-server answers at {url}")
    inducer = Inducer(lambda: mind, wait_s=wait)
    out = []
    for item in captured:
        if not item["examples"]:
            continue
        started = time.perf_counter()
        data, calls, failed = await inducer.ask(item["text"], item["card"], item["known"], kinds=item.get("kinds") or ())
        seconds = time.perf_counter() - started
        read, written = inducer.usage
        made = made_from(data, item["card"], item["examples"], values_seen(item["examples"])) if data is not None else None
        prompt = inducer.messages(item["text"], item["card"], item["known"])
        expect = item.get("expect") or {}
        kind_ok = made is not None and (made.kind == expect.get("kind") or (expect.get("kind") in ("way", "habit") and made.kind in ("move", "procedure", expect.get("kind"))))
        slots_ok = made is not None and sorted(v for items in made.slots.values() for v in items) == sorted(expect.get("slots") or []) if len(item["examples"]) > 1 else None
        out.append({"read": read, "written": written, "session": item.get("session"), "kind_ok": kind_ok, "slots_ok": slots_ok, "data": data, "shown": item["examples"], "name": item["name"], "seconds": round(seconds, 2), "failed": failed, "valid": made is not None and not made.problems, "kind": made.kind if made else "", "made_name": made.name if made else "", "about": made.about if made else "", "slots": made.slots if made else {}, "problems": made.problems if made else [], "prompt_chars": sum(len(m["content"]) for m in prompt), "examples": len(item["examples"])})
        print(json.dumps({k: v for k, v in out[-1].items() if k not in ("data", "shown")}), flush=True)
    await mind.close()
    many = [o for o in out if o["examples"] > 1]
    reads = sorted(o["read"] for o in out if o.get("read"))
    writes = sorted(o["written"] for o in out if o.get("written"))
    return {"items": out, "valid": sum(1 for o in out if o["valid"]), "of": len(out), "kind_ok": sum(1 for o in out if o["kind_ok"]), "slots_ok": [sum(1 for o in many if o["slots_ok"]), len(many)], "median_s": statistics.median([o["seconds"] for o in out]) if out else None, "slowest_s": max((o["seconds"] for o in out), default=None), "prompt_chars": [min((o["prompt_chars"] for o in out), default=0), max((o["prompt_chars"] for o in out), default=0)], "read_tokens": [reads[0], statistics.median(reads), reads[-1]] if reads else None, "written_tokens": [writes[0], statistics.median(writes), writes[-1]] if writes else None}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m pebble.teach.eval", description="Play the scripted teaching sessions in the sim and score them: learned within two sessions, the replay, new values and the one question; with --main, also ask a real model to work out each session")
    parser.add_argument("--main", default="", help="llama-server URL of the main model for Gemma's part")
    parser.add_argument("--only", default="", help="comma separated session ids")
    parser.add_argument("--wait", type=float, default=120.0)
    parser.add_argument("--echo", action="store_true")
    parser.add_argument("--save", default="", help="write the results here as JSON")
    args = parser.parse_args(argv)
    sessions = load()
    if args.only:
        wanted = {int(x) for x in args.only.split(",") if x.strip()}
        sessions = [s for s in sessions if s["id"] in wanted]
    captured: list = []
    started = time.perf_counter()
    results = asyncio.run(run(sessions, args.echo, captured))
    report = {"summary": summary(results), "seconds": round(time.perf_counter() - started, 1), "results": results}
    print(json.dumps(report["summary"]))
    for result in results:
        if not (result["learned"] and result["replay"] in (None, True) and result["new"] in (None, True) and result["question_ok"]):
            print(json.dumps(result))
    if args.main:
        report["real"] = asyncio.run(real(captured, args.main, args.wait))
        print(json.dumps({k: v for k, v in report["real"].items() if k != "items"}))
    if args.save:
        Path(args.save).write_text(json.dumps(report, indent=1, default=str), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
