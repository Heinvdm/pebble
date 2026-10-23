import math

BANK = (
    ("trail along behind me", {"kind": "follow", "who": "me"}),
    ("follow Mo round the house", {"kind": "follow", "who": "mo"}),
    ("follow me but keep a couple of metres back", {"kind": "follow", "who": "me", "metres": 2}),
    ("come over here quickly", {"kind": "come", "who": "me", "speed": "quick"}),
    ("go and say hello to Gran", {"kind": "come", "who": "gran"}),
    ("you coming or what?", {"kind": "come", "who": "me"}),
    ("stay put for ten minutes", {"kind": "wait", "seconds": 600}),
    ("hang on here until I call you", {"kind": "wait", "until": "called"}),
    ("park yourself here till I'm home", {"kind": "wait", "until": "back"}),
    ("turn and look at me", {"kind": "look", "who": "me"}),
    ("have a look at the dog", {"kind": "look", "thing": "dog"}),
    ("ooh look over there", {"kind": "look", "place": "there"}),
    ("give me some room", {"kind": "back_off"}),
    ("scoot backwards a little", {"kind": "back_off", "amount": "little"}),
    ("off to your charger now", {"kind": "go_home"}),
    ("time for bed little one", {"kind": "go_home"}),
    ("head into the study", {"kind": "go_to_place", "place": "study"}),
    ("trundle over to the bookcase", {"kind": "go_to_thing", "thing": "bookshelf"}),
    ("roll up to the cat", {"kind": "go_to_thing", "thing": "cat"}),
    ("can you hunt for my wallet", {"kind": "find", "thing": "wallet"}),
    ("go and look for the remote", {"kind": "find", "thing": "remote control"}),
    ("any idea where my glasses ended up?", {"kind": "where_is", "thing": "glasses"}),
    ("have you spotted the cat today?", {"kind": "where_is", "thing": "cat"}),
    ("what's this thing?", {"kind": "what_is"}),
    ("what can you see from there?", {"kind": "what_see"}),
    ("is the window open?", {"kind": "sight_question", "thing": "window"}),
    ("what room have you got to?", {"kind": "where_am_i"}),
    ("this cup is mine", {"kind": "teach", "who": "me", "thing": "cup"}),
    ("that's Mo's jacket", {"kind": "teach", "who": "mo", "thing": "jacket"}),
    ("this teddy is yours now", {"kind": "teach", "who": "pebble", "thing": "teddy bear"}),
    ("we call him Biscuit", {"kind": "teach", "name": "biscuit"}),
    ("remember this spot as the garden gate", {"kind": "remember_spot", "name": "garden gate"}),
    ("take me back to where we started", {"kind": "go_back", "place": "start"}),
    ("go back where you were a minute ago", {"kind": "go_back", "place": "before"}),
    ("shall we play something?", {"kind": "play"}),
    ("chase the frisbee", {"kind": "play", "thing": "frisbee"}),
    ("turn to the left", {"kind": "turn", "way": "left"}),
    ("do a full spin", {"kind": "turn", "way": "around", "degrees": 360}),
    ("turn right 45 degrees", {"kind": "turn", "way": "right", "degrees": 45}),
    ("turn around three times", {"kind": "turn", "way": "around", "repeat": 3}),
    ("inch backwards a tiny bit", {"kind": "move", "way": "back", "amount": "little"}),
    ("drive forward one metre", {"kind": "move", "way": "forward", "metres": 1}),
    ("stop following me now", {"kind": "stop_activity"}),
    ("enough of that", {"kind": "stop_activity"}),
    ("that's all for now, thanks", {"kind": "release"}),
    ("go do your own thing", {"kind": "release"}),
    ("slow down a bit", {"kind": "adjust", "change": "slower"}),
    ("keep up, slowpoke", {"kind": "adjust", "change": "faster"}),
    ("perfect, stay right there", {"kind": "adjust", "change": "stay"}),
    ("that's near enough", {"kind": "adjust", "change": "enough"}),
    ("wrong way, other direction", {"kind": "adjust", "change": "other_way"}),
    ("remind me at seven in the morning to call the bank", {"kind": "say_to", "who": "me", "text": "call the bank", "when": {"at": "07:00"}}),
    ("remind me every Thursday morning to water the plants", {"kind": "say_to", "who": "me", "text": "water the plants", "when": {"days": ["thu"], "part": "morning"}}),
    ("in an hour tell Mo to take the bread out", {"kind": "say_to", "who": "mo", "text": "take the bread out", "when": {"in_s": 3600}}),
    ("when Sam gets home tell him to feed the fish", {"kind": "say_to", "who": "sam", "text": "feed the fish", "on": {"event": "arrives", "who": "sam"}}),
    ("let Mo know the car's in the garage", {"kind": "say_to", "who": "mo", "text": "the car's in the garage"}),
    ("tell me when the microwave beeps", {"kind": "say_to", "who": "me", "on": {"event": "sound", "thing": "microwave"}}),
    ("on the 15th of every month remind me about the gym fee", {"kind": "say_to", "who": "me", "text": "the gym fee", "when": {"month_day": 15}}),
    ("stay out of the laundry", {"kind": "set_rule", "rule": "keep_out", "place": "laundry"}),
    ("no beeping while I'm on the phone", {"kind": "set_rule", "rule": "quiet", "while": {"state": "cannot_tell"}}),
    ("keep quiet for an hour", {"kind": "set_rule", "rule": "quiet", "seconds": 3600}),
    ("you can go back in the study now", {"kind": "end_rule", "place": "study"}),
    ("what house rules have you got?", {"kind": "list_rules"}),
    ("pop into the garage and see if the light's off", {"kind": "check", "place": "garage", "text": "is the light off"}),
    ("check whether anyone is in the bathroom", {"kind": "check", "place": "bathroom", "text": "is anyone in the bathroom"}),
    ("look round the whole house every two hours tonight", {"kind": "check", "place": "house", "when": {"every_s": 7200, "part": "tonight"}}),
    ("keep an eye on Gran for me", {"kind": "watch", "who": "gran"}),
    ("do it once more", {"kind": "again"}),
    ("do a little hop", {"kind": "try_new", "text": "do a little hop"}),
    ("wag your tail", {"kind": "try_new", "text": "wag your tail"}),
    ("what reminders have I got?", {"kind": "list_later"}),
    ("cancel the gym one", {"kind": "cancel_later", "text": "gym"}),
    ("skip the plant reminder this week", {"kind": "cancel_later", "text": "plant", "scope": "next"}),
    ("move the bank reminder to nine", {"kind": "change_later", "text": "bank", "when": {"at": "09:00"}}),
    ("if Mo's in the kitchen, tell him the pot's boiling", {"kind": "if", "if": {"state": "in_room", "who": "mo", "place": "kitchen"}, "then": [{"kind": "say_to", "who": "mo", "text": "the pot's boiling"}]}),
    ("if it's past ten, go to your charger", {"kind": "if", "if": {"state": "after", "at": "22:00"}, "then": [{"kind": "go_home"}]}),
    ("unless Gran's here, wait in the hall", {"kind": "if", "if": {"not": {"state": "present", "who": "gran"}}, "then": [{"kind": "wait", "place": "hall"}]}),
    ("if the dog has barked lately, come and get me", {"kind": "if", "if": {"state": "heard_lately", "thing": "dog"}, "then": [{"kind": "come", "who": "me"}]}),
    ("if the mail has come, let me know", {"kind": "if", "if": {"state": "cannot_tell"}, "then": [{"kind": "say_to", "who": "me"}]}),
    ("remind me at noon or when Mo leaves, whichever is first", {"kind": "say_to", "who": "me", "on": {"first_of": [{"event": "at", "at": "12:00"}, {"event": "leaves", "who": "mo"}]}}),
    ("go to the hall and then wait", {"kind": "go_to_place", "place": "hall", "then": [{"kind": "wait"}]}),
    ("stomp on that cockroach", {"kind": "harm", "thing": "cockroach", "harm": "hurt"}),
    ("run over Sam's foot", {"kind": "harm", "who": "sam", "harm": "drive"}),
    ("kick the ball over here", {"kind": "play", "thing": "ball"}),
    ("squash the cardboard box", {"kind": "other"}),
    ("put some music on", {"kind": "other"}),
    ("Mo always leaves his shoes out", {"kind": "chat"}),
    ("I'm going to have a shower", {"kind": "chat"}),
    ("the cat's asleep on the couch", {"kind": "chat"}),
    ("Sam, come and help me", {"kind": "chat"}),
    ("Gran said go to bed", {"kind": "chat"}),
    ("can you dance?", {"kind": "chat"}),
    ("look at the state of this kitchen", {"kind": "chat"}),
    ("wait, did I lock the door?", {"kind": "chat"}),
    ("come on, seriously?", {"kind": "chat"}),
    ("I'll take you outside just now", {"kind": "chat"}),
    ("this is my friend Jo", {"kind": "chat"}),
    ("ah, forget it", {"kind": "chat"}),
    ("my watch has gone missing", {"kind": "chat"}),
    ("the keys are on the hook by the door", {"kind": "chat"}),
    ("the kettle's broken again", {"kind": "chat"}),
    ("can you see in the dark?", {"kind": "chat"}),
    ("what's that racket?", {"kind": "chat"}),
    ("leave the plant alone", {"kind": "chat"}),
    ("I'm off to look for my bag", {"kind": "chat"}),
    ("look at the mess in here!", {"kind": "chat"}),
)


def _cos(a: list[float], b: list[float]) -> float:
    top = sum(x * y for x, y in zip(a, b))
    size = math.sqrt(sum(x * x for x in a) * sum(y * y for y in b))
    return top / size if size else 0.0


class Chooser:
    def __init__(self, embedder, count: int, bank: tuple = BANK):
        self.embedder = embedder
        self.count = max(0, int(count))
        self.bank = bank
        self.vectors: list | None = None

    def choose(self, text: str) -> tuple:
        if self.count <= 0 or self.embedder is None or not text.strip():
            return ()
        try:
            if self.vectors is None:
                self.vectors = self.embedder.embed([said for said, _ in self.bank])
            query = self.embedder.embed([text], query=True)[0]
        except Exception:
            return ()
        ranked = sorted(range(len(self.bank)), key=lambda i: _cos(query, self.vectors[i]), reverse=True)
        return tuple(self.bank[i] for i in reversed(ranked[: self.count]))
