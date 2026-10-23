import time

import pytest

from pebble.house import qr

LEVEL_BITS = {1: "L", 0: "M", 3: "Q", 2: "H"}
FINDER = ["1111111", "1000001", "1011101", "1011101", "1011101", "1000001", "1111111"]


def sample(length: int) -> str:
    return "".join(chr(33 + (i * 7) % 90) for i in range(length))


def render(rows: list[str], px: int):
    np = pytest.importorskip("numpy")
    n = len(rows)
    dark = np.array([[ch == "1" for ch in row] for row in rows])
    image = np.full((n + 8, n + 8), 255, np.uint8)
    image[4:4 + n, 4:4 + n][dark] = 0
    return np.repeat(np.repeat(image, px, axis=0), px, axis=1)


def decode(rows: list[str], px: int = 8) -> str:
    cv2 = pytest.importorskip("cv2")
    image = render(rows, px)
    text, _, _ = cv2.QRCodeDetector().detectAndDecode(image)
    if not text and hasattr(cv2, "QRCodeDetectorAruco"):
        text, _, _ = cv2.QRCodeDetectorAruco().detectAndDecode(image)
    return text


def remainder(value: int, divisor: int) -> int:
    while value.bit_length() >= divisor.bit_length():
        value ^= divisor << (value.bit_length() - divisor.bit_length())
    return value


def read_bits(rows: list[str], cells: list[tuple[int, int]]) -> int:
    return sum(int(rows[r][c]) << i for i, (r, c) in enumerate(cells))


def format_word(rows: list[str]) -> tuple[int, int]:
    n = len(rows)
    first = [(i, 8) for i in range(6)] + [(7, 8), (8, 8), (8, 7)] + [(8, 14 - i) for i in range(9, 15)]
    second = [(8, n - 1 - i) for i in range(8)] + [(n - 15 + i, 8) for i in range(8, 15)]
    return read_bits(rows, first), read_bits(rows, second)


def test_hello_at_m_is_version_1_with_21_rows():
    rows = qr.encode("HELLO")
    assert len(rows) == 21
    assert all(len(row) == 21 and set(row) <= {"0", "1"} for row in rows)


def test_the_smallest_version_that_fits_is_used():
    assert len(qr.encode("x" * 14)) == 21
    assert len(qr.encode("x" * 15)) == 25
    assert len(qr.encode("x" * 17, "L")) == 21
    assert len(qr.encode("x" * 8, "H")) == 25
    assert len(qr.encode("é" * 7)) == 21
    assert len(qr.encode("é" * 8)) == 25
    assert len(qr.encode("x" * 213)) == 57
    assert len(qr.encode("x" * 214)) == 61


def test_capacity_matches_the_standard_tables():
    assert [qr.capacity(level, 1) for level in "LMQH"] == [17, 14, 11, 7]
    assert [qr.capacity(level, 7) for level in "LMQH"] == [154, 122, 86, 64]
    assert [qr.capacity(level, 10) for level in "LMQH"] == [271, 213, 151, 119]
    assert [qr.capacity(level, 20) for level in "LMQH"] == [858, 666, 482, 382]
    assert [qr.capacity(level) for level in "LMQH"] == [2953, 2331, 1663, 1273]
    assert qr.capacity() == 2331
    assert qr.capacity("m", 2) == 26
    with pytest.raises(ValueError):
        qr.capacity("M", 41)
    with pytest.raises(ValueError):
        qr.capacity("X")


def test_finders_timing_and_the_dark_module_are_in_place():
    rows = qr.encode("Kia ora", "Q")
    n = len(rows)
    for top, left in ((0, 0), (0, n - 7), (n - 7, 0)):
        assert [rows[top + i][left:left + 7] for i in range(7)] == FINDER
    timing = "".join("1" if i % 2 == 0 else "0" for i in range(8, n - 8))
    assert rows[6][8:n - 8] == timing
    assert "".join(rows[r][6] for r in range(8, n - 8)) == timing
    assert rows[n - 8][8] == "1"


@pytest.mark.parametrize("level", "LMQH")
def test_format_information_names_the_level_and_is_a_valid_code_word(level):
    rows = qr.encode("format check", level)
    first, second = format_word(rows)
    assert first == second
    word = first ^ 0x5412
    assert remainder(word, 0x537) == 0
    assert LEVEL_BITS[word >> 13] == level


