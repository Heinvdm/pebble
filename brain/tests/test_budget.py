import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from conftest import run, small_model

from pebble.laws import laws_text
from pebble.mind.base import MindUnavailable
from pebble.mind.budget import (
    BACKGROUND,
    BUDGET_LOG,
    CORE,
    HISTORY,
    JOB,
    NIGHT,
    PEOPLE,
    READER,
    REPLY,
    ROOM,
    SCRIPT,
    TALK_SHARE,
    TASK,
    TEACH,
    TOOLS,
    TURN,
    WORDS,
    WORK,
    Counter,
    Guard,
    GuardedMind,
    Meter,
    Prompt,
    budgets,
    ceiling,
    compaction,
    guarded,
    meter_of,
)
from pebble.mind.lawful import lawful, with_laws
from pebble.mind.profile import ModelProfile
from pebble.mind.scripted import ScriptedMind
from pebble.understand.context import Context
from pebble.understand.model import messages as reader_messages

WINDOWS = (6144, 8192, 16384)
PER_CALL = (PEOPLE, TASK, "board", "matched", WORDS, ROOM)
FROZEN = (CORE, TOOLS, "self", "notes", "household")


def test_the_table_keeps_fresh_text_the_same_and_gives_a_bigger_window_to_history_and_background_work():
    for kind in (REPLY, TURN, READER, JOB):
        small, pixel, big = (budgets(kind, w) for w in WINDOWS)
        for section in PER_CALL + FROZEN:
            assert small.get(section) == pixel.get(section) == big.get(section), (kind, section)
    for kind in (REPLY, TURN):
        assert budgets(kind, 6144)[HISTORY] < budgets(kind, 8192)[HISTORY] < budgets(kind, 16384)[HISTORY]
    assert budgets(TURN, 6144)[WORK] == budgets(TURN, 8192)[WORK] == 0 < budgets(TURN, 16384)[WORK]
    for kind in BACKGROUND:
        assert budgets(kind, 6144)[WORDS] < budgets(kind, 8192)[WORDS] < budgets(kind, 16384)[WORDS]
    assert {NIGHT, SCRIPT, TEACH} <= BACKGROUND


def test_nothing_in_the_table_goes_past_the_window_or_the_talking_ceiling():
    for window in WINDOWS:
        for kind in (REPLY, TURN, READER, JOB, NIGHT, SCRIPT, TEACH):
            table = budgets(kind, window)
            talk = sum(v for k, v in table.items() if k != WORK)
            assert talk <= ceiling(kind, window) <= window
            assert sum(table.values()) <= window
    assert ceiling(REPLY, 16384) == int(16384 * TALK_SHARE)
    assert ceiling(REPLY, 8192) == 8192 and ceiling(REPLY, 6144) == 6144
    assert ceiling(NIGHT, 16384) == 16384


def test_the_pixel_numbers_are_the_plans_and_a_life_turn_keeps_room_for_history_and_the_task():
    turn = budgets(TURN, 8192)
    assert (turn[CORE], turn[TOOLS], turn["self"], turn["notes"], turn["household"]) == (900, 1200, 350, 300, 60)
    assert turn[HISTORY] >= 2000 and budgets(REPLY, 8192)[HISTORY] >= 2000
    assert turn[HISTORY] + turn[TASK] >= 0.45 * 8192
    assert budgets(READER, 8192)[CORE] == 700


def test_compaction_comes_from_the_table_and_grows_with_the_window():
    found = [compaction(w) for w in WINDOWS]
    for window, (compact, keep) in zip(WINDOWS, found):
        assert 0 < keep < compact < window
        assert compact + budgets(TURN, window)[TOOLS] + budgets(TURN, window)[ROOM] <= ceiling(TURN, window)
    assert found[0][0] < found[1][0] < found[2][0]
    assert found[0][1] < found[1][1] < found[2][1]
    profile = ModelProfile.from_dict({"name": "e4b", "context_tokens": 8192})
    assert not profile.set_by_hand and profile.limits() == found[1]
    profile.served["context"] = 16384
    assert profile.limits() == found[2]
    profile.served["context"] = 6144
    assert profile.limits() == found[0]
    with pytest.raises(ValueError):
        ModelProfile.from_dict({"name": "bad", "context_tokens": 8192, "compact_at_tokens": 9000})


def people_text(count: int) -> str:
    lines = ["People here now:"]
    for n in range(count):
        lines.append(f"- Person{n} (family); likes: " + ", ".join(f"thing{n}{k} with a long story" for k in range(12)) + "; may ask you for small things")
    lines.append("Be equally warm and kind to everyone.")
    return "\n".join(lines)


def turn_prompt(people: str, history: list[dict] | None = None, words: str = "Ina said: hello") -> Prompt:
    history = history or []
    first = 1 + len(history)
    content = f"{people}\n\n{words}"
    messages = [{"role": "system", "content": "You are Pebble. " + laws_text()}] + history + [{"role": "user", "content": content}]
    return Prompt(messages, REPLY, [(PEOPLE, first, people)], [(HISTORY, 1, first)])


def guard(window: int = 8192) -> Guard:
    return Guard(Counter(None, 4.0), lambda: window, 200)


