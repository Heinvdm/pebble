import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from conftest import run

from pebble.chaos.engine import Chaos
from pebble.chaos.ideas import IdeaDecks
from pebble.mind.base import CallOptions, Mind, MindReply, MindUnavailable
from pebble.mind.llama import LlamaServerMind, stream_piece
from pebble.mind.profile import ModelProfile
from pebble.mind.scripted import ScriptedMind
from pebble.screen.gallery import Gallery
from pebble.screen.generator import SceneGenerator
from pebble.screen.grammar import scene_grammar
from pebble.screen.stage import SceneStage
from pebble.screen.studio import Studio
from pebble.screen.tools import SCREEN_TOOLS, register_screen_tools
from pebble.seams.face import LogFace
from pebble.tools.registry import ToolRegistry


class SlowScenes(Mind):
    name = "slow"

    def __init__(self, text: str, gap: float = 0.05):
        self.text = text
        self.gap = gap
        self.calls = []

    async def chat(self, messages, tools=None, purpose="turn", max_tokens=None, options=None):
        return MindReply(self.text)

    async def stream(self, messages, purpose="turn", max_tokens=None, options=None):
        self.calls.append(options)
        for piece in [self.text[i : i + 5] for i in range(0, len(self.text), 5)]:
            await asyncio.sleep(self.gap)
            yield piece


class Down(Mind):
    name = "down"

    async def chat(self, messages, tools=None, purpose="turn", max_tokens=None, options=None):
        raise MindUnavailable("switched off")


class TimedFace(LogFace):
    def __init__(self, loop_time):
        super().__init__()
        self.loop_time = loop_time
        self.line_times = []

    def scene_line(self, scene_id, index, element, text):
        super().scene_line(scene_id, index, element, text)
        self.line_times.append(self.loop_time())


def make_studio(store, clock, minds, chaos=None, face=None):
    chaos = chaos or Chaos(seed=4, pinned=6)
    face = face or LogFace()
    stage = SceneStage(face)
    decks = IdeaDecks.open(store)
    generator = SceneGenerator(minds, stage, chaos.call_options, lambda kind: chaos.cards(decks, kind))
    records = []
    studio = Studio(Gallery.open(store), stage, generator, clock, chaos.stream, lambda: chaos.level, lambda kind, **data: records.append((kind, data)))
    return studio, face, records


def test_the_generator_streams_lines_to_the_face_before_it_finishes(store, clock):
    text = "sky night\nstars 30 twinkle\nmoon 24 6 r4 pale\nhill 0 26 32 6 green"
    mind = SlowScenes(text)

    async def go():
        loop = asyncio.get_running_loop()
        face = TimedFace(loop.time)
        studio, face, _ = make_studio(store, clock, [("subconscious", mind)], face=face)
        start = loop.time()
        result = await studio.draw("a calm night")
        return result, face, loop.time() - start

    result, face, total = run(go())
    assert result["lines"] == 4 and result["by"] == "subconscious"
    assert face.scenes[-1]["lines"] == ["sky night", "stars 30 white twinkle", "moon 24 6 r4 pale still", "hill 0 26 32 6 green"]
    assert face.scenes[-1]["ended"]
    assert face.line_times[0] < face.line_times[-1] - 0.2
    options = mind.calls[0]
    assert options.grammar == scene_grammar() and options.kind == "creative" and options.seed is not None


def test_drawing_falls_back_from_the_subconscious_to_the_main_mind(store, clock):
    scripted = ScriptedMind()
    studio, face, records = make_studio(store, clock, [("subconscious", Down()), ("conscious", scripted)])
    result = run(studio.draw("rain at night", name="my-rain"))
    assert result["by"] == "conscious" and result["saved_as"] == "my-rain"
    assert "my-rain" in studio.names()
    request = [r for r in scripted.requests if r["purpose"] == "scene"][0]
    assert request["options"]["grammar"] is True and request["options"]["kind"] == "creative"
    assert "Draw: rain at night." in request["messages"][-1]["content"]
    assert "sky day|night" in request["messages"][0]["content"]
    assert records[0][0] == "scene_drawn" and records[0][1]["source"] == "conscious"


def test_offline_drawing_shows_a_gallery_scene_instead(store, clock):
    studio, face, _ = make_studio(store, clock, [("subconscious", Down())])
    result = run(studio.draw("something rainy and stormy"))
    assert result["showing"] == "rainy-day" and "could not draw" in result["note"]
    nothing = run(make_studio(store, clock, [])[0].draw("qqqq zzzz"))
    assert nothing["ok"] is False


def test_a_partial_scene_survives_a_timeout(store, clock):
    mind = SlowScenes("sky night\nstars 30\nmoon 4 4\n" * 3, gap=0.2)
    chaos = Chaos(seed=1)
    face = LogFace()
    generator = SceneGenerator([("slow", mind)], SceneStage(face), chaos.call_options, timeout_s=0.9)
    drawn = run(generator.draw("night"))
    assert drawn.scene and "timed out" in drawn.error
    assert face.scenes[-1]["ended"]


