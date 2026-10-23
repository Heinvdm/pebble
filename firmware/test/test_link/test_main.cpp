#include <string.h>
#include <unity.h>

#include "link_guard.h"
#include "pairing.h"
#include "protocol.h"
#include "sha256.h"
#include "text_writer.h"

using namespace pebble;

void setUp() {}
void tearDown() {}

namespace {

constexpr const char* kPhoneNonce = "00112233445566778899aabbccddeeff";
constexpr const char* kBodyNonceHex = "101112131415161718191a1b1c1d1e1f";
constexpr const char* kSessionHex = "c82d126ebaee9f5d482d4a5dcde628f8d8cc33521014ec866e80af85a0f61cf1";
constexpr const char* kBodyProof = "56ca065c618e088268640dc2628ad4c3";
constexpr const char* kPhoneProof = "5c97f3affe363f31e642b9d4d9dd7568";

LinkSecret secret() {
  LinkSecret s;
  s.present = true;
  for (size_t i = 0; i < LinkSecret::kSize; ++i) s.key[i] = static_cast<uint8_t>(i);
  return s;
}

void bodyNonce(uint8_t out[LinkGuard::kNonceSize]) {
  for (size_t i = 0; i < LinkGuard::kNonceSize; ++i) out[i] = static_cast<uint8_t>(16 + i);
}

void digestHex(const uint8_t* digest, char* out) { toHex(digest, Sha256::kDigestSize, out); }

void proveGuard(LinkGuard& g, uint32_t now) {
  uint8_t nonce[LinkGuard::kNonceSize];
  bodyNonce(nonce);
  char buf[128];
  TextWriter w(buf, sizeof(buf));
  TEST_ASSERT_TRUE(g.challenge(secret(), kPhoneNonce, nonce, w));
  TEST_ASSERT_TRUE(g.verify(kPhoneProof));
  g.commit(now);
  TEST_ASSERT_TRUE(g.proven());
}

}

static void test_sha256_vectors() {
  uint8_t d[32];
  char hex[65];
  Sha256 a;
  a.update("abc", 3);
  a.finish(d);
  digestHex(d, hex);
  TEST_ASSERT_EQUAL_STRING("ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad", hex);
  Sha256 b;
  const char* two = "abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq";
  b.update(two, strlen(two));
  b.finish(d);
  digestHex(d, hex);
  TEST_ASSERT_EQUAL_STRING("248d6a61d20638b8e5c026930c3e6039a33ce45964ff2167f6ecedd419db06c1", hex);
}

static void test_hmac_vectors() {
  uint8_t key[131];
  uint8_t d[32];
  char hex[65];
  memset(key, 0x0b, 20);
  HmacSha256 one(key, 20);
  one.update("Hi There");
  one.finish(d);
  digestHex(d, hex);
  TEST_ASSERT_EQUAL_STRING("b0344c61d8db38535ca8afceaf0bf12b881dc200c9833da726e9376c2e32cff7", hex);
  memset(key, 0xaa, sizeof(key));
  HmacSha256 two(key, sizeof(key));
  two.update("Test Using Larger Than Block-Size Key - Hash Key First");
  two.finish(d);
  digestHex(d, hex);
  TEST_ASSERT_EQUAL_STRING("60e431591ee0b67f0d8a26aacbf5b77f8e0bc6213728c5140546040f0ee37f54", hex);
}

static void test_hex_round_trip() {
  uint8_t bytes[4];
  TEST_ASSERT_TRUE(fromHex("0aFf10c3", 8, bytes, 4));
  char hex[9];
  toHex(bytes, 4, hex);
  TEST_ASSERT_EQUAL_STRING("0aff10c3", hex);
  TEST_ASSERT_FALSE(fromHex("0aFf10c", 7, bytes, 4));
  TEST_ASSERT_FALSE(fromHex("0aFg10c3", 8, bytes, 4));
}

