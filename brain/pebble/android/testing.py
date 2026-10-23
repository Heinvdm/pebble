import asyncio
import json
import time

from .main import _lock, _running


def hang(seconds: float) -> bool:
    with _lock:
        loop = _running.get("loop")
    if loop is None or loop.is_closed():
        return False
    loop.call_soon_threadsafe(time.sleep, float(seconds))
    return True


def starter_stems() -> str:
    from ..script.book import STARTERS

    return json.dumps(sorted(path.stem for path in STARTERS.glob("*.py")))


def script_dream(link, name: str) -> str:
    from ..script.book import STARTERS
    from ..script.check import read
    from ..script.dream import dream
    from ..script.host import Phone

    checked = read((STARTERS / f"{name}.py").read_text(encoding="utf-8"))
    here = asyncio.run(dream(checked))
    engine = Phone(link=link)
    started = time.monotonic()
    there = asyncio.run(dream(checked, engine=engine))
    return json.dumps({
        "name": name,
        "engine": engine.kind,
        "passed": there.passed,
        "here_passed": here.passed,
        "failures": there.failures,
        "said": there.said,
        "calls": len(there.calls),
        "same_calls": json.dumps(here.calls, default=str, sort_keys=True) == json.dumps(there.calls, default=str, sort_keys=True),
        "same_said": here.said == there.said,
        "crash": repr(there.crash) if there.crash is not None else None,
        "closed": engine.pid is None,
        "seconds": round(time.monotonic() - started, 3),
    })
