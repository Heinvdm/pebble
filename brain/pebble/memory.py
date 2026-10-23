FACT_CAP = 300
TEXT_MAX = 200


class MemoryBook:
    def __init__(self, data: dict, cap: int = FACT_CAP):
        self.facts: list[dict] = [f for f in (data.get("facts") or []) if isinstance(f, dict) and f.get("text")]
        self.cap = cap
        self.on_remember = lambda fact, new: None

    def remember(self, text: str, at: str, about: str | None = None) -> dict:
        text = " ".join(text.split())[:TEXT_MAX]
        about = (about or "").strip()[:40] or None
        for fact in self.facts:
            if fact["text"].lower() == text.lower():
                fact["at"] = at
                fact["times"] = int(fact.get("times", 1)) + 1
                self.on_remember(fact, False)
                return fact
        fact = {"text": text, "about": about, "at": at, "times": 1}
        self.facts.append(fact)
        if len(self.facts) > self.cap:
            pinned = [f for f in self.facts if f.get("pinned")]
            loose = [f for f in self.facts if not f.get("pinned")]
            self.facts = pinned + loose[len(self.facts) - self.cap :]
        self.on_remember(fact, True)
        return fact

    def recent(self, count: int = 10) -> list[dict]:
        return self.facts[-count:]

    def search(self, words: str, limit: int = 10) -> list[dict]:
        terms = [w for w in words.lower().split() if len(w) > 2]
        if not terms:
            return []
        hits = [f for f in self.facts if any(t in f["text"].lower() or t in (f.get("about") or "").lower() for t in terms)]
        return hits[-limit:]

    def to_dict(self) -> dict:
        return {"format": 1, "facts": self.facts}
