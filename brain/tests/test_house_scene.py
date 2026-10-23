import asyncio

from pebble.house.scene import play


def lines_of(name):
    show = asyncio.run(asyncio.wait_for(play(name, quick=True), 300))
    return show.scene.lines, show


def said(lines):
    return [line.split("says", 1)[1].strip().strip('"') for line in lines if "  says  " in line]


def test_the_door_scene_tells_the_knock_the_microwave_and_what_happened_while_ina_was_out():
    lines, _ = lines_of("door")
    spoken = said(lines)
    assert "Ina, someone's knocking at the door." in spoken
    assert "Ina, the microwave's done." in spoken
    summary = [s for s in spoken if s.startswith("Ina, since I last saw you:")]
    assert len(summary) == 1
    assert "a knock at the door" in summary[0] and "the doorbell rang" in summary[0] and "the dog howled or whimpered on and off" in summary[0]


def test_the_night_scene_keeps_one_knock_and_tells_three():
    lines, show = lines_of("night")
    spoken = said(lines)
    assert spoken == ["Someone has been knocking at the door: three times in two minutes. I won't open it."]
    assert len(show.notifier.sent) == 1


def test_the_alarm_scene_counts_test_presses_and_hears_the_chirping():
    lines, show = lines_of("alarms")
    spoken = said(lines)
    assert [s for s in spoken if s.startswith("Heard that one.")] == ["Heard that one. That's one so far.", "Heard that one. That's two so far.", "Heard that one. That's three so far."]
    assert any(s.startswith("The alarm test is over. I heard three alarms go off.") for s in spoken)
    assert any("an alarm chirping about every 40 seconds" in s for s in spoken)
    assert not any("Is everything okay" in s for s in spoken) and not show.notifier.sent


def test_the_lists_scene_keeps_lists_for_the_household_and_switches_visitors_mode():
    lines, _ = lines_of("lists")
    spoken = said(lines)
    assert "Okay, milk and bread are on the shopping list." in spoken
    assert "Sorry, that's just for the people who live here." in spoken
    assert "Ina told me the water shut-off is under the laundry sink." in spoken
    assert any(s.startswith("Ina, there are a few people here I don't know. Shall I go into visitors mode?") for s in spoken)
    assert any(s.startswith("Okay, visitors mode is on.") for s in spoken) and "Okay, visitors mode is off." in spoken
    screen = [line for line in lines if "  screen  " in line]
    assert any("Shopping list: milk, bread, with a code" in line for line in screen)
    assert any("Guest Wi-Fi" in line for line in screen)


def test_the_teach_scene_learns_a_tune_in_two_goes_and_ignores_another_tune():
    lines, _ = lines_of("teach")
    spoken = said(lines)
    assert spoken[0] == "Got it: the washing machine finishing. Next time it plays, tell me again, so I'm sure."
    assert "Got it. I know the washing machine finishing now. When I hear it, I'll say so." in spoken
    assert "Ina, the washing machine's finished." in spoken
    assert spoken[-1] == "I know one sound: the washing machine finishing."
    assert not any("dryer" in s.lower() for s in spoken)
