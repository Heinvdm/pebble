#include "settings_model.h"

#include <math.h>
#include <stdlib.h>
#include <string.h>

namespace pebble {

namespace {

constexpr const char* kNames[kSettingCount] = {"ssid", "pass", "cpm", "edge", "stop", "tmin", "tmax", "trim", "rest"};

constexpr const char* kEmptyMarker = "-";

bool parseStrictInt(const char* text, int& out) {
  if (text == nullptr || *text == '\0') return false;
  const char* p = text;
  bool negative = false;
  if (*p == '-' || *p == '+') {
    negative = *p == '-';
    ++p;
  }
  if (*p == '\0') return false;
  int64_t value = 0;
  int digits = 0;
  for (; *p; ++p) {
    if (*p < '0' || *p > '9') return false;
    if (++digits > 9) return false;
    value = value * 10 + (*p - '0');
  }
  out = static_cast<int>(negative ? -value : value);
  return true;
}

bool parseStrictFloat(const char* text, float& out) {
  if (text == nullptr || *text == '\0') return false;
  for (const char* p = text; *p; ++p) {
    if (!((*p >= '0' && *p <= '9') || *p == '.' || *p == '-' || *p == '+')) return false;
  }
  char* end = nullptr;
  float v = strtof(text, &end);
  if (end == text || *end != '\0' || isnan(v) || isinf(v)) return false;
  out = v;
  return true;
}

bool isPrintable(const char* text) {
  for (const char* p = text; *p; ++p) {
    if (static_cast<unsigned char>(*p) < 0x20 || static_cast<unsigned char>(*p) == 0x7F) return false;
  }
  return true;
}

SettingError setText(char* dst, size_t cap, const char* text, size_t minLen) {
  if (strcmp(text, kEmptyMarker) == 0) {
    dst[0] = '\0';
    return SettingError::None;
  }
  size_t len = strlen(text);
  if (!isPrintable(text)) return SettingError::Value;
  if (len + 1 > cap || len < minLen) return SettingError::Range;
  memcpy(dst, text, len + 1);
  return SettingError::None;
}

SettingError setInt(int& dst, const char* text, int lo, int hi) {
  int v;
  if (!parseStrictInt(text, v)) return SettingError::Value;
  if (v < lo || v > hi) return SettingError::Range;
  dst = v;
  return SettingError::None;
}

}

SettingKey settingAt(size_t index) { return static_cast<SettingKey>(index < kSettingCount ? index : 0); }

const char* settingName(SettingKey key) {
  size_t i = static_cast<size_t>(key);
  return i < kSettingCount ? kNames[i] : "?";
}

bool settingFromName(const char* name, SettingKey& out) {
  if (name == nullptr) return false;
  for (size_t i = 0; i < kSettingCount; ++i) {
    if (strcmp(name, kNames[i]) == 0) {
      out = static_cast<SettingKey>(i);
      return true;
    }
  }
  return false;
}

bool settingNeedsReboot(SettingKey key) { return key == SettingKey::Ssid || key == SettingKey::Pass; }

bool sameSetting(const Settings& a, const Settings& b, SettingKey key) {
  switch (key) {
    case SettingKey::Ssid:
      return strcmp(a.ssid, b.ssid) == 0;
    case SettingKey::Pass:
      return strcmp(a.pass, b.pass) == 0;
    case SettingKey::Cpm:
      return a.cpm == b.cpm;
    case SettingKey::Edge:
      return a.edge == b.edge;
    case SettingKey::Stop:
      return a.stop == b.stop;
    case SettingKey::Tmin:
      return a.tmin == b.tmin;
    case SettingKey::Tmax:
      return a.tmax == b.tmax;
    case SettingKey::Trim:
      return a.trim == b.trim;
    case SettingKey::Rest:
      return a.rest == b.rest;
  }
  return false;
}

bool applyTiltRange(Settings& s, int tmin, int tmax, int rest) {
  if (tmin < SettingBounds::TiltMin || tmax > SettingBounds::TiltMax || tmin >= tmax) return false;
  if (rest < tmin || rest > tmax) return false;
  s.tmin = tmin;
  s.tmax = tmax;
  s.rest = rest;
  return true;
}

bool settingsSafe(const Settings& s) {
  if (s.edge < SettingBounds::EdgeMin || s.edge > SettingBounds::EdgeMax) return false;
  if (s.stop < SettingBounds::StopMin || s.stop > SettingBounds::StopMax) return false;
  if (s.cpm != 0.0f && (s.cpm < SettingBounds::CpmMin || s.cpm > SettingBounds::CpmMax)) return false;
  if (s.trim < -SettingBounds::TrimMax || s.trim > SettingBounds::TrimMax) return false;
  if (s.tmin < SettingBounds::TiltMin || s.tmax > SettingBounds::TiltMax || s.tmin >= s.tmax) return false;
  return s.rest >= s.tmin && s.rest <= s.tmax;
}

SettingError applySetting(Settings& s, SettingKey key, const char* text) {
  if (text == nullptr) return SettingError::Value;
  switch (key) {
    case SettingKey::Ssid:
      return setText(s.ssid, sizeof(s.ssid), text, 1);
    case SettingKey::Pass:
      return setText(s.pass, sizeof(s.pass), text, 8);
    case SettingKey::Cpm: {
      float v;
      if (!parseStrictFloat(text, v)) return SettingError::Value;
      if (v != 0.0f && (v < SettingBounds::CpmMin || v > SettingBounds::CpmMax)) return SettingError::Range;
      s.cpm = v;
      return SettingError::None;
    }
    case SettingKey::Edge:
      return setInt(s.edge, text, SettingBounds::EdgeMin, SettingBounds::EdgeMax);
    case SettingKey::Stop:
      return setInt(s.stop, text, SettingBounds::StopMin, SettingBounds::StopMax);
    case SettingKey::Tmin: {
      int v = s.tmin;
      SettingError e = setInt(v, text, SettingBounds::TiltMin, SettingBounds::TiltMax);
      if (e != SettingError::None) return e;
      if (v >= s.tmax || v > s.rest) return SettingError::Range;
      s.tmin = v;
      return SettingError::None;
    }
    case SettingKey::Tmax: {
      int v = s.tmax;
      SettingError e = setInt(v, text, SettingBounds::TiltMin, SettingBounds::TiltMax);
      if (e != SettingError::None) return e;
      if (v <= s.tmin || v < s.rest) return SettingError::Range;
      s.tmax = v;
      return SettingError::None;
    }
    case SettingKey::Trim:
      return setInt(s.trim, text, -SettingBounds::TrimMax, SettingBounds::TrimMax);
    case SettingKey::Rest:
      return setInt(s.rest, text, s.tmin, s.tmax);
  }
  return SettingError::Value;
}

const char* settingErrorReason(SettingError error) {
  switch (error) {
    case SettingError::None:
      return "ok";
    case SettingError::Value:
      return "value";
    case SettingError::Range:
      return "range";
  }
  return "value";
}

void formatSettingValue(const Settings& s, SettingKey key, TextWriter& out) {
  switch (key) {
    case SettingKey::Ssid:
      out.put(s.ssid[0] ? s.ssid : kEmptyMarker);
      return;
    case SettingKey::Pass:
      out.put(s.pass[0] ? "*" : kEmptyMarker);
      return;
    case SettingKey::Cpm:
      out.putFixed(s.cpm, 3);
      return;
    case SettingKey::Edge:
      out.putInt(s.edge);
      return;
    case SettingKey::Stop:
      out.putInt(s.stop);
      return;
    case SettingKey::Tmin:
      out.putInt(s.tmin);
      return;
    case SettingKey::Tmax:
      out.putInt(s.tmax);
      return;
    case SettingKey::Trim:
      out.putInt(s.trim);
      return;
    case SettingKey::Rest:
      out.putInt(s.rest);
      return;
  }
}

}
