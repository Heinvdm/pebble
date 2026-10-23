ABOUT = "At eight each evening has a look round the house and notes how it went in my journal."
USES = ["do"]
UNTIL = "ongoing"
WANTS = {"at": ["20:00"]}


def on_at(time):
    went = do("check the house")
    rounds = kept("rounds", 0) + 1
    keep("rounds", rounds)
    if went == "done":
        note(f"Evening look round number {rounds}: all done.")
    else:
        note(f"Evening look round number {rounds}: {went}.")
