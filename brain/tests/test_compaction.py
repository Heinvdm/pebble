import asyncio
import json
import math
from dataclasses import replace

from conftest import run, small_model

from pebble.clock import iso
from pebble.conversation.eval_fold import load as load_fold
from pebble.life.folding import candidates, picked, promises_in, turned
from pebble.life.scene import LaterScene, who
from pebble.life.taskcard import CARD_CHARS, PROMISE_S, Live, TaskCard
from pebble.life.trying_scene import AT, TRYING
from pebble.mind.base import MindReply
from pebble.mind.budget import BUDGET_LOG, FOLD, REPLY_TRIM, TASK, Counter, Meter, cut, note_event
from pebble.mind.history import History
from pebble.mind.profile import ModelProfile
from pebble.mind.scripted import ScriptedMind
from pebble.body.profile import resolve_profile
from pebble.people.trust import TRUSTED
from pebble.self.recall.board import BOARD_LINE, DEEP_LINE
from pebble.self.recall.core import DEEP_CHARS, WORDS_KEPT, WORDS_PIECE, Recall, arguments_of, pieces_of
from pebble.understand.context import context_from
from pebble.understand.rules import understood

TOOLS = ["look", "set_face", "remember", "read_sensors"]
WORDS = "Right, so this week is a bit busy, because Sam has football practice on Wednesday and I have that long work dinner on Tuesday night, but the important thing is that the plumber, Rewi, is coming on Thursday at eight to fix the dripping tap."


def talk_turn(clock, n: int, by: str = "ina", label: str = "Ina", said: str = "", reply: str = "Mm.", t: float | None = None) -> dict:
    text = said or f"line {n} about the garden and the weather " + "and more words " * 6
    return {
        "at": iso(clock.now()),
        "t": clock.now() if t is None else t,
        "audience": [by],
        "by": by,
        "tier": "trusted",
        "messages": [{"role": "user", "content": f'Answer {label} out loud now.\n{label} is talking to you: "{text}"'}, {"role": "assistant", "content": reply}],
    }


def life_turn(clock, n: int) -> dict:
    return {"at": iso(clock.now()), "t": clock.now(), "messages": [{"role": "user", "content": f"Time: 12:{n % 60:02d}\nStatus: " + "battery 80% " * 25 + f"\nEvents: event number {n}"}, {"role": "assistant", "content": "ok"}]}


def stage_args(rig) -> tuple:
    return ("newborn", rig.books.values.describe())


async def collect(stream) -> str:
    return "".join([piece async for piece in stream])


def test_the_reply_path_folds_nothing_until_the_window_would_overflow(rig_factory):
    rig = rig_factory(model=small_model())
    for n in range(24):
        rig.history.add_turn(**{"messages": life_turn(rig.clock, n)["messages"], "at": iso(rig.clock.now())})
    system = rig.turns.builder.system_text(*stage_args(rig), rig.history.summary)
    assert rig.history.needs_compaction(rig.turns._fixed_tokens(system, []))
    before = len(rig.history.turns)
    run(collect(rig.turns.reply('Ina is talking to you: "hello"', *stage_args(rig))))
    rig.turns.reply_done("Hello!")
    assert len(rig.history.turns) == before + 1 and rig.turns.trims == 0 and rig.history.compactions == 0
    for n in range(24, 80):
        rig.history.add_turn(life_turn(rig.clock, n)["messages"], iso(rig.clock.now()))
        run(collect(rig.turns.reply('Ina is talking to you: "and now?"', *stage_args(rig))))
        if rig.turns.trims:
            break
    assert rig.turns.trims == 1
    events = [line for line in rig.store.read_lines(BUDGET_LOG) if line.get("event") == REPLY_TRIM]
    assert events and events[-1]["turns"] == rig.turns.trims
    assert any("event number 0" in r.text for r in rig.life.memory.recall.stream.records.values())


