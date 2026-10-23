#pragma once

#include <stdint.h>

namespace pebble {

struct TiltLimits {
  int minDeg = -35;
  int maxDeg = 90;
  int trimDeg = 0;
};

int tiltPulseMicros(float tiltDeg, int trimDeg, int direction, int centreUs = 1500, int usPer90 = 1000,
                    int minUs = 500, int maxUs = 2500);

class TiltSlew {
 public:
  explicit TiltSlew(float degreesPerSecond = 120.0f) : rate_(degreesPerSecond) {}

  void configure(const TiltLimits& limits);
  void setTarget(float degrees);
  void jumpTo(float degrees);
  float update(uint32_t dtMs);

  float position() const { return position_; }
  float target() const { return target_; }
  const TiltLimits& limits() const { return limits_; }

 private:
  float clamp(float degrees) const;

  float rate_;
  TiltLimits limits_;
  float position_ = 0.0f;
  float target_ = 0.0f;
};

}
