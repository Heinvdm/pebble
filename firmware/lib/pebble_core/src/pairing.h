#pragma once

#include <stdint.h>

namespace pebble {

struct PairingTiming {
  uint32_t holdMs = 3000;
  uint32_t openMs = 120000;
};

class PairingWindow {
 public:
  enum class Change : uint8_t { None, Opened, Closed };

  explicit PairingWindow(const PairingTiming& timing = PairingTiming()) : timing_(timing) {}

  Change update(uint32_t now, bool bumperHeld, bool wheelsStill, bool proven);
  bool open() const { return open_; }

 private:
  PairingTiming timing_;
  bool open_ = false;
  bool holding_ = false;
  bool spent_ = false;
  uint32_t heldSince_ = 0;
  uint32_t openedAt_ = 0;
};

class RateLimiter {
 public:
  RateLimiter(uint32_t perSecond, uint32_t burst) : intervalMs_(1000u / (perSecond ? perSecond : 1)), burst_(burst) {}

  bool take(uint32_t now);

 private:
  uint32_t intervalMs_;
  uint32_t burst_;
  uint32_t tokens_ = 0;
  uint32_t last_ = 0;
  bool started_ = false;
};

}
