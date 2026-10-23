ABOUT = "At six in the evening asks Alex how the day was, listens to the answer, and keeps it to itself."
USES = ["ask", "say"]
FOR = "alex"
UNTIL = "21:00"
WANTS = {"at": ["18:00"]}


def on_at(time):
    answer = ask("me", "How was your day?", wait=60)
    if answer is None:
        return
    said = answer.lower()
    if "good" in said or "great" in said or "fun" in said:
        say("I'm glad!")
    elif "bad" in said or "awful" in said or "tired" in said:
        say("Oh no. I hope tomorrow is kinder.")
    else:
        say("Thanks for telling me.")
    finish()
