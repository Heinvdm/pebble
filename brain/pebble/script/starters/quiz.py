ABOUT = "Asks Alex five quiz questions, listens to each answer and says the score at the end."
USES = ["ask", "say", "face"]
FOR = "alex"
UNTIL = "30 minutes"

QUESTIONS = [
    ["How many legs does a spider have?", "8", "eight"],
    ["What colour do you get when you mix blue and yellow?", "green"],
    ["What is the biggest planet?", "jupiter"],
    ["How many days are in a week?", "7", "seven"],
    ["What do bees make?", "honey"],
]


def right(answer, good):
    said = answer.lower()
    for word in good:
        if word in said:
            return True
    return False


def on_start():
    say("Quiz time! Five questions.")
    score = 0
    for item in QUESTIONS:
        answer = ask("me", item[0], wait=30)
        if answer is None:
            say("No answer? Let's stop there.")
            break
        if right(answer, item[1:]):
            score += 1
            face("happy")
            say("That's right!")
        else:
            best = item[1]
            say(f"Not quite. It was {best}.")
    face("love")
    say(f"You got {score} out of 5.")
    finish()
