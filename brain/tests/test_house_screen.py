import pytest

from pebble.house import qr, screen
from pebble.house.screen import CAPTION_S, LINES_PER_PAGE, MAX_HOLD_S, TextLayer, text_layer_for
from pebble.seams.face import LogFace
from pebble.web.hub import Hub
from pebble.web.webface import WebFace


class Clock:
    def __init__(self, t: float = 1000.0):
        self.t = t

    def __call__(self) -> float:
        return self.t

    def add(self, seconds: float) -> None:
        self.t += seconds


class Sink:
    def __init__(self):
        self.sent: list[tuple[str, dict]] = []

    def __call__(self, event: str, data: dict) -> None:
        self.sent.append((event, data))

    def take(self) -> list[dict]:
        assert all(event == "text" for event, _ in self.sent)
        out = [data for _, data in self.sent]
        self.sent.clear()
        return out


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def sink():
    return Sink()


@pytest.fixture
def layer(sink, clock):
    return TextLayer(sink, clock)


def test_show_publishes_the_message_shape_and_clamps_the_hold_to_30_s(layer, sink, clock):
    item = layer.show("card", "Door", ["Someone knocked"], hold_s=120)
    assert item == "text-1"
    assert sink.take() == [{"op": "show", "id": "text-1", "kind": "card", "title": "Door", "lines": ["Someone knocked"], "qr": None, "hold": MAX_HOLD_S, "page": 1, "pages": 1}]
    clock.add(29.9)
    layer.tick()
    assert sink.take() == []
    assert layer.showing()["id"] == item
    clock.add(0.1)
    layer.tick()
    assert sink.take() == [{"op": "clear", "id": item}]
    assert layer.showing() is None


@pytest.mark.parametrize("hold, expected", [(0, 20.0), (-3, 20.0), (None, 20.0), ("soon", 20.0), (float("nan"), 20.0), (float("inf"), 30.0), (5, 5.0), (30.5, 30.0)])
def test_odd_holds_fall_back_or_clamp(layer, sink, hold, expected):
    layer.show("card", "Hi", hold_s=hold)
    assert sink.take()[0]["hold"] == expected


def test_unknown_kinds_are_refused(layer):
    with pytest.raises(ValueError):
        layer.show("poster", "Hi")


def test_nothing_to_show_publishes_nothing(layer, sink):
    assert layer.show("list", "  ", ["", "   "]) == ""
    assert sink.take() == []
    assert layer.showing() is None


def test_a_25_item_list_shows_ten_a_page_and_never_more_than_the_hold(layer, sink, clock):
    items = [f"Item {i}" for i in range(1, 26)]
    item = layer.show("list", "Shopping", items, hold_s=21)
    first = sink.take()
    assert [m["lines"] for m in first] == [items[:LINES_PER_PAGE]]
    assert (first[0]["page"], first[0]["pages"], first[0]["hold"]) == (1, 3, 21.0)
    clock.add(6.9)
    layer.tick()
    assert sink.take() == []
    clock.add(0.2)
    layer.tick()
    second = sink.take()
    assert [(m["id"], m["page"], m["lines"], m["hold"]) for m in second] == [(item, 2, items[10:20], 13.9)]
    clock.add(7.0)
    layer.tick()
    third = sink.take()
    assert [(m["page"], m["lines"], m["hold"]) for m in third] == [(3, items[20:], 6.9)]
    clock.add(6.8)
    layer.tick()
    assert sink.take() == []
    clock.add(0.2)
    layer.tick()
    assert sink.take() == [{"op": "clear", "id": item}]
    assert [m["page"] for m in layer.shown] == [1, 2, 3]


def test_a_late_tick_skips_to_the_page_that_is_due(layer, sink, clock):
    layer.show("list", "", [f"Item {i}" for i in range(30)], hold_s=30)
    sink.take()
    clock.add(25)
    layer.tick()
    assert [m["page"] for m in sink.take()] == [3]


