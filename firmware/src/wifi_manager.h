#pragma once

#include <stdint.h>

#include "settings_model.h"

namespace pebble {

class WifiManager {
 public:
  void begin(const Settings& settings);
  void poll(uint32_t now);
  bool enabled() const { return enabled_; }
  bool connected() const;

 private:
  void connect(uint32_t now);

  Settings credentials_;
  bool enabled_ = false;
  bool mdnsStarted_ = false;
  bool wasConnected_ = false;
  uint32_t lastAttempt_ = 0;
};

}
