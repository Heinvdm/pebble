ABOUT = "Plays Simon says with Alex: five rounds of actions, some with Simon says and some without."
USES = ["say", "face"]
FOR = "alex"
UNTIL = "20 minutes"

ACTIONS = ["touch your nose", "wave your arms", "spin around", "clap three times", "stand on one leg", "pat your head", "wiggle your fingers"]


def on_start():
    face("happy")
    say("Let's play Simon says! Only do it when I say Simon says.")
    wait(3)
    rounds = 0
    while rounds < 5:
        action = pick(ACTIONS)
        if chance(0.7):
            say(f"Simon says {action}!")
        else:
            face("mischief")
            loud = action[0].upper() + action[1:]
            say(f"{loud}!")
        wait(5)
        rounds += 1
    face("happy")
    say("That's the game! Great playing.")
    finish()