def test_lines_are_tidied_and_capped(layer, sink):
    long = "x" * 100
    layer.show("list", "  My\tlist  ", ["  milk\n and   eggs ", "", None, long] + [f"n{i}" for i in range(80)])
    message = sink.take()[0]
    assert message["title"] == "My list"
    assert message["lines"][:2] == ["milk and eggs", "x" * 59 + "…"]
    assert message["pages"] == 6
    assert len(message["lines"][1]) == 60
    layer.show("card", "Note", "first line\nsecond line")
    assert sink.take()[0]["lines"] == ["first line", "second line"]


def test_a_long_code_text_is_split_into_codes_across_pages(layer, sink, clock):
    items = [f"Item number {i}: something from the shop" for i in range(60)]
    text = "\n".join(items)
    pieces = qr.parts(text)
    assert len(pieces) > 1
    item = layer.show("qr", "Shopping list", items[:5], qr=text, hold_s=30)
    messages = [sink.take()[0]]
    step = 30 / len(pieces) + 0.01
    for page in range(2, len(pieces) + 1):
        clock.add(step)
        layer.tick()
        messages.extend(sink.take())
    assert [m["page"] for m in messages] == list(range(1, len(pieces) + 1))
    assert all(m["pages"] == len(pieces) and m["id"] == item and m["kind"] == "qr" for m in messages)
    assert [m["qr"] for m in messages] == [qr.encode(piece) for piece in pieces]
    assert messages[0]["lines"] == items[:5]
    assert all(m["lines"] == [] for m in messages[1:])


def test_a_huge_code_text_is_capped_at_six_pages(layer, sink):
    layer.show("qr", "Everything", qr="\n".join(f"line {i} of a very long note" for i in range(1000)))
    assert sink.take()[0]["pages"] == screen.MAX_CODE_PAGES


def test_a_code_that_cannot_be_made_is_dropped_and_the_lines_still_show(layer, sink, monkeypatch):
    def refuse(text, ecc="M"):
        raise qr.TooLong("too long")

    monkeypatch.setattr(screen.codes, "encode", refuse)
    item = layer.show("qr", "Guest Wi-Fi", ["Network: Kiwi"], qr=qr.wifi("Kiwi", "secret"))
    message = sink.take()[0]
    assert message["id"] == item and message["qr"] is None and message["lines"] == ["Network: Kiwi"]
    assert layer.show("qr", qr="WIFI:T:WPA;S:Kiwi;P:secret;;") == ""
    assert sink.take() == []


def test_a_caption_keeps_the_last_two_lines_and_goes_after_8_s(layer, sink, clock):
    first = layer.caption(["one", "two", "three"])
    message = sink.take()[0]
    assert (message["kind"], message["lines"], message["hold"], message["qr"]) == ("caption", ["two", "three"], CAPTION_S, None)
    clock.add(3)
    second = layer.caption(["a" * 50 + " the newest words " + "b" * 50])
    message = sink.take()[0]
    assert second != first
    assert len(message["lines"][0]) == 90 and message["lines"][0].startswith("…") and message["lines"][0].endswith("b" * 50)
    assert layer.showing()["id"] == second
    clock.add(5)
    layer.tick()
    assert sink.take() == []
    clock.add(3)
    layer.tick()
    assert sink.take() == [{"op": "clear", "id": second}]
    assert layer.showing() is None


def test_an_empty_caption_takes_the_old_one_down(layer, sink):
    item = layer.caption("hello there")
    sink.take()
    assert layer.caption([]) == ""
    assert sink.take() == [{"op": "clear", "id": item}]


def test_a_caption_and_a_list_can_be_up_together(layer, sink, clock):
    item = layer.show("list", "Shopping", ["Milk"], hold_s=20)
    words = layer.caption(["Where are the keys?"])
    sink.take()
    assert layer.showing()["id"] == item
    assert [data["id"] for _, data in layer.replay()] == [item, words]
    clock.add(8)
    layer.tick()
    assert sink.take() == [{"op": "clear", "id": words}]
    assert layer.showing()["id"] == item


