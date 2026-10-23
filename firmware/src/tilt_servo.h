#pragma once

#include <stdint.h>

#include "tilt.h"

namespace pebble {

class TiltServo {
 public:
  void begin(const TiltLimits& limits, int restDeg);
  void configure(const TiltLimits& limits);
  void setTarget(int degrees) { slew_.setTarget(static_cast<float>(degrees)); }
  void poll(uint32_t now);
  int position() const;

 private:
  void writePulse();

  TiltSlew slew_;
  uint32_t lastUpdate_ = 0;
  int lastPulseUs_ = -1;
};

}
