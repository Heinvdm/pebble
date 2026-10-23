import asyncio
import json

from conftest import run

from pebble.activities.base import Ending
from pebble.activities.card import BLOCKS, Body, Card, request_of, said
from pebble.activities.commands import Commands
from pebble.activities.gate import Asker, Situation, Verdict, decide, unbuilt
from pebble.activities.skills import DRAFT_KEEP_S, Skills, name_of
from pebble.activities.trying import OUT_OF_IDEAS, Planner, answer_of, changed
from pebble.activities.unstuck import Unstuck, problem_of
from pebble.clock import FakeClock
from pebble.life.trying_scene import AT, FIRST, SECOND, TRYING, TryMind
from pebble.mind.base import Mind, MindReply
from pebble.mind.decisions import OwnWords, honest
from pebble.people.trust import CHILD, STRANGER, TRUSTED
from pebble.screen.gbnf import parse_gbnf
from pebble.selfstore import SelfStore
from pebble.understand.context import context_from
from pebble.understand.cover import new_act
from pebble.understand.model import ModelReader
from pebble.understand.request import Request
from pebble.understand.understanding import RULES_FIRST, Understanding

INA = Asker("ina", "Ina", TRUSTED)
CTX = context_from({"speaker": "ina", "tier": "trusted", "present": ["ina", "sam"], "names": ["ina", "sam", "mo"], "places": ["kitchen", "lounge"]})


def card(**extra) -> Card:
    values = {"places": ("kitchen", "lounge"), "people": ("ina", "sam"), **extra}
    return Card(Body(**values))


def store(tmp_path):
    clock = FakeClock.at(AT)
    return SelfStore.open(tmp_path / "self", clock), clock


def test_the_abilities_card_is_built_from_what_this_body_has():
    full = card()
    assert {"turn", "move", "wiggle", "tilt", "face", "say", "wait", "come", "look", "go_to_place", "go_to_thing", "find", "push", "back_off"} <= full.names
    assert "draw" not in full.names and card(draws=True).has("draw")
    blind = card(eyes=False)
    assert not ({"come", "look", "go_to_thing", "find", "push"} & blind.names) and blind.has("turn")
    still = card(wheels=False)
    assert not ({"turn", "move", "wiggle", "come", "go_to_place", "push", "back_off"} & still.names) and still.has("face") and still.has("say")
    assert not card(places=()).has("go_to_place") and not card(head=False).has("tilt")
    assert "place (kitchen, lounge)" in full.text() and "who (me, ina, sam)" in full.text()
    assert len(BLOCKS) == len({block.name for block in BLOCKS})


def test_the_grammar_from_the_card_holds_a_plan_to_its_blocks():
    grammar = parse_gbnf(card().grammar())
    plan = {"think": "turn one way then the other", "steps": [{"do": "face", "expression": "happy"}, {"do": "turn", "way": "left", "degrees": 90, "repeat": 2}, {"do": "push", "thing": "ball", "to": "ina"}]}
    assert grammar.matches(json.dumps(plan, separators=(",", ":")))
    assert grammar.matches('{"cant":"it has no arms"}')
    assert not grammar.matches('{"think":"x","steps":[{"do":"fly"}]}')
    assert not grammar.matches('{"think":"x","steps":[{"do":"go_to_place","place":"garden"}]}')
    assert not grammar.matches('{"think":"x","steps":[{"do":"come","who":"rua"}]}')
    assert not grammar.matches('{"think":"x","steps":[{"do":"turn","repeat":5}]}')
    nine = {"think": "x", "steps": [{"do": "wiggle"}] * 9}
    assert not grammar.matches(json.dumps(nine, separators=(",", ":")))
    blind = parse_gbnf(card(eyes=False).grammar())
    assert not blind.matches('{"think":"x","steps":[{"do":"come","who":"me"}]}')