def fill(rig, count: int, start: int = 0) -> None:
    for n in range(start, start + count):
        rig.history.add_turn(life_turn(rig.clock, n)["messages"], iso(rig.clock.now()), t=rig.clock.now())


def due(rig) -> bool:
    return rig.turns.fold_due(*stage_args(rig))


def test_a_quiet_gap_past_three_quarters_folds_and_warms_the_reply_again(rig_factory):
    rig = rig_factory(model=small_model(read_ahead=True))
    rig.life._mind_ready = True
    count = 0
    while not due(rig):
        fill(rig, 1, count)
        count += 1
    system = rig.turns.builder.system_text(*stage_args(rig), rig.history.summary)
    assert not rig.history.needs_compaction(rig.turns._fixed_tokens(system, []))
    rig.clock.advance(10.0)

    async def go():
        rig.life.folding.tick()
        await rig.life.folding.task
        await asyncio.gather(*list(rig.life.folding.tasks))

    before = len(rig.history.turns)
    run(go())
    assert len(rig.history.turns) < before
    events = [line for line in rig.store.read_lines(BUDGET_LOG) if line.get("event") == FOLD]
    assert events[-1]["where"] == "quiet" and events[-1]["turns"] == before - len(rig.history.turns)
    warms = [r for r in rig.mind.requests if r["purpose"] == "rewarm"]
    assert len(warms) == 1 and warms[0]["messages"][-2]["content"] == rig.history.messages()[-1]["content"]


def test_nothing_is_folded_while_someone_is_talking_or_before_three_quarters(rig_factory):
    rig = rig_factory(model=small_model(read_ahead=True))
    fill(rig, 3)
    rig.clock.advance(30.0)

    async def tick():
        rig.life.folding.tick()
        await asyncio.sleep(0)
        return rig.life.folding.task

    assert run(tick()) is None and len(rig.history.turns) == 3
    count = 3
    while not due(rig):
        fill(rig, 1, count)
        count += 1
    rig.life.memory.heard("ina", "Ina", "trusted", "hang on, I'm still talking")
    assert rig.life.folding.quiet_for() < 5.0
    assert run(tick()) is None
    rig.clock.advance(4.0)
    assert run(tick()) is None
    rig.clock.advance(2.0)
    task = run(tick())
    assert task is not None


class SlowWarm(ScriptedMind):
    def __init__(self):
        super().__init__(acts=[])
        self.gave_way = 0

    async def warm(self, messages, tools=None, purpose="warm"):
        await asyncio.sleep(30.0)
        return True

    def give_way(self) -> int:
        self.gave_way += 1
        return 1


def test_someone_talking_cancels_the_warm_after_a_fold(rig_factory):
    mind = SlowWarm()
    rig = rig_factory(mind=mind, model=small_model(read_ahead=True))
    rig.life._mind_ready = True
    count = 0
    while not due(rig):
        fill(rig, 1, count)
        count += 1
    rig.clock.advance(10.0)

    async def go():
        folding = rig.life.folding
        await folding.fold("quiet")
        await asyncio.sleep(0.01)
        warming = folding.warming
        assert warming is not None and not warming.done()
        rig.life.hear("Pebble, what's that noise?")
        await asyncio.sleep(0.01)
        return warming

    warming = run(go())
    assert warming.cancelled() and mind.gave_way == 1


def test_the_task_card_rides_in_the_current_message_after_the_history(rig_factory):
    rig = rig_factory(model=small_model())
    fill(rig, 3)
    rig.turns.card = lambda kind: f"Your task card. Doing now: following Ina ({kind})"
    history = rig.history.messages()
    _, messages, _ = rig.turns._reply_messages('Ina is talking to you: "hi"', *stage_args(rig), "", None, None)
    assert [m["content"] for m in messages[1:-1]] == [m["content"] for m in history]
    assert messages[-1]["content"].startswith("Your task card. Doing now: following Ina (reply)")
    assert (TASK, len(messages) - 1, "Your task card. Doing now: following Ina (reply)") in messages.parts
    run(rig.turns.run("Time: 12:00\nEvents: nothing new", TOOLS, *stage_args(rig)))
    turn = [r for r in rig.mind.requests if r["purpose"] == "turn"][0]
    assert any("Your task card. Doing now: following Ina (turn)" in (m.get("content") or "") for m in turn["messages"])
    assert all("Your task card" not in (m.get("content") or "") for t in rig.history.turns for m in t["messages"])