def test_screen_tools_draw_and_show(store, clock):
    studio, face, _ = make_studio(store, clock, [("conscious", ScriptedMind())])
    registry = ToolRegistry()
    register_screen_tools(registry, studio)
    assert set(registry.actions()) == set(SCREEN_TOOLS) and registry.names() == []
    drawn = run(registry.call("draw_scene", {"subject": "a night sky", "name": "night two", "seconds": 999, "mode": "overlay"}))
    assert drawn["ok"] and drawn["saved_as"] == "night-two"
    assert any("seconds clamped" in note for note in drawn["notes"])
    assert face.scenes[-1]["mode"] == "overlay" and face.scenes[-1]["hold"] == 60
    shown = run(registry.call("show_scene", {"name": "sunny"}))
    assert shown["showing"] == "sunny" and not shown["varied"]
    varied = run(registry.call("show_scene", {"name": "sunny", "vary": True}))
    assert varied["varied"] and varied["showing"].startswith("sunny-v")
    assert studio.gallery.get("sunny").text() == Gallery.template().get("sunny").text()
    missing = run(registry.call("show_scene", {"name": "nope"}))
    assert not missing["ok"] and varied["showing"] in missing["drawings"] and len(missing["drawings"]) <= 12
    assert not run(registry.call("draw_scene", {}))["ok"]


def test_doodles_and_dreams_use_the_gallery(store, clock):
    studio, face, records = make_studio(store, clock, [], chaos=Chaos(seed=9, pinned=10))
    result = run(studio.doodle())
    assert result["showing"] and face.scenes[-1]["mode"] == "overlay"
    dream = studio.dream("2026-10-15")
    assert dream["saved_as"] == "dream-2026-10-15" and len(dream["from"]) == 2
    assert studio.gallery.entry("dream-2026-10-15")["source"] == "dream"
    assert ("dream_remix", dream) in records
    assert "Your drawings:" in studio.gallery_line()


class FakeStream(BaseHTTPRequestHandler):
    posted: list = []
    pieces = ["sky ni", "ght\nsta", "rs 20\n", "moon 4 4 r2"]

    def log_message(self, *args):
        return

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        FakeStream.posted.append(json.loads(self.rfile.read(length)))
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        for piece in FakeStream.pieces:
            self.wfile.write(f"data: {json.dumps({'choices': [{'delta': {'content': piece}}]})}\n\n".encode())
            self.wfile.flush()
        self.wfile.write(b'data: {"choices": [{"delta": {}, "finish_reason": "stop"}]}\n\ndata: [DONE]\n\n')


@pytest.fixture
def fake_stream():
    FakeStream.posted = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), FakeStream)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server.server_address[1]
    server.shutdown()
    server.server_close()


def test_llama_client_streams_tokens_with_sampling_and_grammar(fake_stream):
    mind = LlamaServerMind(ModelProfile.from_dict({"name": "fake", "endpoint": f"http://127.0.0.1:{fake_stream}", "model": "lfm"}))
    options = CallOptions("creative", 0.9, 0.95, 0.05, 1234, "root ::= \"x\"")

    async def collect():
        return [piece async for piece in mind.stream([{"role": "user", "content": "draw"}], purpose="scene", max_tokens=50, options=options)]

    pieces = run(collect())
    assert "".join(pieces) == "sky night\nstars 20\nmoon 4 4 r2"
    posted = FakeStream.posted[-1]
    assert posted["stream"] is True and posted["grammar"] == 'root ::= "x"'
    assert (posted["temperature"], posted["top_p"], posted["min_p"], posted["seed"]) == (0.9, 0.95, 0.05, 1234)
    assert posted["max_tokens"] == 50
    assert "tools" not in posted
    plain = mind.payload([{"role": "user", "content": "x"}], None, None)
    assert plain["stream"] is False and "grammar" not in plain and "seed" not in plain


def test_llama_stream_reports_a_missing_server():
    mind = LlamaServerMind(ModelProfile.from_dict({"name": "gone", "endpoint": "http://127.0.0.1:9", "timeout_s": 2}))

    async def collect():
        return [piece async for piece in mind.stream([{"role": "user", "content": "x"}])]

    with pytest.raises(MindUnavailable):
        run(collect())


def test_stream_pieces_are_parsed_tolerantly():
    assert stream_piece('data: {"choices": [{"delta": {"content": "hi"}}]}') == ("hi", False)
    assert stream_piece("data: [DONE]") == (None, True)
    assert stream_piece(": ping") == (None, False)
    assert stream_piece("data: not json") == (None, False)
    assert stream_piece('data: {"content": "x", "stop": true}') == ("x", True)
    with pytest.raises(MindUnavailable):
        stream_piece('data: {"error": {"message": "grammar"}}')


def test_free_code_and_joke_variation_are_honest_seams():
    from pebble.seams.later import NoCodeArtist, NoJokeVariation

    drawing = run(NoCodeArtist().draw_code("a cat"))
    assert drawing.ok is False and "not built" in drawing.reason
    assert NoCodeArtist.available is False
    assert run(NoJokeVariation().vary({"text": "x"}, None)) is None