def test_plain_code_checks_every_step_of_a_plan():
    steps, errors = card().check([{"do": "turn", "degrees": 5000}, {"do": "move", "way": "back", "metres": 3}, {"do": "go_to_place", "place": "garden"}, {"do": "push", "thing": "cat"}, {"do": "fly"}, {"do": "look"}])
    assert steps == [{"do": "turn", "degrees": 720, "way": "around"}, {"do": "move", "way": "back", "metres": 0.2}, {"do": "look", "who": "me"}]
    assert any("garden" in e for e in errors) and any("alive" in e for e in errors) and any("fly" in e for e in errors)
    assert card().check([{"do": "wiggle"}] * 9)[1] == ["the plan has 9 steps; at most 8"]
    assert request_of({"do": "push", "thing": "ball", "to": "ina"}) == Request("play", thing="ball", to="ina")
    assert request_of({"do": "turn", "way": "around"}).degrees == 360 and request_of({"do": "face", "expression": "happy"}) is None
    assert said(FIRST["steps"]) == "make a happy face, turn left 90 degrees, turn right 90 degrees"


def test_answers_to_like_that_are_read_three_ways_by_plain_code():
    for text in ("Yes!", "that's it", "Perfect, Pebble.", "good boy", "yes like that"):
        assert answer_of(text) == ("yes", ""), text
    for text in ("No.", "not like that", "No, not like that.", "nope"):
        assert answer_of(text) == ("no", ""), text
    assert answer_of("No, faster!") == ("nearly", "faster")
    assert answer_of("Faster!") == ("nearly", "faster") and answer_of("twice") == ("nearly", "twice")
    assert answer_of("and then come back") == ("nearly", "then come back")
    assert answer_of("Yes, but slower.") == ("nearly", "slower") and answer_of("almost, but spin more") == ("nearly", "spin more")
    assert answer_of("Never mind.") == ("end", "") and answer_of("That's enough.") == ("end", "")
    assert answer_of("hahaha") == ("laugh", "")
    assert answer_of("come here") is None and answer_of("what's for dinner") is None


def test_a_nearly_change_has_a_plain_code_fallback():
    steps = SECOND["steps"]
    assert all(step.get("speed") == "quick" for step in changed(steps, "faster") if step["do"] == "turn")
    swapped = changed(FIRST["steps"], "the other way")
    assert [s.get("way") for s in swapped if s["do"] == "turn"] == ["right", "left"]
    assert changed([{"do": "turn", "way": "around", "degrees": 360}], "twice") == [{"do": "turn", "way": "around", "degrees": 360, "repeat": 2}]
    assert changed(FIRST["steps"], "and then come back")[-1] == {"do": "come", "who": "me"}
    assert changed(FIRST["steps"], "make it sparkle") is None


def test_skill_names_come_from_the_words():
    assert name_of("do a little dance") == "little dance" and name_of("Do a little dance for Sam.") == "little dance"
    assert name_of("Pebble, can you do your dance please") == "dance" and name_of("try the dance again") == "dance"
    assert name_of("show Mo your best trick") == "best trick" and name_of("push the ball to Ina") == "push the ball to ina"


def test_kept_skills_are_data_found_by_name_and_alias(tmp_path):
    self_store, clock = store(tmp_path)
    skills = Skills(self_store, "pc-sim", clock)
    kept = skills.keep("little dance", "do a little dance", FIRST["steps"], {"id": "ina", "name": "Ina", "tier": TRUSTED})
    data = self_store.read("mine/bodies/pc-sim/skills/little-dance.json")
    assert data["name"] == "little dance" and data["steps"] == FIRST["steps"] and data["kind"] == "move"
    assert data["taught_by"] == {"id": "ina", "name": "Ina", "tier": TRUSTED} and data["good"] == 0 and data["versions"] == []
    assert {"name", "aliases", "kind", "about", "steps", "taught_by", "versions", "good", "bad"} <= set(data)
    assert "dance" in kept.aliases and data["about"] == said(FIRST["steps"])
    for text in ("do your dance", "Dance!", "do the little dance", "dance for Ina", "can you do your little dance?"):
        assert skills.matches(text) is not None, text
    for text in ("don't dance", "Sam can dance", "do a happy dance", "come here", "spin around"):
        assert skills.matches(text) is None, text
    spin = skills.keep("spin twice then come to me", "spin twice then come to me", [{"do": "turn", "way": "around", "degrees": 360, "repeat": 2}, {"do": "come", "who": "me"}], {"id": "ina", "name": "Ina", "tier": TRUSTED})
    assert skills.matches("come") is None and skills.matches("come to me") is None and skills.matches("spin twice then come to me").name == spin.name
    newer = skills.keep("little dance", "do a little dance", SECOND["steps"], {"id": "sam", "name": "Sam", "tier": CHILD})
    assert newer.steps == SECOND["steps"] and newer.versions[0]["steps"] == FIRST["steps"] and newer.versions[0]["taught_by"]["id"] == "ina"
    skills.used(newer, True, "do your dance")
    skills.used(newer, False)
    again = skills.get("little dance")
    assert again.good == 1 and again.bad == 1
    assert "Skills you know: little dance" in skills.listed("do the dance")
    other = Skills(self_store, "hexapod", clock)
    assert other.find("little dance") is None and other.elsewhere("do a little dance").name == "little dance"


