#include "protocol.h"

#include <string.h>

namespace pebble {

namespace {

bool isSpace(char c) { return c == ' ' || c == '\t' || c == '\r' || c == '\n'; }

const char* skipSpaces(const char* p) {
  while (*p && isSpace(*p)) ++p;
  return p;
}

size_t tokenLength(const char* p) {
  size_t n = 0;
  while (p[n] && !isSpace(p[n])) ++n;
  return n;
}

bool parseInt(const char* p, size_t len, int64_t& out) {
  if (len == 0 || len > 12) return false;
  size_t i = 0;
  bool negative = false;
  if (p[0] == '-' || p[0] == '+') {
    negative = p[0] == '-';
    i = 1;
    if (len == 1) return false;
  }
  int64_t value = 0;
  for (; i < len; ++i) {
    if (p[i] < '0' || p[i] > '9') return false;
    value = value * 10 + (p[i] - '0');
  }
  out = negative ? -value : value;
  return true;
}

int clampInt(int64_t v, int lo, int hi) {
  if (v < lo) return lo;
  if (v > hi) return hi;
  return static_cast<int>(v);
}

class Tokens {
 public:
  explicit Tokens(const char* text) : p_(skipSpaces(text)) {}

  bool next(const char*& start, size_t& len) {
    p_ = skipSpaces(p_);
    if (!*p_) return false;
    start = p_;
    len = tokenLength(p_);
    p_ += len;
    return true;
  }

  bool nextInt(int64_t& out) {
    const char* s;
    size_t n;
    return next(s, n) && parseInt(s, n, out);
  }

  bool atEnd() { return *skipSpaces(p_) == '\0'; }

  const char* rest() { return skipSpaces(p_); }

