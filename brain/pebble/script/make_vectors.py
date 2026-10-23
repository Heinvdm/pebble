import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path

from .check import read
from .evaluate import Call, Done, Finish, Machine
from .program import LIMITS, Limits

FOLDER = Path(__file__).resolve().parent / "vectors"
ALL_USES = '["do", "say", "ask", "face", "draw", "chirp", "hum", "look", "dial", "tune"]'
HEAD = 'ABOUT = "a conformance test"\nUSES = ' + ALL_USES + '\nUNTIL = "ongoing"\n'


@dataclass
class Case:
    name: str
    body: str = ""
    calls: list = field(default_factory=list)
    out: object = "done"
    replies: list | None = None
    limits: dict | None = None
    source: str = ""
    runs: list | None = None
    extra: str = ""


def say(text: str) -> tuple:
    return ("say", {"text": text})


def source_of(case: Case) -> str:
    if case.source:
        return case.source
    lines = case.body.strip("\n").split("\n")
    body = "\n".join("    " + line for line in lines)
    return HEAD + case.extra + "\n\ndef on_start():\n" + body + "\n"


GROUPS = {
    "numbers": [
        Case("whole division", "say(str(7 // 2))\nsay(str(-7 // 2))", [say("3"), say("-4")]),
        Case("modulo follows the divisor's sign", "say(str(7 % 3))\nsay(str(-7 % 3))\nsay(str(7 % -3))", [say("1"), say("2"), say("-2")]),
        Case("true division gives a float", "say(str(7 / 2))\nsay(str(10 / 5))", [say("3.5"), say("2.0")]),
        Case("powers", "say(str(2 ** 10))\nsay(str(2 ** -1))\nsay(str(9 ** 0.5))", [say("1024"), say("0.5"), say("3.0")]),
        Case("float text", "say(str(0.1 + 0.2))\nsay(str(1 / 3))\nsay(str(1e16))", [say("0.30000000000000004"), say("0.3333333333333333"), say("1e+16")]),
        Case("round to even", "say(str(round(2.5)))\nsay(str(round(3.5)))\nsay(str(round(2.675, 2)))\nsay(str(round(7)))", [say("2"), say("4"), say("2.67"), say("7")]),
        Case("int and float from text", 'say(str(int(" 42 ")))\nsay(str(int(-3.7)))\nsay(str(float("1.5")))', [say("42"), say("-3"), say("1.5")]),
        Case("abs, min and max", "say(str(abs(-4)))\nsay(str(min(3, 1, 2)))\nsay(str(max([3, 9, 2])))", [say("4"), say("1"), say("9")]),
        Case("booleans are numbers", "say(str(True + True))\nsay(str(True == 1))", [say("2"), say("True")]),
        Case("unary minus and not", "x = 5\nsay(str(-x))\nsay(str(not x))\nsay(str(not 0))", [say("-5"), say("False"), say("True")]),
        Case("chained comparison", "x = 3\nsay(str(1 < x < 5))\nsay(str(1 < x > 5))", [say("True"), say("False")]),
        Case("integer and float equality", "say(str(1 == 1.0))\nsay(str(2 != 2.5))", [say("True"), say("True")]),
        Case("augmented arithmetic", "n = 10\nn += 5\nn -= 3\nn *= 2\nn //= 5\nn %= 3\nsay(str(n))", [say("1")]),
        Case("sum of a list", "say(str(sum([1, 2, 3.5])))", [say("6.5")]),
    ],
    "text": [
        Case("lower and upper", 'say("Hello World".lower())\nsay("Hello World".upper())', [say("hello world"), say("HELLO WORLD")]),
        Case("strip", 'say("  hi there  ".strip())\nsay("xxhixx".strip("x"))', [say("hi there"), say("hi")]),
        Case("split and join", 'parts = "a,b,c".split(",")\nsay(str(parts))\nsay("-".join(parts))\nsay(str("one  two".split()))', [say("['a', 'b', 'c']"), say("a-b-c"), say("['one', 'two']")]),
        Case("split with a most", 'say(str("a b c d".split(" ", 2)))', [say("['a', 'b', 'c d']")]),
        Case("starts and ends", 'w = "pebble"\nsay(str(w.startswith("peb")))\nsay(str(w.endswith("x")))', [say("True"), say("False")]),
        Case("replace", 'say("the cat sat".replace("at", "og"))\nsay("aaa".replace("a", "b", 2))', [say("the cog sog"), say("bba")]),
        Case("indexing and slicing text", 'w = "hello"\nsay(w[1:3])\nsay(w[::-1])\nsay(w[-1])\nsay(w[:2])', [say("el"), say("olleh"), say("o"), say("he")]),
        Case("length counts characters", 'say(str(len("héllo")))', [say("5")]),
        Case("f-strings", 'n = 3\nthing = "cat"\nnothing = None\nsay(f"{n} {thing}s and {nothing}")', [say("3 cats and None")]),
        Case("f-string of a list", 'items = [1, "a"]\nsay(f"got {items}")', [say("got [1, 'a']")]),
        Case("text in text", 'say(str("at" in "cat"))\nsay(str("dog" not in "cat"))', [say("True"), say("True")]),
        Case("adding and repeating text", 'say("ab" + "cd")\nsay("ha" * 3)\nsay(3 * "-")\nsay(str("x" * 0 == ""))', [say("abcd"), say("hahaha"), say("---"), say("True")]),
        Case("str of values", 'say(str(True))\nsay(str(None))\nsay(str(1.0))\nsay(str((1,)))\nsay(str({"a": 1}))\nsay(str([None, 2.5]))', [say("True"), say("None"), say("1.0"), say("(1,)"), say("{'a': 1}"), say("[None, 2.5]")]),
        Case("comparing text", 'say(str("apple" < "banana"))\nsay(str("21:00" >= "09:30"))', [say("True"), say("True")]),
    ],
    "lists": [
        Case("append, pop and insert", "a = [1, 2]\na.append(3)\nlast = a.pop()\nfirst = a.pop(0)\na.insert(0, 9)\nsay(str(a))\nsay(str(last + first))", [say("[9, 2]"), say("4")]),
        Case("remove, index and count", "a = [5, 6, 5, 7]\na.remove(5)\nsay(str(a))\nsay(str(a.index(7)))\nsay(str(a.count(5)))", [say("[6, 5, 7]"), say("2"), say("1")]),
        Case("adding and repeating lists", "say(str([1, 2] + [3]))\nsay(str([0] * 3))", [say("[1, 2, 3]"), say("[0, 0, 0]")]),
        Case("negative index and slices", "a = [1, 2, 3, 4, 5]\nsay(str(a[-2]))\nsay(str(a[1:4]))\nsay(str(a[::2]))", [say("4"), say("[2, 3, 4]"), say("[1, 3, 5]")]),
        Case("set an item", "a = [1, 2, 3]\na[1] = 20\na[-1] = 30\nsay(str(a))", [say("[1, 20, 30]")]),
        Case("sorted and reversed", "a = [3, 1, 2]\nsay(str(sorted(a)))\nsay(str(sorted(a, reverse=True)))\nsay(str(a))", [say("[1, 2, 3]"), say("[3, 2, 1]"), say("[3, 1, 2]")]),
        Case("enumerate and zip", 'say(str(enumerate(["a", "b"])))\nsay(str(enumerate(["a"], start=1)))\nsay(str(zip([1, 2, 3], ["x", "y"])))', [say("[(0, 'a'), (1, 'b')]"), say("[(1, 'a')]"), say("[(1, 'x'), (2, 'y')]")]),
        Case("any and all", "say(str(any([0, 0, 3])))\nsay(str(all([1, 0])))\nsay(str(all([])))", [say("True"), say("False"), say("True")]),
        Case("in a list", 'say(str(2 in [1, 2]))\nsay(str("x" not in ["y"]))', [say("True"), say("True")]),
        Case("plus-equals changes the list in place", "a = [1]\nb = a\na += [2]\nsay(str(b))", [say("[1, 2]")]),
        Case("lists nest", "grid = [[1, 2], [3, 4]]\ngrid[1][0] = 30\nsay(str(grid))\nsay(str(len(grid[0])))", [say("[[1, 2], [30, 4]]"), say("2")]),
        Case("list equality", "say(str([1, [2]] == [1, [2]]))\nsay(str([1] != [1, 1]))", [say("True"), say("True")]),
        Case("tuples", "t = (1, 2)\na, b = t\nsay(str(a + b))\nsay(str(t + (3,)))", [say("3"), say("(1, 2, 3)")]),
        Case("unpacking names", "x, y = [10, 20]\nx, y = y, x\nsay(f\"{x} {y}\")", [say("20 10")]),
    ],
    "dicts": [
        Case("get with and without a default", 'd = {"a": 1}\nsay(str(d.get("a")))\nsay(str(d.get("b")))\nsay(str(d.get("b", 0)))', [say("1"), say("None"), say("0")]),
        Case("keys, values and items keep their order", 'd = {"b": 2, "a": 1}\nd["c"] = 3\nsay(str(d.keys()))\nsay(str(d.values()))\nsay(str(d.items()))', [say("['b', 'a', 'c']"), say("[2, 1, 3]"), say("[('b', 2), ('a', 1), ('c', 3)]")]),
        Case("counting with a dict", 'counts = {}\nfor w in ["cat", "dog", "cat"]:\n    counts[w] = counts.get(w, 0) + 1\nsay(str(counts))', [say("{'cat': 2, 'dog': 1}")]),
        Case("plus-equals on an item", 'd = {"n": 1}\nd["n"] += 4\nsay(str(d["n"]))', [say("5")]),
        Case("in a dict looks at keys", 'd = {"a": 1}\nsay(str("a" in d))\nsay(str(1 in d))', [say("True"), say("False")]),
        Case("numbers as keys", "d = {1: \"one\"}\nd[2] = \"two\"\nsay(str(d))\nsay(str(len(d)))", [say("{1: 'one', 2: 'two'}"), say("2")]),
        Case("nested dicts", 'd = {"ina": {"cat": 1}}\nd["ina"]["cat"] += 1\nsay(str(d))', [say("{'ina': {'cat': 2}}")]),
        Case("looping over a dict", 'd = {"x": 1, "y": 2}\nfor k in d:\n    say(k)', [say("x"), say("y")]),
    ],
    "control": [
        Case("if, elif and else", "for n in [1, 5, 9]:\n    if n < 3:\n        say(\"small\")\n    elif n < 7:\n        say(\"middle\")\n    else:\n        say(\"big\")", [say("small"), say("middle"), say("big")]),
        Case("while with break and continue", "n = 0\nwhile True:\n    n += 1\n    if n == 2:\n        continue\n    if n > 4:\n        break\n    say(str(n))", [say("1"), say("3"), say("4")]),
        Case("range forms", "say(str(len(range(5))))\nfor i in range(1, 10, 4):\n    say(str(i))\nfor i in range(3, 0, -1):\n    say(str(i))", [say("5"), say("1"), say("5"), say("9"), say("3"), say("2"), say("1")]),
        Case("looping over text", 'for c in "ab":\n    say(c)', [say("a"), say("b")]),
        Case("loop with two names", 'for i, w in enumerate(["x", "y"]):\n    say(f"{i}{w}")', [say("0x"), say("1y")]),
        Case("a loop goes over a copy", "a = [1, 2]\nfor x in a:\n    a.append(x)\nsay(str(a))", [say("[1, 2, 1, 2]")]),
        Case("nested loops break the inner one", "for i in range(2):\n    for j in range(5):\n        if j == 1:\n            break\n        say(f\"{i}{j}\")", [say("00"), say("10")]),
        Case("and and or give a value", 'say(str(0 or "x"))\nsay(str(3 and 4))\nsay(str(None or 0))\nsay(str("" and "y"))', [say("x"), say("4"), say("0"), say("")]),
        Case("the if expression", 'n = 4\nsay("even" if n % 2 == 0 else "odd")', [say("even")]),
        Case("is None", 'x = None\nsay(str(x is None))\nsay(str(3 is not None))', [say("True"), say("True")]),
        Case("truth of empty values", 'say(str(not []))\nsay(str(not {}))\nsay(str(not ""))\nsay(str(not 0.0))', [say("True"), say("True"), say("True"), say("True")]),
        Case("top-level values", 'say(str(LIMIT))\nsay(GREETING)', [say("3"), say("hi")], extra='LIMIT = 3\nGREETING = "hi"\n'),
        Case("the header can be read", "say(ABOUT)\nsay(str(len(USES)))", [say("a conformance test"), say("10")]),
    ],
    "functions": [
        Case("return a value", "say(str(double(4)))", [say("8")], extra="\ndef double(n):\n    return n * 2\n"),
        Case("defaults and keywords", 'say(greet("Ina"))\nsay(greet("Sam", word="Hi"))', [say("Hello Ina"), say("Hi Sam")], extra='\ndef greet(name, word="Hello"):\n    return f"{word} {name}"\n'),
        Case("a recursive function", "say(str(fact(5)))", [say("120")], extra="\ndef fact(n):\n    if n <= 1:\n        return 1\n    return n * fact(n - 1)\n"),
        Case("a function with no return gives None", "say(str(nothing()))", [say("None")], extra="\ndef nothing():\n    x = 1\n"),
        Case("a helper may call abilities", "tell(\"one\")\ntell(\"two\")", [say("one!"), say("two!")], extra="\ndef tell(word):\n    say(word + \"!\")\n"),
        Case("functions read top-level names", "say(str(bigger(2)))", [say("12")], extra="\nBASE = 10\n\ndef bigger(n):\n    return BASE + n\n"),
        Case("a function changes a list it was given", "a = []\nadd_two(a)\nsay(str(a))", [say("[2]")], extra="\ndef add_two(items):\n    items.append(2)\n"),
        Case("return inside a loop", "say(str(first_big([1, 5, 9])))", [say("5")], extra="\ndef first_big(items):\n    for x in items:\n        if x > 3:\n            return x\n    return None\n"),
    ],
    "abilities": [
        Case("say_to binds by name", 'say_to("me", "hello")', [("say_to", {"who": "me", "text": "hello"})]),
        Case("ask fills in its defaults", 'answer = ask("me", "Ready?")\nsay(f"you said {answer}")', [("ask", {"who": "me", "question": "Ready?", "choices": None, "wait": 20}), say("you said yes")], replies=["yes", None]),
        Case("ask with choices and a wait", 'answer = ask("me", "Red or blue?", ["red", "blue"], wait=30)\nsay(answer)', [("ask", {"who": "me", "question": "Red or blue?", "choices": ["red", "blue"], "wait": 30}), say("blue")], replies=["blue", None]),
        Case("no answer is None", 'answer = ask("me", "Hello?")\nif answer is None:\n    say("nobody")', [("ask", {"who": "me", "question": "Hello?", "choices": None, "wait": 20}), say("nobody")]),
        Case("keep and kept", 'keep("n", 1)\nn = kept("n", 0)\nsay(str(n + 1))', [("keep", {"key": "n", "value": 1}), ("kept", {"key": "n", "default": 0}), say("2")], replies=[None, 1, None]),
        Case("do returns its result", 'r = do("go to the kitchen")\nif r == "done":\n    say("there")', [("do", {"request": "go to the kitchen"}), say("there")], replies=["done", None]),
        Case("a refusal comes back as text", 'r = say("hi")\nif r.startswith("refused"):\n    note("it was refused")', [say("hi"), ("note", {"text": "it was refused"})], replies=["refused: it's quiet hours", None]),
        Case("look gives a list", "seen = look()\nsay(str(len(seen)))\nsay(seen[0])", [("look", {}), say("2"), say("cat")], replies=[["cat", "Ina"], None, None]),
        Case("state with a value", 'if state("present", "ina") == True:\n    say("Ina is here")', [("state", {"name": "present", "value": "ina", "who": None, "place": None, "thing": None, "at": None, "end": None, "day": None, "minutes": None, "level": None, "what": None}), say("Ina is here")], replies=[True, None]),
        Case("now and today", 'if now() >= "21:00":\n    say(today())', [("now", {}), ("today", {}), say("2026-10-21")], replies=["21:05", "2026-10-21", None]),
        Case("chance and pick", 'if chance(0.5):\n    say(pick(["a", "b"]))', [("chance", {"p": 0.5}), ("pick", {"items": ["a", "b"]}), say("b")], replies=[True, "b", None]),
        Case("wait and face", 'face("happy")\nwait(2)\nsay("done")', [("face", {"expression": "happy"}), ("wait", {"seconds": 2}), say("done")]),
        Case("finish ends the run at once", 'say("bye")\nfinish()\nsay("never")', [say("bye")], out="finish"),
        Case("feel and dial", 'f = feel()\nd = dial("speakup.per_hour")\nsay(str(f["happy"]))', [("feel", {}), ("dial", {"name": "speakup.per_hour"}), say("0.6")], replies=[{"happy": 0.6}, 2, None]),
        Case("tune with a reason", 'tune("speakup.per_hour", 1, "quieter")', [("tune", {"name": "speakup.per_hour", "value": 1, "why": "quieter"})]),
        Case("where and who_here", 'w = where("ball")\nppl = who_here()\nsay(f"{w} {ppl}")', [("where", {"thing": "ball"}), ("who_here", {}), say("lounge ['Ina']")], replies=["lounge", ["Ina"], None]),
        Case("a reply is a fresh value", 'a = kept("list", [])\na.append(1)\nb = kept("list", [])\nsay(str(len(b)))', [("kept", {"key": "list", "default": []}), ("kept", {"key": "list", "default": []}), say("0")], replies=[[], [], None]),
    ],
    "handlers": [
        Case(
            "the cat counter",
            source='ABOUT = "Counts the cat."\nUSES = ["look", "say"]\nFOR = "alex"\nUNTIL = "21:00"\nWANTS = {"seen": ["cat"], "at": ["21:00"]}\n\n\ndef on_start():\n    keep("count", 0)\n\n\ndef on_seen(thing, place):\n    if place == "lounge":\n        keep("count", kept("count") + 1)\n\n\ndef on_at(time):\n    n = kept("count")\n    say_to("alex", f"The cat came {n} times.")\n    finish()\n',
            runs=[
                {"handler": "on_start", "args": [], "replies": [None], "calls": [("keep", {"key": "count", "value": 0})], "out": "done"},
                {"handler": "on_seen", "args": ["cat", "lounge"], "replies": [0, None], "calls": [("kept", {"key": "count", "default": None}), ("keep", {"key": "count", "value": 1})], "out": "done"},
                {"handler": "on_seen", "args": ["cat", "kitchen"], "replies": [], "calls": [], "out": "done"},
                {"handler": "on_at", "args": ["21:00"], "replies": [5, None], "calls": [("kept", {"key": "count", "default": None}), ("say_to", {"who": "alex", "text": "The cat came 5 times."})], "out": "finish"},
            ],
        ),
        Case(
            "a handler gets only the arguments it asks for",
            source='ABOUT = "x"\nUSES = ["say"]\nUNTIL = "ongoing"\nWANTS = {"seen": ["cat"]}\n\n\ndef on_seen(thing):\n    say(thing)\n',
            runs=[{"handler": "on_seen", "args": ["cat", "lounge"], "replies": [None], "calls": [say("cat")], "out": "done"}],
        ),
        Case(
            "missing arguments are None",
            source='ABOUT = "x"\nUSES = ["say"]\nUNTIL = "ongoing"\nWANTS = {"heard": ["me"]}\nFOR = "alex"\n\n\ndef on_heard(who, words):\n    say(str(words))\n',
            runs=[{"handler": "on_heard", "args": ["Alex"], "replies": [None], "calls": [say("None")], "out": "done"}],
        ),
        Case(
            "a handler that isn't there does nothing",
            source='ABOUT = "x"\nUSES = ["say"]\nUNTIL = "ongoing"\n\n\ndef on_start():\n    say("hi")\n',
            runs=[{"handler": "on_seen", "args": ["cat"], "replies": [], "calls": [], "out": "done"}],
        ),
        Case(
            "top-level lists last between events",
            source='ABOUT = "x"\nUSES = ["say"]\nUNTIL = "ongoing"\nWANTS = {"sound": ["doorbell"]}\nSEEN = []\n\n\ndef on_sound(thing):\n    SEEN.append(thing)\n    say(str(len(SEEN)))\n',
            runs=[
                {"handler": "on_sound", "args": ["doorbell"], "replies": [None], "calls": [say("1")], "out": "done"},
                {"handler": "on_sound", "args": ["doorbell"], "replies": [None], "calls": [say("2")], "out": "done"},
            ],
        ),
        Case(
            "a crash ends only that run",
            source='ABOUT = "x"\nUSES = ["say"]\nUNTIL = "ongoing"\nWANTS = {"sound": ["knock"]}\n\n\ndef on_sound(thing):\n    say(thing)\n    x = 1 / 0\n',
            runs=[
                {"handler": "on_sound", "args": ["knock"], "replies": [None], "calls": [say("knock")], "out": ("crash", "error", "", 9)},
                {"handler": "on_sound", "args": ["knock"], "replies": [None], "calls": [say("knock")], "out": ("crash", "error", "", 9)},
            ],
        ),
    ],
    "limits": [
        Case("steps", "n = 0\nwhile True:\n    n += 1", out=("crash", "limit", "steps", 'n += 1'), limits={"ms": None}),
        Case("steps reset each run", "n = 0\nwhile n < 10000:\n    n += 1\nsay(str(n))", [say("10000")], limits={"ms": None}),
        Case("text made by repeating", 'x = "a" * 2001', out=("crash", "limit", "text", 'x = "a" * 2001')),
        Case("text made by adding", 'x = "a" * 2000\ny = x + "b"', out=("crash", "limit", "text", 'y = x + "b"')),
        Case("text made by an f-string", 'x = "a" * 1500\ny = f"{x}{x}"', out=("crash", "limit", "text", 'y = f"{x}{x}"')),
        Case("text made by replace", 'x = "a" * 1000\ny = x.replace("a", "aaa")', out=("crash", "limit", "text", 'y = x.replace("a", "aaa")')),
        Case("text made by join", 'parts = ["abcdefghij"] * 201\ny = "".join(parts)', out=("crash", "limit", "text", 'y = "".join(parts)')),
        Case("items by repeating", "x = [0] * 501", out=("crash", "limit", "items", 'x = [0] * 501')),
        Case("items by appending", "a = []\nwhile True:\n    a.append(1)", out=("crash", "limit", "items", 'a.append(1)')),
        Case("items in a dict", "d = {}\nfor i in range(501):\n    d[i] = i", out=("crash", "limit", "items", 'd[i] = i')),
        Case("items from range", "x = sorted(range(501))", out=("crash", "limit", "items", 'x = sorted(range(501))')),
        Case("nesting deeper than four", "x = [[[[[1]]]]]", out=("crash", "limit", "depth", 'x = [[[[[1]]]]]')),
        Case("nesting by appending", "a = [[[1]]]\nb = [a]\nc = [[]]\nc[0].append(b)", out=("crash", "limit", "depth", 'c[0].append(b)')),
        Case("four deep is fine", "x = [[[[1]]]]\nsay(str(x))", [say("[[[[1]]]]")]),
        Case("size of all values", 'big = "a" * 2000\nrows = [big] * 200', out=("crash", "limit", "size", 'rows = [big] * 200')),
        Case("size across names", 'a = ["x" * 2000] * 100\nb = ["y" * 2000] * 100\nc = ["z" * 2000] * 100\nsay("too much")', out=("crash", "limit", "size", 'say("too much")')),
        Case("recursion", "deep(0)", out=("crash", "limit", "recursion", 'return deep(n + 1)'), extra="\ndef deep(n):\n    return deep(n + 1)\n"),
        Case("nineteen calls deep is fine", "say(str(deep(18)))", [say("18")], extra="\ndef deep(n):\n    if n == 0:\n        return 0\n    return 1 + deep(n - 1)\n"),
        Case("a power bomb", "x = 10 ** 10 ** 10", out=("crash", "limit", "number", 'x = 10 ** 10 ** 10')),
        Case("big powers are refused before they are worked out", "x = 2 ** 100", out=("crash", "limit", "number", 'x = 2 ** 100')),
        Case("numbers past 2 to the 53rd", "x = 9007199254740991\ny = x + 1", out=("crash", "limit", "number", 'y = x + 1')),
        Case("a repeat bomb", 'x = "a" * 1000000000', out=("crash", "limit", "text", 'x = "a" * 1000000000')),
        Case("a list repeat bomb", "x = [1, 2] * 100000000", out=("crash", "limit", "items", 'x = [1, 2] * 100000000')),
        Case("a list can't hold itself", "a = []\na.append(a)", out=("crash", "error", "", 'a.append(a)')),
        Case("a list can't hold something that holds it", "a = []\nb = [a]\na.append(b)", out=("crash", "error", "", 'a.append(b)')),
    ],
    "errors": [
        Case("dividing by zero", "x = 1 / 0", out=("crash", "error", "", 'x = 1 / 0')),
        Case("whole division by zero", "x = 5 // 0", out=("crash", "error", "", 'x = 5 // 0')),
        Case("a name used before it is set", "say(str(y))\ny = 1", out=("crash", "error", "", 'say(str(y))')),
        Case("past the end of a list", "a = [1]\nx = a[3]", out=("crash", "error", "", 'x = a[3]')),
        Case("a key that isn't there", 'd = {}\nx = d["k"]', out=("crash", "error", "", 'x = d["k"]')),
        Case("adding text and a number", 'x = "a" + 1', out=("crash", "error", "", 'x = "a" + 1')),
        Case("unpacking the wrong number", "a, b = [1, 2, 3]", out=("crash", "error", "", 'a, b = [1, 2, 3]')),
        Case("too many arguments", "f(1, 2)", out=("crash", "error", "", 'f(1, 2)'), extra="\ndef f(a):\n    return a\n"),
        Case("a missing argument", "f()", out=("crash", "error", "", 'f()'), extra="\ndef f(a):\n    return a\n"),
        Case("text that isn't a number", 'x = int("abc")', out=("crash", "error", "", 'x = int("abc")')),
        Case("popping an empty list", "a = []\na.pop()", out=("crash", "error", "", 'a.pop()')),
        Case("removing what isn't there", "a = [1]\na.remove(2)", out=("crash", "error", "", 'a.remove(2)')),
        Case("a list as a key", "d = {}\nd[[1]] = 2", out=("crash", "error", "", 'd[[1]] = 2')),
        Case("looping over a number", "for x in 5:\n    say(x)", out=("crash", "error", "", 'for x in 5:')),
        Case("comparing None with a number", "x = None < 1", out=("crash", "error", "", 'x = None < 1')),
        Case("a method on the wrong kind of value", "x = 5\nx.append(1)", out=("crash", "error", "", 'x.append(1)')),
        Case("text % is not formatting", 'x = "%d" % 5', out=("crash", "error", "", 'x = "%d" % 5')),
        Case("an ability not in USES", source='ABOUT = "x"\nUSES = ["look"]\nUNTIL = "ongoing"\n\n\ndef on_start():\n    say("hi")\n', out=("crash", "uses", "say", 'say("hi")')),
        Case("an ability with a wrong argument name", 'say(words="hi")', out=("crash", "error", "", 'say(words="hi")')),
        Case("a slice step of zero", "x = [1, 2][::0]", out=("crash", "error", "", 'x = [1, 2][::0]')),
    ],
}


