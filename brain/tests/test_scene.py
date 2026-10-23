import random
import re

import pytest

from pebble.chaos.engine import Chaos
from pebble.screen.director import SceneDirector, parse_scene
from pebble.screen.elements import ELEMENTS, GRID, MAX_LINES, MAX_TEXT, PALETTE, REGISTRY, TEXT_CHARS, Element, RegistryError, Slot, check_registry, colour, motion, num, registry_dict
from pebble.screen.gallery import MAX_SCENES, Gallery, GalleryError
from pebble.screen.gbnf import GrammarError, parse_gbnf
from pebble.screen.grammar import number_rule, scene_grammar
from pebble.screen.guide import scene_guide
from pebble.screen.mutate import mutate, remix
from pebble.screen.parse import SceneError, format_line, make_line, parse_line

SPEC_EXAMPLE = 'sky night\nstars 30 twinkle\nmoon 24 6 r4 pale\nhill 0 26 32 6 green\nrain 40 blue slow\ntext 3 28 "zzz" drift'


@pytest.fixture(scope="module")
def grammar():
    return parse_gbnf(scene_grammar())


def test_the_registry_has_about_thirty_well_formed_elements():
    assert 30 <= len(ELEMENTS) <= 40
    check_registry()
    names = {e.name for e in ELEMENTS}
    for wanted in ("sky", "stars", "moon", "sun", "cloud", "rain", "snow", "fire", "waves", "hill", "grass", "tree", "flower", "heart", "star", "circle", "rect", "line", "dot", "text", "sparkle", "bubbles", "fish", "bird", "eyes", "mouth", "zzz", "lightning", "rainbow", "particles"):
        assert wanted in names
    assert len(PALETTE) == 8
    data = registry_dict()
    assert set(data["elements"]) == names and data["grid"] == GRID


def test_bad_registries_are_refused():
    with pytest.raises(RegistryError):
        check_registry((Element("a", (num("x", 0, 9, 1), num("y", 0, 9, 2)), "", "a"),))
    with pytest.raises(RegistryError):
        check_registry((Element("a", (colour("red"), num("x", 0, 9)), "", "a"),))
    with pytest.raises(RegistryError):
        check_registry((Element("a", (Slot("look", "word", words=("red",), default="red"),), "", "a"),))
    with pytest.raises(RegistryError):
        check_registry((Element("a", (motion("wobble"),), "", "a"),))


def test_the_spec_example_parses_exactly(grammar):
    assert grammar.matches(SPEC_EXAMPLE)
    scene = parse_scene(SPEC_EXAMPLE)
    assert not scene.rejected
    assert scene.elements() == ["sky", "stars", "moon", "hill", "rain", "text"]
    moon = scene.lines[2]
    assert moon.values == {"x": 24, "y": 6, "r": 4, "colour": "pale", "motion": "still"}
    assert scene.lines[5].values == {"x": 3, "y": 28, "text": "zzz", "colour": "white", "motion": "drift"}
    assert scene.lines[4].values == {"n": 40, "colour": "blue", "speed": "slow"}


@pytest.mark.parametrize("element", ELEMENTS, ids=lambda e: e.name)
def test_every_element_round_trips_between_parser_and_grammar(element, grammar):
    line = parse_line(element.example)
    assert line.element == element.name
    text = format_line(line)
    assert grammar.matches(text), text
    assert grammar.matches(element.example), element.example
    assert parse_line(text) == line
    bare = make_line(element.name, **{s.name: (s.lo if s.kind in ("num", "radius") else ("hi" if s.kind == "text" else s.choices()[0])) for s in element.slots if s.required})
    assert grammar.matches(bare.text())
    assert parse_line(bare.text()) == bare
    for slot in element.slots:
        if not slot.required:
            assert bare.values[slot.name] == slot.default


def test_grammar_is_llama_cpp_friendly(grammar):
    text = scene_grammar()
    for line in text.strip().splitlines():
        name = line.split("::=", 1)[0].strip()
        assert re.fullmatch(r"[a-z0-9-]+", name), name
    assert "root" in grammar.rules
    assert text.count("\n") == len(grammar.rules)
    with pytest.raises(GrammarError):
        parse_gbnf("root ::= missing-rule")
    with pytest.raises(GrammarError):
        parse_gbnf('root ::= "unterminated')


def test_number_rules_are_exact():
    for lo, hi in ((0, 31), (1, 60), (1, 8), (4, 24), (0, 9), (10, 99), (1, 32), (0, 200), (7, 7)):
        rules = parse_gbnf(f"root ::= {number_rule(lo, hi)}")
        accepted = {n for n in range(0, 300) if rules.matches(str(n))}
        assert accepted == set(range(lo, hi + 1)), (lo, hi)
        assert not rules.matches(f"0{hi}")


def test_random_grammar_scenes_always_parse(grammar):
    rng = random.Random(2026)
    for _ in range(1500):
        text = grammar.sample(rng)
        scene = parse_scene(text)
        assert not scene.rejected, (text, scene.rejected)
        assert 1 <= len(scene.lines) <= MAX_LINES
        assert grammar.matches(scene.text()), scene.text()


