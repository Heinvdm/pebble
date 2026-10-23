import re
from dataclasses import dataclass

from .context import Context
from .request import CHAT, MOVING, QUESTIONS, Request
from ..respect import ME as HARM_ME, PERSON as HARM_PERSON, harm_request, word_for
from ..things.facts import FACT_PHRASES
from ..things.words import FAR_PLACES, ROOMS, THING_WORDS, canonical
from .words import FAMILY, GENERIC, HOME_WORDS, ME, NOT_NAMES, NUMBER, PLACE_STOP, PRONOUNS, TITLES, normalise, number

THING_DETERMINERS = ("the", "my", "your", "our", "a", "an", "this", "that", "these", "those", "his", "her", "their", "some", "mums", "dads", "its")
THING_STOP = frozenset({"today", "yesterday", "tonight", "lately", "recently", "before", "earlier", "anymore", "instead", "too", "also", "please", "now", "for", "and", "then", "over", "there", "here", "on", "in", "under", "by", "near", "next", "behind", "beside", "with", "if", "when", "so", "again", "quick", "quickly", "too", "mate", "bro", "boet", "bru", "eh", "around", "round", "is", "are", "was", "thanks", "ok", "okay", "pebble", "at", "from", "to", "real", "slowly", "gently", "carefully", "will", "you", "would", "can", "could", "somewhere", "anywhere", "no", "or", "though", "aye", "yeah", "darling", "love", "buddy"})
ADJECTIVES = frozenset({"new", "old", "big", "little", "small", "tiny", "huge", "red", "blue", "green", "yellow", "black", "white", "pink", "purple", "brown", "grey", "gray", "favourite", "favorite", "other", "nice", "dirty", "clean", "lost", "missing", "good", "best", "spare", "wee", "own", "stupid", "silly", "cute", "fluffy", "furry", "shiny", "striped", "spotty", "orange", "gold", "silver"})
THING_PRONOUNS = frozenset({"it", "that", "this", "that one", "this one", "the thing", "that thing", "this thing"})
PLURAL_PRONOUNS = frozenset({"them", "those", "these"})
HAVE_A = re.compile(r"^have a (?:look|squiz|squizz|gander|peek|geek|nosy|dekko|butchers|proper look|good look|quick look|little look|hunt|go)\b")
NOT_THINGS = frozenset({"news", "film", "movie", "show", "weather", "game", "match", "video", "episode", "results", "score", "time", "latest", "programme", "program", "series", "photos", "pictures", "way", "answer", "problem", "point", "difference", "recipe", "song", "word", "number", "day", "date"})
FIND = re.compile(
    r"^(?:find|look for|looking for|search for|search around for|hunt for|hunt down|look around for|have a look for|have a look around for|sniff out|dig out|dig up|root out|ferret out|turn up|hunt around for|rummage for|rummage around for|poke around for|have a hunt for|have a squiz for|have a squiz around for|go on a hunt for|take a look for|go find|go and find|go look for|go and look for|help me find|help me look for|track down|locate|seek out|search out|spot|go hunt for|scout for|look everywhere for|search the house for|search the room for|see if you can find|try find|try and find|try to find)\b(.*)$"
)
WHERE = re.compile(
    r"^(?:where is|where are|wheres|where is my|where did you see|where did you last see|where was|where were|have you seen|you seen|seen|do you know where|you know where|any idea where|know where|have you spotted|did you see where i left|did you see where i put|did you see|spotted|where has|where have|any sign of|seen any sign of|where did|where would|do you remember where|you remember where|remember where|can you remember where|any clue where)\b(.*)$"
)
WHAT_IS = re.compile(
    r"^(?:what is that|what is this|what is it|what are those|what are these|whats that|whats this|what is that thing|what is this thing|what are you looking at|what do you call that|what do you call this|what do you reckon this is|what do you reckon that is|what do you think that is|what do you think this is|tell me what that is|tell me what this is|what am i holding|what have i got here|what have i got|any idea what this is|any idea what that is|what kind of thing is that|what sort of thing is that|what is in front of me|can you tell what this is|can you tell what that is|do you know what this is|do you know what that is|guess what this is|what is that over there|what is this one|what is that one|what is that you have found|what have you found|what did you find|what would you call this|what would you call that|recognise this|recognise that|recognize this|recognize that|do you recognise this|do you recognise that|do you recognize this|do you recognize that|know what this is|know what that is|what do you think this is called|what is this called|what is that called)\b(.*)$"
)
WHAT_IS_NOT = re.compile(r"^(?:noise|smell|sound|song|music|for|about|mean|supposed|doing|all about|on the telly|on tv|on the radio|you said|word|called again)\b")
WHAT_SEE = re.compile(
    r"^(?:what can you see|what do you see|what are you seeing|what can you spot|tell me what you see|tell me what you can see|tell me what is in front of you|what is in front of you|what is around|what is around you|anything interesting|anything interesting around|see anything|see anything interesting|can you see anything|do you see anything|describe what you see|look around and tell me what you see|what is in view|what is there|whats around|whats in front of you|what are you looking at right now|what else can you see|i spy|describe what you are seeing|describe what you can see|what are you seeing right now|tell me what you are seeing|anything interesting around|anything interesting out there|tell me everything you can see|tell me everything you see|tell me all you can see|what is in the room with you|what is in the room|what is in here|what is near you|what is next to you|what have you got in view)\b(.*)$"
)
IDIOMS = re.compile(r"^(look at the size of|look at the state of|look at the mess|look at you go|look at him go|look at her go|look who|come to think of it|come to mention it|come what may|come rain or shine|come hell or high water|look who is here|look who it is|look at that|look at this|look at the time|wait and see|wait for it|wait till you see|wait until you see|hold that thought|hang in there|come again|how come|look out|watch out|watch it|watch this|look alive|come off it|go figure|go on with you|look here)\b")
INTERJECTION_TAIL = re.compile(r"^(let me|let us|i |i am|i was|i will|i have|i need|i think|i forgot|i just|we |what|where|who|why|how|when|is |are |was |did |do you|does |that is|it is|this is|my |the |oh |actually|sorry|no |yes |you know|um|uh|hmm|really|seriously)")
RETARGET_WORDS = 3
VERB_STARTS = frozenset({"follow", "come", "wait", "stay", "look", "turn", "spin", "go", "back", "move", "give", "head", "tag", "shadow", "face", "watch", "sit", "hang", "hold", "scoot", "reverse", "do", "eyes"})
LATER = re.compile(r"\b(just now|now now|later on|later|tomorrow|tonight|in a while|after (dinner|lunch|breakfast|school|work)|one day|some ?day|next time)\b")
FILLERS = ("ok", "hey", "oi", "um", "uh", "er", "erm", "eh", "oh", "yo", "alright", "so", "well", "please", "now", "and", "but", "hi", "hello", "kindly", "just", "aye", "listen", "yeah", "yes")
COMMA_FILLERS = ("go on", "come on then", "never mind", "nevermind", "actually", "sorry", "oops", "wait no", "no wait", "oh", "um", "uh", "er", "erm", "hmm", "right", "good", "great", "sweet", "sweet as", "lekker", "chur", "mate", "bro", "boet", "bru", "nice", "cool", "perfect", "thanks", "thank you", "cheers", "buddy", "little guy", "my friend", "ag", "hey there", "excellent", "awesome", "brilliant", "good boy", "good girl", "there", "ja", "yes", "no", "lovely", "ka pai", "tino pai")
TAIL_FILLERS = ("please", "mate", "bro", "boet", "bru", "eh", "thanks", "thank you", "now", "ok", "will you", "would you", "yeah", "aye", "hey", "buddy", "lad", "boy", "girl", "my friend", "for me", "right now", "now please", "please now", "too", "as well", "alright", "chop chop", "pronto", "my china", "china", "little guy", "kiddo", "yeah")
POLITE = (
    "would you be able to",
    "could you be able to",
    "are you able to",
    "would it be possible to",
    "is it possible for you to",
    "do you think you could",
    "think you could",
    "any chance you could",
    "any chance you can",
    "switch to",
    "change to",
    "start",
    "begin",
    "go on and",
    "would you mind",
    "do you mind",
    "would you please",
    "could you please",
    "can you please",
    "will you please",
    "could you just",
    "can you just",
    "would you",
    "could you",
    "can you",
    "will you",
    "mind",
    "i need you to",
    "i want you to",
    "i would like you to",
    "i would love you to",
    "i would love it if you would",
    "i would love it if you could",
    "how about you",
    "why do not you",
    "why not",
    "be a dear and",
    "be a love and",
    "be a good boy and",
    "be a good girl and",
    "be a sweetie and",
    "do me a favour and",
    "do us a favour and",
    "you should",
    "you can just",
    "you need to",
    "you must",
    "you have to",
    "you better",
    "you had better",
    "you would better",
    "time to",
    "go on and",
    "go ahead and",
    "try to",
    "try and",
    "please",
    "kindly",
    "just",
    "now",
    "quickly",
    "quick",
)
SUBJECTS = frozenset(
    {
        "i",
        "we",
        "she",
        "he",
        "they",
        "it",
        "my",
        "our",
        "his",
        "their",
        "someone",
        "somebody",
        "everyone",
        "everybody",
        "nobody",
        "people",
        "the",
        "that",
        "this",
        "these",
        "those",
        "your",
        "a",
        "an",
        "what",
        "who",
        "where",
        "when",
        "why",
        "how",
        "which",
        "is",
        "are",
        "was",
        "were",
        "do",
        "does",
        "did",
        "have",
        "has",
        "had",
        "should",
        "shall",
        "may",
        "might",
        "must",
        "if",
        "maybe",
        "perhaps",
        "no",
        "nah",
        "nope",
        "thanks",
        "thank",
        "sorry",
        "bye",
        "goodbye",
        "wow",
        "haha",
        "lol",
        "there",
        "here",
        "dogs",
        "cats",
        "robots",
        "robot",
        "phones",
        "her",
        "him",
        "its",
        "whose",
        "anyone",
        "anybody",
        "doing",
        "being",
        "following",
        "waiting",
        "coming",
        "let",
        "good",
        "nice",
    }
)
INTERJECTIONS = ("hold your horses", "hang on", "hold on", "hold up", "come on", "oh come on", "look here", "look", "wait", "listen", "oh")
LEAD = ("beep beep", "beep", "whoa", "woah", "oh", "ok", "hey", "um", "uh", "er", "erm", "well", "so", "yo", "aw", "ah", "argh", "ugh")
OTHER_VERBS = frozenset({"tell", "draw", "remember", "play", "set", "sing", "show", "switch", "open", "close", "make", "read", "write", "take", "dance", "count", "say", "call", "text", "order", "buy", "check", "help", "fetch", "bring", "put", "pick", "clean", "charge", "find", "send", "start", "teach", "learn", "guess", "beep", "hum", "whistle", "smile", "blink", "wink", "laugh", "record", "film", "photograph", "snap", "paint", "describe", "explain", "list", "note", "save", "forget", "delete", "wake", "light", "dim", "mute", "unmute", "pause", "resume", "skip", "repeat", "spell", "translate", "calculate", "add", "remind", "ring", "email", "message", "google", "search", "lock", "unlock", "feed", "water", "grab", "hand", "pass", "give", "get", "do"})
BODY = frozenset({"face", "eyes", "eye", "hand", "hands", "nose", "head", "mouth", "feet"})
TIMES = re.compile(r"\b(twice|two times|three times|thrice|four times)\b")
TIMES_N = {"twice": 2, "two times": 2, "three times": 3, "thrice": 3, "four times": 4}
GERUNDS = {
    "following": "follow",
    "waiting": "wait",
    "coming": "come",
    "looking": "look",
    "tagging": "tag",
    "backing": "back",
    "going": "go",
    "turning": "turn",
    "staying": "stay",
    "moving": "move",
    "spinning": "spin",
    "shadowing": "shadow",
    "heading": "head",
    "giving": "give",
    "walking": "walk",
    "sticking": "stick",
    "scooting": "scoot",
    "getting": "get",
    "keeping": "keep",
    "hanging": "hang",
    "holding": "hold",
    "sitting": "sit",
    "watching": "watch",
    "facing": "face",
    "reversing": "reverse",
    "rolling": "roll",
    "driving": "drive",
    "trundling": "trundle",
    "charging": "charge",
    "doing": "do",
    "hopping": "hop",
}
DURATION = re.compile(
    rf"\b(?:for )?(?:about |like |around |just )?({NUMBER}) ?(seconds|second|secs|sec|minutes|minute|mins|min|hours|hour|hrs|hr|moments|moment|ticks|tick|jiffy|mo)\b"
)
UNIT_S = {"second": 1, "seconds": 1, "sec": 1, "secs": 1, "minute": 60, "minutes": 60, "min": 60, "mins": 60, "hour": 3600, "hours": 3600, "hr": 3600, "hrs": 3600}
CASUAL = frozenset({"moment", "moments", "tick", "ticks", "jiffy", "mo"})
METRES = re.compile(rf"\b({NUMBER}) ?(metre|m|cm|foot|feet|step|steps)\b")
DEGREES = re.compile(rf"\b({NUMBER}|one eighty|three sixty|a hundred and eighty) ?(degrees|degree|deg)\b")
UNTIL = re.compile(r"\b(?:till|until|unless|before)\b (.*)$")
BACK_WORDS = re.compile(r"\b(i am back|i come back|i get back|i return|i am home|i come home|i get home|we are back|we come back|we get back|we return|i am done|back|return|i finish|i am finished)\b")
CALLED_WORDS = re.compile(r"\b(call|calls|called|say so|said so|tell you|told|whistle|say|ask|shout|send for)\b")
BE_BACK = re.compile(r"\b(i will be back|be right back|back in a|i will come back|i will return|i am going to come back|i will be right back|wait for me|until i return|brb|back soon|be back)\b")
QUICK = re.compile(r"\b(quick|quickly|fast|hurry|hurry up|chop chop|pronto|asap|on the double|hop to it|smartly|as fast as you can|right away|at once|speedy|zoom)\b")
SLOW = re.compile(r"\b(slowly|slow|gently|carefully|take it easy|easy does it|nice and slow|steady|softly|no rush|in your own time)\b")
LITTLE = re.compile(r"\b(a bit|a little|a little bit|a touch|a tad|slightly|a smidge|a wee bit|a fraction|an inch|a few cm|a step|just a bit|a skosh|a wee)\b")
LOT = re.compile(r"\b(a lot|loads|a long way|far|heaps|way)\b")