def test_the_guard_never_cuts_a_one_line_card():
    line = "Your task card (from what is happening now, not from memory). Doing now: following Ina, for Ina, because Ina said: \"follow me\""
    assert cut(TASK, line) == line
    assert cut(TASK, line + "\nNext in the plan: go to the kitchen.") == line


def card_at(tmp_path):
    from pebble.clock import FakeClock
    from pebble.selfstore import SelfStore

    clock = FakeClock.at(AT)
    store = SelfStore.open(tmp_path / "self", clock)
    return TaskCard(store, clock), clock, store


def test_the_card_holds_what_it_is_doing_and_why_the_plan_tries_question_promises_decisions_and_due_items(tmp_path):
    card, clock, store = card_at(tmp_path)
    card.promised("ina", "Ina", "I'll tell you if I see the cat go into the bedroom.", {"ina"})
    card.corrected("ina", "Ina", "No, I meant my car keys, not the house keys.", {"ina"})
    card.refused("sam", "Sam", "I can't go into the bathroom.", {"ina", "sam"}, "go to the bathroom")
    live = Live("following Ina for Ina", "follow me to the kitchen, I want to show you the plant", "Ina", ("go to the kitchen", "look at the fridge"), 'Trying something new for Ina: "do a little dance". try 1: wiggle (Ina said "No.").', 'Waiting for Ina to answer: "Which room?"', "Due within the hour: 3:20, for Ina: water the plant.")
    lines = card.lines(live, frozenset({"ina", "sam"}), clock.now())
    text = "\n".join(lines)
    assert lines[0].endswith('Doing now: following Ina for Ina, because Ina said: "follow me to the kitchen, I want to show you the plant"')
    assert "Next in the plan: go to the kitchen, then look at the fridge." in text and "try 1: wiggle" in text and 'Waiting for Ina to answer: "Which room?"' in text
    assert "Due within the hour: 3:20, for Ina: water the plant." in text
    assert 'You said no to Sam when asked to go to the bathroom' in text
    assert "car keys" not in text and "cat go into the bedroom" not in text
    alone = "\n".join(card.lines(live, frozenset({"ina"}), clock.now()))
    assert "car keys" in alone and "cat go into the bedroom" in alone
    assert len(text) <= CARD_CHARS
    clock.advance(3700.0)
    later = "\n".join(card.lines(Live(), frozenset({"ina"}), clock.now()))
    assert "car keys" not in later and "cat go into the bedroom" in later
    clock.advance(PROMISE_S)
    assert card.lines(Live(), frozenset({"ina"}), clock.now()) == []
    again = TaskCard(store, clock)
    assert again.promises == [] and again.decided == []


def test_the_card_survives_a_restart_and_forget_takes_a_persons_entries(tmp_path):
    card, clock, store = card_at(tmp_path)
    card.promised("ina", "Ina", "I'll tell you a joke later.", {"ina"})
    card.corrected("sam", "Sam", "Actually, his name is Tane.", {"sam"})
    again = TaskCard(store, clock)
    assert len(again.promises) == 1 and len(again.decided) == 1
    again.forget("ina", ["Ina"])
    assert again.promises == [] and len(again.decided) == 1


def test_the_reader_gets_a_short_card_as_its_last_task_line():
    ctx = context_from({"activity": {"kind": "wait", "by": "ina"}, "recent": ["ina: wait here"]})
    ctx = replace(ctx, card="Task card: next go to the kitchen")
    parts = ctx.parts()
    assert parts[-1] == (TASK, "Task card: next go to the kitchen")
    assert [section for section, _ in parts].count(TASK) >= 3


