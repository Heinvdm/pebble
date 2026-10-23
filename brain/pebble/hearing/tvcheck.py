import asyncio

CHECKS = "hearing/checks.json"
BLOCK_S = 300.0
BLOCKS = 6
POLL_S = 0.5


def tv_passed(checks) -> bool:
    found = (checks or {}).get("tv") if isinstance(checks, dict) else None
    return isinstance(found, dict) and found.get("passed") is True


class TvCheck:
    def __init__(self, set_gain, keyword_at, monotonic, sleep=asyncio.sleep, block_s: float = BLOCK_S, blocks: int = BLOCKS, poll_s: float = POLL_S):
        self.set_gain = set_gain
        self.keyword_at = keyword_at
        self.monotonic = monotonic
        self.sleep = sleep
        self.block_s = float(block_s)
        self.blocks = int(blocks)
        self.poll_s = float(poll_s)
        self.stopped = ""
        self.running = False
        self.block = -1
        self.counts = {False: 0, True: 0}
        self.seconds = {False: 0.0, True: 0.0}

    def stop(self, why: str = "stopped") -> None:
        self.stopped = why or "stopped"

    async def run(self) -> dict:
        self.running = True
        last = self.keyword_at()
        try:
            for index in range(self.blocks):
                if self.stopped:
                    break
                gain = index % 2 == 1
                self.block = index
                self.set_gain(gain)
                began = self.monotonic()
                while not self.stopped and self.monotonic() - began < self.block_s:
                    await self.sleep(self.poll_s)
                    found = self.keyword_at()
                    if found is not None and found != last:
                        self.counts[gain] += 1
                        last = found
                self.seconds[gain] += self.monotonic() - began
        finally:
            self.set_gain(False)
            self.running = False
        return self.result()

    def result(self) -> dict:
        finished = not self.stopped
        return {
            "minutes_off": round(self.seconds[False] / 60.0, 1),
            "minutes_on": round(self.seconds[True] / 60.0, 1),
            "false_off": self.counts[False],
            "false_on": self.counts[True],
            "passed": finished and self.counts[True] <= self.counts[False],
            "stopped": self.stopped or None,
        }

    def status(self) -> dict:
        return {"running": self.running, "block": self.block, "of": self.blocks, **self.result()}