def test_drafts_last_seven_days_and_forget_drops_the_teacher(tmp_path):
    self_store, clock = store(tmp_path)
    skills = Skills(self_store, "pc-sim", clock)
    skills.draft("little dance", "do a little dance", [{"steps": FIRST["steps"], "answer": "", "answer_kind": "silence"}], "ina")
    assert skills.drafted("try the dance again").best() == FIRST["steps"]
    clock.advance(DRAFT_KEEP_S + 60)
    assert skills.drafted("try the dance again") is None
    skills.draft("little dance", "do a little dance", [{"steps": FIRST["steps"], "answer": "", "answer_kind": "silence"}], "ina")
    skills.keep("little dance", "do a little dance", FIRST["steps"], {"id": "ina", "name": "Ina", "tier": TRUSTED})
    assert skills.drafted("try the dance again") is None
    skills.draft("happy dance", "do a happy dance", [{"steps": SECOND["steps"], "answer": "no", "answer_kind": "no"}], "ina")
    skills.forget("ina", ["Ina"])
    assert skills.get("little dance").taught_by == {"id": None, "name": "", "tier": TRUSTED}
    assert skills.drafted("try the happy dance again") is None and skills.get("little dance") is not None


class Planned(Mind):
    def __init__(self, replies):
        self.replies = list(replies)
        self.asked = []

    async def chat(self, messages, tools=None, purpose="turn", max_tokens=None, options=None):
        self.asked.append((messages, purpose, max_tokens, options))
        return MindReply(json.dumps(self.replies.pop(0)) if self.replies else '{"cant":"none"}')


def test_the_planner_sends_only_the_error_lines_back_for_one_fix():
    bad = {"think": "go to the garden", "steps": [{"do": "go_to_place", "place": "garden"}, {"do": "turn", "way": "left"}]}
    good = {"think": "the lounge instead", "steps": [{"do": "go_to_place", "place": "lounge"}, {"do": "turn", "way": "left"}]}
    mind = Planned([bad, good])
    planner = Planner(lambda: mind)
    result = run(planner.ask(card(), 'Asked by Ina: "go to the garden and turn"\nPlan it.'))
    assert result.steps == [{"do": "go_to_place", "place": "lounge"}, {"do": "turn", "way": "left"}] and not result.errors
    fix = mind.asked[1][0][-1]["content"]
    assert fix.startswith("Problems with that plan:\nstep 1:") and "garden" in fix and "Asked by" not in fix
    messages, purpose, max_tokens, options = mind.asked[0]
    assert purpose == "plan" and max_tokens == 476 and options.grammar and options.temperature == 0.3
    assert "Blocks (each step" in messages[0]["content"] and messages[-1]["content"].endswith("Plan it.")
    cant = run(Planner(lambda: Planned([{"cant": "no arms"}])).ask(card(), "Plan it."))
    assert cant.cant == "no arms" and not cant.steps
    assert run(Planner(lambda: None).ask(card(), "Plan it.")).failed and not Planner(lambda: None).ready()