def test_too_many_people_are_named_only_and_the_fairness_line_stays():
    prompt = turn_prompt(people_text(6))
    fit = guard().fit(prompt, None, "reply", 90)
    assert fit.trimmed[PEOPLE][0] > budgets(REPLY, 8192)[PEOPLE] >= fit.trimmed[PEOPLE][1]
    content = fit.messages[-1]["content"]
    assert "Also here: " in content and "Person5" in content and "thing50" not in content
    assert "Person0 (family); likes" in content
    assert "Be equally warm and kind to everyone." in content
    assert content.endswith("Ina said: hello")


def test_the_laws_the_core_and_the_words_are_never_trimmed_and_an_oversized_call_is_never_sent():
    huge = "the words just said " * 3000
    prompt = turn_prompt(people_text(1), words=huge)
    fit = guard().fit(prompt, None, "reply", 90)
    assert fit.refused
    assert huge in fit.messages[-1]["content"] and laws_text() in fit.messages[0]["content"]
    sent = ScriptedMind(replies=["hi"])
    mind = GuardedMind(sent, guard())
    with pytest.raises(MindUnavailable):
        run(mind.chat(prompt, purpose="reply", max_tokens=90))
    assert sent.requests == []
    big_core = Prompt([{"role": "system", "content": laws_text() + " rule" * 4000}, {"role": "user", "content": "hi"}], REPLY)
    fit = guard().fit(big_core, None, "reply", 90)
    assert CORE in fit.over and not fit.refused and fit.messages[0]["content"] == big_core[0]["content"]


def test_history_is_dropped_oldest_first_and_never_leaves_a_tool_answer_without_its_call():
    history = []
    for n in range(40):
        history.append({"role": "user", "content": f"turn {n} " + "words " * 120})
        history.append({"role": "assistant", "content": "", "tool_calls": [{"id": f"c{n}", "type": "function", "function": {"name": "say", "arguments": "{}"}}]})
        history.append({"role": "tool", "tool_call_id": f"c{n}", "name": "say", "content": "{}"})
    prompt = turn_prompt(people_text(1), history)
    fit = guard().fit(prompt, None, "reply", 90)
    assert not fit.refused and fit.total <= 8192
    kept = fit.messages[1:-1]
    assert kept[0]["role"] == "user" and "turn 39 " in kept[-3]["content"]
    assert "turn 0 " not in json.dumps(kept)
    assert fit.trimmed[HISTORY][1] < fit.trimmed[HISTORY][0]


def test_the_task_cards_first_line_is_never_trimmed():
    card = "Doing: following Ina because she asked\n" + "\n".join(f"- step {n} " + "and more " * 30 for n in range(20))
    messages = [{"role": "system", "content": "x"}, {"role": "user", "content": card + "\n\nnow"}]
    fit = guard().fit(Prompt(messages, TURN, [(TASK, 1, card)]), None, "turn", 200)
    assert fit.messages[1]["content"].startswith("Doing: following Ina because she asked")
    assert fit.trimmed[TASK][1] <= budgets(TURN, 8192)[TASK]


def test_a_bigger_window_lets_more_history_through_but_talking_stays_under_the_ceiling():
    history = [{"role": "user" if n % 2 == 0 else "assistant", "content": f"line {n} " + "word " * 200} for n in range(120)]
    kept = {}
    for window in WINDOWS:
        fit = guard(window).fit(turn_prompt(people_text(1), history), None, "reply", 90)
        assert fit.total <= ceiling(REPLY, window)
        kept[window] = len(fit.messages)
    assert kept[6144] < kept[8192] < kept[16384]


class Tokenizer(BaseHTTPRequestHandler):
    def log_message(self, *args):
        return

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if self.path == "/tokenize":
            out = {"tokens": list(range(len(body["content"].split())))}
        else:
            out = {"prompt": " ".join(m["content"] for m in body["messages"]) + (" tool" * 50 if body.get("tools") else "")}
        data = json.dumps(out).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


@pytest.fixture
def tokenizer():
    server = ThreadingHTTPServer(("127.0.0.1", 0), Tokenizer)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def test_the_meter_writes_numbers_only_and_says_where_they_came_from(store, clock, tokenizer):
    secret = "Ina told you in private that she is planning a surprise party"
    prompt = turn_prompt(people_text(1), words=secret)
    meter = Meter(store, clock, Counter(None, 4.0))
    mind = GuardedMind(ScriptedMind(replies=["Ooh."]), Guard(meter.counter, lambda: 8192, 200), meter)
    run(mind.chat(prompt, purpose="reply", max_tokens=90))
    real = Meter(store, clock, Counter(tokenizer, 4.0))
    mind = GuardedMind(ScriptedMind(replies=["Ooh."]), Guard(real.counter, lambda: 8192, 200), real)

    async def both():
        await mind.chat(prompt, purpose="reply", max_tokens=90)
        await real.settle()

    run(both())
    first, second = store.read_lines(BUDGET_LOG)
    for record in (first, second):
        text = json.dumps(record)
        assert "surprise" not in text and "Person0" not in text and "Pebble" not in text
        assert record["kind"] == REPLY and record["window"] == 8192
        assert set(record["sizes"]) >= {"laws", CORE, PEOPLE, WORDS, ROOM}
        assert all(isinstance(v, int) for v in record["sizes"].values())
    assert first["counted"] == "estimate" and "estimated" in first
    assert second["counted"] == "tokenizer" and "estimated" not in second
    assert second["sizes"][WORDS] >= len(secret.split())


