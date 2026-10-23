import json
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "pebble" / "web" / "text_layer.js"
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node is not on PATH")

HELPERS = """
const t = require(process.argv[1]);
const sizes = [[21, 3120, 1440], [93, 3120, 1440], [177, 3120, 1440], [25, 1440, 3120], [177, 100, 100], [57, 891, 411]];
console.log(JSON.stringify({
  keys: Object.keys(t).sort(),
  hold: [t.holdSeconds(5), t.holdSeconds(45), t.holdSeconds(0), t.holdSeconds(-2), t.holdSeconds(undefined), t.holdSeconds(null), t.holdSeconds("9"), t.holdSeconds(NaN), t.holdSeconds(Infinity), t.holdSeconds(30), t.holdSeconds(0.5)],
  sizes: sizes.map(s => [s, t.moduleSize(s[0], s[1], s[2])]),
  corners: [0, 1, 2, 3, 4, -1].map(t.nextCorner)
}));
"""

PAGE = """
const script = process.argv[1];
let clock = 0, timerId = 1;
const timers = [];
Object.defineProperty(globalThis, "performance", { value: { now: () => clock * 1000 }, configurable: true, writable: true });
globalThis.setTimeout = (fn, ms) => { timers.push({ id: timerId, at: clock + ms / 1000, fn: fn, every: 0 }); return timerId++; };
globalThis.setInterval = (fn, ms) => { timers.push({ id: timerId, at: clock + ms / 1000, fn: fn, every: ms / 1000 }); return timerId++; };
globalThis.clearTimeout = id => { const i = timers.findIndex(x => x.id === id); if (i >= 0) timers.splice(i, 1); };
function advance(seconds) {
  const end = clock + seconds;
  for (;;) {
    timers.sort((a, b) => a.at - b.at);
    const next = timers[0];
    if (!next || next.at > end) break;
    clock = next.at;
    if (next.every) next.at += next.every; else timers.shift();
    next.fn();
  }
  clock = end;
}
const ink = { font: "", fills: 0, measureText(s) { return { width: s.length * parseFloat(/([0-9.]+)px/.exec(this.font)[1]) * 0.55 }; }, fillRect() { this.fills++; } };
class El {
  constructor(tag) { this.tag = tag; this.style = {}; this.children = []; this.on = {}; this.own = ""; this.width = 300; this.height = 150; }
  appendChild(child) { this.children.push(child); return child; }
  addEventListener(name, fn) { (this.on[name] = this.on[name] || []).push(fn); }
  set textContent(value) { this.own = String(value); this.children = []; }
  get textContent() { return this.own + this.children.map(c => c.textContent).join(""); }
  getContext() { return ink; }
  click() { (this.on.click || []).forEach(fn => fn({})); }
}
const sources = [];
globalThis.EventSource = class {
  constructor(url) { this.url = url; this.on = {}; this.closed = false; sources.push(this); }
  addEventListener(name, fn) { (this.on[name] = this.on[name] || []).push(fn); }
  close() { this.closed = true; }
};
globalThis.document = { body: new El("body"), createElement: tag => new El(tag), addEventListener() {} };
globalThis.window = { innerWidth: 891, innerHeight: 411, devicePixelRatio: 3.5, addEventListener() {} };
const send = data => (sources[sources.length - 1].on.text || []).forEach(fn => fn({ data: JSON.stringify(data) }));
const helpers = require(script);
const root = document.body.children[0];
const [panel, band, badge] = root.children;
const inner = panel.children[0];
const canvas = inner.children[0].children[0];
const textBox = inner.children[1];
const title = textBox.children[0].children[0];
const counter = textBox.children[0].children[1];
const lineBox = textBox.children[1];
const shown = () => panel.style.display === "block";
const lineCount = () => lineBox.children.reduce((n, col) => n + col.children.length, 0);
const out = {};
out.connected = [sources.length, sources[0].url, Object.keys(sources[0].on)];
const lines = Array.from({ length: 10 }, (_, i) => "Item " + (i + 1));
send({ op: "show", id: "text-1", kind: "list", title: "Shopping", lines: lines, qr: null, hold: 6, page: 1, pages: 2 });
out.list = [shown(), title.textContent, counter.textContent, lineCount()];
advance(5.9);
out.listBeforeHold = shown();
advance(0.2);
out.listAfterHold = shown();
const rows = Array.from({ length: 21 }, (_, y) => Array.from({ length: 21 }, (_, x) => ((x + y) % 3 === 0 ? "1" : "0")).join(""));
send({ op: "show", id: "text-2", kind: "qr", title: "Guest Wi-Fi", lines: ["Network: Kiwi"], qr: rows, hold: 10, page: 1, pages: 1 });
out.qr = [shown(), canvas.width, canvas.height, canvas.style.width, lineCount()];
panel.click();
out.tapped = shown();
send({ op: "show", id: "text-2", kind: "qr", title: "Guest Wi-Fi", lines: [], qr: rows, hold: 10, page: 1, pages: 1 });
out.tappedStaysDown = shown();
send({ op: "show", id: "text-3", kind: "card", title: "DOOR", lines: ["Someone knocked"], qr: null, hold: 25, page: 1, pages: 2 });
advance(20);
send({ op: "show", id: "text-3", kind: "card", title: "DOOR", lines: ["Still there"], qr: null, hold: 25, page: 2, pages: 2 });
advance(9.9);
out.capBefore = shown();
advance(0.2);
out.capAfter = shown();
send({ op: "show", id: "text-4", kind: "caption", title: "", lines: ["one", "two", "three"], qr: null, hold: 8, page: 1, pages: 1 });
out.caption = [band.style.display, band.textContent];
advance(8.1);
out.captionGone = band.style.display;
send({ op: "badge", text: "Visitors" });
out.badge = [badge.style.display, badge.textContent, badge.style.left, badge.style.top];
advance(60);
out.badgeMoved = [badge.style.right, badge.style.top];
send({ op: "show", id: "text-5", kind: "list", title: "A", lines: ["x"], qr: null, hold: 20, page: 1, pages: 1 });
send({ op: "show", id: "text-6", kind: "caption", title: "", lines: ["hi"], qr: null, hold: 8, page: 1, pages: 1 });
send({ op: "clear", id: "text-99" });
out.clearOther = [shown(), band.style.display, badge.style.display];
send({ op: "clear", id: "text-6" });
out.clearCaption = [shown(), band.style.display];
send({ op: "clear", id: null });
out.clearAll = [shown(), band.style.display, badge.style.display];
send({ op: "badge", text: null });
out.badgeGone = badge.style.display;
send({ op: "show", id: "text-7", kind: "list", title: "B", lines: ["y"], hold: 999 });
advance(29.9);
out.longHoldBefore = shown();
advance(0.2);
out.longHoldAfter = shown();
sources[0].onerror();
out.closed = sources[0].closed;
advance(1.9);
out.beforeRetry = sources.length;
advance(0.2);
out.afterRetry = [sources.length, Object.keys(sources[1].on)];
out.helpers = Object.keys(helpers).sort();
console.log(JSON.stringify(out));
"""