static void test_handshake_matches_the_phone() {
  uint8_t session[32];
  char hex[65];
  LinkGuard::sessionKey(secret(), kPhoneNonce, kBodyNonceHex, session);
  digestHex(session, hex);
  TEST_ASSERT_EQUAL_STRING(kSessionHex, hex);
  LinkGuard g;
  g.reset(0);
  uint8_t nonce[LinkGuard::kNonceSize];
  bodyNonce(nonce);
  char buf[128];
  TextWriter w(buf, sizeof(buf));
  TEST_ASSERT_TRUE(g.challenge(secret(), "00112233445566778899AABBCCDDEEFF", nonce, w));
  char expected[128];
  strcpy(expected, "h ");
  strcat(expected, kBodyNonceHex);
  strcat(expected, " ");
  strcat(expected, kBodyProof);
  TEST_ASSERT_EQUAL_STRING(expected, w.c_str());
  TEST_ASSERT_TRUE(g.challenged());
  TEST_ASSERT_FALSE(g.proven());
  TEST_ASSERT_TRUE(g.verify(kPhoneProof));
  g.commit(10);
  TEST_ASSERT_TRUE(g.proven());
}

static void test_no_key_no_challenge() {
  LinkGuard g;
  g.reset(0);
  uint8_t nonce[LinkGuard::kNonceSize];
  bodyNonce(nonce);
  char buf[128];
  TextWriter w(buf, sizeof(buf));
  TEST_ASSERT_FALSE(g.challenge(LinkSecret(), kPhoneNonce, nonce, w));
  TEST_ASSERT_FALSE(g.challenged());
  TEST_ASSERT_FALSE(g.challenge(secret(), "0011", nonce, w));
}

static void test_wrong_proof_fails_and_counts() {
  LinkGuard g;
  g.reset(0);
  uint8_t nonce[LinkGuard::kNonceSize];
  bodyNonce(nonce);
  char buf[128];
  TextWriter w(buf, sizeof(buf));
  for (int i = 0; i < LinkGuard::kMaxFailures; ++i) {
    TEST_ASSERT_FALSE(g.failedTooOften());
    TEST_ASSERT_TRUE(g.challenge(secret(), kPhoneNonce, nonce, w));
    TEST_ASSERT_FALSE(g.verify(kBodyProof));
    TEST_ASSERT_FALSE(g.proven());
  }
  TEST_ASSERT_TRUE(g.failedTooOften());
  LinkGuard h;
  h.reset(0);
  TEST_ASSERT_FALSE(h.verify(kPhoneProof));
  h.commit(0);
  TEST_ASSERT_FALSE(h.proven());
}

static void test_tags_in_and_out() {
  LinkGuard g;
  g.reset(0);
  proveGuard(g, 100);
  char out[128];
  TEST_ASSERT_EQUAL(LinkGuard::Inbound::Tagged, g.unwrap("D 300 300 #1 92edd70232c8", out, sizeof(out), 200));
  TEST_ASSERT_EQUAL_STRING("D 300 300", out);
  TEST_ASSERT_EQUAL(LinkGuard::Inbound::BadTag, g.unwrap("D 300 300 #1 92edd70232c8", out, sizeof(out), 210));
  TEST_ASSERT_EQUAL(LinkGuard::Inbound::BadTag, g.unwrap("D 900 900 #2 6bf0f2c15a3b", out, sizeof(out), 220));
  TEST_ASSERT_EQUAL(LinkGuard::Inbound::Tagged, g.unwrap("X #2 6BF0F2C15A3B\r", out, sizeof(out), 230));
  TEST_ASSERT_EQUAL_STRING("X", out);
  TEST_ASSERT_EQUAL(LinkGuard::Inbound::Plain, g.unwrap("X", out, sizeof(out), 240));
  char wire[160];
  TextWriter w(wire, sizeof(wire));
  TEST_ASSERT_TRUE(g.seal("ok", 2, w));
  TEST_ASSERT_EQUAL_STRING("ok #1 2f9524c7b9ae", w.c_str());
  TEST_ASSERT_TRUE(g.seal("ok", 2, w));
  TEST_ASSERT_EQUAL(0, strncmp("ok #2 ", w.c_str(), 6));
}

