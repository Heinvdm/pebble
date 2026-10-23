#include "analog_math.h"

namespace pebble {

BumpSample classifyBumpMv(int mv, const BumpThresholds& t) {
  if (mv < t.faultBelowMv) return BumpSample::Fault;
  if (mv < t.bothBelowMv) return BumpSample::Both;
  if (mv < t.leftBelowMv) return BumpSample::Left;
  if (mv < t.rightBelowMv) return BumpSample::Right;
  return BumpSample::None;
}

float LowPassFilter::update(float sample, uint32_t dtMs) {
  if (!primed_) {
    primed_ = true;
    value_ = sample;
    return value_;
  }
  float alpha = tauMs_ <= 0.0f ? 1.0f : static_cast<float>(dtMs) / (tauMs_ + static_cast<float>(dtMs));
  value_ += alpha * (sample - value_);
  return value_;
}

int packMillivolts(int adcMillivolts, float dividerRatio, float calibration) {
  float mv = static_cast<float>(adcMillivolts) * dividerRatio * calibration;
  return static_cast<int>(mv + 0.5f);
}

}