def test_version_information_is_written_from_version_7():
    rows = qr.encode(sample(qr.capacity("M", 7)), "M")
    n = len(rows)
    assert n == 45
    top_right = read_bits(rows, [(i // 3, n - 11 + i % 3) for i in range(18)])
    bottom_left = read_bits(rows, [(n - 11 + i % 3, i // 3) for i in range(18)])
    assert top_right == bottom_left
    assert top_right >> 12 == 7
    assert remainder(top_right, 0x1F25) == 0


@pytest.mark.parametrize("version", [1, 2, 7, 10, 20, 32])
@pytest.mark.parametrize("level", "LMQH")
def test_full_codes_scan_back_at_every_level(version, level):
    text = sample(qr.capacity(level, version))
    rows = qr.encode(text, level)
    assert len(rows) == 4 * version + 17
    assert decode(rows) == text


def test_the_biggest_code_scans_back():
    text = sample(qr.capacity("L", 40))
    rows = qr.encode(text, "L")
    assert len(rows) == 177
    assert decode(rows) == text


@pytest.mark.parametrize("text", ["Kia ora, café", "Tēnā koutou, ngā mihi — 你好 — Привет ☕ " * 6])
def test_utf8_text_scans_back(text):
    assert decode(qr.encode(text)) == text


def test_wifi_payload_escapes_special_characters_and_scans():
    text = qr.wifi('Kiwi "Home";5G', 'pa:ss,wo\\rd;"x"')
    assert text == r'WIFI:T:WPA;S:Kiwi \"Home\"\;5G;P:pa\:ss\,wo\\rd\;\"x\";;'
    assert decode(qr.encode(text)) == text


def test_wifi_payload_options():
    assert qr.wifi("Guests", "secret", hidden=True) == "WIFI:T:WPA;S:Guests;P:secret;H:true;;"
    assert qr.wifi("Open Cafe", "ignored", security="nopass") == "WIFI:T:nopass;S:Open Cafe;;"
    assert qr.wifi("Shed", "pw", security="wep") == "WIFI:T:WEP;S:Shed;P:pw;;"


def test_parts_leaves_a_text_that_fits_alone():
    assert qr.parts("Milk\nEggs") == ["Milk\nEggs"]
    exact = "y" * 600
    assert qr.parts(exact) == [exact]
    assert qr.parts("") == [""]


def test_parts_splits_a_long_list_at_line_ends():
    lines = [f"Item number {i}: something from the shop" for i in range(60)]
    text = "\n".join(lines)
    pieces = qr.parts(text)
    assert len(pieces) == 5
    assert all(len(piece.encode("utf-8")) <= 600 for piece in pieces)
    bodies = []
    for i, piece in enumerate(pieces, 1):
        prefix = f"({i}/{len(pieces)}) "
        assert piece.startswith(prefix)
        bodies.append(piece[len(prefix):])
    assert all(set(body.split("\n")) <= set(lines) for body in bodies)
    assert "\n".join(bodies) == text


def test_parts_cuts_one_long_line_at_spaces_and_never_inside_a_character():
    words = " ".join(f"word{i}" for i in range(400))
    pieces = qr.parts(words, limit=200)
    assert all(len(piece.encode("utf-8")) <= 200 for piece in pieces)
    assert " ".join(piece.split(" ", 1)[1] for piece in pieces) == words
    long_vowels = "ā" * 1000
    pieces = qr.parts(long_vowels, limit=300)
    assert all(len(piece.encode("utf-8")) <= 300 for piece in pieces)
    assert "".join(piece.split(" ", 1)[1] for piece in pieces) == long_vowels


def test_parts_with_ten_or_more_pieces_still_fit():
    pieces = qr.parts("word " * 2000, limit=100)
    assert len(pieces) >= 10
    assert pieces[0].startswith(f"(1/{len(pieces)}) ")
    assert all(len(piece.encode("utf-8")) <= 100 for piece in pieces)


def test_parts_refuses_a_limit_too_small_for_the_numbering():
    with pytest.raises(ValueError):
        qr.parts("x" * 50, limit=10)


def test_too_long_is_a_value_error_past_version_40():
    assert len(qr.encode("x" * 2331)) == 177
    with pytest.raises(qr.TooLong):
        qr.encode("x" * 2332)
    with pytest.raises(ValueError):
        qr.encode("x" * 2954, "L")
    with pytest.raises(qr.TooLong):
        qr.encode("é" * 1200)
    with pytest.raises(ValueError):
        qr.encode("hi", "X")


def test_a_600_byte_payload_encodes_well_under_half_a_second():
    text = sample(600)
    qr.encode(text)
    best = 1.0
    for _ in range(3):
        began = time.perf_counter()
        rows = qr.encode(text)
        best = min(best, time.perf_counter() - began)
    assert len(rows) == 93
    assert best < 0.5
