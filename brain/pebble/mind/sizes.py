import argparse
import asyncio
import json
import sys
import tempfile
from pathlib import Path

from ..activities.base import Ending
from ..activities.gate import Asker
from ..activities.places import GoToPlace
from ..activities.trying import PLAN_TOKENS, THINK_TOKENS
from ..script.write import WRITE_TOKENS, Task
from ..teach.induce import TEACH_TOKENS
from ..teach.record import sample as sample_record
from ..activities.unstuck import Case
from ..conversation.gist import GIST_SYSTEM
from ..conversation.quality import PROBES, TURNS, Bench
from ..conversation.turns import Turn
from ..self.tidy import SYSTEM as TIDY_SYSTEM
from ..self.words import SYSTEM as WORDS_SYSTEM
from ..understand.model import messages as reader_messages
from ..understand.request import Request
from .budget import JOB, MATCHED, NIGHT, PEOPLE, SECTION_ORDER, TASK, TURN, Counter, Guard, Prompt, budgets, ceiling, compaction, pieces, row
from .lawful import with_laws
from .profile import ModelProfile
from .decisions import OwnWords
from .wordsmith import Wordsmith

PROFILE = Path(__file__).resolve().parents[1] / "profiles" / "model_gemma4_e4b.json"
TALK = [
    "Ina: did you put the washing out?",
    "Sam: not yet, it's still in the machine",
    "Ina: it might rain later though",
    "Sam: I'll do it after lunch then",
    "Mo: can someone pick up bread on the way home?",
    "Ina: I'll get it, I'm going past the shop anyway",
]
NOTES = [
    "n1: Ina likes tea in the morning and coffee after lunch.",
    "n2: Sam plays jazz records on Sundays.",
    "n3: The cat sleeps on the couch in the afternoon.",
    "n4: Mo walks the dog before work.",
    "n5: The kitchen gets warm in the evening when the oven is on.",
]
HAPPENED = [
    "- e1: I followed Ina to the kitchen and waited by the fridge.",
    "- e2: Sam laughed at my joke about wheels.",
    "- e3: I found the ball under the couch.",
    "- e4: Tui asked me to draw a dinosaur and I did.",
]


class Ruler:
    def __init__(self, counter: Counter):
        self.counter = counter

    def tokens(self, text: str) -> int:
        count = self.counter.real(text)
        if count is None:
            raise SystemExit("the llama-server stopped answering /tokenize")
        return count

    def rendered(self, messages: list[dict], tools: list[dict] | None = None) -> int:
        payload = {"messages": [{k: v for k, v in m.items() if k in ("role", "content", "tool_calls", "tool_call_id", "name")} for m in messages]}
        if tools:
            payload["tools"] = tools
        return self.tokens(self.counter.post("/apply-template", payload)["prompt"])


def measure(ruler: Ruler, prompt: Prompt, tools: list[dict] | None, room: int, window: int) -> dict:
    sections: dict = {}
    estimate: dict = {}
    for piece in pieces(prompt, tools):
        if piece.section == "tools":
            real = ruler.counter.rendered(tools) or 0
        else:
            real = ruler.tokens(piece.text)
        sections[piece.section] = sections.get(piece.section, 0) + real
        estimate[piece.section] = estimate.get(piece.section, 0) + ruler.counter.estimate(piece.text)
    whole = ruler.rendered(list(prompt), tools)
    table = budgets(prompt.kind, window)
    rows: dict = {}
    for section, count in sections.items():
        rows[row(section)] = rows.get(row(section), 0) + count
    return {
        "kind": prompt.kind,
        "sections": {name: sections[name] for name in SECTION_ORDER if name in sections},
        "estimate": {name: estimate[name] for name in SECTION_ORDER if name in estimate},
        "rows": rows,
        "budget": {name: table[name] for name in table},
        "whole_prompt": whole,
        "room": room,
        "fits": whole + room <= window,
        "under_ceiling": whole + room <= ceiling(prompt.kind, window),
    }