def expect_calls(calls: list) -> list:
    return [{"call": name, "args": args} for name, args in calls]


def expect_out(out) -> dict:
    if out == "done":
        return {"done": True}
    if out == "finish":
        return {"finish": True}
    _, kind, what, line = out
    return {"crash": kind, "what": what, "line": line}


def located(out, source: str):
    if not isinstance(out, tuple) or not isinstance(out[3], str):
        return out
    for number, text in enumerate(source.splitlines(), 1):
        if text.strip() == out[3]:
            return (out[0], out[1], out[2], number)
    raise ValueError(f"no line {out[3]!r}")


def actual(outcome) -> dict:
    if isinstance(outcome, Done):
        return {"done": True}
    if isinstance(outcome, Finish):
        return {"finish": True}
    return {"crash": outcome.kind, "what": outcome.what, "line": outcome.line}


def run_one(program: dict, limits: Limits, handler: str | None, args: list, replies: list) -> tuple[list, dict]:
    machine = Machine(program, limits)
    return run_on(machine, handler, args, replies)


def run_on(machine: Machine, handler: str | None, args: list, replies: list) -> tuple[list, dict]:
    run = machine.start() if handler is None else machine.run(handler, args)
    out = run.go()
    calls = []
    left = list(replies)
    while isinstance(out, Call):
        calls.append({"call": out.name, "args": out.args})
        out = run.go(left.pop(0) if left else None)
    return calls, actual(out)