def fold_turns(store, clock, turns) -> list:
    recall = Recall(store, clock)
    recall.from_turns(turns)
    return list(recall.stream.records.values())


def test_folding_keeps_long_words_and_what_it_answered(store, clock):
    records = fold_turns(store, clock, [talk_turn(clock, 1, said=WORDS, reply="That's a busy week. Thursday will be tap day then.")])
    said = [r for r in records if r.kind == "said"]
    assert any("Rewi, is coming on Thursday at eight" in r.text for r in said)
    assert all(len(r.text) <= 200 for r in records) and all(r.who == "ina" and r.mark == "private" for r in said)
    assert any("you answered" in r.text or "You answered Ina" in r.text for r in said)


def test_folding_keeps_tool_results_under_the_merged_tools(store, clock):
    calls = [
        {"id": "a", "type": "function", "function": {"name": "do", "arguments": json.dumps({"words": "follow Ina"})}},
        {"id": "b", "type": "function", "function": {"name": "recall", "arguments": json.dumps({"about": "ball"})}},
        {"id": "c", "type": "function", "function": {"name": "say", "arguments": json.dumps({"text": "I saw your ball by the couch a minute ago, Ina, next to the slipper."})}},
        {"id": "d", "type": "function", "function": {"name": "remember", "arguments": json.dumps({"fact": "Sam's birthday party", "kind": "event", "when": "12 March"})}},
    ]
    results = [
        {"role": "tool", "tool_call_id": "a", "name": "do", "content": json.dumps({"ok": True, "answer": "yes", "read_as": "follow Ina"})},
        {"role": "tool", "tool_call_id": "b", "name": "recall", "content": json.dumps({"ok": True, "thing": "the ball was by the couch at 2:10 pm"})},
        {"role": "tool", "tool_call_id": "c", "name": "say", "content": json.dumps({"ok": True})},
        {"role": "tool", "tool_call_id": "d", "name": "remember", "content": json.dumps({"ok": True})},
    ]
    turn = {"at": iso(clock.now()), "t": clock.now(), "messages": [{"role": "user", "content": "Time: 12:00\nEvents: 12:00:01 Ina came in; 12:00:05 Sam asked you to go to the bathroom; you said no (that room is private)"}, {"role": "assistant", "content": "", "tool_calls": calls}] + results}
    texts = " | ".join(r.text for r in fold_turns(store, clock, [turn]))
    assert "you did: follow Ina (yes)" in texts and "you recalled ball: the ball was by the couch at 2:10 pm" in texts
    assert 'you said: "I saw your ball by the couch a minute ago, Ina, next to the slipper."' in texts and "you kept a date: Sam's birthday party" in texts
    assert "Ina came in" in texts
    decided = [r for r in fold_turns(store, clock, [turn]) if r.kind == "decided"]
    assert decided and decided[0].text.startswith("Sam asked you to go to the bathroom; you said no")
    assert arguments_of('{"a": 1}') == {"a": 1} and arguments_of("not json") == {}


def test_corrections_and_refusals_become_decided_records_that_come_back_with_the_topic(store, clock):
    turns = [
        talk_turn(clock, 1, said="Can you keep an eye out for my house keys today?", reply="Okay, the house keys."),
        talk_turn(clock, 2, said="No, I meant my car keys, not the house keys.", reply="Oh, your car keys. Got it."),
        talk_turn(clock, 3, by="sam", label="Sam", said="Can you tell me where Ina hides the chocolate?", reply="I'd rather not say where Ina keeps her things."),
    ] + [talk_turn(clock, n) for n in range(4, 14)]
    recall = Recall(store, clock)
    recall.from_turns(turns)
    decided = [r for r in recall.stream.records.values() if r.kind == "decided"]
    assert {r.text for r in decided} == {'Ina corrected you: "No, I meant my car keys, not the house keys."', 'You told Sam no: "I\'d rather not say where Ina keeps her things."'}
    assert all(r.importance > max(x.importance for x in recall.stream.records.values() if x.kind == "said") for r in decided)
    run(recall.work(lambda: True))
    found = run(recall.search("which keys was I looking for", frozenset({"ina"}), ("ina",)))
    assert any("corrected you" in line and "car keys" in line for line in found)
    assert not any("Sam" in line for line in found)