def test_the_day_line_says_how_the_prompts_did(store, clock):
    meter = Meter(store, clock, Counter(None, 4.0))
    mind = GuardedMind(ScriptedMind(replies=["Hi."]), Guard(meter.counter, lambda: 8192, 200), meter)
    run(mind.chat(turn_prompt(people_text(1)), purpose="reply", max_tokens=90))
    day = clock.local().date().isoformat()
    line = meter.day_line(day)
    assert line.startswith("1 model calls; prompts stayed in budget; the biggest was the ")
    run(mind.chat(turn_prompt(people_text(8)), purpose="reply", max_tokens=90))
    line = meter.write_day(day)
    assert "went over budget 1 time and were trimmed (people 1)" in line
    assert store.read_lines(BUDGET_LOG)[-1] == {"at": store.read_lines(BUDGET_LOG)[-1]["at"], "day": day, "line": line}


def test_the_nightly_run_writes_the_days_line(store, clock, rig_factory):
    rig = rig_factory()
    meter = Meter(rig.store, rig.clock, Counter(None, 4.0))
    mind = GuardedMind(ScriptedMind(replies=["Hi."]), Guard(meter.counter, lambda: 8192, 200), meter)
    run(mind.chat(turn_prompt(people_text(1)), purpose="reply", max_tokens=90))
    night = rig.clock.local().date().isoformat()
    rig.life.nightly.budget = meter.write_day
    report = run(rig.life.nightly.run(night, "adult", None))
    assert report["budget"].startswith("1 model calls; prompts stayed in budget")


def test_every_kind_of_call_carries_its_sections(rig_factory):
    scripted = ScriptedMind(replies=["Hello!"])
    rig = rig_factory(mind=None)
    meter = Meter(rig.store, rig.clock, Counter(None, 4.0))
    mind = lawful(GuardedMind(scripted, Guard(meter.counter, lambda: 8192, 200), meter))
    rig.turns.mind = mind
    assert meter_of(mind) is meter
    run(rig.turns.run("Time: noon\nStatus: fine\nThings on your mind (from your own memory; what others said stays their words): the cat / the ball", ["look", "set_face"], "adult", "Values: kindness."))

    async def talk():
        async for _ in rig.turns.reply("Ina is talking to you: \"hi\"", "adult", "Values: kindness.", people=people_text(2)):
            pass

    run(talk())
    ctx = Context(speaker="ina", tier="trusted", present=("ina",), places=("kitchen", "lounge"), now="2026-10-15T12:00")
    run(mind.chat(reader_messages("go to the kitchen", ctx), purpose="understand", max_tokens=160))
    records = rig.store.read_lines(BUDGET_LOG)
    turns = [r for r in records if r["kind"] == TURN]
    turn, reply, reader = turns[0], records[len(turns)], records[len(turns) + 1]
    assert {"laws", CORE, "self", TOOLS, "board", WORDS} <= set(turn["sizes"]) and WORK not in turn["sizes"]
    assert len(turns) == 2 and WORK in turns[1]["sizes"]
    assert reply["kind"] == REPLY and {"laws", CORE, "self", PEOPLE, WORDS} <= set(reply["sizes"])
    assert TOOLS not in reply["sizes"]
    assert reader["kind"] == READER and {"laws", "guide", "examples", PEOPLE, TASK, "matched", WORDS} <= set(reader["sizes"])
    assert "over" in reader and CORE in reader["over"]


def test_a_warm_call_and_the_real_call_send_the_same_trimmed_prompt():
    scripted = ScriptedMind(replies=["Hi."])
    mind = GuardedMind(scripted, guard())
    prompt = turn_prompt(people_text(7))
    run(mind.warm(prompt, purpose="warm"))
    run(mind.chat(prompt, purpose="reply", max_tokens=90))
    warmed, asked = scripted.requests
    assert warmed["messages"] == asked["messages"]
    assert "Also here: " in asked["messages"][-1]["content"]


def test_the_laws_stay_first_and_the_sections_survive_the_laws_wrapper():
    prompt = Prompt([{"role": "user", "content": "hello there"}], JOB, [(TASK, 0, "hello")], [(HISTORY, 0, 1)])
    wrapped = with_laws(prompt)
    assert isinstance(wrapped, Prompt) and wrapped[0]["content"] == laws_text()
    assert wrapped.parts == ((TASK, 1, "hello"),) and wrapped.spans == ((HISTORY, 1, 2),)


def test_the_app_mind_is_guarded_and_metered(store, clock):
    from pebble.app import make_mind

    mind, profile = make_mind("scripted", "gemma4_e4b", store, clock)
    assert meter_of(mind) is not None
    assert isinstance(guarded(ScriptedMind(), small_model()), GuardedMind)