async def build(bench: Bench, profile: ModelProfile) -> dict:
    life = bench.life
    p = life.p
    bench.use(profile)
    now = p.clock.now()
    local = p.clock.local(now)
    out: dict = {}
    item = next(t for t in TURNS if t["id"] == "arrive")
    observation, allowed, private = bench.turn_situation(item)
    shown = p.turns._shown(allowed)
    hidden = [name for name in shown if name not in p.turns.registry.offered(allowed)]
    if hidden:
        observation = "\n".join([observation, "Tools you can't use just now: " + ", ".join(hidden) + "."])
    in_system, household, here = p.turns._people(life.company.prompt_text(now, p.clock.local))
    parts = p.turns.builder.system_parts(life.stage(local), p.books.values.describe(), p.turns.history.summary, in_system, household)
    schemas = p.turns.registry.schemas(shown) or None
    lead = [(PEOPLE, here), (TASK, p.turns._card(TURN)), (MATCHED, p.turns._matched_parts(observation, TURN)[0])]
    out["turn"] = (with_laws(p.turns._prompt(TURN, parts, [{"role": "user", "content": observation}], life.company.private_to(now), lead)), schemas, profile.max_reply_tokens)
    probe = next(x for x in PROBES if x["id"] == "joke")
    bench.here(set(probe["people"]))
    conv = bench.conversation
    conv.window.clear()
    pid = bench.ids.get(probe["who"])
    turn = Turn(id=0, started=conv.mono(), speaker=pid, label="Ina")
    obs, priv = conv._observation(turn, probe["say"], pid)
    reply, tools = bench.reply_prompt(obs, priv)
    out["reply"] = (with_laws(reply), tools, 90)
    ctx = life.commands.context(None)
    out["reader"] = (with_laws(reader_messages("could you go to the kitchen and see if the oven is still on", ctx, life.p.books.name)), None, 160)
    words = Wordsmith(None, lambda kind: None, p.turns.builder.personality_text, name=p.books.name)
    out["job: wordsmith"] = (with_laws(Prompt(words.messages("I'd love to play a game with you.", "talk"), JOB)), None, 60)
    plan_ask = "\n".join(['Asked by Ina: "do a little dance"', "Plan it."])
    out["job: plan"] = (with_laws(life.commands.trying.planner.messages(life._plan_card(plan_ask), plan_ask, [])), None, THINK_TOKENS + PLAN_TOKENS)
    own = OwnWords(lambda: None, p.books.name, p.turns.builder.personality_text)
    out["job: own words"] = (with_laws(own.messages("no", "Sorry, I only follow people I know really well.", "you only follow people you trust, and Alex is a friend", "follow them")), None, 40)
    ina = Asker("ina", "Ina", "trusted")
    going = GoToPlace(Request("go_to_place", place="kitchen"), ina)
    stuck = Ending("reflex", "you got stuck by the kitchen door", "Something's in the way, so I stopped here.")
    case = Case("k", ina, going.request, going.describe(), 0.0)
    options = [("another_way", ""), ("wait", ""), ("ask", "Ina"), ("explain", ""), ("give_up", "")]
    out["job: what now"] = (with_laws(life.commands.unstuck._prompt(case, going, stuck, options, None)), None, 24)
    out["job: gist"] = (with_laws(Prompt([{"role": "system", "content": GIST_SYSTEM}, {"role": "user", "content": "\n".join(TALK)}], JOB)), None, 48)
    out["night: tidy notes"] = (with_laws(Prompt([{"role": "system", "content": TIDY_SYSTEM.format(name=p.books.name)}, {"role": "user", "content": "Your notes:\n" + "\n".join(NOTES) + "\n\nNew memory: Ina said she'd bake bread on Saturday.\n\nOne change, as JSON:"}], NIGHT)), None, 90)
    scripts = getattr(life, "scripts", None)
    if scripts is not None:
        task = Task("count how many times the cat comes through the lounge today and tell me tonight", "ina", "Ina", "trusted")
        out["script: write"] = (with_laws(scripts.writer.messages(task, scripts.ground(None), local.replace(tzinfo=None), scripts.book.closest(task.words))), None, WRITE_TOKENS)
    teaching = getattr(life, "teaching", None)
    if teaching is not None:
        record = sample_record(now).text()
        out["teach: work out"] = (with_laws(teaching.inducer.messages(record, life._plan_card(record), teaching.book.closest(record))), None, TEACH_TOKENS)
    out["night: own words"] = (with_laws(Prompt([{"role": "system", "content": WORDS_SYSTEM.format(name=p.books.name)}, {"role": "user", "content": "How you describe yourself now:\n1. I'm a curious little robot.\n\nWhat happened lately:\n" + "\n".join(HAPPENED) + "\n\nOne change or none, as JSON:"}], NIGHT)), None, 120)
    return out


async def run(args: argparse.Namespace) -> int:
    profile = ModelProfile.load(PROFILE)
    counter = Counter(args.main, profile.chars_per_token)
    if counter.real("ready") is None:
        print(f"no llama-server answers /tokenize at {args.main}")
        return 2
    ruler = Ruler(counter)
    window = args.window
    profile.served["context"] = window
    with tempfile.TemporaryDirectory(prefix="pebble-sizes-", ignore_cleanup_errors=True) as folder:
        bench = Bench(Path(folder) / "self", args.age_days)
        await bench.setup()
        built = await build(bench, profile)
        report = {"window": window, "compaction": list(compaction(window)), "calls": {}}
        guard = Guard(counter, lambda: window, profile.max_reply_tokens)
        for name, (prompt, tools, room) in built.items():
            row_out = measure(ruler, prompt, tools, room, window)
            fit = guard.fit(prompt, tools, prompt.kind, room)
            row_out["guard"] = {"trimmed": fit.trimmed, "over": fit.over, "refused": fit.refused}
            report["calls"][name] = row_out
        await bench.close()
    text = json.dumps(report, indent=1)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    for name, data in report["calls"].items():
        shown = ", ".join(f"{k} {v}" for k, v in data["sections"].items())
        print(f"{name}: whole {data['whole_prompt']} + room {data['room']} | {shown}")
        print("    estimate: " + ", ".join(f"{k} {v}" for k, v in data["estimate"].items()))
        if data["guard"]["trimmed"] or data["guard"]["over"]:
            print(f"    guard: trimmed {data['guard']['trimmed']}, over budget {data['guard']['over']}")
    print(f"compaction at {report['compaction'][0]}, keep {report['compaction'][1]} (window {window})")
    return 0


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(errors="backslashreplace")
    parser = argparse.ArgumentParser(prog="python -m pebble.mind.sizes", description="Build each kind of call the brain makes (a reply, a life turn, the request reader, background jobs) in the sim and count every section of its prompt with the real tokenizer of a running llama-server.")
    parser.add_argument("--main", default="http://127.0.0.1:8080", help="llama-server URL to count with")
    parser.add_argument("--window", type=int, default=8192, help="the served window to plan for (6144, 8192 or 16384)")
    parser.add_argument("--age-days", type=int, default=120, help="Pebble's age, which sets its stage")
    parser.add_argument("--out", default="", help="write the full report as JSON here")
    return asyncio.run(run(parser.parse_args(argv)))


if __name__ == "__main__":
    sys.exit(main())