def vector(case: Case) -> dict:
    source = source_of(case)
    checked = read(source)
    if checked.program is None:
        raise ValueError(f"{case.name}: {checked.errors}")
    runs = case.runs or [{"handler": "on_start", "args": [], "replies": case.replies or [], "calls": case.calls, "out": case.out}]
    return {
        "name": case.name,
        "source": source,
        "program": checked.program,
        "limits": case.limits or {},
        "runs": [{"handler": r["handler"], "args": list(r["args"]), "replies": list(r.get("replies") or []), "calls": expect_calls(r["calls"]), "outcome": expect_out(located(r["out"], source))} for r in runs],
    }


def replay(item: dict) -> list[str]:
    problems = []
    machine = Machine(item["program"], Limits.from_dict(item.get("limits")))
    start_calls, start_out = run_on(machine, None, [], [])
    if start_out.get("crash"):
        return [f"{item['name']}: the top level crashed {start_out}"]
    for index, run in enumerate(item["runs"]):
        calls, out = run_on(machine, run["handler"], run["args"], run["replies"])
        if calls != run["calls"]:
            problems.append(f"{item['name']} run {index}: calls {calls} != {run['calls']}")
        if out != run["outcome"]:
            problems.append(f"{item['name']} run {index}: outcome {out} != {run['outcome']}")
    return problems


