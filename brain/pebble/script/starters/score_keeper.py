ABOUT = "Keeps score for Alex's game: says each new score as it comes, and the final score at the end."
USES = ["say"]
FOR = "alex"
UNTIL = "3 hours"
WANTS = {"heard": ["me"]}


def on_start():
    keep("scores", {})
    say("I'll keep score. Tell me who scored, like: point to Sam. Say final score when you're done.")


def summary(scores):
    if len(scores) == 0:
        return "Nobody has scored yet."
    parts = []
    for name in sorted(scores.keys()):
        points = scores[name]
        parts.append(f"{name} {points}")
    text = ", ".join(parts)
    return f"Final score: {text}."


def on_heard(who, words):
    said = words.lower().strip(" .!")
    scores = kept("scores", {})
    if "final score" in said or "game over" in said:
        say(summary(scores))
        finish()
        return
    parts = said.split(" ", 2)
    if len(parts) == 3 and parts[0] == "point" and parts[1] in ["to", "for"]:
        name = parts[2]
        scores[name] = scores.get(name, 0) + 1
        keep("scores", scores)
        total = scores[name]
        say(f"Point to {name}! That's {total}.")