ADJUST = (
    ("slower", re.compile(r"^(slower|slow it down a bit|slow down|not so fast|too fast|ease up|ease off|steady on|take it easy|easy|easy there|gently|go slower|a bit slower|slower please|slow it down|calm down|whoa there)$")),
    ("faster", re.compile(r"^(faster|speed up|keep up|hurry|hurry up|pick up the pace|quicker|go faster|a bit faster|come on keep up|chop chop|get a move on|step on it|catch up|you are too slow|too slow|move it|keep pace|hop to it|come on keep up|shake a leg|faster faster|quick quick|step it up)$")),
    ("closer", re.compile(r"^(closer|come closer|a bit closer|a little closer|not so far|you are too far|too far away|too far|nearer|come nearer|get closer)$")),
    ("further", re.compile(r"^(not so close|too close|further|further back|further away|a bit further back|a bit further|back off a bit|back off a little|back up a bit|give me (a bit |a little |some )?(more )?(room|space)|stay back a bit|keep your distance|back a bit|a bit back|not that close|stay further back|drop back|fall back|hang back|you are too close|you are crowding me|keep back)$")),
    ("enough", re.compile(r"^(that is far enough|far enough|that will do|that is close enough|close enough|that is good|there you go|that is fine|that is it|that is plenty|right there is fine|this is good|that is near enough|near enough|good enough)$")),
    ("stay", re.compile(r"^(stay there|stay right there|right there|stop there|just there|stay put|stay|good stay there|perfect stay there|stay where you are|stop right there|hold it there|keep there|park there|wait there)$")),
    ("other_way", re.compile(r"^(other way|the other way|wrong way|no the other way|not that way|other direction|the other direction|turn the other way|go the other way|opposite way|the opposite way)$")),
    ("keep_going", re.compile(r"^(keep going|go on|continue|keep it up|carry on following|keep following|keep on|keep at it|keep on going|onwards|go go go|keep coming|keep moving|keep turning|keep looking|keep backing up)$")),
)

FOLLOW = re.compile(
    r"^(?:(?:follow|shadow|tail|chase|go after|run after|chase after|trot after|tag after|trail after|come after|trot along(?: after| behind)?|toddle along(?: after| behind)?|tootle along(?: after| behind)?|scoot along(?: after| behind)?|roll along(?: after| behind)?)(?: after| along| along behind| behind| along after| on after)?|tag along(?: with| behind)?|come (?:along )?with|come along(?: with)?|walk (?:with|alongside|beside|next to|behind)|stick (?:with|close to|by)|stay (?:with|close to|near|by|right by|next to)|keep up with|keep (?:close to|near|by)|go (?:along )?with|trail(?: after)?|heel|this way|come on this way|follow along(?: with| behind)?|keep me company|be my shadow|accompany|escort|walk me)\b(.*)$"
)
COME = re.compile(
    r"^(?:come(?: on)?(?: over)?(?: here| to me| to us| this way| my way| over here| back| back here| closer| find me| get me)?|get (?:over )?here|over here|here|come back to me|come say (?:hi|hello|hey|howzit|kia ora|bye|goodnight|good night)|come and say (?:hi|hello|hey|howzit|kia ora|bye|goodnight|good night)|come (?:and )?(?:see|meet|greet|visit|find|check on|check out|say hi to|say hello to)|run (?:over )?here|hurry (?:over )?here|zoom (?:over )?here|roll (?:on )?over(?: here)?|scoot (?:over )?here|(?:pop|nip|zip|whizz|scoot) back(?: here)?|(?:pop|nip|zip|whizz) over here|trundle (?:over )?here|you coming|are you coming|come to|approach|come towards|head (?:over )?here|bring yourself (?:over )?here|get yourself (?:over )?here|join (?:me|us)|come join (?:me|us)|come hang out(?: with (?:me|us))?|come keep me company)\b(.*)$"
)
WAIT = re.compile(
    r"^(?:wait(?: up| here| there| right here| for me| for us| a bit| a sec| a second| a moment| a minute| on| by| at| near)?|stay(?: here| put| right here| still| where you are| by| at| near| in| behind)?|remain(?: here)?|hang on(?: there| here)?|hold on|hold up|hold your horses|sit tight|stay put|park (?:it|yourself|up|here)|chill(?: here| there| out)?|keep still|be still|stand by|stand still|hang tight|hang about|hang around|hang fire|hang ten|halt there|pause|freeze there|do not go anywhere|do not move|do not wander off|do not run off|do not leave|do not budge|stay where you are|take a seat|have a rest here|rest here|settle(?: down)?(?: here)?|wait and see|hold still|hold fire|hold it|easy now|give me a (?:sec|second|moment|minute|tick)|one (?:sec|second|moment|minute)|just a (?:sec|second|moment|minute|tick))\b(.*)$"
)
LOOK = re.compile(
    r"^(?:look(?: over)?(?: up)?(?: at| towards| over at| over here at| up at| this way at)|eyes on|eyes up|look over here|look this way|look up here|watch|face|turn to face|turn (?:to|towards)|turn and look at|turn and face|turn around and look at|look me in the eye|give me a look|give us a look|check me out|check out|come and look at|come look at|go and look at|go look at|have a (?:look|squiz|squizz|gander|peek|geek|nosy|dekko|butchers|proper look|good look|quick look|little look) at|take a (?:look|peek|squiz|gander) at)\b(.*)$"
)
BACK_OFF = re.compile(
    r"^(?:back off|back up|back away|scoot back|scoot|shoo|go away|get away(?: from me)?|move away(?: from me)?|get out of (?:the|my) way|out of the way|outta the way|give (?:me|us) (?:some |a bit of |a little |a bit |more )*(?:space|room|breathing room)|voetsek|voertsek|fokof|bugger off|buzz off|push off|rack off|nick off|piss off|sod off|hamba|hamba wena|get lost|leave me alone|stop crowding me|quit crowding me|you are crowding me|get out from under(?: my feet)?|out from under(?: my feet)?|out from under foot|get from under my feet|stop getting under my feet|out of my road|stay away(?: from me)?|stay back|make (?:some )?room|clear off|shove off|move along|go on get|off with you|away with you|move it along|get back|back back|move back|step back|go back a bit|reverse away|get outta here|get out of here|begone|scram|skedaddle|vamoose|make way|budge up|move over)\b(.*)$"
)
HOME = re.compile(
    r"^(?:(?:go|head|get|run|toddle|trundle|zoom|off|hop|scoot|roll|time to go|time to head|back)(?: on)?(?: back)?(?: off)?(?: to| into| on| onto)? (?:your |the |to |)*(?:home|bed|sleep|charger|dock|base|charging station|charging spot|charging pad|nest|kennel|night night|nap|pad|beddy byes)|bed ?time|time for (?:bed|sleep|a nap|your nap|night night|beddy byes)|it is (?:bed ?time|time for bed|time to sleep|late)|go (?:and )?(?:charge|recharge|plug in|power up|top up)(?: yourself| up)?|charge (?:yourself|up)|dock yourself|return to (?:your )?(?:base|dock|charger|home)|go to your (?:bed|charger|dock|spot|base)|plug (?:yourself )?in|go plug (?:yourself )?in|lights out|night night|nighty night|go have a (?:nap|rest|sleep|lie down)|go rest|go lie down|go recharge|time to recharge|go get some sleep|get some sleep|off to bed(?: with you)?|sleep time|nap time|go and sleep|go and rest)\b(.*)$"
)
PLACE = re.compile(
    r"^(?:off|go|head|run|drive|roll|trundle|move|get|take yourself|wheel yourself|roll yourself|scoot yourself|make your way|find your way|navigate|travel|scoot|zoom|come|walk|wander|pop|nip|shoot|whizz|zip)(?: on)?(?: over| back| down| up| out| off| along| right)?(?: to| into| in| towards| through to| on to| onto| inside| through| up to| by| near| next to| beside) (.+)$"
)
THERE = re.compile(r"^(?:go |head |run |move |get |scoot |come )?(?:over )?(?:there|yonder|that way|over that way)$")
TURN = re.compile(
    r"^(?:turn|spin|twirl|rotate|swivel|pivot|whirl|do (?:a |an )?(?:little |wee |quick |full |half |quarter |big |small |slow |fast )*(?:spin|twirl|turn|360|three sixty|circle|loop|pirouette|u ?turn|about turn)|do (?:a |an )?(?:180|one eighty|360|three sixty)|hang a (?:left|right|u ?ey|uey)|chuck a (?:left|right|u ?ey|uey)|take a (?:left|right)|do a pirouette|pirouette|about face|about turn|face (?:the )?(?:other way|left|right|around|the wall|away)|u ?turn|look (?:left|right|behind you|around)|go (?:in )?(?:a )?circle|spin yourself around|show me a spin|give us a twirl|give me a spin|give us a spin)\b(.*)$"
)
MOVE = re.compile(
    r"^(?:(?:go|move|come|scoot|roll|drive|inch|shuffle|budge|edge|nudge|step|creep|trundle|get|ease|shift|zoom|wheel)(?: yourself)?(?: a (?:little |wee |tiny )?(?:bit|touch|tad|smidge))?(?: just)? (?:forward|ahead|backwards|back)|move up|scoot up|shuffle up|forward|ahead|backwards|reverse|back up a bit)\b(.*)$"
)
RELEASE = re.compile(
    r"^(?:carry on|as you were|at ease|off you go|you can go(?: now| off)?|you are free(?: to go)?(?: now)?|free to go|you may go|you may leave|you can leave|that is all|that is it for now|that is all for now|that is everything|dismissed|go play|go and play|go do your (?:own )?thing|do your (?:own )?thing|you are done|we are done|all done|you can carry on|carry on then|on your way|run along|go on then|you are off the hook|off duty|you are off duty|free time|go have fun|go explore|go wander|go about your business|back to what you were doing|go back to what you were doing|never mind|nevermind|thanks that is all|thank you that is all|that will be all|you can relax|relax|be free|you are released|i release you|you are dismissed|okay go|go on|go ahead|you can go play|you can wander|wander off|off you pop|you can do what you like|do whatever you like)$"
)
STOP_ACTIVITY = re.compile(
    r"^(?:(?:stop|quit|cease|no more|enough|give up|done|leave off|finish|end|cancel|forget|drop|knock off|cut out|pack in|give over|enough of|stop with|no need for)(?: with| the| your| all| this| that)* (?:following|waiting|looking|coming|turning|moving|backing|spinning|staring|watching|tagging along|tagging|chasing|trailing|shadowing|going|that|it|this|the follow|the wait)|you can stop(?: \w+ing)?(?: now| me| us| her| him| them)?|that is enough (?:following|waiting|looking|turning|spinning|of that|for now|for today)|(?:there is )?no need to (?:follow|wait|come|look|keep)\w*(?: \w+)*|stop following|quit following|no more following|enough waiting|enough following|you do not need to (?:follow|wait|come|look)\w*(?: \w+)*|you do not have to (?:follow|wait|come|look)\w*(?: \w+)*|do not follow me any ?more|stop it|forget it|cancel that|leave it|that is enough|enough now|enough|stop that|quit it|cut it out)\b(.*)$"
)
STOPPING = re.compile(r"^(stop|halt|freeze|whoa|stop stop|stop right now|stop now|stop please|please stop|that is it stop)$")
INDIRECT_COME = re.compile(r"^(?:are you coming|you coming|coming|are you going to come|you going to come)$")
NEGATION = re.compile(r"^(?:do not|never|no need to|you do not need to|you do not have to|you need not|there is no need to|please do not|you should not|you must not|stop|no)\b")
QUESTION = re.compile(r"^(?:do|does|did|are|is|was|were|have|has|had|should|shall|may|might|must|who|what|where|when|why|how|which|whose|whom|am)\b")
STATEMENT_END = re.compile(r"\b(i think|i guess|i reckon|you know|is it|is not it|right\?)$")
GENERIC_REST = re.compile(r"^(?:people|anyone|anybody|strangers|someone|somebody|everyone|everybody|things|humans|others|the dog|the cat|dogs|cats|instructions|orders|rules|directions|the rules|the leader|suit|along with that|through|up on|that|this|it)\b")


