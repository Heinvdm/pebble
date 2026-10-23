#pragma once

#include <stddef.h>
#include <stdint.h>

#include "text_writer.h"

namespace pebble {

struct Settings {
  static constexpr size_t kSsidSize = 33;
  static constexpr size_t kPassSize = 65;

  char ssid[kSsidSize] = {0};
  char pass[kPassSize] = {0};
  float cpm = 0.0f;
  int edge = 75;
  int stop = 60;
  int tmin = -35;
  int tmax = 90;
  int trim = 0;
  int rest = 8;
};

enum class SettingKey : uint8_t { Ssid, Pass, Cpm, Edge, Stop, Tmin, Tmax, Trim, Rest };

constexpr size_t kSettingCount = 9;

enum class SettingError : uint8_t { None, Value, Range };

namespace SettingBounds {
constexpr int EdgeMin = 40;
constexpr int EdgeMax = 150;
constexpr int StopMin = 30;
constexpr int StopMax = 300;
constexpr float CpmMin = 5.0f;
constexpr float CpmMax = 60.0f;
constexpr int TiltMin = -35;
constexpr int TiltMax = 90;
constexpr int TrimMax = 10;
}

SettingKey settingAt(size_t index);
const char* settingName(SettingKey key);
bool settingFromName(const char* name, SettingKey& out);
SettingError applySetting(Settings& settings, SettingKey key, const char* text);
const char* settingErrorReason(SettingError error);
void formatSettingValue(const Settings& settings, SettingKey key, TextWriter& out);
bool settingNeedsReboot(SettingKey key);
bool sameSetting(const Settings& a, const Settings& b, SettingKey key);
bool applyTiltRange(Settings& settings, int tmin, int tmax, int rest);
bool settingsSafe(const Settings& settings);

}