def test_the_gate_still_answers_for_something_new():
    request = Request("try_new", text="do a little dance")
    assert unbuilt(request) == [] and decide(request, INA, Situation(later=True)).yes
    assert decide(request, Asker(None, "someone", STRANGER), Situation(later=True)).yes
    assert not decide(request, INA, Situation(later=True, asleep=True)).yes


def test_own_words_must_be_honest_short_and_kind():
    line = "Sorry, I only follow people I know really well."
    facts = "you only follow people you trust, and Alex is a friend"
    assert honest("no", "Sorry, Alex, I only tag along with people I know well.", line, facts, ("alex", "ina")) == ""
    assert honest("no", "Okay, I'll follow you!", line, facts) == "it did not say no"
    assert honest("no", "Sure, sorry, I'm coming.", line, facts) == "it sounded like a yes"
    assert honest("no", "Sorry, maybe in 5 minutes.", line, facts) == "it added the number 5"
    assert honest("no", "Sorry, not now, maybe tomorrow.", line, facts) == "it added a time (tomorrow)"
    assert honest("no", "Sorry, Ina doesn't let me.", line, facts, ("ina",)) == "it added ina"
    assert honest("no", "Sorry " + "really " * 15, line, facts) == "too long"
    assert honest("yes", "Sorry, no.", "Coming!", "") == "it sounded like a no"
    assert honest("ask", "Who should I follow?", "Who should I follow: Sam or Mo?", "", ("sam", "mo")) == "it dropped sam"
    assert honest("ask", "Sam or Mo, who should I follow", "Who should I follow: Sam or Mo?", "", ("sam", "mo")) == "it did not ask"


class Slow(Mind):
    def __init__(self, text: str, delay: float):
        self.text = text
        self.delay = delay

    async def chat(self, messages, tools=None, purpose="turn", max_tokens=None, options=None):
        await asyncio.sleep(self.delay)
        return MindReply(self.text)


def test_own_words_fall_back_to_the_fixed_line_when_slow_or_wrong():
    line = "Sorry, I only follow people I know really well."
    quick = OwnWords(lambda: Slow("Sorry, I only tag along with people I know well.", 0.0))
    assert run(quick.word("no", line, "you only follow people you trust", "follow them")) == "Sorry, I only tag along with people I know well."
    slow = OwnWords(lambda: Slow("Sorry, I only tag along with people I know well.", 2.0), wait_s=0.05)
    assert run(slow.word("no", line, "", "")) == line
    leaky = OwnWords(lambda: Slow("Sorry, Sam told me a secret.", 0.0))
    leaky.leaks = lambda text: "secret" in text
    assert run(leaky.word("no", line, "", "")) == line
    assert run(OwnWords(lambda: None).word("no", line)) == line
    assert run(quick.word("no", "")) == ""


def test_harm_privacy_and_watch_lines_are_never_reworded():
    commands = Commands.__new__(Commands)
    harm = Verdict("no", "you never harm a living thing on purpose, even when told to (law 1)", "I won't hurt it.")
    assert commands._fixed(Request("harm", thing="spider"), harm.say, harm)
    assert commands._fixed(Request("look"), "Not now — I'm giving someone privacy.", None)
    assert commands._fixed(Request("watch", thing="baby"), "I'll keep an eye on the baby...", Verdict("yes", "ok", "x"))
    assert commands._fixed(Request("go_to_place", place="bathroom"), "x", Verdict("no", "that room is private, so you never go in on your own", "x"))
    assert not commands._fixed(Request("follow", who="me"), "Sorry, I only follow people I know really well.", Verdict("no", "you only follow people you trust", "x"))