@dataclass(frozen=True)
class Parse:
    request: Request
    certain: bool
    cue: bool


def _strip_prefixes(s: str) -> tuple[str, bool]:
    polite = False
    changed = True
    while changed and s:
        changed = False
        for word in COMMA_FILLERS:
            if s.startswith(word + ", ") or s == word + ",":
                s = s[len(word) + 1 :].strip(" ,")
                changed = True
        for word in FILLERS:
            if s == word or s.startswith(word + " ") or s.startswith(word + ", "):
                rest = s[len(word) :].strip(" ,")
                if rest:
                    s = rest
                    changed = True
        for phrase in POLITE:
            if s.startswith(phrase + " ") or s.startswith(phrase + ", "):
                rest = s[len(phrase) :].strip(" ,")
                if rest:
                    s = rest
                    polite = True
                    changed = True
                    break
        for lead in ("go and ", "go ", "you can ", "you may ", "stop and ", "now "):
            if s.startswith(lead) and s[len(lead):].split(" ", 1)[0] in VERB_STARTS - {"go", "back", "do"}:
                s = s[len(lead):]
                polite = True
                changed = True
        if s.startswith("you ") and not re.match(r"^you (are|can|may|do|did|have|had|will|would|could|should|must|need|might|were|was|coming|going|know|see|think|like|look like|seem|sound)\b", s):
            s = s[4:]
            changed = True
    return s, polite


def _strip_tail(s: str) -> str:
    changed = True
    while changed and s:
        changed = False
        s = s.strip(" ,.!?")
        for word in TAIL_FILLERS:
            if s.endswith(" " + word) or s.endswith(", " + word):
                s = s[: -len(word)].strip(" ,")
                changed = True
    return s


def _gerunds(s: str) -> str:
    words = s.split(" ")
    if words and words[0] in GERUNDS:
        words[0] = GERUNDS[words[0]]
    return " ".join(words)


def _seconds(s: str) -> float:
    if re.search(r"\bhalf an hour\b", s):
        return 1800.0
    if re.search(r"\bhalf a minute\b", s):
        return 30.0
    match = DURATION.search(s)
    if match:
        count = number(match.group(1)) or 1.0
        unit = match.group(2)
        if unit in CASUAL:
            return 30.0
        if unit in ("sec", "second", "secs", "seconds") and match.group(1) in ("a", "one", "an") and not re.search(r"\b(one|1) seconds?\b", s.replace("a sec", "")):
            return 30.0
        return count * UNIT_S.get(unit, 1)
    if re.search(r"\b(a while|a bit|a little while)\b", s) and re.search(r"\bwait|stay|hang|hold\b", s):
        return 0.0
    return 0.0


def _metres(s: str) -> float:
    if re.search(r"\bhalf a metre\b", s):
        return 0.5
    match = METRES.search(s)
    if not match:
        return 0.0
    count = number(match.group(1))
    if count is None:
        return 0.0
    unit = match.group(2)
    if unit == "cm":
        return count / 100.0
    if unit in ("foot", "feet"):
        return count * 0.3
    if unit in ("step", "steps"):
        return count * 0.1
    return count


def _degrees(s: str) -> float:
    if re.search(r"\bquarter (turn|way)\b", s):
        return 90.0
    if re.search(r"\bhalf (turn|way around|a turn)\b|\bu ?turn\b|\babout (face|turn)\b", s):
        return 180.0
    if re.search(r"\b(full (turn|circle|spin)|360|three sixty|all the way around|in a circle|a circle)\b", s):
        return 360.0
    if re.search(r"\b(180|one eighty)\b", s) and not DEGREES.search(s):
        return 180.0
    match = DEGREES.search(s)
    if match:
        word = match.group(1)
        if word in ("one eighty", "a hundred and eighty"):
            return 180.0
        if word == "three sixty":
            return 360.0
        return number(word) or 0.0
    return 0.0


def _until(s: str) -> str:
    match = UNTIL.search(s)
    clause = match.group(1) if match else ""
    if clause:
        if CALLED_WORDS.search(clause):
            return "called"
        if BACK_WORDS.search(clause):
            return "back"
    if BE_BACK.search(s):
        return "back"
    return ""


def _speed(s: str) -> str:
    if SLOW.search(s):
        return "slow"
    if QUICK.search(s):
        return "quick"
    return ""


def _amount(s: str) -> str:
    if LITTLE.search(s):
        return "little"
    if LOT.search(s):
        return "lot"
    return ""


def _who(rest: str, ctx: Context) -> str:
    words = [w for w in re.split(r"[\s,]+", rest.strip()) if w]
    known = ctx.known_names()
    index = 0
    while index < len(words) and words[index] in ("tell", "show", "to", "after", "along", "behind", "with", "at", "over", "up", "on", "and", "say", "hi", "hello", "hey", "howzit", "see", "meet", "greet", "find", "visit", "check", "towards", "near", "by", "beside", "next", "kia", "ora", "goodnight", "good", "night", "bye", "close", "right", "out", "just", "quickly", "quick", "please", "around", "the", "my", "our", "your", "dear", "little", "old"):
        if words[index] in ("my", "your") and index + 1 < len(words) and words[index + 1] in BODY:
            return "me"
        if words[index] in ("the", "my", "our", "your") and index + 1 < len(words) and (words[index + 1] in FAMILY or words[index + 1] in known):
            index += 1
            break
        index += 1
    if index >= len(words):
        return ""
    word = words[index]
    if word in ME:
        return "me"
    if word in PRONOUNS:
        return {"she": "her", "he": "him", "they": "them"}.get(word, word)
    if word in TITLES and index + 1 < len(words) and words[index + 1] not in NOT_NAMES:
        return words[index + 1]
    if word in GENERIC:
        return "*generic"
    if word in NOT_NAMES or not word.isalpha():
        return ""
    if word in known or word in FAMILY:
        return word
    return word


def _place(rest: str) -> str:
    words = [w for w in re.split(r"[\s,]+", rest.strip()) if w]
    while words and words[0] in ("the", "my", "our", "your", "to", "into", "in", "by", "near", "at", "next", "beside", "over", "towards", "on", "front", "of"):
        if words[0] == "front" and len(words) > 2 and words[1] == "of":
            words = words[2:]
            continue
        if words[0] == "front" and len(words) > 1 and words[1] in ("door", "gate", "room", "step", "steps", "porch", "garden", "yard"):
            break
        words = words[1:]
    out = []
    for word in words:
        if word in PLACE_STOP or word.endswith("?"):
            break
        out.append(word)
        if len(out) == 2:
            break
    return " ".join(out).strip(" ,.!?")


