import asyncio

from ..tools.registry import Param, Tool, ToolRegistry
from .mine import MineRefused

SELF_TOOLS = ("recall", "mine", "wonder")
MINE_ACTIONS = ("list", "read", "write", "rename", "tag", "pin", "unpin", "delete")
WONDER_ACTIONS = ("add", "answered", "list")


def register_self_tools(registry: ToolRegistry, memory) -> None:
    async def recall(args: dict) -> dict:
        lines = await memory.remember_about(args["about"])
        return {"memories": lines} if lines else {"memories": [], "note": "nothing comes to mind"}

    async def mine(args: dict) -> dict:
        folder = memory.mine
        action = args["action"]
        name = args.get("name") or ""
        try:
            if action == "list":
                return {"files": await asyncio.to_thread(folder.files, name, args.get("tags") or "")}
            if not name:
                return {"ok": False, "error": "say which file"}
            if action == "read":
                return {"name": name, "text": await asyncio.to_thread(folder.read, name)}
            if action == "write":
                return await asyncio.to_thread(folder.write, name, args.get("text") or "")
            if action == "rename":
                return await asyncio.to_thread(folder.rename, name, args.get("to") or "")
            if action == "tag":
                return await asyncio.to_thread(folder.tag, name, args.get("tags") or "")
            if action in ("pin", "unpin"):
                return await asyncio.to_thread(folder.pin, name, action == "pin")
            return await asyncio.to_thread(folder.delete, name)
        except MineRefused as error:
            return {"ok": False, "error": str(error)}

    async def wonder(args: dict) -> dict:
        folder = memory.mine
        action = args["action"]
        try:
            if action == "add":
                return await asyncio.to_thread(folder.wonder, args.get("text") or "")
            if action == "answered":
                return await asyncio.to_thread(folder.answered, args.get("id") or "", args.get("text") or "")
        except MineRefused as error:
            return {"ok": False, "error": str(error)}
        return {"wonderings": [{"id": w["id"], "text": w["text"]} for w in folder.open_wonderings()]}

    registry.register_action(Tool(
        "recall",
        "Search your own memories. At most five short lines come back; what others said stays their words.",
        {"about": Param("string", "what to remember", max_length=120)},
        recall,
    ))
    registry.register_action(Tool(
        "mine",
        "Your own folder of notes, collections, stories, songs and projects: list, read, write, rename, tag, pin, unpin or delete.",
        {
            "action": Param("enum", "what to do", choices=MINE_ACTIONS),
            "name": Param("string", "the file, like stories/the-cat.md (or a folder to list)", max_length=120, required=False),
            "text": Param("string", "what to write", max_length=4000, required=False),
            "to": Param("string", "the new name, to rename", max_length=120, required=False),
            "tags": Param("string", "tags, separated by commas", max_length=120, required=False),
        },
        mine,
    ))
    registry.register_action(Tool(
        "wonder",
        "Your wonderings: questions with no 'done when'. Add one, mark one answered, or list them.",
        {
            "action": Param("enum", "what to do", choices=WONDER_ACTIONS),
            "text": Param("string", "the wondering, or what you found out", max_length=160, required=False),
            "id": Param("string", "which wondering, to mark it answered", max_length=12, required=False),
        },
        wonder,
    ))
