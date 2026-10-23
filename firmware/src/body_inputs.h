#pragma once

#include <stdint.h>

#include "analog_math.h"
#include "config.h"
#include "debouncer.h"
#include "events.h"

namespace pebble {

class BumpSensor {
 public:
  void begin();
  void poll(uint32_t now);
  uint8_t state() const { return state_; }
  bool fault() const { return faultDebounce_.state(); }

 private:
  Debouncer<BumpSample> sampleDebounce_{BumpSample::None, analog::BumpDebounceMs};
  Debouncer<bool> faultDebounce_{false, analog::BumpFaultMs};
  uint32_t lastSample_ = 0;
  uint8_t state_ = 0;
};

class PackMonitor {
 public:
  void begin();
  void poll(uint32_t now);
  int millivolts() const { return millivolts_; }
  bool valid() const { return filter_.primed(); }
  bool fault() const { return faultDebounce_.state(); }

 private:
  LowPassFilter filter_{analog::PackFilterTauMs};
  Debouncer<bool> faultDebounce_{false, analog::PackFaultMs};
  uint32_t lastSample_ = 0;
  int millivolts_ = 0;
};

class DockSensor {
 public:
  void begin();
  void poll(uint32_t now, EventQueue& events);
  bool seated() const { return debounce_.state(); }

 private:
  Debouncer<bool> debounce_{false, dock::DebounceMs};
};

}