def _noun_phrase(words: list[str]) -> str:
    out = []
    for word in words:
        if word in THING_STOP or word.endswith("?"):
            break
        out.append(word)
        if len(out) == 4:
            break
    if not out:
        return ""
    while len(out) > 1 and out[0] in ADJECTIVES:
        out = out[1:]
    for size in (4, 3, 2):
        if len(out) >= size and " ".join(out[-size:]) in FACT_PHRASES:
            return " ".join(out[-size:])
    two = " ".join(out[-2:])
    if len(out) >= 2 and two in ROOMS:
        return two
    if len(out) >= 2 and canonical(two) in THING_WORDS:
        return canonical(two)
    if len(out) >= 2 and two in ("plant pot", "water bottle", "teddy bear", "remote control", "tennis ball", "flip flops", "flip flop", "car keys", "house keys", "stuffed toy", "rubbish bin", "hair dryer", "computer mouse", "guinea pig", "pot plant", "potted plant", "lounge suite", "cell phone", "mobile phone", "soccer ball", "rugby ball", "pussy cat", "kitty cat", "dining table", "trash can", "lunch box"):
        return canonical(two)
    if len(out) >= 2 and canonical(out[-1]) not in THING_WORDS and out[-2] not in ADJECTIVES and canonical(out[-2]) not in THING_WORDS:
        return canonical(two)
    if len(out) >= 2 and out[-2] in ("toy", "fish", "christmas", "dog", "cat", "bird", "shoe", "book", "fruit", "bread", "lunch", "pencil", "tool", "coffee", "tea", "kitchen", "bath", "beach", "garden", "baby", "dolls", "rubbish", "laundry", "ironing", "washing", "music", "jewellery", "toolbox"):
        return canonical(two)
    return canonical(out[-1])


def _object(rest: str, ctx: Context, plural_things: bool = False) -> tuple[str, str]:
    cleaned = re.sub(r"^(?:at|to|towards|over to|over at|up to|right up to|after|for|on|over|up)\s+", "", rest.strip())
    cleaned = re.sub(r"^(?:at|to|towards|after|for)\s+", "", cleaned)
    words = [w for w in re.split(r"[\s,]+", cleaned) if w]
    if not words:
        return "", ""
    first = words[0]
    pair = " ".join(words[:2])
    if pair in THING_PRONOUNS or plural_things and first in PLURAL_PRONOUNS:
        return "", "it"
    if first in ("my", "your") and len(words) > 1 and words[1] in BODY:
        return "me", ""
    if first in ("it", "that", "this", "those", "these") and (len(words) == 1 or words[1] in THING_STOP or words[1] in ("one", "thing")):
        return "", "it"
    if first in ME:
        return "me", ""
    if first == "them":
        return "them", ""
    if first in ("her", "him") and (len(words) == 1 or words[1] in THING_STOP):
        return first, ""
    if first in ("her", "his", "their") and len(words) > 1 and words[1] not in THING_STOP:
        return "", _noun_phrase(words[1:])
    if first in THING_DETERMINERS:
        noun = _noun_phrase(words[1:])
        if not noun:
            return "", ""
        if noun in FAMILY or noun in ctx.known_names():
            return noun, ""
        if noun not in THING_WORDS and first == "the" and noun in ROOMS:
            return "", noun
        return "", noun
    if first in ctx.known_names() or first in FAMILY or first in PRONOUNS:
        return _who(cleaned, ctx), ""
    noun = _noun_phrase(words)
    if noun in THING_WORDS:
        return "", noun
    return _who(cleaned, ctx), ""


def _thing_request(kind: str, rest: str, ctx: Context, whole: str) -> Request | None:
    who, thing = _object(rest, ctx)
    if thing and thing not in NOT_THINGS and thing not in ROOMS and thing not in FAR_PLACES:
        return Request(kind, thing=thing, speed=_speed(whole), seconds=_seconds(whole) if kind == "look" else 0.0)
    return None


def _person_or_place(rest: str, ctx: Context) -> tuple[str, str]:
    cleaned = rest.strip()
    who = _who(cleaned, ctx)
    first = re.split(r"[\s,]+", cleaned)[0] if cleaned else ""
    if first in ("the", "your") and who not in FAMILY:
        return "", _place(cleaned)
    if who and who != "*generic" and (who in ME or who in PRONOUNS or who in ctx.known_names() or who in FAMILY or who == "me" or who in ("her", "him", "them")):
        return who, ""
    place = _place(cleaned)
    if place and place in ctx.places:
        return "", place
    if who and who != "*generic" and not place.count(" "):
        return who, ""
    return "", place


def _after_verb(s: str, pattern: re.Pattern) -> str | None:
    match = pattern.match(s)
    if match is None:
        return None
    return match.group(match.lastindex or 0) if match.lastindex else ""


def _running(ctx: Context) -> str:
    return ctx.activity.kind if ctx.activity else ""


ADJUST_TRIM = re.compile(r"^(?:just |even |no |nah |now |ok |yeah |try to |go |get |be |stay |keep |a )+|(?: please| eh| then| now| mate| ok| though| yeah| again| alright| with me| with us| for today| for now| there| though)+$")
ADJUST_INNER = re.compile(r"\b(?:a (?:bit|little|touch|tad|smidge|wee bit|little bit)|just|bit|slightly|even|little)\b ?")
ADJUST_EXTRA = (
    ("slower", re.compile(r"^(?:you are )?(?:going|driving|moving|rolling|zooming) (?:too|a bit|way) (?:fast|quick)$|^slow your roll$|^too fast$|^easy tiger$|^calm your wheels$")),
    ("faster", re.compile(r"^(?:you are )?(?:going|driving|moving|rolling) (?:too|a bit|way) slow(?:ly)?$|^you are falling behind$|^catch me up$")),
    ("other_way", re.compile(r"^(?:you are )?(?:turning|going|heading|driving) (?:the )?wrong way$")),
    ("closer", re.compile(r"^(?:stay|keep|come) (?:a bit |a little )?(?:nearer|closer)(?: to me)?$")),
    ("further", re.compile(r"^give me (?:some |a bit of |a little )?breathing (?:room|space)$|^stop crowding me$|^you are crowding me$")),
    ("stay", re.compile(r"^(?:stay|stop|hold it|keep it) (?:just |right )?(?:like that|like this|there|right there)$")),
    ("enough", re.compile(r"^(?:that is )?(?:a )?good distance$|^(?:yep |yeah )?that will do nicely$")),
    ("further", re.compile(r"^(?:not )?(?:right )?(?:on my heels|under my feet|breathing down my neck|in my space|in my face|crowding me|so near|that near|right behind me)$")),
    ("closer", re.compile(r"^(?:nearer|get nearer|come nearer|closer to me|closer please|stay closer|keep closer)$")),
    ("other_way", re.compile(r"^(?:opposite direction|the opposite direction|reverse direction|wrong direction|back the other way|turn back the other way)$")),
    ("faster", re.compile(r"^(?:keep pace|keep up the pace|keep pace with me|keep up with me|try keep up|go a bit faster|faster)$")),
    ("slower", re.compile(r"^(?:go slower|go slow|slow|slowly|slowly now|not so quick|too quick)$")),
)


def _adjust(s: str, ctx: Context) -> Request | None:
    trimmed = ADJUST_TRIM.sub("", ADJUST_INNER.sub("", s).strip()).strip(" ,") or s
    kind = _running(ctx)
    if kind and kind != "wait" and re.match(r"^(do not stop|do not give up|keep it going|do not quit)\b", s):
        return Request("adjust", change="keep_going")
    for change, pattern in ADJUST_EXTRA:
        if pattern.match(s) or pattern.match(trimmed):
            if kind:
                return Request("adjust", change=change)
            if change == "further":
                return Request("back_off")
            return None
    for change, pattern in ADJUST:
        if pattern.match(s) or pattern.match(trimmed) or (change == "further" and _running(ctx) in ("follow", "come") and re.match(r"^(back off|back up|give me some (room|space)|move back|scoot back)\b", s)):
            kind = _running(ctx)
            if kind:
                if change == "keep_going" and kind == "wait":
                    return Request("release")
                if change in ("stay", "enough") and kind == "wait":
                    return Request("adjust", change=change)
                return Request("adjust", change=change)
            if change == "closer":
                return Request("come", who="me")
            if change == "further":
                return Request("back_off")
            if change == "stay":
                return Request("wait")
            if change == "faster" and (s in ("keep up", "catch up", "keep pace", "keep up with me", "keep pace with me") or trimmed in ("catch up", "keep pace")):
                return Request("follow", who="me")
            return CHAT
    return None


def _wait(rest: str, s: str) -> Request:
    place = ""
    match = re.search(r"\b(?:by|at|near|next to|beside|in|on|outside|inside) (?:the |my |our |your )?([a-z]+(?: [a-z]+)?)", rest)
    if match:
        candidate = _place(match.group(0).split(" ", 1)[1])
        if candidate and candidate not in ("me", "us", "here", "there", "a", "bit", "while") and not candidate.startswith(("a ", "bit", "sec", "minute", "moment", "the meantime", "meantime")):
            place = candidate
    return Request("wait", place=place, seconds=_seconds(s), until=_until(s))