static void test_tags_refused_before_proof() {
  LinkGuard g;
  g.reset(0);
  char out[128];
  TEST_ASSERT_EQUAL(LinkGuard::Inbound::BadTag, g.unwrap("D 300 300 #1 92edd70232c8", out, sizeof(out), 0));
  TEST_ASSERT_EQUAL(LinkGuard::Inbound::Plain, g.unwrap("D 300 300", out, sizeof(out), 0));
  char wire[160];
  TextWriter w(wire, sizeof(wire));
  TEST_ASSERT_TRUE(g.seal("S 1", 3, w));
  TEST_ASSERT_EQUAL_STRING("S 1", w.c_str());
}

static void test_long_lines() {
  LinkGuard g;
  g.reset(0);
  char line[200];
  memset(line, 'a', kMaxLineLength + 1);
  line[kMaxLineLength + 1] = '\0';
  char out[128];
  TEST_ASSERT_EQUAL(LinkGuard::Inbound::Long, g.unwrap(line, out, sizeof(out), 0));
  line[kMaxLineLength] = '\0';
  TEST_ASSERT_EQUAL(LinkGuard::Inbound::Plain, g.unwrap(line, out, sizeof(out), 0));
}

static void test_longest_tagged_command_fits_a_line() {
  char longest[128];
  strcpy(longest, "C pass ");
  for (int i = 0; i < 64; ++i) strcat(longest, "x");
  TEST_ASSERT_TRUE(strlen(longest) + LinkGuard::kSuffixMax <= kMaxLineLength);
}

static void test_expiry_and_holding() {
  LinkGuard g;
  g.reset(1000);
  TEST_ASSERT_FALSE(g.expired(1000 + LinkGuard::kProveWithinMs - 1));
  TEST_ASSERT_TRUE(g.expired(1000 + LinkGuard::kProveWithinMs));
  TEST_ASSERT_FALSE(g.holding(1001));
  proveGuard(g, 2000);
  TEST_ASSERT_FALSE(g.expired(100000));
  TEST_ASSERT_TRUE(g.holding(2000 + LinkGuard::kHeldForMs - 1));
  TEST_ASSERT_FALSE(g.holding(2000 + LinkGuard::kHeldForMs));
}