 private:
  const char* p_;
};

bool copyText(char* dst, size_t cap, const char* src, size_t len) {
  if (len + 1 > cap) return false;
  memcpy(dst, src, len);
  dst[len] = '\0';
  return true;
}

size_t trimmedLength(const char* s) {
  size_t n = strlen(s);
  while (n > 0 && isSpace(s[n - 1])) --n;
  return n;
}

ParseResult parsePair(Tokens& t, Command& out, int limit) {
  int64_t a, b;
  if (!t.nextInt(a) || !t.nextInt(b) || !t.atEnd()) return ParseResult::Syntax;
  out.left = clampInt(a, -limit, limit);
  out.right = clampInt(b, -limit, limit);
  return ParseResult::Ok;
}

ParseResult parseConfig(Tokens& t, Command& out) {
  const char* s;
  size_t n;
  if (!t.next(s, n)) return ParseResult::Syntax;
  if (n == 1 && s[0] == '?') {
    if (!t.atEnd()) return ParseResult::Syntax;
    out.type = CommandType::ConfigList;
    return ParseResult::Ok;
  }
  if (!copyText(out.key, sizeof(out.key), s, n)) return ParseResult::Syntax;
  const char* rest = t.rest();
  if (*rest == '\0') {
    out.type = CommandType::ConfigGet;
    return ParseResult::Ok;
  }
  if (!copyText(out.value, sizeof(out.value), rest, trimmedLength(rest))) return ParseResult::Syntax;
  out.type = CommandType::ConfigSet;
  return ParseResult::Ok;
}

bool isHex(const char* s, size_t n) {
  for (size_t i = 0; i < n; ++i) {
    char c = s[i];
    if (!((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f') || (c >= 'A' && c <= 'F'))) return false;
  }
  return true;
}

ParseResult parseHexArgument(Tokens& t, Command& out, size_t length) {
  const char* s;
  size_t n;
  if (!t.next(s, n) || !t.atEnd() || n != length || !isHex(s, n)) return ParseResult::Syntax;
  if (!copyText(out.value, sizeof(out.value), s, n)) return ParseResult::Syntax;
  return ParseResult::Ok;
}

ParseResult parseKey(Tokens& t, Command& out) {
  const char* s;
  size_t n;
  if (!t.next(s, n) || !t.atEnd()) return ParseResult::Syntax;
  if (n == 1 && s[0] == '?') {
    out.type = CommandType::KeyQuery;
    return ParseResult::Ok;
  }
  if (n == 1 && s[0] == '-') {
    out.type = CommandType::KeyClear;
    return ParseResult::Ok;
  }
  if (n != kKeyHexLength || !isHex(s, n) || !copyText(out.value, sizeof(out.value), s, n)) return ParseResult::Syntax;
  out.type = CommandType::KeySet;
  return ParseResult::Ok;
}

}

bool isReverseCommand(int left, int right) { return left <= 0 && right <= 0 && (left < 0 || right < 0); }

char commandLetter(CommandType type) {
  switch (type) {
    case CommandType::Drive:
      return 'D';
    case CommandType::Speed:
      return 'M';
    case CommandType::Tilt:
      return 'T';
    case CommandType::Stop:
      return 'X';
    case CommandType::Ping:
      return 'P';
    case CommandType::Query:
      return 'Q';
    case CommandType::ConfigSet:
    case CommandType::ConfigGet:
    case CommandType::ConfigList:
      return 'C';
    case CommandType::Reboot:
      return 'R';
    case CommandType::Hello:
      return 'H';
    case CommandType::Verify:
      return 'V';
    case CommandType::KeySet:
    case CommandType::KeyClear:
    case CommandType::KeyQuery:
      return 'K';
  }
  return kUnknownCommandLetter;
}

char lineCommandLetter(const char* line) {
  if (line == nullptr) return kUnknownCommandLetter;
  const char* p = skipSpaces(line);
  if (tokenLength(p) != 1) return kUnknownCommandLetter;
  return strchr("DMTXPQCRHVK", p[0]) != nullptr ? p[0] : kUnknownCommandLetter;
}

ParseResult parseCommand(const char* line, Command& out) {
  out = Command();
  if (line == nullptr) return ParseResult::Empty;
  Tokens t(line);
  const char* s;
  size_t n;
  if (!t.next(s, n)) return ParseResult::Empty;
  if (n != 1) return ParseResult::Unknown;
  int64_t v;
  switch (s[0]) {
    case 'D':
      out.type = CommandType::Drive;
      return parsePair(t, out, kMaxWheelPower);
    case 'M':
      out.type = CommandType::Speed;
      return parsePair(t, out, kMaxWheelSpeed);
    case 'T':
      out.type = CommandType::Tilt;
      if (!t.nextInt(v) || !t.atEnd()) return ParseResult::Syntax;
      out.tilt = clampInt(v, -kMaxTiltDegrees, kMaxTiltDegrees);
      return ParseResult::Ok;
    case 'X':
      out.type = CommandType::Stop;
      return t.atEnd() ? ParseResult::Ok : ParseResult::Syntax;
    case 'Q':
      out.type = CommandType::Query;
      return t.atEnd() ? ParseResult::Ok : ParseResult::Syntax;
    case 'R':
      out.type = CommandType::Reboot;
      return t.atEnd() ? ParseResult::Ok : ParseResult::Syntax;
    case 'P': {
      out.type = CommandType::Ping;
      if (!t.next(s, n) || !t.atEnd()) return ParseResult::Syntax;
      if (!parseInt(s, n, v)) return ParseResult::Syntax;
      if (!copyText(out.token, sizeof(out.token), s, n)) return ParseResult::Syntax;
      return ParseResult::Ok;
    }
    case 'C':
      return parseConfig(t, out);
    case 'H':
      out.type = CommandType::Hello;
      return parseHexArgument(t, out, kNonceHexLength);
    case 'V':
      out.type = CommandType::Verify;
      return parseHexArgument(t, out, kNonceHexLength);
    case 'K':
      out.type = CommandType::KeyQuery;
      return parseKey(t, out);
    default:
      return ParseResult::Unknown;
  }
}

const char* parseResultReason(ParseResult result) {
  switch (result) {
    case ParseResult::Ok:
      return "ok";
    case ParseResult::Empty:
      return "empty";
    case ParseResult::Unknown:
      return "unknown";
    case ParseResult::Syntax:
      return "syntax";
  }
  return "syntax";
}

bool formatStatus(TextWriter& out, const StatusData& s) {
  out.clear();
  out.put('S').space().putInt(s.ms);
  out.space().putInt(s.encLeft).space().putInt(s.encRight);
  out.space().putInt(s.frontMm).space().putInt(s.downMm);
  out.space().putInt(s.bump).space().putInt(s.dock ? 1 : 0);
  out.space().putInt(s.packMv).space().putInt(s.tilt).space().putInt(s.flags);
  return out.ok() && out.length() <= kMaxLineLength;
}

bool formatAir(TextWriter& out, const AirData& a) {
  out.clear();
  out.put('A').space().putInt(kAirVersion).space().putInt(a.ms);
  if (!a.present) {
    out.put(" none");
    return out.ok() && out.length() <= kMaxLineLength;
  }
  out.space().putFixed(a.temperatureC, 2).space().putFixed(a.humidityPct, 2);
  out.space().putInt(a.pressurePa).space().putInt(a.gasOhm < 0 ? -1 : a.gasOhm);
  out.space().putInt(a.heatedS);
  return out.ok() && out.length() <= kMaxLineLength;
}

bool formatEvent(TextWriter& out, const Event& e) {
  out.clear();
  out.put("E ");
  switch (e.type) {
    case EventType::Boot:
      out.put("boot").space().put(e.text ? e.text : "?");
      break;
    case EventType::Bump:
      out.put("bump").space().put(e.value == 1 ? "L" : e.value == 2 ? "R" : "B");
      break;
    case EventType::Edge:
      out.put("edge");
      break;
    case EventType::Obstacle:
      out.put("obstacle").space().putInt(e.value);
      break;
    case EventType::Stall:
      out.put("stall").space().put(e.value == static_cast<int32_t>(Wheel::Left) ? "L" : "R");
      break;
    case EventType::Dock:
      out.put("dock").space().putInt(e.value ? 1 : 0);
      break;
    case EventType::LowBat:
      out.put("lowbat").space().putInt(e.value);
      break;
    case EventType::Deadman:
      out.put("deadman");
      break;
    case EventType::Fault:
      out.put("fault").space().put(e.text ? e.text : "unknown");
      break;
  }
  return out.ok() && out.length() <= kMaxLineLength;
}

bool formatPing(TextWriter& out, const char* token) {
  out.clear();
  out.put("p ").put(token);
  return out.ok() && out.length() <= kMaxLineLength;
}

bool formatOk(TextWriter& out) {
  out.clear();
  out.put("ok");
  return out.ok();
}

bool formatError(TextWriter& out, char command, const char* reason) {
  out.clear();
  out.put("err ").put(command).space().put(reason);
  return out.ok() && out.length() <= kMaxLineLength;
}

bool formatConfig(TextWriter& out, const char* key, const char* value) {
  out.clear();
  out.put("c ").put(key).space().put(value);
  return out.ok() && out.length() <= kMaxLineLength;
}

bool formatChallenge(TextWriter& out, const char* nonceHex, const char* proofHex) {
  out.clear();
  out.put("h ").put(nonceHex).space().put(proofHex);
  return out.ok() && out.length() <= kMaxLineLength;
}

bool formatKeyState(TextWriter& out, bool present) {
  out.clear();
  out.put("k ").put(present ? "set" : "none");
  return out.ok();
}

}