def _clause(s: str, ctx: Context, whole: str) -> Request | None:
    s = _strip_tail(s)
    if not s:
        return None
    s = _gerunds(s)
    adjusted = _adjust(s, ctx)
    if adjusted is not None:
        return adjusted
    if INDIRECT_COME.match(s):
        return Request("come", who="me")
    if RELEASE.match(s):
        kind = _running(ctx)
        if s in ("go on", "go ahead", "okay go") and kind and kind != "wait":
            return Request("adjust", change="keep_going")
        if s in ("go on", "go ahead", "okay go", "never mind", "nevermind", "relax") and not kind:
            return CHAT
        return Request("release")
    rest = _after_verb(s, STOP_ACTIVITY)
    if rest is not None:
        kind = _running(ctx)
        if re.match(r"^(you do not (need|have) to|(there is )?no need to) wait", s) and kind == "wait":
            return Request("release")
        if s in ("stop it", "forget it", "cancel that", "leave it", "that is enough", "enough now", "enough", "stop that", "quit it", "cut it out") and not kind:
            return CHAT
        if not kind and re.match(r"^you do not (need|have) to", s):
            return CHAT
        return Request("stop_activity")
    if NEGATION.match(s):
        rest = _after_verb(s, WAIT) if re.match(r"^do not (go anywhere|move|wander off|run off|leave|budge)", s) else None
        if rest is not None:
            return Request("wait", seconds=_seconds(whole), until=_until(whole))
        return CHAT
    rest = _after_verb(s, HOME)
    if rest is not None:
        return Request("go_home", speed=_speed(whole))
    rest = _after_verb(s, FIND)
    if rest is not None and not re.match(r"^(?:find out|find me a|find me an|find me some)\b", s):
        who, thing = _object(rest, ctx, plural_things=True)
        if thing and thing not in NOT_THINGS and thing not in ROOMS and thing not in FAR_PLACES:
            return Request("find", thing=thing, speed=_speed(whole))
        if who in ("her", "him", "them"):
            return Request("find", who=who, speed=_speed(whole))
        if who and who not in ("*generic",):
            return Request("come", who=who, speed=_speed(whole))
        if not rest.strip():
            return Request("find", thing="it")
        return CHAT if thing in NOT_THINGS else None
    if re.match(r"^(?:find out|find me a|find me an|find me some)\b", s):
        thing = _object(re.sub(r"^(?:find out|find me)\s*", "", s), ctx)[1]
        if thing in THING_WORDS:
            return Request("find", thing=thing)
        return Request("other")
    rest = _after_verb(s, FOLLOW)
    if rest is not None:
        _, followed = _object(rest, ctx)
        if followed and followed not in THING_WORDS and followed != "it":
            return CHAT
        thinged = _thing_request("follow", rest, ctx, whole)
        if thinged is not None:
            return thinged
        if GENERIC_REST.match(rest.strip()):
            return CHAT
        who = _who(rest, ctx) or "me"
        if who == "*generic":
            return CHAT
        return Request("follow", who=who, speed=_speed(whole), metres=_metres(rest))
    rest = _after_verb(s, LOOK)
    if rest is not None and not re.match(r"^(watch|look) (out|it|your step|this space|that|tv|telly|a movie|the news|the time|the tv|the telly|the game|the match|the footy|the rugby|the cricket|the show)\b", s):
        thinged = _thing_request("look", rest, ctx, whole)
        if thinged is not None:
            return thinged
        who = _who(rest, ctx) or "me"
        if who == "*generic":
            return CHAT if s.startswith(("watch", "see")) else Request("look", who="me")
        if s.startswith("see") and not re.match(r"^see me\b", s):
            return None
        return Request("look", who=who, seconds=_seconds(whole))
    if THERE.match(s):
        return Request("go_to_place", place="there")
    rest = _after_verb(s, TURN)
    if rest is not None:
        text = s
        way = ""
        if re.search(r"\bleft\b", text):
            way = "left"
        elif re.search(r"\bright\b", text):
            way = "right"
        elif re.search(r"\b(around|about|other way|away|behind|spin|twirl|360|180|three sixty|one eighty|circle|u ?turn|pirouette|whirl|loop)\b", text):
            way = "around"
        degrees = _degrees(text)
        times = TIMES.search(text)
        if way == "around" and not degrees and re.search(r"\b(spin|twirl|360|three sixty|circle|pirouette|whirl|loop)\b", text) and not re.search(r"\bturn around\b", text):
            degrees = 360.0
        if times and degrees:
            degrees = min(720.0, degrees * TIMES_N[times.group(1)])
        if not way and not degrees:
            if re.search(r"\b(off|on|up|down)\b", text) and re.search(r"\b(the|my|your|it|that|this)\b", text):
                return Request("other")
            return Request("turn", sure=False)
        if re.search(r"\b(the|my|your)\b (?!left|right|other|way)", text) and re.search(r"\b(off|on|up|down)\b", text):
            return Request("other")
        return Request("turn", way=way, degrees=degrees, amount=_amount(text), speed=_speed(whole))
    rest = _after_verb(s, MOVE)
    if rest is not None and not re.match(r"^scoot back\b", s) and (not re.match(r"^(come|go|get|step) (back)\b", s) or _metres(s) or _amount(s)):
        way = "back" if re.search(r"\b(back|backwards|reverse|down)\b", s) else "forward"
        small = re.match(r"^(scoot|inch|edge|nudge|budge|creep|shuffle|ease|step)\b", s) or re.search(r"\bup\b", s)
        return Request("move", way=way, amount=_amount(s) or ("little" if small else ""), metres=_metres(s), speed=_speed(whole))
    rest = _after_verb(s, BACK_OFF)
    if rest is not None and re.match(r"^\s*(?:over )?(?:to|up to|towards|across to)\b", rest):
        rest = None
    if rest is not None:
        metres = _metres(s)
        if metres > 0.25:
            return Request("move", way="back", metres=metres, speed=_speed(whole))
        return Request("back_off", amount=_amount(s), metres=metres)
    rest = _after_verb(s, COME)
    if rest is not None and re.match(r"^\s*(?:to|towards|up to|right up to|by|next to)\s", rest):
        _, aimed = _object(rest, ctx)
        if aimed and aimed not in NOT_THINGS and aimed not in ROOMS and aimed not in FAR_PLACES and aimed not in HOME_WORDS:
            return Request("go_to_thing", thing=aimed, speed=_speed(whole))
    if rest is not None and re.match(r"^come\b", s) and not re.match(r"^come (on|over|here|to|back|closer|find|get|with|along|say|and|see|meet|greet|visit|check|join|hang|keep|this|my|tell|show)\b", s) and rest.strip() and not re.match(r"^(please|now|quick|quickly|then|asap|right now)\b", rest.strip()):
        rest = None
    if rest is not None and re.match(r"^come (?:over )?(?:to|towards|and see|see|up to|over and see)\b", s):
        thinged = _thing_request("go_to_thing", rest, ctx, whole)
        if thinged is not None:
            return thinged
    if rest is not None:
        if s.startswith("come to") or s.startswith("come and see") or s.startswith("come see"):
            who, place = _person_or_place(rest, ctx)
            if place and not who:
                if place in HOME_WORDS:
                    return Request("go_home")
                return Request("go_to_place", place=place)
        who = _who(rest, ctx)
        if who == "*generic":
            return CHAT
        if s.startswith("here") and s != "here" and not re.match(r"^here (please|now|quick|boy|girl)", s):
            return None
        sure = s not in ("here", "come")
        then = ()
        if re.search(r"\b(and )?(say|said) (hi|hello|hey|howzit|kia ora|goodnight|good night|bye)\b", s) and not who:
            who = "me"
        return Request("come", who=who or "me", speed=_speed(whole), sure=sure, then=then)
    rest = _after_verb(s, WAIT)
    if rest is not None:
        if re.match(r"^stay (with|close to) (me|us)\b", s):
            return Request("follow", who="me")
        if re.match(r"^stay (away|back)\b", s):
            return Request("back_off")
        if re.match(r"^(hold on|hang on|hold up|wait) (to|tight to)\b", s):
            return CHAT
        if re.match(r"^(wait|stay) (for|until|till) (the|a|my|your|it|that|dinner|lunch|bus|train)\b", s):
            return CHAT
        return _wait(rest, whole)
    if re.match(r"^(go|run|hurry|pop|nip|scoot)(?: over| and)? (?:say|said) (?:hi|hello|hey|howzit|kia ora|bye|goodnight|good night) to\b", s) or re.match(r"^(go|run|pop|nip)(?: and)? (?:see|greet|visit|meet|check on)\b", s):
        rest = re.sub(r"^(go|run|hurry|pop|nip|scoot)(?: over| and)? (?:say|said|see|greet|visit|meet|check)(?: hi| hello| hey| howzit| kia ora| bye| goodnight| good night| on)?(?: to)?", "", s)
        thinged = _thing_request("go_to_thing", rest, ctx, whole)
        if thinged is not None:
            return thinged
        who = _who(rest, ctx)
        if who and who != "*generic":
            return Request("come", who=who, speed=_speed(whole))
    rest = _after_verb(s, PLACE)
    if rest is not None:
        target = rest.strip()
        if not target or re.match(r"^(away|on|ahead|back|forward|up|down|out|in|inside|outside|around|home)$", target):
            if target == "home":
                return Request("go_home")
            return None
        _, aimed = _object(target, ctx)
        if aimed:
            if aimed in HOME_WORDS or set(aimed.split(" ")) & {"charger", "charging", "dock", "base"}:
                return Request("go_home")
            if aimed in ROOMS or aimed in ctx.places or aimed in FAR_PLACES:
                return Request("go_to_place", place=aimed, speed=_speed(whole))
            if aimed not in NOT_THINGS:
                return Request("go_to_thing", thing=aimed, speed=_speed(whole))
        who, place = _person_or_place(target, ctx)
        if who and not place:
            if re.match(r"^(come|go|head|walk|run|get|scoot|zoom|trundle|roll)(?: on)?(?: over| back)? (to|towards)\b", s):
                return Request("come", who=who, speed=_speed(whole))
            return None
        if place in HOME_WORDS or place.split(" ")[0] in HOME_WORDS:
            return Request("go_home")
        if place in ("there", "over there", "that way", "yonder"):
            return Request("go_to_place", place="there")
        if place:
            if place.split(" ")[0] in NOT_NAMES and place not in ctx.places:
                return None
            return Request("go_to_place", place=place, speed=_speed(whole))
    first = s.split(" ", 1)[0]
    if first in OTHER_VERBS and not re.match(r"^(get|give|do|put|take|find|check|charge|play|show|help) (yourself|over|back|out of|away|me some (space|room)|us some (space|room)|me space|me room|lost)\b", s):
        return Request("other")
    return None


def _split(s: str) -> list[str]:
    s = re.sub(r",? and when you (?:find|see|get to|reach) (?:her|him|it|them|that)\b", " and then", s)
    parts = re.split(r",? (?:and then|then|and after that|after that|and afterwards|afterwards|and also) |, then |, (?:and )?", s)
    return [p.strip() for p in parts if p and p.strip()]


def _interjection(s: str) -> tuple[str, str] | None:
    for word in INTERJECTIONS:
        if s.startswith(word + ", ") or s.startswith(word + "! ") or s.startswith(word + ". ") or s.startswith(word + "? "):
            return word, s[len(word) + 1 :].strip(" ,.!?")
    return None


CORRECTION = re.compile(r"\s(?:no sorry|no wait|wait no|sorry no|no no|actually no|i mean|no i mean|no make that|make that|sorry|no|or rather|scratch that|oh wait|i meant)\s")
SLOT_WORDS = {"left": "way", "right": "way", "forward": "way", "back": "way", "backwards": "way", "around": "way"}


def _correction(s: str, ctx: Context, question: bool) -> Request | None:
    parts = CORRECTION.split(s, maxsplit=1)
    if len(parts) != 2:
        return None
    before, after = parts[0].strip(" ,"), parts[1].strip(" ,")
    first = _sequence(before, ctx, before, question)
    if first is None or not first.action:
        return None
    second = _sequence(after, ctx, after, question)
    if second is not None and second.action:
        return second
    words = after.split(" ")
    head = re.sub(r"^(at|to|the|a|bit|by)\b ?", "", after).strip()
    head_word = head.split(" ")[0] if head else ""
    if words[0] in SLOT_WORDS:
        way = "back" if words[0] == "backwards" else words[0]
        fixed = first.with_(way=way)
        if first.kind == "move" and re.search(r"\b(a bit|a little|bit)\b", after):
            fixed = fixed.with_(amount="little")
        return fixed
    if head_word and (head_word in ctx.known_names() or head_word in FAMILY) and first.kind in ("follow", "come", "look"):
        return first.with_(who=head_word)
    if first.thing and first.thing != "it":
        _, thing = _object(after, ctx)
        if thing and thing not in ("it",):
            return first.with_(thing=thing)
    if head and first.kind in ("go_to_place", "wait") and (head in ctx.places or head.split(" ")[0] in ctx.places):
        rest = _sequence(head, ctx, head, question)
        place = head if head in ctx.places else head.split(" ")[0]
        fixed = first.with_(place=place)
        if rest is not None and rest.action and rest.kind != first.kind:
            return fixed
        tail = re.sub(rf"^{re.escape(place)}\s*(then|and then|and)?\s*", "", head)
        if tail:
            later = _sequence(tail, ctx, tail, question)
            if later is not None and later.action:
                return fixed.with_(then=(later,) + later.then)
        return fixed.with_(then=first.then)
    return None


