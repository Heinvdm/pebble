#pragma once

#include <stdint.h>

namespace pebble {

class RampLimiter {
 public:
  enum class Mode : uint8_t { Symmetric, InstantTowardZero };

  RampLimiter(float ratePerSecond, Mode mode);

  float step(float target, uint32_t dtMs);
  void reset(float value = 0.0f);
  float value() const { return value_; }
  void setRate(float ratePerSecond) { rate_ = ratePerSecond; }

 private:
  float rate_;
  Mode mode_;
  float value_ = 0.0f;
};

}
