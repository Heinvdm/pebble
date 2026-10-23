import os
import random
import secrets
import sys

import pytest

from pebble.seal import cards as cardlib
from pebble.seal import shamir
from pebble.seal.crypto import Aead, derive
from pebble.seal.errors import CardError, CryptoMissing, DeviceKeyDamaged, SealError
from pebble.seal.keys import FileKeyHolder, SelfKey, default_key_path
from pebble.selfstore import BadSeal


def test_gf256_matches_the_aes_field():
    assert shamir.mul(0x57, 0x83) == 0xC1
    assert shamir.mul(0x57, 0x13) == 0xFE
    for a in range(1, 256):
        assert shamir.mul(a, shamir.div(1, a)) == 1
        assert shamir.div(shamir.mul(a, 0x1F), 0x1F) == a


@pytest.mark.parametrize("pair", [(1, 2), (1, 3), (2, 3), (3, 1)])
def test_any_two_shares_rebuild_the_secret(pair):
    secret = secrets.token_bytes(32)
    coeffs = shamir.coefficients(32)
    shares = {x: shamir.share(secret, coeffs, x) for x in (1, 2, 3)}
    assert shamir.combine([(x, shares[x]) for x in pair]) == secret
    assert shamir.combine([(x, shares[x]) for x in (1, 2, 3)]) == secret


def test_one_share_is_consistent_with_every_possible_secret():
    rng = random.Random(5)
    secret = bytes(rng.randrange(256) for _ in range(32))
    coeffs = bytes(rng.randrange(256) for _ in range(32))
    for x1 in (1, 2, 3):
        y1 = shamir.share(secret, coeffs, x1)
        for _ in range(20):
            candidate = bytes(rng.randrange(256) for _ in range(32))
            forged = bytes(shamir.div(y ^ s, x1) for y, s in zip(y1, candidate))
            assert shamir.share(candidate, forged, x1) == y1
            for x2 in {1, 2, 3} - {x1}:
                y2 = shamir.share(candidate, forged, x2)
                assert shamir.combine([(x1, y1), (x2, y2)]) == candidate


def deck():
    secret = secrets.token_bytes(32)
    coeffs = shamir.coefficients(32)
    set_id = cardlib.new_set_id()
    return secret, coeffs, set_id, cardlib.deal(secret, coeffs, set_id)


def test_cards_print_the_same_every_time_and_parse_back():
    secret, coeffs, set_id, dealt = deck()
    again = cardlib.deal(secret, coeffs, set_id)
    assert [cardlib.render(c) for c in dealt] == [cardlib.render(c) for c in again]
    for card in dealt:
        text = cardlib.render(card)
        assert f"CARD {card.number} OF 3" in text
        assert cardlib.pretty_set(set_id) in text
        assert cardlib.parse(text) == card
    assert cardlib.join([dealt[0], dealt[2]]) == secret


def test_the_parser_ignores_spaces_dashes_and_case():
    _, _, _, dealt = deck()
    code = cardlib.code_of(dealt[1])
    messy = " ".join(code[i:i + 3] for i in range(0, len(code), 3)).lower().replace(" ", " - ", 5)
    assert cardlib.parse(messy) == dealt[1]
    assert cardlib.parse("\n\tcode: " + code[:30] + "\n code:" + code[30:]) == dealt[1]


def test_a_typo_is_caught_by_the_check():
    card = cardlib.Card("PEBBLE23", 2, bytes(range(7, 39)))
    code = cardlib.code_of(card)
    assert cardlib.parse(code) == card
    for index in (0, 9, 20, 40, 63):
        wrong = "B" if code[index] != "B" else "C"
        with pytest.raises(CardError, match="mistyped|does not exist"):
            cardlib.parse(code[:index] + wrong + code[index + 1:])
    with pytest.raises(CardError, match="64"):
        cardlib.parse(code[:-4])
    with pytest.raises(CardError, match="characters"):
        cardlib.parse(code[:-1] + "!")


def test_one_card_or_the_same_card_twice_opens_nothing():
    _, _, _, dealt = deck()
    with pytest.raises(CardError, match="Two different"):
        cardlib.join([dealt[0]])
    with pytest.raises(CardError, match="same card"):
        cardlib.join([dealt[0], dealt[0]])
    _, _, _, other = deck()
    with pytest.raises(CardError, match="different sets"):
        cardlib.join([dealt[0], other[1]])


def test_aead_refuses_a_wrong_key_or_name():
    key = secrets.token_bytes(32)
    blob = Aead(key).seal(b"hello", b"a")
    assert Aead(key).open(blob, b"a") == b"hello"
    with pytest.raises(BadSeal):
        Aead(key).open(blob, b"b")
    with pytest.raises(BadSeal):
        Aead(secrets.token_bytes(32)).open(blob, b"a")
    with pytest.raises(BadSeal):
        Aead(key).open(blob[:-1] + bytes([blob[-1] ^ 1]), b"a")


def test_scrypt_is_deterministic_and_bounded():
    salt = b"s" * 16
    assert derive("pass word", salt, 2**10, 8, 1) == derive("pass word", salt, 2**10, 8, 1)
    assert derive("pass word", salt, 2**10, 8, 1) != derive("pass wore", salt, 2**10, 8, 1)
    with pytest.raises(SealError):
        derive("x", salt, 2**30, 8, 1)


def test_a_missing_cryptography_package_says_how_to_install_it(monkeypatch):
    monkeypatch.setitem(sys.modules, "cryptography.hazmat.primitives.ciphers.aead", None)
    with pytest.raises(CryptoMissing) as raised:
        SelfKey.generate()
    text = str(raised.value)
    assert "pip install" in text and "py3-cryptography" in text and "pkg install python-cryptography" in text


def test_the_key_file_is_made_private_and_reloads(tmp_path):
    holder = FileKeyHolder(tmp_path / "dot-pebble" / "self.key")
    assert holder.load() is None
    key = holder.load_or_create()
    assert len(key) == 32
    assert holder.load() == key
    assert holder.load_or_create() == key
    if os.name == "posix":
        assert holder.path.stat().st_mode & 0o777 == 0o600
    assert not list(holder.path.parent.glob("*.tmp"))
    holder.path.write_text("garbage", encoding="ascii")
    with pytest.raises(DeviceKeyDamaged):
        holder.load()
    assert holder.load_or_create() != key
    holder.delete()
    assert not holder.path.exists()


def test_the_key_path_comes_from_the_flag_then_the_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("PEBBLE_KEY_FILE", str(tmp_path / "env.key"))
    assert default_key_path(tmp_path / "flag.key") == tmp_path / "flag.key"
    assert default_key_path() == tmp_path / "env.key"
    monkeypatch.delenv("PEBBLE_KEY_FILE")
    assert default_key_path().parts[-2:] == (".pebble", "self.key")


def test_a_self_key_never_shows_itself():
    key = SelfKey.generate("pebble")
    assert key.secret().hex() not in repr(key)
    assert key.as_access("cards").access == "cards"
    with pytest.raises(ValueError):
        SelfKey(b"short", "pebble")
    with pytest.raises(ValueError):
        SelfKey(secrets.token_bytes(32), "stranger")