def _addressed_elsewhere(s: str, ctx: Context) -> bool:
    names = ctx.known_names() - {ctx.name}
    head = _lead(s)
    first = re.match(r"^([a-z]+), ", head)
    if first and first.group(1) in names:
        return True
    spoken_to = re.match(r"^([a-z]+) (?:can you|could you|would you|will you|please|you need to|go and|come and)\s", head)
    if spoken_to and spoken_to.group(1) in names:
        return True
    last = re.search(r", ([a-z]+)$", s)
    return bool(last and last.group(1) in names and last.group(1) not in ("ok", "please"))


def _lead(s: str) -> str:
    changed = True
    while changed:
        changed = False
        for word in LEAD:
            if s.startswith(word + " ") or s.startswith(word + ", "):
                rest = s[len(word) :].strip(" ,")
                if rest and not rest.startswith(("come on", "look")) or (word == "oh" and rest.startswith("come on")):
                    s = rest
                    changed = True
    return s


def _asked(s: str, ctx: Context) -> Request | None:
    s = _strip_tail(s)
    if WHERE_AM_I.match(s.replace(",", "")):
        return Request("where_am_i")
    sight = _sight_question(s)
    if sight is not None:
        return sight
    s = ROOM_ASK.sub(lambda m: ROOM_ASK_AS[next(g for g in m.groups() if g)], s)
    match = WHAT_SEE.match(s)
    if match and (not match.group(1).strip() or re.match(r"^(?:from (?:down |up |over |in )?there|from here|right now|now|at the moment|around|out there|around you|around here|over there|in front of you|here|there|from where you are|today)$", match.group(1).strip())):
        return Request("what_see")
    match = WHAT_IS.match(s)
    if match:
        rest = match.group(1).strip()
        if not rest or not WHAT_IS_NOT.match(rest):
            return Request("what_is") if not rest or re.match(r"^(?:called|over there|there|then|thing|in front of you|right there|you are holding|on the floor|on the table|you have found|you found|you are looking at|you see|you have got|one|thing called)\b", rest) else None
        return CHAT
    topic = re.match(r"^(?:the|my|our) ([a-z ]+?) where (?:is|are|did) (?:he|she|it|they)(?: go)?$", s)
    if topic:
        return Request("where_is", thing=canonical(topic.group(1)))
    match = WHERE.match(s)
    if match:
        rest = match.group(1).strip()
        rest = re.sub(r"^(?:where )?(?:i|we|you|they|he|she) (?:left|put|dropped|had|last saw)\s+", "", rest).strip()
        rest = re.sub(r"\b(?:is|are|went|got to|gone|ended up|be|was|were|get to|go|end up|wander off to|go to)$", "", rest).strip()
        rest = re.sub(r"\s+(?:get to|go to|end up|got to)$", "", rest).strip()
        rest = re.sub(r"\s+(?:is|are|went|got to|gone|ended up|might be|could be)\b.*$", "", rest).strip()
        who, thing = _object(rest, ctx)
        if thing and thing not in NOT_THINGS and thing not in ROOMS and thing not in FAR_PLACES:
            return Request("where_is", thing=thing)
        return CHAT
    return None


def _is_statement(s: str, ctx: Context) -> bool:
    first = s.split(" ", 1)[0] if s else ""
    if re.match(r"^(do (a|an|me|us|not|the|\d)|have a (look|go|peek|squiz|gander|nosy)|let us|let me go|no need|that is enough)\b", s):
        return False
    if first in SUBJECTS:
        return True
    if first in ctx.known_names() and not s.startswith(first + ","):
        return True
    return False


def _single(s: str, ctx: Context, whole: str, question: bool) -> Request | None:
    s = s.strip(" ,.!?")
    if not s:
        return None
    if re.match(r"^(it is |its )?(bed ?time|time for bed|time to sleep|time to go to bed|time for your nap|nap time|sleep time|time to charge|time to recharge|time to go home)\b", s):
        return Request("go_home")
    if re.match(r"^(that is|that will be) (all|it)( for now| thanks| thank you)?$", _strip_tail(s)):
        return Request("release")
    if re.match(r"^(that is|that will do|this is) ", s) or s in ("that will do", "that is enough"):
        adjusted = _adjust(s, ctx)
        if adjusted is not None:
            return adjusted
    if re.match(r"^i am (back|home|here)\b", s) and _running(ctx) == "wait":
        return Request("release")
    stripped, polite = _strip_prefixes(s)
    if not stripped:
        return None
    asked = _asked(stripped, ctx)
    if asked is not None:
        return asked
    retargeted = _retarget(_strip_tail(stripped), ctx)
    if retargeted is not None:
        return retargeted
    if STOPPING.match(stripped):
        return Request("stop_activity") if _running(ctx) else CHAT
    if re.match(r"^(oh )?come on( now| then| mate| really| seriously| man| bro)?$", stripped):
        return CHAT
    adjusted = _adjust(_strip_tail(stripped), ctx)
    if adjusted is not None and adjusted.kind == "adjust":
        return adjusted
    if not polite and question and QUESTION.match(stripped) and not INDIRECT_COME.match(stripped) and not HAVE_A.match(stripped):
        return CHAT
    if not polite and _is_statement(stripped, ctx):
        return CHAT
    request = _clause(stripped, ctx, whole)
    if polite and question and (request is None or request.kind == "other"):
        return CHAT
    return request


ABSTRACT = frozenset({"life", "fault", "turn", "idea", "problem", "job", "chance", "pleasure", "call", "choice", "decision", "night", "week", "stop", "story", "plan", "question", "thing", "mess", "disaster", "joke", "shame", "pity", "surprise", "nightmare", "dream", "luck", "go", "lot", "bit", "favourite", "house", "home", "place", "room", "name", "business", "own", "best", "worst", "first", "last", "one", "fun", "idea", "treat", "secret", "promise", "word", "way"})
NAME_FILLERS = re.compile(r"^(?:um|uh|er|erm|like|just|maybe|well|oh|hmm|it is|its|he is|she is|call him|call her|call it)\b[ ,]*|[ ,]*\b(?:i think|i guess|maybe|probably|now|please|for short|i reckon|i suppose)$")
NAME_LEADS = frozenset({"mr", "mrs", "ms", "miss", "sir", "lady", "captain", "doctor", "dr", "little", "big", "princess", "prince", "king", "queen", "uncle", "auntie", "aunty", "mister", "professor", "lord", "general"})
OWNED = re.compile(r"^(mine|yours|for you|all yours|your one|my one|ours|for me|[a-z]+'s|[a-z]+s)(?: now| to keep| from now on| one)?$")
CALLED = re.compile(r"^(.*?)\b(?:is|are) (?:called|named) (.+)$")
NAME_IS = re.compile(r"^(?:his|her|its|their|the|this ones|the little guys) name is (.+)$")
CALL_IT = re.compile(r"^(?:i am going to|i will|let us|we will|we can|i want to|we are going to|i have|we have|we|i|you can|we shall|i shall|i would like to|we should)? ?(?:call|name|named|called) (?:it|him|her|this|this one|them|this little guy|the [a-z]+) (.+)$")
YOU_HAVE = re.compile(r"^(?:you can have|you may have|have|you can keep|keep|this is a present for you|this is a gift for you|here is a present for you)(?: (.+?))?(?: now| one)?$")
MEET = re.compile(r"^(?:meet|say hi to|say hello to|this is) (.+)$")
SUBJECT = re.compile(r"^(?:this|that|these|those|it|here)(?: one| here| one here| thing| little thing| one there)? (?:is|are) (.+)$")
PLAY_LEAD = r"(?:let us|shall we|should we|can we|could we|will we|want to|do you want to|you want to|would you like to|do you wanna|time to|it is time to|ready to|how about we|why do not we|come|come and|come on let us|go|go and|we can|you can|you could|you may|you go|feel free to|can you|could you|will you|would you|do you want to come|i want to|i wanna|we should|we could)"
PLAY = re.compile(rf"^(?:{PLAY_LEAD} )?play(?: (.+))?$")
PLAY_ALONE = frozenset({"", "a game", "a bit", "for a bit", "for a while", "a while", "together", "with me", "with us", "now", "a little", "for a little bit", "a game with me", "a game with us", "with me for a bit", "with me for a while", "a little bit", "games", "some games", "a game together", "for a minute", "for a few minutes"})
PLAY_GAMES = {"ball": "ball", "fetch": "ball", "catch": "ball", "chase": "", "tag": "", "peekaboo": "", "peek a boo": "", "hide and seek": "", "a game of chase": "", "a game of catch": "ball", "a game of fetch": "ball"}
GAME = re.compile(r"^(?:let us have|let us play|fancy|want|how about|up for|shall we have|do you want|you want|do you fancy|you fancy|want to have|time for|ready for|can we have|could we have|what about|we should have) (?:a |another |a quick |a little )?(game|play|game of (?:chase|catch|fetch|ball|tag|hide and seek|peekaboo|peek a boo)|play date)$")
CHASE = re.compile(r"^(?:go |go and |you |come |let us |can you |could you |will you |you can |)chase (?:after )?(.+)$")
WHERE_AM_I = re.compile(r"^(?:(?:where|whereabouts) (?:are you|are you now|are you at|are you hiding|have you got to|have you gone|did you get to|did you go|did you end up|are you then|are you exactly|you at|have you gone off to|have you got to now)|(?:which|what) (?:room|part of the house) are you in|tell me where you are|where in the house are you|do you know where you are|you know where you are|which room is this|what room is this)(?: (?:right now|right|now|at the moment|exactly|then|buddy|mate|little guy|hiding))*$")
LOOK_THERE = re.compile(r"^(?:look|look at|have a look at|have a look|take a look at|take a look|check out|see|kyk|kyk na|look over at|look out at|look over|look out)(?: at| over| over at)? (?:that|there|over there|that way|over that way|yonder|over yonder|daar|that one|that thing|this way|out there)$|^check (?:that|this) out$|^(?:kyk daar|kyk hier)$")
GO_LOOK_THERE = re.compile(r"^(?:go|go and|go on and) (?:have a look|look|take a look|check|check it out|have a squiz|have a nosy|see)(?: over)? (?:there|over there|that way|yonder|daar)$")
POINT_LEAD = re.compile(r"^(?:ooh|oh|wow|hey|oi|quick|whoa|look|see|aw|aww)[ ,]+")
THERE_WORDS = frozenset({"there", "over there", "that way", "over that way", "yonder", "over yonder", "daar", "out there"})