def test_new_act_words_reach_the_model_even_in_rules_first():
    assert new_act("Do a little dance.") and new_act("Push the ball to Ina.") and new_act("Pretend to be a train.") and new_act("Nod three times.")
    for text in ("Do you dance?", "I like to dance.", "Don't dance.", "Tell Sam a joke.", "Do that again.", "A dog is dancing"):
        assert not new_act(text), text
    mind = TryMind({"Do a little dance.": {"kind": "try_new", "text": "do a little dance"}})
    understanding = Understanding(ModelReader([("conscious", mind)]), RULES_FIRST)
    reading = run(understanding.read("Do a little dance.", CTX))
    assert reading.request == Request("try_new", text="do a little dance") and reading.source == "conscious"
    understanding.skills = lambda text: Request("try_new", text="do your dance", name="little dance") if "your dance" in text else None
    door = understanding.door("do your dance", CTX)
    assert door.why == "a kept skill" and door.reading.request.name == "little dance" and not door.model
    assert understanding.door("Mo, do your dance", CTX).why != "a kept skill"


class Choosing(Mind):
    def __init__(self, reply):
        self.reply = reply
        self.asked = []

    async def chat(self, messages, tools=None, purpose="turn", max_tokens=None, options=None):
        self.asked.append((messages, purpose, options))
        return MindReply(self.reply)


def test_the_what_now_call_offers_options_from_code_and_takes_only_those():
    from pebble.activities.kinds import Come
    from pebble.activities.unstuck import Case

    fake = type("Fake", (), {})()
    fake.clock = FakeClock.at(AT)
    unstuck = Unstuck(fake, lambda: Choosing('{"choose":"ask","who":"ina"}'))
    activity = Come(Request("come", who="me"), INA)
    ending = Ending("lost", "you lost sight of them", "I lost you. I'll stop here.")
    case = Case("k", INA, activity.request, "coming to you", 0.0)
    options = [("another_way", ""), ("wait", ""), ("ask", "Ina"), ("explain", ""), ("give_up", "")]
    assert run(unstuck.what_now(case, activity, ending, options)) == ("ask", "Ina")
    grammar = parse_gbnf(unstuck._grammar(options))
    assert grammar.matches('{"choose":"wait"}') and grammar.matches('{"choose":"ask","who":"ina"}') and not grammar.matches('{"choose":"dance"}')
    refused = unstuck.options(None, Ending("refused", "x", ""), INA)
    assert [option for option, _ in refused] == ["another_way", "explain", "give_up"]
    off = Unstuck(fake, lambda: Choosing('{"choose":"fly"}'))
    assert run(off.what_now(case, activity, ending, options)) is None
    assert run(Unstuck(fake, lambda: None).what_now(case, activity, ending, options)) is None
    assert not Unstuck(fake, lambda: None).wants(activity, ending)
    assert problem_of(ending) == "I lost you"
    assert problem_of(Ending("refused", "you stopped trying x: go to the kitchen was refused (Mo asked you to stay out of the kitchen)", "")) == "Mo asked me to stay out of the kitchen"


def test_do_reaches_something_new_in_plain_words(tmp_path):
    from pebble.life.trying_scene import staged
    from pebble.sim.scene import Who

    async def scenario():
        play, mind = await staged(tmp_path / "self", False, [Who("Ina", TRUSTED, 1300.0, 0.0)], [FIRST])
        life = play.life
        registry = life.p.turns.registry
        await play.scene.say("Ina", "hello Pebble")
        life.company.asking = life._asking(play.scene.clock.now())
        done = await registry.call("do", {"words": "do a little dance", "for": "Ina"})
        await play.scene.run(1.0)
        doing = getattr(life.commands.runner.current, "kind", None)
        purposes = mind.purposes()
        await play.close()
        return done, doing, purposes

    done, doing, purposes = run(scenario(), timeout=120)
    assert done["ok"] and doing == "try_new" and "plan" in purposes and done["read_as"] == "try something new (do a little dance)"


def scene(name: str, tmp_path):
    return asyncio.run(asyncio.wait_for(TRYING[name](tmp_path / "self", False), 600))