def test_folding_keeps_the_last_four_turns_with_whoever_pebble_is_talking_to(store, clock):
    history = History(store, small_model(compact_at_tokens=1500, keep_tokens_after_compaction=300))
    for n in range(6):
        history.add_turn(**talk_turn(clock, n))
        for m in range(3):
            history.add_turn(**life_turn(clock, n * 10 + m))
    history.add_turn(**{k: v for k, v in talk_turn(clock, 99, by="sam", label="Sam").items()})
    history.talker = lambda: "ina"
    fold, keep = history.plan()
    kept_talk = [t for t in keep if t.get("by") == "ina"]
    assert len(kept_talk) == 4 and all(t not in fold for t in kept_talk)
    assert any(t.get("by") is None for t in fold) and keep[-1].get("by") == "sam"
    history.talker = lambda: None
    fold, keep = history.plan()
    assert len([t for t in keep if t.get("by") == "ina"]) < 4


def test_promise_patterns_and_turning_the_words_round():
    assert promises_in("Sure! I'll remind you to call Mo at six. It's sunny.") == ["I'll remind you to call Mo at six."]
    assert promises_in("I'll be fine. Let me check the door.") == []
    assert turned("remind you to put your coat on.") == "remind me to put my coat on"
    assert picked('{"keep":[2,9,2,1]}', 3) == [2, 1] and picked("nope", 3) == []


def promise_scene(tmp_path, people, readings: dict, reply: str):
    async def go():
        play = LaterScene(tmp_path / "self", people, AT, readings)
        await play.setup()
        life = play.life
        life._mind_ready = True
        life.p.turns.mind.replies = [reply]
        name = people[0].name
        await play.scene.say(name, "I need to remember something.")
        person = life.company.book.find(name.lower())
        observation = f'Answer {name} out loud now.\n{name} is talking to you: "I need to remember something."'
        await collect(life.reply(observation, [], 90, speaker=person.id))
        life.reply_done(reply)
        for _ in range(40):
            if not any(not task.done() for task in life.folding.tasks):
                break
            await play.scene.run(0.5)
        out = {"items": [item.words for item in life.later.agenda.waiting()], "promises": [p["text"] for p in life.taskcard.promises], "said": play.scene.lines}
        await life.folding.close()
        await play.close()
        return out

    return run(go(), timeout=120)


def test_a_promise_in_talk_becomes_an_agenda_item_without_a_second_read_back(tmp_path):
    readings = {"remind me to water the plant in twenty minutes": {"kind": "say_to", "who": "me", "text": "water the plant", "when": {"in_s": 1200}}}
    out = promise_scene(tmp_path, [who("Ina", TRUSTED)], readings, "Sure, I'll remind you to water the plant in twenty minutes.")
    assert out["items"] == ["water the plant"] and out["promises"] == []
    assert not any("I'll remind you to water the plant" in line and "says" in line for line in out["said"])


def test_a_promise_someone_may_not_set_stays_open_on_the_card(tmp_path):
    readings = {"remind me to water the plant in twenty minutes": {"kind": "say_to", "who": "me", "text": "water the plant", "when": {"in_s": 1200}}}
    out = promise_scene(tmp_path, [who("Rua", None)], readings, "Sure, I'll remind you to water the plant in twenty minutes.")
    assert out["items"] == [] and out["promises"] == ["Sure, I'll remind you to water the plant in twenty minutes."]


