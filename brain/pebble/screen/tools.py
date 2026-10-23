from ..respect import harsh
from ..seams.face import SCENE_MODES
from ..tools.registry import Param, Tool, ToolRegistry
from .studio import Studio

SCREEN_TOOLS = ("draw_scene", "show_scene")


def register_screen_tools(registry: ToolRegistry, studio: Studio) -> None:
    async def draw_scene(args: dict) -> dict:
        if harsh(args["subject"]):
            return {"ok": False, "error": "not drawn: it would be unkind to something alive"}
        return await studio.draw(args["subject"], args.get("name") or None, args["mode"], args["seconds"])

    async def show_scene(args: dict) -> dict:
        return await studio.show(args["name"], args["mode"], args["seconds"], bool(args.get("vary")))

    registry.register_action(Tool(
        "draw_scene",
        "Draw a small animated picture on your face screen. Say in a few words what to draw; it appears line by line within a second or two. Give it a name to keep it in your gallery.",
        {
            "subject": Param("string", "what to draw, in a few words", max_length=80),
            "name": Param("string", "a short name to keep it under (letters, numbers, dashes)", max_length=32, required=False),
            "mode": Param("enum", "full screen, or over your face", choices=SCENE_MODES, required=False, default="full"),
            "seconds": Param("number", "how long it stays before your face comes back", 3, 60, required=False, default=8),
        },
        draw_scene,
    ))
    registry.register_action(Tool(
        "show_scene",
        "Show a drawing from your gallery at once. Set vary to show a small variation of it (the original is kept).",
        {
            "name": Param("string", "the drawing's name", max_length=32),
            "mode": Param("enum", "full screen, or over your face", choices=SCENE_MODES, required=False, default="full"),
            "seconds": Param("number", "how long it stays", 3, 60, required=False, default=8),
            "vary": Param("boolean", "show a small variation", required=False, default=False),
        },
        show_scene,
    ))