static void test_access_rules() {
  TEST_ASSERT_EQUAL(LinkAccess::Allowed, linkAccess(CommandType::Stop, false, false, false));
  TEST_ASSERT_EQUAL(LinkAccess::Allowed, linkAccess(CommandType::Ping, false, false, false));
  TEST_ASSERT_EQUAL(LinkAccess::Allowed, linkAccess(CommandType::Hello, false, false, false));
  TEST_ASSERT_EQUAL(LinkAccess::Allowed, linkAccess(CommandType::Verify, false, false, false));
  TEST_ASSERT_EQUAL(LinkAccess::NeedsProof, linkAccess(CommandType::Drive, false, false, false));
  TEST_ASSERT_EQUAL(LinkAccess::NeedsProof, linkAccess(CommandType::Speed, false, false, false));
  TEST_ASSERT_EQUAL(LinkAccess::NeedsProof, linkAccess(CommandType::Tilt, false, false, false));
  TEST_ASSERT_EQUAL(LinkAccess::NeedsProof, linkAccess(CommandType::Query, false, false, false));
  TEST_ASSERT_EQUAL(LinkAccess::NeedsProof, linkAccess(CommandType::ConfigList, false, false, false));
  TEST_ASSERT_EQUAL(LinkAccess::NeedsProof, linkAccess(CommandType::ConfigSet, false, false, false));
  TEST_ASSERT_EQUAL(LinkAccess::NeedsProof, linkAccess(CommandType::Reboot, false, false, false));
  TEST_ASSERT_EQUAL(LinkAccess::Allowed, linkAccess(CommandType::Drive, false, true, true));
  TEST_ASSERT_EQUAL(LinkAccess::Allowed, linkAccess(CommandType::ConfigList, false, true, true));
  TEST_ASSERT_EQUAL(LinkAccess::Allowed, linkAccess(CommandType::ConfigGet, false, true, true));
  TEST_ASSERT_EQUAL(LinkAccess::Allowed, linkAccess(CommandType::KeyQuery, false, true, true));
  TEST_ASSERT_EQUAL(LinkAccess::UsbOnly, linkAccess(CommandType::ConfigSet, false, true, true));
  TEST_ASSERT_EQUAL(LinkAccess::UsbOnly, linkAccess(CommandType::Reboot, false, true, true));
  TEST_ASSERT_EQUAL(LinkAccess::UsbOnly, linkAccess(CommandType::KeySet, false, true, true));
  TEST_ASSERT_EQUAL(LinkAccess::UsbOnly, linkAccess(CommandType::KeyClear, false, true, true));
  TEST_ASSERT_EQUAL(LinkAccess::NeedsProof, linkAccess(CommandType::Drive, false, true, false));
  TEST_ASSERT_EQUAL(LinkAccess::Allowed, linkAccess(CommandType::Stop, false, true, false));
  TEST_ASSERT_EQUAL(LinkAccess::Allowed, linkAccess(CommandType::Drive, true, false, false));
  TEST_ASSERT_EQUAL(LinkAccess::Allowed, linkAccess(CommandType::ConfigSet, true, false, false));
  TEST_ASSERT_EQUAL(LinkAccess::Allowed, linkAccess(CommandType::Reboot, true, false, false));
  TEST_ASSERT_EQUAL(LinkAccess::Allowed, linkAccess(CommandType::KeySet, true, false, false));
  TEST_ASSERT_EQUAL(LinkAccess::NeedsProof, linkAccess(CommandType::Drive, true, true, false));
  TEST_ASSERT_EQUAL(LinkAccess::Allowed, linkAccess(CommandType::ConfigSet, true, true, true));
}

static void test_pairing_window_opens_on_a_held_bumper() {
  PairingWindow w;
  TEST_ASSERT_EQUAL(PairingWindow::Change::None, w.update(0, true, true, false));
  TEST_ASSERT_EQUAL(PairingWindow::Change::None, w.update(2999, true, true, false));
  TEST_ASSERT_FALSE(w.open());
  TEST_ASSERT_EQUAL(PairingWindow::Change::Opened, w.update(3000, true, true, false));
  TEST_ASSERT_TRUE(w.open());
  TEST_ASSERT_EQUAL(PairingWindow::Change::None, w.update(9000, true, true, false));
  TEST_ASSERT_EQUAL(PairingWindow::Change::None, w.update(9100, false, true, false));
  TEST_ASSERT_EQUAL(PairingWindow::Change::None, w.update(3000 + 119999, false, true, false));
  TEST_ASSERT_EQUAL(PairingWindow::Change::Closed, w.update(3000 + 120000, false, true, false));
  TEST_ASSERT_FALSE(w.open());
}

static void test_pairing_window_needs_still_wheels_and_a_steady_hold() {
  PairingWindow w;
  w.update(0, true, false, false);
  TEST_ASSERT_EQUAL(PairingWindow::Change::None, w.update(5000, true, false, false));
  TEST_ASSERT_FALSE(w.open());
  w.update(6000, true, true, false);
  w.update(8000, false, true, false);
  w.update(8010, true, true, false);
  TEST_ASSERT_EQUAL(PairingWindow::Change::None, w.update(10000, true, true, false));
  TEST_ASSERT_FALSE(w.open());
  TEST_ASSERT_EQUAL(PairingWindow::Change::Opened, w.update(11010, true, true, false));
}

static void test_pairing_window_stays_while_a_proven_phone_is_linked() {
  PairingWindow w;
  w.update(0, true, true, false);
  w.update(3000, true, true, false);
  TEST_ASSERT_EQUAL(PairingWindow::Change::None, w.update(500000, false, true, true));
  TEST_ASSERT_TRUE(w.open());
  TEST_ASSERT_EQUAL(PairingWindow::Change::Closed, w.update(500010, false, true, false));
}

