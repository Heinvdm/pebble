#include "settings_store.h"

#include <Preferences.h>
#include <string.h>

namespace pebble {

namespace {

constexpr const char* kNamespace = "pebble";
constexpr const char* kLinkKeyName = "lkey";

Preferences prefs;

void loadKey(Settings& settings, SettingKey key) {
  const char* name = settingName(key);
  if (!prefs.isKey(name)) return;
  char text[Settings::kPassSize + 8] = {0};
  switch (key) {
    case SettingKey::Ssid:
    case SettingKey::Pass:
      prefs.getString(name, text, sizeof(text));
      if (text[0] == '\0') return;
      break;
    case SettingKey::Cpm: {
      TextWriter w(text, sizeof(text));
      w.putFixed(prefs.getFloat(name, settings.cpm), 4);
      break;
    }
    default: {
      TextWriter w(text, sizeof(text));
      w.putInt(prefs.getInt(name, 0));
      break;
    }
  }
  Settings candidate = settings;
  if (applySetting(candidate, key, text) == SettingError::None) settings = candidate;
}

}

bool SettingsStore::begin() {
  ready_ = prefs.begin(kNamespace, false);
  return ready_;
}

void SettingsStore::load(Settings& settings) {
  if (!ready_) return;
  for (size_t i = 0; i < kSettingCount; ++i) {
    SettingKey key = settingAt(i);
    if (key == SettingKey::Tmin || key == SettingKey::Tmax || key == SettingKey::Rest) continue;
    loadKey(settings, key);
  }
  int tmin = prefs.getInt(settingName(SettingKey::Tmin), settings.tmin);
  int tmax = prefs.getInt(settingName(SettingKey::Tmax), settings.tmax);
  int rest = prefs.getInt(settingName(SettingKey::Rest), settings.rest);
  if (!applyTiltRange(settings, tmin, tmax, rest)) {
    Settings defaults;
    applyTiltRange(settings, defaults.tmin, defaults.tmax, defaults.rest);
  }
}

bool SettingsStore::loadLinkKey(uint8_t* out, size_t length) {
  if (!ready_ || !prefs.isKey(kLinkKeyName)) return false;
  if (prefs.getBytesLength(kLinkKeyName) != length) return false;
  return prefs.getBytes(kLinkKeyName, out, length) == length;
}

bool SettingsStore::saveLinkKey(const uint8_t* key, size_t length) {
  if (!ready_) return false;
  return prefs.putBytes(kLinkKeyName, key, length) == length;
}

bool SettingsStore::clearLinkKey() {
  if (!ready_) return false;
  if (!prefs.isKey(kLinkKeyName)) return true;
  return prefs.remove(kLinkKeyName);
}

bool SettingsStore::save(const Settings& settings, SettingKey key) {
  if (!ready_) return false;
  const char* name = settingName(key);
  switch (key) {
    case SettingKey::Ssid:
      return prefs.putString(name, settings.ssid) == strlen(settings.ssid);
    case SettingKey::Pass:
      return prefs.putString(name, settings.pass) == strlen(settings.pass);
    case SettingKey::Cpm:
      return prefs.putFloat(name, settings.cpm) == sizeof(float);
    case SettingKey::Edge:
      return prefs.putInt(name, settings.edge) == sizeof(int32_t);
    case SettingKey::Stop:
      return prefs.putInt(name, settings.stop) == sizeof(int32_t);
    case SettingKey::Tmin:
      return prefs.putInt(name, settings.tmin) == sizeof(int32_t);
    case SettingKey::Tmax:
      return prefs.putInt(name, settings.tmax) == sizeof(int32_t);
    case SettingKey::Trim:
      return prefs.putInt(name, settings.trim) == sizeof(int32_t);
    case SettingKey::Rest:
      return prefs.putInt(name, settings.rest) == sizeof(int32_t);
  }
  return false;
}

}
