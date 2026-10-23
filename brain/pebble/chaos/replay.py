import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .streams import check, replay


@dataclass(frozen=True)
class Replayed:
    record: dict
    outcome: object
    same: bool


def chaos_records(path: Path, lever: str | None = None, open_line: Callable[[str], str | None] | None = None) -> list[dict]:
    records = []
    paths = sorted(Path(path).parent.glob(Path(path).name + ".*"), reverse=True) + [Path(path)]
    for file in paths:
        if not file.exists():
            continue
        for raw in file.read_text(encoding="utf-8", errors="replace").splitlines():
            text = raw if open_line is None else open_line(raw)
            if not text:
                continue
            try:
                record = json.loads(text)
            except ValueError:
                continue
            if isinstance(record, dict) and record.get("kind") == "chaos" and (lever is None or record.get("lever") == lever):
                records.append(record)
    return records


def replay_records(records: list[dict]) -> list[Replayed]:
    return [Replayed(record, replay(record), check(record)) for record in records]


def self_of(blackbox: Path) -> Path:
    path = Path(blackbox)
    return path.parent.parent if path.parent.name == "logs" else path.parent


def sealed_opener(blackbox: Path, self_dir: Path | None, key_file: str | None, key_holder: str | None = None) -> Callable[[str], str | None] | None:
    from ..selfstore.sealed import is_sealed

    root = Path(self_dir) if self_dir else self_of(blackbox)
    if not is_sealed(root):
        return None
    from ..seal.startup import holder_for, line_opener

    return line_opener(root, blackbox, holder=holder_for(root, key_file, key_holder))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m pebble.chaos.replay", description="Replay every logged chaos draw and check it comes out the same")
    parser.add_argument("blackbox", help="path to logs/blackbox.jsonl")
    parser.add_argument("--lever", default=None)
    parser.add_argument("--id", dest="draw_id", default=None, help="one draw, as lever:seed:n")
    parser.add_argument("--self", dest="self_dir", default=None, help="the self folder, when the black box is sealed (default: the folder above logs/)")
    parser.add_argument("--key-file", default=None, help="Pebble's key file for a sealed self (default $PEBBLE_KEY_FILE or ~/.pebble/self.key)")
    parser.add_argument("--key-holder", choices=("file", "android"), default=None, help="where Pebble's lock lives (default $PEBBLE_KEY_HOLDER, else what seal.json says)")
    args = parser.parse_args(argv)
    from ..seal.errors import SealError

    try:
        open_line = sealed_opener(Path(args.blackbox), args.self_dir, args.key_file, args.key_holder)
    except (OSError, SealError) as error:
        print(f"The black box is sealed and cannot be opened here: {error}", file=sys.stderr)
        return 2
    records = chaos_records(Path(args.blackbox), args.lever, open_line)
    if args.draw_id:
        records = [r for r in records if r.get("id") == args.draw_id]
    results = replay_records(records)
    for result in results:
        mark = "same" if result.same else "DIFFERENT"
        print(f"{result.record.get('at', '?')} {result.record.get('id')} {result.record.get('op')} -> {json.dumps(result.outcome)} {mark}")
    different = sum(1 for r in results if not r.same)
    print(f"{len(results)} draws replayed, {different} different", file=sys.stderr)
    return 1 if different else 0


if __name__ == "__main__":
    raise SystemExit(main())
