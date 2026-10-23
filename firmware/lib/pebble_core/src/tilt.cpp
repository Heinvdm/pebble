#include "tilt.h"

namespace pebble {

int tiltPulseMicros(float tiltDeg, int trimDeg, int direction, int centreUs, int usPer90, int minUs, int maxUs) {
  float servoDeg = (tiltDeg + static_cast<float>(trimDeg)) * (direction < 0 ? -1.0f : 1.0f);
  float us = static_cast<float>(centreUs) + servoDeg * static_cast<float>(usPer90) / 90.0f;
  int rounded = static_cast<int>(us < 0.0f ? us - 0.5f : us + 0.5f);
  if (rounded < minUs) return minUs;
  if (rounded > maxUs) return maxUs;
  return rounded;
}

void TiltSlew::configure(const TiltLimits& limits) {
  limits_ = limits;
  if (limits_.minDeg > limits_.maxDeg) {
    int t = limits_.minDeg;
    limits_.minDeg = limits_.maxDeg;
    limits_.maxDeg = t;
  }
  target_ = clamp(target_);
}

float TiltSlew::clamp(float degrees) const {
  if (degrees < static_cast<float>(limits_.minDeg)) return static_cast<float>(limits_.minDeg);
  if (degrees > static_cast<float>(limits_.maxDeg)) return static_cast<float>(limits_.maxDeg);
  return degrees;
}

void TiltSlew::setTarget(float degrees) { target_ = clamp(degrees); }

void TiltSlew::jumpTo(float degrees) {
  target_ = clamp(degrees);
  position_ = target_;
}

float TiltSlew::update(uint32_t dtMs) {
  float budget = rate_ * static_cast<float>(dtMs) / 1000.0f;
  float diff = target_ - position_;
  if (diff > budget) {
    position_ += budget;
  } else if (diff < -budget) {
    position_ -= budget;
  } else {
    position_ = target_;
  }
  return position_;
}

}
