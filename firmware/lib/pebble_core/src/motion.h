#pragma once

#include <stdint.h>

#include "drive.h"
#include "events.h"
#include "protocol.h"
#include "reflexes.h"

namespace pebble {

class MotionCore {
 public:
  enum class Outcome : uint8_t { NotMotion, Accepted, NeedsCalibration };

  MotionCore();
  MotionCore(const DriveTuning& drive, const ReflexTuning& reflex);

  void configure(const ReflexSettings& settings);
  Outcome command(const Command& command, uint32_t now);
  Wheels stopNow(uint32_t now);
  void halt();
  Wheels tick(uint32_t now, uint32_t dtMs, const ReflexSense& sense, Wheels applied, EventQueue& events);

  uint8_t flags() const { return reflexes_.flags(); }
  const Reflexes& reflexes() const { return reflexes_; }
  const DriveController& drive() const { return drive_; }

 private:
  DriveController drive_;
  Reflexes reflexes_;
  float countsPerMm_ = 0.0f;
};

}