def test_scene_a_little_dance_with_no_nearly_and_yes_then_done_at_once(tmp_path):
    play, out = scene("dance", tmp_path)
    said = out["said"]
    assert out["first"][0] in ("Hmm, let me try something.", "Ooh, let me try.", "Let me think how I'd do that.")
    asks = [line for line in said if line in ("Like that?", "Was that it?", "How was that?", "Is that what you meant?")]
    assert len(asks) == 3 and len(set(asks[:2])) == 2
    assert "Yay! I'll remember how to do the little dance." in said
    kept = out["kept"]
    assert kept is not None and kept.steps == [{"do": "turn", "way": "around", "degrees": 360, "speed": "quick"}, {"do": "wiggle", "repeat": 2}, {"do": "face", "expression": "love"}]
    assert kept.taught_by["name"] == "Ina" and kept.taught_by["tier"] == TRUSTED
    assert out["again"] == [] and len(out["tries"]) == 4 and out["tries"][-1] == kept.steps
    assert out["purposes"].count("plan") == 3
    assert '1. [{"do":"face","expression":"happy"}' in out["prompts"][1] and 'They said: "No."' in out["prompts"][1]
    assert out["prompts"][2].endswith('The last try, number 2, was [{"do":"turn","way":"around","degrees":360},{"do":"wiggle","repeat":2},{"do":"face","expression":"love"}]. Change it: faster. Keep the rest of it the same.')
    answers = [r["said"] for r in out["records"] if r["kind"] == "try_answer"]
    assert answers == ["no", "nearly", "yes"] and [r["kind"] for r in out["records"]].count("skill_run") == 1


def test_scene_spin_twice_then_come_to_me(tmp_path):
    play, out = scene("spin_come", tmp_path)
    assert out["turns"] == [{"kind": "turn", "way": "around", "degrees": 720}] and out["kinds"][:2] == ["turn", "come"]
    assert out["gap"] < 1.0 and "Here I am!" in out["said"] and out["planned"] == 0


def test_scene_push_the_ball_to_ina(tmp_path):
    play, out = scene("push_ball", tmp_path)
    assert out["before"] > 1.8 and out["after"] < 1.0
    assert out["asked"][-1] in ("Like that?", "Was that it?", "How was that?", "Is that what you meant?")
    assert out["kept"] is not None and out["kept"].steps == [{"do": "push", "thing": "ball", "to": "ina"}]
    assert "Yay! I'll remember how to push the ball to Ina." in out["said"]


def test_scene_a_refused_step_inside_an_allowed_plan(tmp_path):
    play, out = scene("refused_step", tmp_path)
    said = out["said"]
    assert said.index("I'll leave that part out.") > said.index(next(line for line in said if line.startswith("Ina asked me to stay out of the kitchen")))
    assert out["tries"] == [[{"do": "turn", "way": "around", "degrees": 360}, {"do": "face", "expression": "happy"}]]
    assert [r["step"] for r in out["refused"]] == ["go_to_place"] and ("go_to_place", "done") not in out["endings"]


def test_scene_a_step_refused_mid_plan_gets_the_what_now_call(tmp_path):
    play, out = scene("refused_midway", tmp_path)
    assert ("try_new", "refused") in out["endings"] and out["endings"][-1] == ("try_new", "done")
    assert "I'll leave that part out and carry on." in out["said"]
    assert out["what_now"] and "another_way: leave that part out and carry on with the rest" in out["what_now"][0]
    chose = [r for r in out["unstuck"] if r["kind"] == "unstuck"]
    assert chose[0]["chose"] == "another_way" and chose[0]["ended"] == "refused"
    assert any(r["kind"] == "unstuck_outcome" and r["label"] == "another way worked" for r in out["unstuck"])


def test_scene_a_stop_mid_try_keeps_nothing(tmp_path):
    play, out = scene("stop_try", tmp_path)
    assert out["moving"] == "try_new" and out["after"] is None
    assert ("try_new", "stopped") in out["endings"] and out["kept"] is None and out["draft"] is None and out["loop"] is None


def test_scene_a_tv_laugh_and_an_unseen_yes_keep_nothing(tmp_path):
    play, out = scene("tv_laugh", tmp_path)
    assert out["kept"] is None and "Okay, I'll leave it there for now." in out["said"]
    assert {r["sound"] for r in out["hints"]} >= {"laugh", "unseen yes"}
    assert out["ignored"] and out["ignored"][0]["why"] == "not seen saying it"
    assert out["draft"] is not None