def test_invalid_lines_are_rejected_without_crashing():
    bad = [
        "teapot 1 2",
        "moon",
        "moon 3",
        "moon 3 4 5",
        "moon 3 4 r4 pale still extra",
        "sky purple",
        'text 1 2 zzz',
        'text 1 2 ""',
        "rain fast blue",
        "hill 0 26 green",
        '"sky" night',
        "\x00\x01",
        "line 1 2 3",
    ]
    for raw in bad:
        with pytest.raises(SceneError):
            parse_line(raw)
    scene = parse_scene("\n".join(bad + ["sky night", "stars"]))
    assert scene.elements() == ["sky", "stars"]
    assert len(scene.rejected) == len(bad)
    assert parse_line("moon 99 99 r99").values["r"] == 8
    assert parse_line("MOON 3 4 R2 PALE").values == {"x": 3, "y": 4, "r": 2, "colour": "pale", "motion": "still"}
    clipped = parse_line('text 0 0 "' + "A" * 40 + '"')
    assert len(clipped.values["text"]) == MAX_TEXT and clipped.notes


def test_parser_is_forgiving_about_markdown_from_a_big_model():
    text = "```\n- sky night\n1. stars 20\n# a comment\n\nmoon 4 4\n```"
    scene = parse_scene(text)
    assert scene.elements() == ["sky", "stars", "moon"] and not scene.rejected


def test_the_director_emits_each_line_as_soon_as_it_completes():
    emitted = []
    director = SceneDirector(on_line=lambda line: emitted.append(line.element))
    chunks = ["sky ni", "ght\nsta", "rs 30 tw", "inkle\nmo", "on 24 6 r4 pa", "le\nhill 0 2", "6 32 6 green"]
    progress = []
    for chunk in chunks:
        director.feed(chunk)
        progress.append(list(emitted))
    assert progress[0] == [] and progress[1] == ["sky"]
    assert progress[2] == ["sky"] and progress[3] == ["sky", "stars"]
    assert progress[5] == ["sky", "stars", "moon"]
    scene = director.finish()
    assert emitted == ["sky", "stars", "moon", "hill"]
    assert scene.elements() == emitted
    assert director.feed("rain 3\n") == []


def test_the_director_limits_lines_and_survives_garbage():
    rejected = []
    director = SceneDirector(on_reject=lambda text, why: rejected.append(why), max_lines=3)
    director.feed("dot 1 1\n" * 5)
    director.feed("x" * 1000)
    director.feed("\n")
    scene = director.finish()
    assert len(scene.lines) == 3 and director.full
    assert rejected.count("too many lines") == 2
    assert "line too long" in rejected


def test_text_characters_are_the_grammar_characters(grammar):
    for ch in TEXT_CHARS:
        assert grammar.matches(f'text 0 0 "{ch}"'), ch
    assert not grammar.matches('text 0 0 "a\\"b"')
    assert not grammar.matches('text 0 0 "' + "a" * (MAX_TEXT + 1) + '"')


def test_the_guide_lists_every_element_and_the_palette():
    guide = scene_guide()
    for element in ELEMENTS:
        assert f"\n{element.name} " in guide or guide.startswith(element.name)
    for name in PALETTE:
        assert name in guide
    assert len(guide) < 4000


def test_gallery_keeps_originals_and_names_variants(tmp_path, clock, store):
    gallery = Gallery.open(store)
    assert "night-sky" in gallery.names()
    for name in gallery.names():
        assert gallery.get(name) and not gallery.get(name).rejected, name
    scene = parse_scene(SPEC_EXAMPLE)
    first = gallery.save("Rain at Night!", scene, "drawn", "2026-10-15")
    second = gallery.save("rain-at-night", parse_scene("sky day"), "drawn", "2026-10-15")
    assert first == "rain-at-night" and second == "rain-at-night-2"
    assert gallery.get(first).text() == scene.text()
    chaos = Chaos(seed=8, pinned=9)
    varied = mutate(scene, chaos.stream("mutation"), 9)
    name = gallery.variant(first, varied)
    assert name == "rain-at-night-v1"
    assert gallery.variant(name, varied) == "rain-at-night-v2"
    assert gallery.get(first).text() == scene.text()
    again = Gallery.open(store)
    assert again.entry("rain-at-night-v1")["parent"] == "rain-at-night"
    with pytest.raises(GalleryError):
        gallery.save("!!!", scene, "drawn")
    with pytest.raises(GalleryError):
        gallery.save("empty", parse_scene(""), "drawn")
    with pytest.raises(GalleryError):
        gallery.variant("nope", scene)
    assert gallery.find("a stormy rainy day") == "rainy-day"


def test_gallery_prunes_variants_never_curated(store):
    gallery = Gallery.open(store)
    curated = set(gallery.names())
    for index in range(MAX_SCENES + 20):
        gallery.save(f"d{index}", parse_scene("dot 1 1"), "dream")
    assert len(gallery.names()) == MAX_SCENES
    assert curated <= set(gallery.names())


def test_mutation_makes_small_valid_changes(grammar):
    scene = parse_scene(SPEC_EXAMPLE)
    for seed in range(40):
        chaos = Chaos(seed=seed)
        for level in (0, 5, 10):
            varied = mutate(scene, chaos.stream("mutation"), level)
            assert len(varied.lines) == len(scene.lines)
            assert grammar.matches(varied.text())
            changed = sum(a != b for a, b in zip(scene.lines, varied.lines))
            assert changed <= 3
            for before, after in zip(scene.lines, varied.lines):
                assert before.element == after.element
                for key in ("x", "y"):
                    if key in before.values:
                        assert abs(before.values[key] - after.values[key]) <= 2
    assert scene.text() == parse_scene(SPEC_EXAMPLE).text()


def test_dream_remix_takes_background_and_foreground():
    night = parse_scene(SPEC_EXAMPLE)
    party = parse_scene('sky space\nfirework 10 8 pink\nheart 16 14\ntext 4 24 "YAY"')
    mixed = remix(night, party)
    assert mixed.elements() == ["sky", "stars", "hill", "rain", "firework", "heart", "text"]
    assert all(REGISTRY[e].layer for e in mixed.elements())