def test_the_badge_stays_until_it_is_taken_away(layer, sink, clock):
    layer.badge("Visitors")
    assert sink.take() == [{"op": "badge", "text": "Visitors"}]
    layer.badge("Visitors")
    assert sink.take() == []
    clock.add(3600)
    layer.tick()
    assert sink.take() == []
    assert layer.replay() == [("text", {"op": "badge", "text": "Visitors"})]
    layer.badge("A much longer badge than is allowed")
    assert len(sink.take()[0]["text"]) == 24
    layer.badge(None)
    assert sink.take() == [{"op": "badge", "text": None}]
    assert layer.replay() == []


def test_replay_after_a_reconnect_gives_the_page_due_now_with_the_hold_left(layer, sink, clock):
    items = [f"Item {i}" for i in range(1, 26)]
    item = layer.show("list", "Shopping", items, hold_s=21)
    layer.badge("Visitors")
    sink.take()
    clock.add(8)
    events = layer.replay()
    assert [event for event, _ in events] == ["text", "text"]
    page, badge = events[0][1], events[1][1]
    assert (page["op"], page["id"], page["page"], page["lines"], page["hold"]) == ("show", item, 2, items[10:20], 13.0)
    assert badge == {"op": "badge", "text": "Visitors"}
    assert sink.take() == []
    clock.add(13)
    assert layer.replay() == [("text", {"op": "badge", "text": "Visitors"})]


def test_clear_by_id_only_clears_a_match(layer, sink):
    item = layer.show("card", "Door")
    sink.take()
    layer.clear("text-99")
    assert sink.take() == []
    assert layer.showing()["id"] == item
    layer.clear(item)
    assert sink.take() == [{"op": "clear", "id": item}]
    assert layer.showing() is None
    layer.show("card", "Door")
    layer.caption("hi")
    sink.take()
    layer.clear()
    assert sink.take() == [{"op": "clear", "id": None}]
    assert layer.showing() is None and layer.replay() == []


def test_publish_errors_are_swallowed(clock, caplog):
    def broken(event, data):
        raise OSError("hub gone")

    layer = TextLayer(broken, clock)
    item = layer.show("list", "Shopping", ["Milk"], hold_s=5)
    layer.caption("hello")
    layer.badge("Visitors")
    clock.add(10)
    layer.tick()
    layer.clear()
    assert item == "text-1"
    assert [m["id"] for m in layer.shown] == ["text-1", "text-2"]
    assert "publish failed" in caplog.text


def test_shown_keeps_the_last_20(layer):
    for i in range(25):
        layer.show("card", f"Card {i}")
    assert len(layer.shown) == 20
    assert layer.shown[-1]["id"] == "text-25" and layer.shown[0]["id"] == "text-6"


def test_showing_is_a_copy(layer):
    layer.show("list", "Shopping", ["Milk"])
    layer.showing()["lines"].append("Cake")
    assert layer.showing()["lines"] == ["Milk"]


def test_text_layer_for_a_web_face_publishes_to_its_hub_and_replays(clock):
    hub = Hub()
    face = WebFace(hub)
    layer = text_layer_for(face, clock)
    layer.badge("Visitors")
    layer.show("card", "Door", ["Someone knocked"])
    assert hub.published == 2
    client = hub.subscribe()
    replayed = []
    while not client.empty():
        replayed.append(client.get_nowait())
    texts = [message for message in replayed if message.startswith(b"event: text\n")]
    assert len(texts) == 2
    assert b'"title":"Door"' in texts[0] and b'"text":"Visitors"' in texts[1]
    hub.close()


def test_text_layer_for_a_face_without_a_hub_only_logs(clock):
    layer = text_layer_for(LogFace(), clock)
    assert layer.publish is None
    item = layer.show("card", "Door", ["Someone knocked"])
    assert layer.showing()["id"] == item
    layer.tick()
    layer.clear(item)
    assert layer.showing() is None
