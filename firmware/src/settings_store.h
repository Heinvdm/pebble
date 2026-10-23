#pragma once

#include <stddef.h>
#include <stdint.h>

#include "settings_model.h"

namespace pebble {

class SettingsStore {
 public:
  bool begin();
  void load(Settings& settings);
  bool save(const Settings& settings, SettingKey key);
  bool loadLinkKey(uint8_t* out, size_t length);
  bool saveLinkKey(const uint8_t* key, size_t length);
  bool clearLinkKey();

 private:
  bool ready_ = false;
};

}
