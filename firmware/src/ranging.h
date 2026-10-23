#pragma once

#include <VL53L0X.h>

#include "reflexes.h"

namespace pebble {

class RangeSensors {
 public:
  void begin();
  void poll(uint32_t now);

  RangeReading front() const { return front_.reading; }
  RangeReading down() const { return drop_.reading; }
  uint8_t faults() const;

 private:
  enum class Phase : uint8_t { Running, HoldDrop, HaltFront, ReleaseDrop, DriveDrop };

  struct Channel {
    VL53L0X device;
    RangeReading reading;
    uint32_t lastSample = 0;
    uint32_t budgetUs = 33000;
    bool running = false;
  };

  void startSequence(uint32_t now);
  void advance(uint32_t now);
  void finishSequence(uint32_t now);
  void enter(Phase phase, uint32_t waitMs);
  void bringUpFront();
  bool startFront();
  bool startDrop();
  bool configure(Channel& channel);
  void pollChannel(Channel& channel, uint32_t now);
  void markFailed(Channel& channel);

  Channel front_;
  Channel drop_;
  Phase phase_ = Phase::Running;
  uint32_t phaseSince_ = 0;
  uint32_t phaseWaitMs_ = 0;
  uint32_t lastPoll_ = 0;
  uint32_t lastAttempt_ = 0;
  bool pollFront_ = true;
};

}