def test_scene_silence_keeps_a_draft_and_try_again_picks_it_up(tmp_path):
    play, out = scene("silence", tmp_path)
    assert out["quiet"][-1] == "Okay, I'll leave it there for now." and out["draft"] is not None and out["kept_before"] is None
    assert out["again"][0] == "Okay, let me try the little dance again."
    assert out["kept"] is not None and out["kept"].steps == FIRST["steps"] and out["draft_after"] is None and out["plans"] == 1


def test_scene_a_strangers_yes_keeps_nothing(tmp_path):
    play, out = scene("stranger_yes", tmp_path)
    assert out["said"][-1] == "Glad you liked it!" and out["kept"] is None and out["draft"] is None and out["one_off"]


def test_scene_out_of_ideas(tmp_path):
    play, out = scene("out_of_ideas", tmp_path)
    assert out["said"][-1] == OUT_OF_IDEAS and out["plans"] == 3 and len(out["tries"]) == 1
    assert out["draft"] is not None and out["kept"] is None


def test_scene_no_not_like_that_reopens_a_kept_skill(tmp_path):
    play, out = scene("not_like_that", tmp_path)
    assert out["first"] == [] and len(out["tries"]) == 2
    assert out["said"][-1] == "Okay, I'll do the little dance like that from now on."
    kept = out["kept"]
    assert kept.steps == SECOND["steps"] and kept.versions[-1]["steps"] == FIRST["steps"] and kept.bad == 1


def test_scene_a_skill_from_another_body_is_only_a_first_try(tmp_path):
    play, out = scene("other_body", tmp_path)
    assert out["asked"][0] == "I learned the little dance in another body, so let me try it in this one."
    assert out["tries"] == [[{"do": "turn", "way": "left", "degrees": 45}, {"do": "face", "expression": "happy"}]] and out["plans"] == 0
    assert out["here"] is not None and out["here"].body == "pc-sim" and out["there"].steps[0]["do"] == "leg_wave"


def test_scene_a_refusal_in_its_own_words_and_the_fixed_line_when_slow(tmp_path):
    play, out = scene("worded", tmp_path)
    assert out["worded"] == ["Sorry, Alex, I only tag along with people I know really well."]
    assert out["slow"] == ["Sorry, I only follow people I know really well."]
    assert out["dishonest"] == ["Sorry, I only follow people I know really well."]
    assert out["harm"] and out["harm"][0] != "" and not any("spider" in text for text in out["asked"])
    assert out["ack"][0] == "On my way to you!"
    used = [(r["answer"], r["used"], r.get("why")) for r in out["records"]]
    assert used[:3] == [("no", "own", None), ("no", "fixed", "slow"), ("no", "fixed", "it did not say no")] and ("yes", "own", None) in used


def test_scene_stuck_in_a_doorway_with_the_what_now_call(tmp_path):
    play, out = scene("doorway", tmp_path)
    assert out["calls"] == 2 and out["kitchen"] < 0.9
    said = out["said"]
    assert said.index("I'll wait a moment and try again.") < said.index("Here I am in the kitchen.")
    assert "Options:" in out["what_now"][0] and "wait: wait a little and try again" in out["what_now"][0] and "ask: ask Ina for help" in out["what_now"][0]
    assert [r["label"] for r in out["unstuck"] if r["kind"] == "unstuck_outcome"] == ["waiting worked"]
    assert out["kept"] and out["kept"][-1]["label"] == "waiting worked"


def test_scene_three_decisions_then_back_to_the_asker(tmp_path):
    play, out = scene("three_tries", tmp_path)
    chose = [r["chose"] for r in out["unstuck"] if r["kind"] == "unstuck"]
    assert chose == ["wait", "ask", "another_way"] and out["calls"] == 4 and out["left_choices"] == [{"choose": "wait"}]
    assert "Ina, could you help me? Something's in the way, so I stopped here." in out["said"]
    assert "Ina, I tried three times, but I couldn't finish going to the kitchen: something's in the way." in out["said"]
    labels = [r["label"] for r in out["unstuck"] if r["kind"] == "unstuck_outcome"]
    assert labels[-1] == "went back to explain after three tries" and labels[:3] == ["waiting did not help", "asking Ina did not help", "another way did not help"]
    assert "Already tried: wait a little and try again, ask Ina for help." in out["what_now"][2]