def test_a_promise_with_no_time_stays_open_on_the_card(tmp_path):
    out = promise_scene(tmp_path, [who("Ina", TRUSTED)], {}, "I'll tell you if I see the cat go into the bedroom.")
    assert out["items"] == [] and out["promises"] == ["I'll tell you if I see the cat go into the bedroom."]


def test_a_promise_that_cannot_be_kept_is_said(tmp_path):
    readings = {"remind me to take the cake out when it's golden": {"kind": "say_to", "who": "me", "text": "take the cake out", "on": {"event": "cannot_tell"}}}
    out = promise_scene(tmp_path, [who("Ina", TRUSTED)], readings, "Sure, I'll remind you to take the cake out when it's golden.")
    assert out["items"] == [] and out["promises"] == []
    assert any("Sorry Ina, I can't keep that promise after all. I can't tell when that happens." in line for line in out["said"])


class Picker(ScriptedMind):
    async def chat(self, messages, tools=None, purpose="turn", max_tokens=None, options=None):
        if purpose == "picks":
            self.requests.append({"purpose": purpose, "messages": messages, "options": options.summary() if options else None})
            lines = messages[-1]["content"].splitlines()
            wanted = next(n for n, line in enumerate(lines, 1) if "Rewi" in line)
            return MindReply(json.dumps({"keep": [wanted]}))
        return await super().chat(messages, tools, purpose, max_tokens, options)


def test_its_own_picks_copy_the_chosen_lines_with_more_weight(rig_factory):
    mind = Picker(acts=[])
    rig = rig_factory(mind=mind, model=small_model(fold_picks=True))
    rig.life._mind_ready = True
    rig.history.add_turn(**talk_turn(rig.clock, 0, said=WORDS))
    fill(rig, 30)
    rig.clock.advance(400.0)
    folded = run(rig.life.folding.fold("quiet", warm=False))
    assert folded > 0
    asked = [r for r in mind.requests if r["purpose"] == "picks"]
    assert len(asked) == 1 and asked[0]["options"]["grammar"] is True
    picks = [r for r in rig.life.memory.recall.stream.records.values() if "Rewi" in r.text]
    assert max(r.importance for r in picks) >= 7
    events = [line for line in rig.store.read_lines(BUDGET_LOG) if line.get("event") == FOLD]
    assert events[-1]["picks"] == 1


def test_picks_are_off_by_default_and_need_a_cool_phone():
    gemma = ModelProfile.load(resolve_profile("gemma4_e4b", "model"))
    assert gemma.fold_picks is False and ModelProfile.from_dict({"name": "x"}).fold_picks is False


def test_the_picks_lines_leave_out_overheard_words(clock):
    turn = life_turn(clock, 1)
    turn["messages"][0]["content"] += '\nHeard: Sam told Mo a secret about the party'
    lines = candidates([turn, talk_turn(clock, 2, said=WORDS)])
    assert not any("secret" in line["text"] for line in lines)
    assert any("event number 1" in line["text"] for line in lines) and any("Rewi" in line["text"] for line in lines)


def test_the_day_line_counts_quiet_folds_and_reply_path_trims(store, clock):
    meter = Meter(store, clock, Counter(None, 4.0))
    store.append(BUDGET_LOG, {"at": iso(clock.now()), "day": clock.local().date().isoformat(), "kind": "reply", "purpose": "reply", "window": 8192, "sizes": {"core": 100}, "total": 100})
    note_event(store, clock, FOLD, where="quiet", turns=12)
    note_event(store, clock, FOLD, where="turn_end", turns=3)
    note_event(store, clock, REPLY_TRIM, turns=1)
    line = meter.day_line(clock.local().date().isoformat())
    assert "the history was folded 2 times in quiet moments" in line and "the reply path had to trim the history 1 time" in line


