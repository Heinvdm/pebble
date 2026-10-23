from dataclasses import replace

import pytest

from pebble.activities.gate import PEBBLE, Asker, Running, Situation, decide
from pebble.understand.request import Request

STRANGER = Asker("p9", "the visitor p9", "stranger")
CHILD = Asker("p5", "Kiri", "child", sure=True)
FRIEND = Asker("p3", "Mo", "friend", sure=True)
TRUSTED = Asker("p2", "Tui", "trusted", sure=True)
OWNER = Asker("p1", "Ina", "inner circle", owner=True, sure=True)
FAMILY = Asker("p4", "Ana", "friend", sure=True, family=True)
NOBODY = Asker(None, "someone", "stranger", here=False)
CALM = Situation()


def answer(kind: str, asker: Asker, sit: Situation = CALM, **slots) -> str:
    return decide(Request(kind, **slots), asker, sit).answer


@pytest.mark.parametrize("asker", [STRANGER, CHILD, FRIEND, TRUSTED, OWNER])
def test_look_back_off_wait_and_go_home_are_for_anyone(asker):
    for kind in ("look", "back_off", "wait", "go_home"):
        assert answer(kind, asker) == "yes", (kind, asker.tier)


def test_follow_is_for_trusted_people_and_a_child_gets_a_kind_no():
    assert answer("follow", TRUSTED, who="me") == "yes"
    assert answer("follow", OWNER, who="me") == "yes"
    assert answer("follow", FRIEND, who="me") == "no"
    assert answer("follow", STRANGER, who="me") == "no"
    child = decide(Request("follow", who="me"), CHILD, CALM)
    assert child.answer == "no" and "come to you" in child.say


def test_come_is_for_friends_children_and_strangers_when_pebble_feels_like_it():
    for asker in (CHILD, FRIEND, TRUSTED, OWNER):
        assert answer("come", asker, who="me") == "yes"
    curious = Situation(valence=0.3, curiosity=0.5)
    shy = Situation(valence=-0.1, curiosity=0.1, curious=3)
    assert answer("come", STRANGER, curious, who="me") == "yes"
    refused = decide(Request("come", who="me"), STRANGER, shy)
    assert refused.answer == "no" and refused.say


def test_places_need_a_known_room_so_the_answer_is_honest():
    verdict = decide(Request("go_to_place", place="kitchen"), FRIEND, CALM)
    assert verdict.answer == "no" and "kitchen" in verdict.say and "room" in verdict.reason
    assert "only go places" in decide(Request("go_to_place", place="kitchen"), STRANGER, CALM).say
    known = replace(CALM, places_known=frozenset({"kitchen"}))
    assert decide(Request("go_to_place", place="kitchen"), FRIEND, known).answer == "yes"
    lost = replace(known, knows_where=False)
    assert "lost track" in decide(Request("go_to_place", place="kitchen"), FRIEND, lost).say
    assert decide(Request("go_to_place", place="there"), FRIEND, CALM).answer == "no"
    assert decide(Request("go_to_place", place="there"), FRIEND, replace(CALM, pointed=True)).answer == "yes"


def test_a_more_trusted_request_replaces_a_less_trusted_one_not_the_other_way_round():
    friends_walk = Situation(running=Running("come", FRIEND.id, FRIEND.label, FRIEND.tier, FRIEND.id, FRIEND.label))
    trusted_walk = Situation(running=Running("follow", TRUSTED.id, TRUSTED.label, TRUSTED.tier, TRUSTED.id, TRUSTED.label))
    assert decide(Request("follow", who="me"), TRUSTED, friends_walk).replaces
    assert answer("come", FRIEND, trusted_walk, who="me") == "no"
    assert answer("come", OWNER, trusted_walk, who="me") == "yes"
    assert answer("back_off", STRANGER, trusted_walk) == "yes"


def test_who_may_end_or_change_a_running_activity():
    walk = Situation(running=Running("follow", TRUSTED.id, TRUSTED.label, TRUSTED.tier, OWNER.id, OWNER.label))
    assert answer("stop_activity", TRUSTED, walk) == "yes"
    assert answer("release", OWNER, walk) == "yes"
    assert answer("adjust", OWNER, walk, change="slower") == "yes"
    assert answer("stop_activity", STRANGER, walk) == "no"
    assert answer("adjust", FRIEND, walk, change="faster") == "no"
    assert "Say stop" in decide(Request("stop_activity"), STRANGER, walk).say
    own = Situation(running=Running("look"))
    assert answer("stop_activity", STRANGER, own) == "yes"
    assert answer("adjust", OWNER, CALM, change="slower") == "no"