def _owner_of(words: list[str], ctx: Context) -> tuple[str, list[str]] | None:
    if not words:
        return None
    first = words[0]
    known = ctx.known_names() | FAMILY
    if first in ("my", "mine") and len(words) > 1 and (words[1].endswith("'s") or words[1].endswith("s")):
        base = words[1][:-2] if words[1].endswith("'s") else words[1][:-1]
        if base in FAMILY:
            return base, words[2:]
    if first in ("my", "mine", "me"):
        return "me", words[1:]
    if first in ("your", "yours"):
        return "pebble", words[1:]
    if first.endswith("'s") and first[:-2].isalpha() and first[:-2] not in ("it", "that", "this", "what", "who", "there", "here"):
        return first[:-2], words[1:]
    if first.endswith("s") and first[:-1] in known:
        return first[:-1], words[1:]
    return None


def _taught_thing(words: list[str], ctx: Context) -> str | None:
    if not words:
        return ""
    if words[0] in FAMILY or words[0] in ctx.known_names() or words[0] in ("name", "brother", "sister", "friend"):
        return None
    thing = _noun_phrase(words)
    if not thing or thing in NOT_THINGS or thing in ABSTRACT or thing in ROOMS or thing in FAR_PLACES or thing in FAMILY or thing in ctx.known_names():
        return None
    if thing.split(" ")[0] in FAMILY:
        return None
    return thing


def _name(text: str, ctx: Context) -> str:
    out = text.strip(" ,")
    for _ in range(3):
        out = NAME_FILLERS.sub("", out).strip(" ,")
    words = [w for w in out.split(" ") if w]
    if not words or len(words) > 3 or not all(w.isalpha() for w in words):
        return ""
    if words[0] in ("a", "an", "the", "it", "him", "her", "them", "this", "that", "my", "your", "nothing", "no", "not", "what", "why", "how", "who", "huh", "eh", "dunno", "idk"):
        return ""
    if " ".join(words) in COMMA_FILLERS or " ".join(words) in TAIL_FILLERS or " ".join(words) in FILLERS:
        return ""
    return " ".join(words)


def _owned(body: str, ctx: Context) -> str | None:
    match = OWNED.match(body)
    if match is None:
        return None
    word = match.group(1)
    if word in ("mine", "my one", "for me"):
        return "me"
    if word in ("yours", "for you", "all yours", "your one"):
        return "pebble"
    if word == "ours":
        return None
    if word.endswith("'s"):
        base = word[:-2]
        return base if base.isalpha() else None
    base = word[:-1]
    return base if base in ctx.known_names() or base in FAMILY else None


def _teach_part(part: str, ctx: Context, follow: bool, real: bool = False) -> dict | None:
    match = NAME_IS.match(part)
    if match:
        name = _name(match.group(1), ctx)
        return {"name": name} if name else None
    match = CALL_IT.match(part)
    if match:
        name = _name(match.group(1), ctx)
        return {"name": name} if name else None
    match = CALLED.match(part)
    if match:
        name = _name(match.group(2), ctx)
        if not name:
            return None
        subject = match.group(1).strip()
        slots = {"name": name}
        if subject in ("", "it", "he", "she", "they", "this", "that", "this one", "that one", "this little guy", "this little one", "this guy", "this girl", "this fella", "this one here", "this here"):
            return slots
        words = subject.split(" ")
        owner = _owner_of(words, ctx)
        if owner is not None:
            slots["who"] = owner[0]
            words = owner[1]
        elif words[0] in ("this", "that", "the", "these", "those"):
            words = words[1:]
        else:
            return None
        thing = _taught_thing(words, ctx)
        if thing is None:
            return None
        if thing:
            slots["thing"] = thing
        return slots
    if follow:
        match = re.match(r"^(?:he|she|it|they) (?:is|are) (?:a|an|my|your) (.+)$", part)
        if match:
            thing = _taught_thing(match.group(1).split(" "), ctx)
            return {"thing": thing} if thing else None
        name = _name(part, ctx) if real else ""
        first = part.split(" ")[0]
        if name and first not in VERB_STARTS and first not in OTHER_VERBS and canonical(name) not in THING_WORDS and name not in ctx.known_names():
            return {"name": name}
    match = YOU_HAVE.match(part)
    if match:
        rest = (match.group(1) or "").strip()
        if rest in ("", "this", "that", "it", "this one", "that one", "them", "these", "those"):
            return {"who": "pebble"}
        words = rest.split(" ")
        if words[0] in ("this", "that", "the", "these", "those"):
            thing = _taught_thing(words[1:], ctx)
            return {"who": "pebble", "thing": thing} if thing else None
        return None
    match = re.match(r"^(?:this|that|the|my|your|these|those) ([a-z' ]+?) (?:is|are) (.+)$", part)
    if match and not part.startswith(("this is", "that is", "these are", "those are")) and match.group(1) not in ("one", "here", "one here", "thing", "little thing", "one there"):
        who = _owned(match.group(2), ctx)
        if who is None:
            return None
        subject = part.split(" ")
        if subject[0] in ("my", "your"):
            return None
        thing = _taught_thing(match.group(1).split(" "), ctx)
        if not thing:
            return None
        return {"who": who, "thing": thing}
    match = SUBJECT.match(part)
    if match is None:
        match = MEET.match(part) if part.startswith(("meet ", "say hi to ", "say hello to ")) else None
    if match is None:
        return None
    body = match.group(1).strip()
    if re.match(r"^(?:yours|for you|all yours|your one|your own)(?: now| to keep| from now on)?$", body) or re.match(r"^(?:a present|a gift|a little present|something) for you$", body):
        return {"who": "pebble"}
    if re.match(r"^(?:mine|my one)(?: now)?$", body):
        return {"who": "me"}
    who = _owned(body, ctx)
    if who is not None and " " not in body.strip():
        return {"who": who}
    article = re.match(r"^(?:a|an) (.+)$", body)
    if article:
        thing = _taught_thing(article.group(1).split(" "), ctx)
        return {"thing": thing} if thing else None
    words = body.split(" ")
    owner = _owner_of(words, ctx)
    if owner is not None:
        thing = _taught_thing(owner[1], ctx)
        if thing is None:
            return None
        return {"who": owner[0], "thing": thing} if thing else {"who": owner[0]}
    if len(words) <= 3 and all(w.isalpha() for w in words) and words[0] not in ("the", "a", "an", "so", "not", "very", "really", "too", "just", "what", "how", "why", "where", "when", "all", "it", "no", "fine", "good", "great", "nice", "fun", "true", "wrong", "right"):
        if words[0] in ctx.known_names() or words[0] in FAMILY or len(words) > 2:
            return None
        if canonical(" ".join(words)) in THING_WORDS:
            return {"thing": canonical(" ".join(words))}
        return {"maybe": " ".join(words)}
    return None


def _teach(s: str, ctx: Context) -> Request | None:
    body = re.sub(r"^(?:look|hey|oi|ooh|see|here|aw|aww|oh)[ ,]+", "", s).strip(" ,")
    body = re.sub(r"\b([a-z]+)'s (?=(?:yours|mine|for you|called|named|a |an |all yours|ours)\b)", r"\1 is ", body)
    body = re.sub(r"\b([a-z]+)'s$", lambda m: m.group(0) if m.group(1) not in ("ball", "cup", "mug", "toy") else m.group(1) + " is", body)
    parts = [p.strip() for p in re.split(r"\s*,\s*|\s+and\s+(?=(?:he|she|it|they|his|her|its) )", body) if p.strip()]
    parts = [p for p in parts if p not in COMMA_FILLERS and p not in FILLERS]
    if not parts:
        return None
    found: dict = {}
    for index, part in enumerate(parts):
        slots = _teach_part(part, ctx, index > 0, any(key in found for key in ("who", "thing", "name")))
        if slots is None:
            return None
        for key, value in slots.items():
            found.setdefault(key, value)
    maybe = found.pop("maybe", "")
    if maybe and not found:
        return None
    if maybe and "name" not in found:
        found["name"] = maybe
    if not found:
        return None
    return Request("teach", who=found.get("who", ""), thing=found.get("thing", ""), name=found.get("name", ""))


def _play(s: str, ctx: Context) -> Request | None:
    match = GAME.match(s)
    if match:
        game = match.group(1)
        return Request("play", thing="ball" if any(w in game for w in ("catch", "fetch", "ball")) else "")
    match = CHASE.match(s)
    if match:
        rest = match.group(1).strip()
        if rest in ("me", "us"):
            return Request("play", who="me")
        words = rest.split(" ")
        if words[0] in THING_DETERMINERS:
            words = words[1:]
        thing = _noun_phrase(words) if words else ""
        if not thing or thing in NOT_THINGS or thing in ROOMS or thing in FAMILY or thing in ctx.known_names():
            return None
        return Request("play", thing=thing)
    match = PLAY.match(s)
    if match is None:
        return None
    rest = (match.group(1) or "").strip()
    rest = re.sub(r"\s+(?:for a (?:bit|while|minute|little bit|little while)|a bit|for now|now|together|again|ok|then)$", "", rest).strip()
    lead = s[: match.start(1)].strip() if match.group(1) else s
    if not rest or rest in PLAY_ALONE:
        if ctx.activity is not None and re.match(r"^(?:go|go and|you can|you go|feel free to|off you go and|you may|go on and) play$", lead):
            return Request("release")
        return Request("play")
    if rest in PLAY_GAMES:
        return Request("play", thing=PLAY_GAMES[rest])
    with_ = re.match(r"^with (.+)$", rest)
    if with_ is None:
        return None
    target = with_.group(1).strip()
    if target in ("me", "us", "me for a bit", "us for a bit"):
        return Request("play")
    words = target.split(" ")
    if words[0] in ctx.known_names() or words[0] in FAMILY:
        return Request("play", who=words[0])
    if words[0] in THING_DETERMINERS:
        words = words[1:]
    thing = _noun_phrase(words) if words else ""
    if not thing or thing in NOT_THINGS or thing in ROOMS:
        return None
    return Request("play", thing=thing)


def _pointed(s: str, ctx: Context) -> Request | None:
    if not ctx.pointing:
        return None
    body = s
    for _ in range(2):
        body = POINT_LEAD.sub("", body).strip(" ,") if not LOOK_THERE.match(body) else body
    body = re.sub(r"[ ,]+(?:quick|now|please|mate|buddy)$", "", body)
    if LOOK_THERE.match(body):
        return Request("look", place="there")
    if GO_LOOK_THERE.match(body):
        return Request("go_to_place", place="there")
    return None


