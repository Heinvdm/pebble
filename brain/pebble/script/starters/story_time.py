ABOUT = "Tells Alex a short bedtime story, a line at a time, with a face to match each part."
USES = ["say", "face", "draw"]
FOR = "alex"
UNTIL = "30 minutes"

STORY = [
    ["happy", "Once upon a time, a little robot rolled out to see the garden."],
    ["curious", "It found a snail on a leaf, and stopped to say hello."],
    ["surprised", "The snail said hello back, very slowly."],
    ["love", "They watched the sun go down together."],
    ["sleepy", "Then the robot rolled home to bed. The end."],
]


def on_start():
    draw("a little robot and a snail in a garden at sunset")
    for part in STORY:
        face(part[0])
        say(part[1])
        wait(2)
    say("Goodnight!")
    finish()
