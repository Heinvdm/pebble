#include "link_guard.h"

#include <string.h>

namespace pebble {

namespace {

constexpr const char* kSessionLabel = "pebble-link-1 ";

bool isSpace(char c) { return c == ' ' || c == '\t' || c == '\r' || c == '\n'; }

bool isHexDigit(char c) { return (c >= '0' && c <= '9') || (c >= 'a' && c <= 'f') || (c >= 'A' && c <= 'F'); }

char lower(char c) { return (c >= 'A' && c <= 'F') ? static_cast<char>(c - 'A' + 'a') : c; }

size_t decimal(uint32_t value, char* out) {
  char digits[11];
  size_t n = 0;
  do {
    digits[n++] = static_cast<char>('0' + value % 10);
    value /= 10;
  } while (value > 0);
  for (size_t i = 0; i < n; ++i) out[i] = digits[n - 1 - i];
  out[n] = '\0';
  return n;
}

struct Suffix {
  bool found = false;
  size_t textLength = 0;
  uint32_t counter = 0;
  const char* tag = nullptr;
};

Suffix findSuffix(const char* line, size_t length) {
  Suffix s;
  if (length < LinkGuard::kTagHexLength + 4) return s;
  size_t tagStart = length - LinkGuard::kTagHexLength;
  for (size_t i = tagStart; i < length; ++i) {
    if (!isHexDigit(line[i])) return s;
  }
  if (line[tagStart - 1] != ' ') return s;
  size_t end = tagStart - 1;
  size_t start = end;
  while (start > 0 && line[start - 1] >= '0' && line[start - 1] <= '9') --start;
  size_t digits = end - start;
  if (digits == 0 || digits > 10 || start < 2 || line[start - 1] != '#' || line[start - 2] != ' ') return s;
  uint64_t value = 0;
  for (size_t i = start; i < end; ++i) value = value * 10 + static_cast<uint64_t>(line[i] - '0');
  if (value == 0 || value > 0xFFFFFFFFull) return s;
  s.found = true;
  s.textLength = start - 2;
  s.counter = static_cast<uint32_t>(value);
  s.tag = line + tagStart;
  return s;
}

}

LinkAccess linkAccess(CommandType type, bool usb, bool proven, bool tagged) {
  bool always = type == CommandType::Stop || type == CommandType::Hello || type == CommandType::Verify;
  if (!always) {
    if (proven && !tagged) return LinkAccess::NeedsProof;
    if (!proven && !usb && type != CommandType::Ping) return LinkAccess::NeedsProof;
  }
  switch (type) {
    case CommandType::ConfigSet:
    case CommandType::Reboot:
    case CommandType::KeySet:
    case CommandType::KeyClear:
      return usb ? LinkAccess::Allowed : LinkAccess::UsbOnly;
    default:
      return LinkAccess::Allowed;
  }
}

void LinkGuard::reset(uint32_t now) {
  state_ = State::Open;
  memset(session_, 0, sizeof(session_));
  received_ = 0;
  sent_ = 0;
  openedAt_ = now;
  lastGood_ = now;
  failures_ = 0;
}

bool LinkGuard::expired(uint32_t now) const {
  return state_ != State::Proven && static_cast<uint32_t>(now - openedAt_) >= kProveWithinMs;
}

bool LinkGuard::holding(uint32_t now) const {
  return state_ == State::Proven && static_cast<uint32_t>(now - lastGood_) < kHeldForMs;
}

void LinkGuard::sessionKey(const LinkSecret& secret, const char* phoneNonceHex, const char* bodyNonceHex,
                           uint8_t out[Sha256::kDigestSize]) {
  HmacSha256 mac(secret.key, LinkSecret::kSize);
  mac.update(kSessionLabel);
  mac.update(phoneNonceHex);
  mac.update(" ");
  mac.update(bodyNonceHex);
  mac.finish(out);
}

void LinkGuard::proof(const uint8_t session[Sha256::kDigestSize], const char* who, uint8_t out[kProofSize]) {
  HmacSha256 mac(session, Sha256::kDigestSize);
  mac.update(who);
  uint8_t full[Sha256::kDigestSize];
  mac.finish(full);
  memcpy(out, full, kProofSize);
}

void LinkGuard::tag(const uint8_t session[Sha256::kDigestSize], char direction, uint32_t counter, const char* text,
                    size_t length, char out[kTagHexLength + 1]) {
  HmacSha256 mac(session, Sha256::kDigestSize);
  char head[13];
  head[0] = direction;
  size_t n = decimal(counter, head + 1);
  head[n + 1] = ' ';
  mac.update(head, n + 2);
  mac.update(text, length);
  uint8_t full[Sha256::kDigestSize];
  mac.finish(full);
  toHex(full, kTagSize, out);
}

LinkGuard::Inbound LinkGuard::unwrap(const char* line, char* out, size_t capacity, uint32_t now) {
  size_t length = strlen(line);
  while (length > 0 && isSpace(line[length - 1])) --length;
  Suffix suffix = findSuffix(line, length);
  if (!suffix.found) {
    if (length > kMaxLineLength || length + 1 > capacity) return Inbound::Long;
    memcpy(out, line, length);
    out[length] = '\0';
    return Inbound::Plain;
  }
  if (state_ != State::Proven || suffix.counter <= received_) return Inbound::BadTag;
  if (suffix.textLength > kMaxLineLength || suffix.textLength + 1 > capacity) return Inbound::Long;
  char expected[kTagHexLength + 1];
  tag(session_, 'p', suffix.counter, line, suffix.textLength, expected);
  char given[kTagHexLength];
  for (size_t i = 0; i < kTagHexLength; ++i) given[i] = lower(suffix.tag[i]);
  if (!constantTimeEqual(reinterpret_cast<const uint8_t*>(expected), reinterpret_cast<const uint8_t*>(given),
                         kTagHexLength)) {
    return Inbound::BadTag;
  }
  received_ = suffix.counter;
  lastGood_ = now;
  memcpy(out, line, suffix.textLength);
  out[suffix.textLength] = '\0';
  return Inbound::Tagged;
}

bool LinkGuard::challenge(const LinkSecret& secret, const char* phoneNonceHex, const uint8_t bodyNonce[kNonceSize],
                          TextWriter& reply) {
  state_ = State::Open;
  memset(session_, 0, sizeof(session_));
  received_ = 0;
  sent_ = 0;
  if (!secret.present || phoneNonceHex == nullptr || strlen(phoneNonceHex) != kNonceSize * 2) return false;
  char phone[kNonceSize * 2 + 1];
  for (size_t i = 0; i < kNonceSize * 2; ++i) {
    if (!isHexDigit(phoneNonceHex[i])) return false;
    phone[i] = lower(phoneNonceHex[i]);
  }
  phone[kNonceSize * 2] = '\0';
  char body[kNonceSize * 2 + 1];
  toHex(bodyNonce, kNonceSize, body);
  sessionKey(secret, phone, body, session_);
  uint8_t mine[kProofSize];
  proof(session_, "body", mine);
  char mineHex[kProofSize * 2 + 1];
  toHex(mine, kProofSize, mineHex);
  state_ = State::Challenged;
  return formatChallenge(reply, body, mineHex);
}

bool LinkGuard::verify(const char* proofHex) {
  if (state_ != State::Challenged || proofHex == nullptr) {
    ++failures_;
    return false;
  }
  uint8_t given[kProofSize];
  uint8_t expected[kProofSize];
  proof(session_, "phone", expected);
  bool ok = fromHex(proofHex, strlen(proofHex), given, kProofSize) && constantTimeEqual(given, expected, kProofSize);
  if (!ok) {
    ++failures_;
    state_ = State::Open;
    memset(session_, 0, sizeof(session_));
  }
  return ok;
}

void LinkGuard::commit(uint32_t now) {
  if (state_ != State::Challenged) return;
  state_ = State::Proven;
  received_ = 0;
  sent_ = 0;
  lastGood_ = now;
}

bool LinkGuard::seal(const char* text, size_t length, TextWriter& out) {
  out.clear();
  for (size_t i = 0; i < length; ++i) out.put(text[i]);
  if (state_ != State::Proven) return out.ok();
  ++sent_;
  if (sent_ == 0) sent_ = 1;
  char tagHex[kTagHexLength + 1];
  tag(session_, 'b', sent_, text, length, tagHex);
  out.put(" #").putInt(sent_).space().put(tagHex);
  return out.ok();
}

}