def test_the_eval_set_has_twenty_scenes_of_four_kinds():
    filler, scenes = load_fold()
    kinds = {}
    for scene in scenes:
        kinds[scene["kind"]] = kinds.get(scene["kind"], 0) + 1
        assert scene["probe"] and scene["good"] and 60 <= scene["filler"] <= 110
    assert len(scenes) == 20 and kinds == {"fact": 5, "correction": 5, "promise": 5, "task": 5} and len(filler) >= 30


def test_scene_a_long_talk_while_following_and_trying_something_new(tmp_path):
    play, out = asyncio.run(asyncio.wait_for(TRYING["long_talk"](tmp_path / "self", False), 600))
    assert out["following"] == "following Ina for Ina" and out["promise"] == ["water the plant"]
    assert out["passed_point"] and out["before_quiet"] == 0 and out["after_quiet"] == 1 and out["folds"] >= 2
    assert out["trims"] == 0 and all(e["event"] == FOLD and e["where"] == "quiet" for e in out["events"])
    assert out["warms"].count("rewarm") == out["folds"]
    assert 'Doing now: following Ina for Ina, because Ina said: "Follow me."' in out["card_following"]
    card = out["card_trying"]
    assert card.startswith("Your task card") and 'Doing now: trying "do a little dance" for Ina' in card
    assert 'try 1: make a happy face, turn left 90 degrees, turn right 90 degrees (Ina said "No.")' in card and "try 2: spin round, wiggle" in card
    assert "Due within the hour" in card and "water the plant" in card
    assert out["kept"] is not None and len(out["tries"]) == 2


def test_thinking_back_fits_one_memory_in_the_recall_row_and_takes_the_boards_place(rig_factory, clock):
    import test_holds as th

    def prepare(talk):
        memory = talk.rig.life.memory
        ina = talk.ids["ina"]
        memory.recall.from_turns([talk_turn(clock, 1, by=ina, said=WORDS, reply="That's a busy week. Thursday will be tap day then.")])
        memory.recall.keep("The plant by the window likes the morning sun.", weight=5)
        run(memory.recall.work(lambda: True))
        run(memory.refresh())
        memory.swap_ahead()

    talk, _, holds = th.asked(rig_factory, clock, 3.0, "Pebble, do you remember when the plumber is coming?", prepare=prepare)
    reply = [r for r in talk.rig.turns.mind.requests if r["purpose"] == "reply"][-1]
    words = reply["messages"][-1]["content"]
    deep = next(line for line in words.splitlines() if line.startswith(DEEP_LINE))
    assert "Thursday at eight" in deep and "you answered" not in deep
    assert len(deep) <= len(DEEP_LINE) + DEEP_CHARS and math.ceil(len(deep) / 3.0 * 1.05) <= 60
    assert BOARD_LINE not in words and "On your mind: " not in words


def test_pieces_keep_a_fact_with_what_it_is_about():
    pieces = pieces_of(WORDS, WORDS_KEPT, WORDS_PIECE)
    assert any("plumber, Rewi, is coming on Thursday at eight" in piece for piece in pieces)
    assert all(len(piece) <= WORDS_PIECE for piece in pieces) and len(" ".join(pieces)) >= len(WORDS)
    assert pieces_of("short and sweet", WORDS_KEPT, WORDS_PIECE) == ["short and sweet"]


def test_talk_while_following_stays_talk_and_a_short_the_still_retargets():
    following = context_from({"activity": {"kind": "follow", "by": "ina", "with": "ina"}})
    for line in ("The kids next door were playing cricket in the street until it got dark.", "I watched that cooking show again last night, the one with the big tent.", "My phone keeps running out of battery, I think it's getting old."):
        assert understood(line, following).kind == "chat"
    finding = context_from({"activity": {"kind": "find", "by": "ina"}})
    assert understood("no, the red ball", finding).as_dict() == {"kind": "find", "thing": "ball"}
    assert understood("the big red ball", finding).as_dict() == {"kind": "find", "thing": "ball"}
