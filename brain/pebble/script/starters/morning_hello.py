ABOUT = "Every morning says hello to whoever is up first, and mentions a coat if it has been raining."
USES = ["say", "look"]
UNTIL = "ongoing"
WANTS = {"arrives": ["anyone"]}


def on_arrives(who):
    if kept("greeted", "") == today():
        return
    hour = now()
    if hour < "05:00" or hour > "11:00":
        return
    keep("greeted", today())
    if state("heard_lately", "rain") == True:
        say(f"Good morning, {who}! I heard rain, so a coat might be handy.")
    else:
        say(f"Good morning, {who}!")