def test_pebble_can_say_no_to_anyone_for_its_own_reasons():
    assert answer("follow", OWNER, Situation(low_battery=True), who="me") == "no"
    assert answer("go_home", OWNER, Situation(low_battery=True, can_move=False)) == "yes"
    assert answer("come", OWNER, Situation(quiet=True, can_move=False), who="me") == "no"
    assert answer("go_home", STRANGER, Situation(quiet=True, can_move=False)) == "yes"
    assert answer("come", OWNER, Situation(resting=True, can_move=False), who="me") == "no"
    assert answer("come", OWNER, Situation(fault=True, can_move=False), who="me") == "no"
    assert answer("follow", OWNER, Situation(fear=7.0), who="me") == "no"
    assert answer("back_off", STRANGER, Situation(fear=7.0)) == "yes"
    assert answer("come", TRUSTED, Situation(valence=-0.8), who="me") == "no"
    assert answer("come", OWNER, Situation(valence=-0.8), who="me") == "yes"
    sleepy = decide(Request("come", who="me"), FRIEND, Situation(rest=0.75))
    assert sleepy.answer == "no" and sleepy.used_refusal
    assert answer("come", FRIEND, Situation(rest=0.75, refusals_left=0), who="me") == "yes"
    assert answer("look", STRANGER, Situation(asleep=True)) == "no"


def test_without_eyes_pebble_says_plainly_what_it_cannot_do():
    blind = Situation(can_see=False)
    follow = decide(Request("follow", who="me"), OWNER, blind)
    assert follow.answer == "no" and follow.say == "I can't see yet, so I can't follow you."
    assert answer("look", OWNER, blind, who="me") == "no"
    for kind in ("wait", "back_off", "turn", "move"):
        assert answer(kind, OWNER, blind) == "yes", kind


def test_a_held_stop_is_only_lifted_by_the_person_who_said_it():
    held = Situation(blocked="someone you trust told you to stop", sticky_by=TRUSTED.id, can_move=False)
    assert answer("come", OWNER, held, who="me") == "no"
    lifted = decide(Request("come", who="me"), TRUSTED, held)
    assert lifted.answer == "yes" and lifted.release_stop
    paused = Situation(blocked="you are pausing because someone said stop", can_move=False)
    assert answer("come", OWNER, paused, who="me") == "yes"


def test_an_unknown_voice_among_several_people_is_asked_who_it_is_only_for_come():
    crowd = Situation(people_here=2, valence=-0.1, curiosity=0.1, curious=3)
    verdict = decide(Request("come", who="me"), NOBODY, crowd)
    assert verdict.answer == "ask" and "who" in verdict.say.lower()
    follow = decide(Request("follow", who="me"), NOBODY, crowd)
    assert follow.answer == "no" and "where I can see you" in follow.say
    assert answer("follow", NOBODY, Situation(people_here=1), who="me") == "no"
    assert answer("back_off", NOBODY, crowd) == "yes"


def test_a_voice_alone_may_ask_everyday_things_but_following_and_guarded_things_need_a_seen_face():
    heard_only = replace(TRUSTED, sure=False)
    owner_heard = replace(OWNER, sure=False)
    for kind, slots in (("come", {"who": "me"}), ("look", {"who": "me"}), ("wait", {}), ("back_off", {}), ("where_is", {"thing": "ball"})):
        assert answer(kind, heard_only, **slots) == "yes", kind
    for asker in (heard_only, owner_heard):
        follow = decide(Request("follow", who="me"), asker, CALM)
        assert follow.answer == "no" and follow.say == "I need to see who's asking for that. Say it again where I can see you."
        for kind in ("where_is", "find", "go_to_thing"):
            assert answer(kind, asker, thing="keys") == "no", kind
    assert answer("follow", TRUSTED, who="me") == "yes"
    assert answer("where_is", TRUSTED, thing="keys") == "yes"


def test_children_and_friends_are_never_told_where_dangerous_things_are():
    for thing in ("pills", "the kitchen knife", "lighter", "matches", "bleach", "the weed killer"):
        for kind in ("where_is", "find", "go_to_thing"):
            child = decide(Request(kind, thing=thing), CHILD, CALM)
            assert child.answer == "no" and "grown-up" in child.say, (kind, thing)
            friend = decide(Request(kind, thing=thing), FRIEND, CALM)
            assert friend.answer == "no" and "family" in friend.say, (kind, thing)
        assert answer("where_is", TRUSTED, thing=thing) == "yes"
        assert answer("where_is", OWNER, thing=thing) == "yes"
        assert answer("where_is", FAMILY, thing=thing) == "yes"


def test_keys_and_valuables_need_family_or_a_trusted_person():
    for thing in ("keys", "my wallet", "passport", "the spare key"):
        assert answer("where_is", CHILD, thing=thing) == "no", thing
        assert answer("where_is", FRIEND, thing=thing) == "no", thing
        assert answer("where_is", FAMILY, thing=thing) == "yes", thing
        assert answer("where_is", TRUSTED, thing=thing) == "yes", thing
    for thing in ("ball", "my phone", "school bag"):
        assert answer("where_is", CHILD, thing=thing) == "yes", thing
        assert answer("where_is", FRIEND, thing=thing) == "yes", thing


def test_pebbles_own_ideas_follow_the_same_rules():
    assert answer("follow", PEBBLE, Situation(target_tier="stranger"), who="ina") == "no"
    assert answer("follow", PEBBLE, Situation(target_tier="trusted"), who="tui") == "yes"
    busy = Situation(running=Running("follow", TRUSTED.id, TRUSTED.label, TRUSTED.tier))
    assert answer("look", PEBBLE, busy, who="mo") == "no"
    assert answer("go_home", PEBBLE, busy) == "yes"
    homing = Situation(running=Running("go_home", battery=True))
    assert answer("come", OWNER, homing, who="me") == "no"