def test_the_loop_ends_with_a_draft_when_the_asker_leaves_or_the_battery_calls_a_rest(tmp_path):
    from pebble.life.trying_scene import DANCE, staged
    from pebble.sim.scene import Who

    async def scenario():
        play, mind = await staged(tmp_path / "self", False, [Who("Ina", TRUSTED, 1300.0, 0.0)], [FIRST, SECOND])
        trying = play.life.commands.trying
        await play.scene.say("Ina", DANCE)
        await play.scene.until_idle(60.0)
        waiting = trying.loop is not None and trying.loop.waiting_since is not None
        play.scene.leave("Ina")
        await play.scene.run(18.0)
        left = trying.loop is None and play.life.skills.drafted("little dance") is not None
        ended = [r["how"] for r in play.records() if r["kind"] == "try_ended"]
        play.scene.arrive("Ina", 1.3, 0.0)
        await play.scene.run(3.0)
        await play.scene.say("Ina", DANCE)
        await play.scene.run(1.0)
        running = getattr(play.life.commands.runner.current, "kind", None)
        trying.fence = lambda: "battery"
        await play.scene.run(2.0)
        rested = running == "try_new" and trying.loop is None and play.life.commands.runner.current is None and play.life.skills.drafted("try the little dance again").best() == SECOND["steps"]
        said = play.said()
        await play.close()
        return waiting, left, ended, rested, said

    waiting, left, ended, rested, said = run(scenario(), timeout=120)
    assert waiting and left and ended == ["left"]
    assert rested and said[-1] == "My battery's low, so I'll stop trying for now. I'll remember where I got to."


def test_the_planning_eval_set_scores_plans_with_a_stand_in_person():
    from pebble.activities.try_eval import load, refused, wanted

    items = load()
    assert len(items) >= 12 and sum(1 for item in items if item["want"] == "cant") >= 3
    assert wanted([{"do": "tilt", "way": "down"}], {"all": ["tilt"], "none": ["move"]})
    assert not wanted([{"do": "tilt"}, {"do": "move"}], {"all": ["tilt"], "none": ["move"]})
    assert not wanted([{"do": "face"}], {"any": ["turn", "wiggle"]}) and not wanted([], {"any": ["turn"]}) and not wanted([{"do": "turn"}], "cant")
    assert refused([{"do": "turn", "way": "left"}, {"do": "go_to_place", "place": "garden"}]) == 1


def test_something_it_cant_do_with_an_action_verb_is_tried_and_a_ball_goes_to_someone(tmp_path):
    from pebble.activities.push import Push
    from pebble.life.trying_scene import staged
    from pebble.sim.scene import Who

    nod = {"think": "nod: the head down and up", "steps": [{"do": "tilt", "way": "down", "degrees": 20}, {"do": "tilt", "way": "up", "degrees": 10}], "repeat": 3}

    async def scenario():
        play, mind = await staged(tmp_path / "self", False, [Who("Ina", TRUSTED, 1300.0, 0.0)], [nod])
        await play.scene.say("Ina", "Nod three times.")
        await play.scene.until_idle(60.0)
        nodding = [activity.kind for activity, _ in play.life.commands.runner.history]
        words = play.life.commands.trying.loop.words if play.life.commands.trying.loop else ""
        play.life.commands.runner.end("stopped", "test")
        await play.scene.say("Ina", "Kick the ball to Ina.")
        kicking = play.life.commands.runner.current
        await play.close()
        return nodding, words, kicking

    nodding, words, kicking = run(scenario(), timeout=120)
    assert nodding == ["try_new"] and words == "nod three times"
    assert isinstance(kicking, Push) and kicking.request.to == "me" and kicking.target.label == "Ina"