def node(code: str, *args: str) -> str:
    result = subprocess.run([NODE, "-e", code, *args], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    return result.stdout


def test_the_script_parses():
    result = subprocess.run([NODE, "--check", str(SCRIPT)], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr


def test_the_helpers_work_from_node():
    out = json.loads(node(HELPERS, str(SCRIPT)))
    assert out["keys"] == ["holdSeconds", "moduleSize", "nextCorner"]
    assert out["hold"] == [5, 30, 20, 20, 20, 20, 20, 20, 30, 30, 0.5]
    assert [size for _, size in out["sizes"]] == [42, 12, 6, 37, 1, 5]
    for (modules, width, height), size in out["sizes"]:
        assert size == 1 or (modules + 8) * size <= 0.85 * min(width, height) < (modules + 8) * (size + 1)
    assert out["corners"] == [1, 2, 3, 0, 1, 0]


def test_the_script_loads_nothing_from_elsewhere_and_listens_for_text():
    source = SCRIPT.read_text(encoding="utf-8")
    assert "http://" not in source and "https://" not in source
    assert "eval(" not in source and "new Function" not in source and "innerHTML" not in source
    assert 'addEventListener("text"' in source
    assert 'new EventSource("/events")' in source


def test_the_overlay_shows_holds_and_hides_on_a_fake_page():
    out = json.loads(node(PAGE, str(SCRIPT)))
    assert out["connected"] == [1, "/events", ["text"]]
    assert out["list"] == [True, "Shopping", "1/2", 10]
    assert out["listBeforeHold"] is True and out["listAfterHold"] is False
    assert out["qr"] == [True, 29 * 42, 29 * 42, "348px", 1]
    assert out["tapped"] is False and out["tappedStaysDown"] is False
    assert out["capBefore"] is True and out["capAfter"] is False
    assert out["caption"] == ["block", "twothree"]
    assert out["captionGone"] == "none"
    assert out["badge"][:2] == ["block", "Visitors"] and out["badge"][2] != "auto" and out["badge"][3] != "auto"
    assert out["badgeMoved"][0] != "auto" and out["badgeMoved"][1] != "auto"
    assert out["clearOther"] == [True, "block", "none"]
    assert out["clearCaption"] == [True, "none"]
    assert out["clearAll"] == [False, "none", "block"]
    assert out["badgeGone"] == "none"
    assert out["longHoldBefore"] is True and out["longHoldAfter"] is False
    assert out["closed"] is True and out["beforeRetry"] == 1
    assert out["afterRetry"] == [2, ["text"]]
    assert out["helpers"] == ["holdSeconds", "moduleSize", "nextCorner"]
