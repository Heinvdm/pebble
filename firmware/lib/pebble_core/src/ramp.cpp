#include "ramp.h"

namespace pebble {

namespace {

float approach(float from, float to, float budget) {
  if (to > from) return (to - from > budget) ? from + budget : to;
  return (from - to > budget) ? from - budget : to;
}

bool sameSideOrZero(float a, float b) { return (a >= 0.0f && b >= 0.0f) || (a <= 0.0f && b <= 0.0f); }

float magnitude(float v) { return v < 0.0f ? -v : v; }

}

RampLimiter::RampLimiter(float ratePerSecond, Mode mode) : rate_(ratePerSecond), mode_(mode) {}

void RampLimiter::reset(float value) { value_ = value; }

float RampLimiter::step(float target, uint32_t dtMs) {
  float budget = rate_ * static_cast<float>(dtMs) / 1000.0f;
  if (mode_ == Mode::Symmetric) {
    value_ = approach(value_, target, budget);
    return value_;
  }
  if (!sameSideOrZero(value_, target)) value_ = 0.0f;
  if (magnitude(target) <= magnitude(value_)) {
    value_ = target;
    return value_;
  }
  value_ = approach(value_, target, budget);
  return value_;
}

}