REMEMBER_SPOT = re.compile(
    r"^(?:remember|mark|note|save|keep in mind|don't forget|do not forget) (?:this|here|where we are|where we parked|this spot|this place|this position|the spot|the place)(?: (?:spot|place|position))?(?: as (?:the |my |our )?([a-z ]+?))?$"
)
GO_BACK = re.compile(
    r"^(?:(?:take|lead|get|bring) (?:me|us) back(?: to (?:the |my |our )?([a-z ]+?))?|(?:go|head|let us go) back to (?:where we started|the start|the beginning|where we came from|the (car|bike|bus stop|entrance|lift|elevator|stairs|meeting point)|my (car|bike))|(?:go|head) back the way we came)$"
)
START_WORDS = frozenset({"", "where we started", "the start", "the beginning", "start", "beginning", "where we came from"})


def _spots(s: str) -> Request | None:
    match = REMEMBER_SPOT.match(s)
    if match:
        return Request("remember_spot", name=(match.group(1) or "").strip())
    match = GO_BACK.match(s)
    if match:
        named = next((group for group in match.groups() if group), "")
        place = "start" if named in START_WORDS else named.strip()
        if place in ("home", "bed", "charger", "your charger", "dock"):
            return Request("go_home")
        if place in ROOMS:
            return Request("go_to_place", place=place)
        return Request("go_back", place=place or "start")
    return None


def _alive(s: str, ctx: Context) -> Request | None:
    spot = _spots(s)
    if spot is not None:
        return spot
    pointed = _pointed(s, ctx)
    if pointed is not None:
        return pointed
    taught = _teach(s, ctx)
    if taught is not None:
        return taught
    return _play(s, ctx)


OPEN_SHUT = re.compile(
    r"^(?:is|are) (?:the |my |our |that |this )?((?:back |front |side |garage |fridge |oven |bedroom |kitchen |bathroom |sliding |cat |dog )?(?:door|doors|window|windows|gate|light|lights|lamp|oven|tv|telly|stove|hob|tap|taps|fridge|curtains|blinds|cupboard|drawer|lid|heater|fan|iron)) (?:still |left )?(?:open|opened|closed|shut|on|off|locked|running)\b"
)
COLOUR = re.compile(r"^what colou?r (?:is|are|is it|are they) ?(?:this|that|it|these|those|they|the [a-z ]+|my [a-z ]+)?$")
READING = re.compile(
    r"^(?:what does (?:this|that|it|the [a-z ]+) say|what do (?:these|those|they) say|can you read (?:this|that|it|the [a-z ]+)|read (?:this|that|it|the [a-z ]+)(?: (?:for me|out|to me|out loud))*|what does it say|what is written (?:here|there|on (?:this|that|it|the [a-z ]+))|what time does the clock say|what is the time on the clock|what number is (?:this|that|it))$"
)
HOW_MANY = re.compile(r"^how many [a-z ]+? (?:are there|can you see|do you see|are on (?:the )?[a-z ]+|are in (?:the )?[a-z ]+)$")
ANYONE_AT = re.compile(r"^is (?:there )?(?:anyone|anybody|someone|somebody) (?:at|by|outside|on|in front of) (?:the )?(?:door|front door|back door|window|gate)$")


ROOM_ASK = re.compile(r"^(?:(?:has|have) (?:anyone|anybody|someone|somebody|any of you) (seen|spotted)|(?:anyone|anybody) (seen|spotted)|(?:does|do) (?:anyone|anybody|any of you) (know) where|(?:did) (?:anyone|anybody|any of you) (see))\b")
ROOM_ASK_AS = {"seen": "have you seen", "spotted": "have you spotted", "know": "do you know where", "see": "did you see"}


def _sight_question(s: str) -> Request | None:
    match = OPEN_SHUT.match(s)
    if match:
        return Request("sight_question", thing=canonical(match.group(1)) if canonical(match.group(1)) in THING_WORDS else "")
    if COLOUR.match(s) or READING.match(s) or HOW_MANY.match(s) or ANYONE_AT.match(s):
        return Request("sight_question")
    return None


def harmed(text: str, ctx: Context) -> Request | None:
    s = normalise(text, ctx.name).replace("?", "").replace("!", "").strip(" ,.")
    if not s or _addressed_elsewhere(s, ctx):
        return None
    harm = harm_request(text, ctx.known_names() | FAMILY, ctx.life, ctx.name, [line.partition(":")[2] for line in ctx.recent])
    if harm is None:
        return None
    joking = "joking" if harm.joking else ""
    if harm.kind in (HARM_PERSON, HARM_ME):
        return Request("harm", who=harm.target, harm=harm.how, name=joking)
    return Request("harm", thing=word_for(harm), harm=harm.how, name=joking)


def parse(text: str, ctx: Context) -> Parse:
    s = normalise(text, ctx.name)
    question = "?" in s
    s = s.replace("?", "").replace("!", "").strip(" ,.")
    if not s:
        return Parse(CHAT, True, False)
    cue = bool(re.search(r"\b(follow|come|wait|stay|look|back|go|turn|spin|move|stop|here|home|bed|me|charger|dock|scoot|shoo|forward|closer|slower|faster|hold|hang|tag|shadow|carry|free|enough|left|right|around|kitchen|room|voetsek|bugger|away|space)\b", s))
    if _addressed_elsewhere(s, ctx) or re.search(r"\byour own\b", s):
        return Parse(CHAT, True, cue)
    harmful = harmed(text, ctx)
    if harmful is not None:
        return Parse(harmful, True, True)
    if LATER.search(s) and not re.search(r"\b(right now|now now now)\b", s):
        return Parse(CHAT, True, cue)
    s = _lead(s)
    alive = _alive(s, ctx)
    if alive is not None:
        return Parse(alive, True, cue)
    corrected = _correction(s, ctx, question)
    if corrected is not None:
        return Parse(corrected, corrected.sure, cue)
    if IDIOMS.match(s):
        return Parse(CHAT, True, cue)
    bare = re.match(r"^(hold on|hang on|hold up|wait|look|come on|listen) (.+)$", s)
    if bare and INTERJECTION_TAIL.match(bare.group(2)):
        return Parse(CHAT, True, cue)
    head = _interjection(s)
    if head is not None:
        word, rest = head
        if not rest:
            return Parse(_single(word, ctx, s, question) or CHAT, True, cue)
        later = _sequence(rest, ctx, s, question)
        if later is None or not later.action or later.kind in QUESTIONS:
            return Parse(CHAT, True, cue)
        return Parse(later, later.sure, cue)
    request = _sequence(s, ctx, s, question)
    if request is None:
        return Parse(CHAT, False, cue)
    return Parse(request, request.sure if request.action else True, cue)


def _sequence(s: str, ctx: Context, whole: str, question: bool) -> Request | None:
    single = _single(s, ctx, whole, question)
    if single is not None and single.action and not re.search(r",|\b(and|then)\b", s) and len(_runon(s, ctx, whole, question)) <= 1:
        return single
    parts = []
    for part in _split(s):
        if part in COMMA_FILLERS or part in FILLERS:
            continue
        runon = _runon(part, ctx, whole, question)
        if len(runon) > 1 or runon != [part]:
            parts.extend(runon)
            continue
        pieces = [p.strip() for p in re.split(r" and ", part) if p.strip()]
        if len(pieces) > 1:
            readings = [_single(p, ctx, whole, question) for p in pieces]
            if sum(1 for r in readings if r is not None and r.action) >= 2:
                parts.extend(pieces)
                continue
        parts.append(part)
    if len(parts) == 1 and parts[0] != s:
        return _single(parts[0], ctx, whole, question)
    if len(parts) <= 1:
        return single
    steps = [r for r in (_single(p, ctx, whole, question) for p in parts) if r is not None]
    actions = [r for r in steps if r.action]
    if not actions:
        if single is not None:
            return single
        return CHAT if steps else None
    if single is not None and single.action and len(actions) == 1 and single.kind == actions[0].kind:
        return single
    merged = _merge(actions, bool(re.search(r"\b(again|twice|another|more)\b", whole)))
    first, rest = merged[0], merged[1:]
    return first.with_(then=tuple(rest))


def _statement_noun(text: str) -> str:
    words = re.findall(r"[a-z]+", text)
    for index in range(len(words) - 1, -1, -1):
        for size in (2, 1):
            if index - size + 1 >= 0:
                phrase = canonical(" ".join(words[index - size + 1 : index + 1]))
                if phrase in THING_WORDS:
                    return phrase
    return ""


def _retarget(s: str, ctx: Context) -> Request | None:
    if ctx.activity is None or ctx.activity.kind not in ("go_to_thing", "find", "look", "follow"):
        return None
    match = re.match(r"^(?:no |wait |actually |sorry |i mean |oh |not that one |not that )*(?:the|my|that|this) ([a-z ]+?)(?: instead| please| then)?$", s)
    if match is None or len(match.group(1).split()) > RETARGET_WORDS:
        return None
    thing = _noun_phrase(match.group(1).split(" "))
    if not thing or thing in NOT_THINGS:
        return None
    if ctx.activity.kind in ("look", "follow") and thing in ctx.known_names():
        return Request(ctx.activity.kind, who=thing)
    return Request(ctx.activity.kind, thing=thing)


def _runon(part: str, ctx: Context, whole: str, question: bool) -> list[str]:
    words = part.split(" ")
    for index in range(1, len(words)):
        if words[index] not in VERB_STARTS or words[index - 1] in ("and", "then", "to", "you", "i", "not", "please", "my", "your", "the", "a", "his", "her", "our", "their", "go"):
            continue
        left, right = " ".join(words[:index]), " ".join(words[index:])
        first = _single(left, ctx, whole, question)
        second = _single(right, ctx, whole, question)
        if first is not None and first.action and second is not None and second.action:
            return [left] + _runon(right, ctx, whole, question)
        if second is not None and second.action and re.match(r"^(?:ok |okay |right )?(?:forget|never mind|not|leave) (?:the|my|that|it)\b", left):
            return _runon(right, ctx, whole, question)
    asking = re.search(r"\s(can you|could you|would you|will you|please)\s", part)
    if asking:
        left, right = part[: asking.start()].strip(), part[asking.start() :].strip()
        later = _single(right, ctx, whole, question)
        if left and later is not None and later.action and _is_statement(left, ctx):
            noun = _statement_noun(left)
            if noun and re.search(r"\b(her|him|it|them)$", right):
                right = re.sub(r"\b(her|him|it|them)$", f"the {noun}", right)
            return [right]
    return [part]


def _merge(actions: list[Request], again: bool = False) -> list[Request]:
    out: list[Request] = []
    for step in actions:
        if out and step == out[-1] and not again:
            continue
        if out and step.kind == out[-1].kind and step.kind in ("wait", "come", "follow", "go_home"):
            prior = out[-1]
            out[-1] = prior.with_(
                seconds=prior.seconds or step.seconds,
                until=prior.until or step.until,
                place=prior.place or step.place,
                who=prior.who if prior.who and prior.who != "me" else (step.who or prior.who),
                speed=prior.speed or step.speed,
            )
            continue
        if out and step.kind == "adjust" and out[-1].kind == "adjust":
            continue
        out.append(step)
    return out


def understood(text: str, ctx: Context) -> Request:
    return parse(text, ctx).request


def moving(request: Request) -> bool:
    return request.kind in MOVING
