ABOUT = "Plays tag with my ball for Alex: on go I chase the ball, and I say the score when Alex has had enough."
USES = ["do", "say", "face"]
FOR = "alex"
UNTIL = "30 minutes"
WANTS = {"heard": ["me"]}


def on_start():
    keep("tags", 0)
    say("Let's play tag with my ball! Say go and I'll chase it. Say that's enough when you're done.")


def on_heard(who, words):
    said = words.lower().replace("!", " ").replace(".", " ").replace(",", " ")
    if "enough" in said:
        tags = kept("tags", 0)
        face("happy")
        say(f"Good game! I tagged the ball {tags} times.")
        finish()
    elif "go" in said.split():
        went = do("go to the ball")
        if went == "done":
            tags = kept("tags", 0) + 1
            keep("tags", tags)
            face("happy")
            say(f"Tag! That's {tags}.")
        else:
            face("curious")
            say("Hmm, I lost the ball. Say go to try again.")
