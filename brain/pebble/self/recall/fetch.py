import sys

from ...eyes.fetch import Asset, check, cli, fetch
from .embed import MODEL_FILE, MODELS, VOCAB_FILE

ARCTIC = "https://huggingface.co/Snowflake/snowflake-arctic-embed-xs/resolve/d8c86521100d3556476a063fc2342036d45c106f"
LICENCE = "Apache-2.0 (snowflake-arctic-embed-xs, Snowflake; the int8 ONNX export in its own repository)"

ASSETS = (
    Asset("recall_model", MODEL_FILE, f"{ARCTIC}/onnx/model_int8.onnx", "e6aa5e656466a73d7c3111e9a3378bd13e5b93af30eaac2b3f13fd56692589a1", 22972992, LICENCE),
    Asset("recall_vocab", VOCAB_FILE, f"{ARCTIC}/vocab.txt", "07eced375cec144d27c900241f3e339478dec958f92fddbc551f295c992038a3", 231508, LICENCE),
)

__all__ = ["ASSETS", "MODELS", "Asset", "check", "cli", "fetch", "main"]


def main(argv: list[str] | None = None) -> int:
    return cli(argv, ASSETS, MODELS, "python -m pebble.self.recall.fetch", "the small sentence model Pebble's memory search uses (snowflake-arctic-embed-xs)")


if __name__ == "__main__":
    sys.exit(main())