static void test_rate_limiter() {
  RateLimiter r(4, 4);
  for (int i = 0; i < 4; ++i) TEST_ASSERT_TRUE(r.take(1000));
  TEST_ASSERT_FALSE(r.take(1000));
  TEST_ASSERT_FALSE(r.take(1249));
  TEST_ASSERT_TRUE(r.take(1250));
  TEST_ASSERT_FALSE(r.take(1251));
  for (int i = 0; i < 4; ++i) TEST_ASSERT_TRUE(r.take(100000));
  TEST_ASSERT_FALSE(r.take(100000));
}

static void test_handshake_lines_parse() {
  Command c;
  TEST_ASSERT_EQUAL(ParseResult::Ok, parseCommand("H 00112233445566778899aabbccddeeff", c));
  TEST_ASSERT_EQUAL(CommandType::Hello, c.type);
  TEST_ASSERT_EQUAL_STRING("00112233445566778899aabbccddeeff", c.value);
  TEST_ASSERT_EQUAL(ParseResult::Syntax, parseCommand("H 0011", c));
  TEST_ASSERT_EQUAL(ParseResult::Syntax, parseCommand("H 00112233445566778899aabbccddeefg", c));
  TEST_ASSERT_EQUAL(ParseResult::Syntax, parseCommand("H", c));
  TEST_ASSERT_EQUAL(ParseResult::Ok, parseCommand("V 5c97f3affe363f31e642b9d4d9dd7568", c));
  TEST_ASSERT_EQUAL(CommandType::Verify, c.type);
  TEST_ASSERT_EQUAL(ParseResult::Ok, parseCommand("K ?", c));
  TEST_ASSERT_EQUAL(CommandType::KeyQuery, c.type);
  TEST_ASSERT_EQUAL(ParseResult::Ok, parseCommand("K -", c));
  TEST_ASSERT_EQUAL(CommandType::KeyClear, c.type);
  TEST_ASSERT_EQUAL(ParseResult::Ok, parseCommand("K 000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f", c));
  TEST_ASSERT_EQUAL(CommandType::KeySet, c.type);
  TEST_ASSERT_EQUAL(ParseResult::Syntax, parseCommand("K 0001", c));
  TEST_ASSERT_EQUAL(ParseResult::Syntax, parseCommand("K", c));
  TEST_ASSERT_EQUAL_CHAR('H', lineCommandLetter("H 1"));
  TEST_ASSERT_EQUAL_CHAR('V', commandLetter(CommandType::Verify));
  TEST_ASSERT_EQUAL_CHAR('K', commandLetter(CommandType::KeySet));
  char buf[128];
  TextWriter w(buf, sizeof(buf));
  TEST_ASSERT_TRUE(formatKeyState(w, true));
  TEST_ASSERT_EQUAL_STRING("k set", w.c_str());
  TEST_ASSERT_TRUE(formatKeyState(w, false));
  TEST_ASSERT_EQUAL_STRING("k none", w.c_str());
}

int main(int, char**) {
  UNITY_BEGIN();
  RUN_TEST(test_sha256_vectors);
  RUN_TEST(test_hmac_vectors);
  RUN_TEST(test_hex_round_trip);
  RUN_TEST(test_handshake_matches_the_phone);
  RUN_TEST(test_no_key_no_challenge);
  RUN_TEST(test_wrong_proof_fails_and_counts);
  RUN_TEST(test_tags_in_and_out);
  RUN_TEST(test_tags_refused_before_proof);
  RUN_TEST(test_long_lines);
  RUN_TEST(test_longest_tagged_command_fits_a_line);
  RUN_TEST(test_expiry_and_holding);
  RUN_TEST(test_access_rules);
  RUN_TEST(test_pairing_window_opens_on_a_held_bumper);
  RUN_TEST(test_pairing_window_needs_still_wheels_and_a_steady_hold);
  RUN_TEST(test_pairing_window_stays_while_a_proven_phone_is_linked);
  RUN_TEST(test_rate_limiter);
  RUN_TEST(test_handshake_lines_parse);
  return UNITY_END();
}
