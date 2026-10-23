from dataclasses import dataclass

FACE_FRESH_S = 10.0
WORD_HOLDS_S = 60.0
UNSEEN_SAY = "I need to see who's asking for that. Say it again where I can see you."
UNSEEN_REASON = "for this you need to see them say it, or hear their family word, and a voice alone is not enough"


@dataclass(frozen=True)
class Proof:
    person_id: str | None = None
    voiced: bool = False
    lips: bool = False
    track: int | None = None


SEEN_SPEAKING = Proof(lips=True)


def shown(person, proof: Proof | None, matched: bool, presence, at: float) -> bool:
    if person is None or proof is None or not proof.lips:
        return False
    if proof.person_id is not None and proof.person_id != person.id:
        return False
    if not matched and not (proof.voiced and proof.person_id == person.id):
        return False
    if person.print_vectors("face"):
        return presence.seen(person.id, at, FACE_FRESH_S)
    return True
