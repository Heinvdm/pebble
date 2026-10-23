#include "speed_pi.h"

namespace pebble {

namespace {

float clampFloat(float v, float lo, float hi) {
  if (v < lo) return lo;
  if (v > hi) return hi;
  return v;
}

}

SpeedPi::SpeedPi(const PiGains& gains) : gains_(gains) {}

float SpeedPi::update(float targetMmS, float measuredMmS, float dtSeconds, bool allowIntegrate) {
  if (targetMmS == 0.0f) {
    integral_ = 0.0f;
    return 0.0f;
  }
  float error = targetMmS - measuredMmS;
  float base = gains_.feedForward * targetMmS + gains_.kp * error;
  if (allowIntegrate && dtSeconds > 0.0f) {
    float candidate = clampFloat(integral_ + gains_.ki * error * dtSeconds, -gains_.integralLimit, gains_.integralLimit);
    float raw = base + candidate;
    bool pushesSaturation = (raw > gains_.outputLimit && error > 0.0f) || (raw < -gains_.outputLimit && error < 0.0f);
    if (!pushesSaturation) integral_ = candidate;
  }
  return clampFloat(base + integral_, -gains_.outputLimit, gains_.outputLimit);
}

float SpeedEstimator::update(int64_t count, uint32_t dtMs, float countsPerMm) {
  if (!primed_) {
    primed_ = true;
    last_ = count;
    value_ = 0.0f;
    return value_;
  }
  int64_t delta = count - last_;
  last_ = count;
  if (dtMs == 0 || countsPerMm <= 0.0f) {
    value_ = 0.0f;
    return value_;
  }
  float raw = static_cast<float>(delta) / countsPerMm * 1000.0f / static_cast<float>(dtMs);
  value_ += alpha_ * (raw - value_);
  return value_;
}

void SpeedEstimator::rebase(int64_t count) {
  primed_ = true;
  last_ = count;
}

}