def build_all() -> dict:
    out = {}
    for group, cases in GROUPS.items():
        out[group] = [vector(case) for case in cases]
    return out


def load_all(folder: Path = FOLDER) -> list[dict]:
    items = []
    for path in sorted(folder.glob("*.json")):
        items.extend(json.loads(path.read_text(encoding="utf-8"))["vectors"])
    return items


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m pebble.script.make_vectors", description="Write the Pebble script conformance vectors, after checking that the reference evaluator gives what each one expects.")
    parser.add_argument("--check", action="store_true", help="only replay the vectors already written")
    args = parser.parse_args(argv)
    if args.check:
        items = load_all()
        problems = [p for item in items for p in replay(item)]
        print(f"{len(items)} vectors, {len(problems)} problems")
        for problem in problems:
            print(problem)
        return 1 if problems else 0
    built = build_all()
    problems = [p for items in built.values() for item in items for p in replay(item)]
    for problem in problems:
        print(problem)
    if problems:
        return 1
    FOLDER.mkdir(parents=True, exist_ok=True)
    for group, items in built.items():
        text = json.dumps({"format": 1, "limits": LIMITS.as_dict(), "vectors": items}, indent=1, ensure_ascii=False) + "\n"
        (FOLDER / f"{group}.json").write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {sum(len(v) for v in built.values())} vectors in {len(built)} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
