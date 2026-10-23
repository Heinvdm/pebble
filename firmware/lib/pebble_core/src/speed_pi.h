#pragma once

#include <stdint.h>

namespace pebble {

struct PiGains {
  float feedForward = 4.5f;
  float kp = 2.0f;
  float ki = 8.0f;
  float integralLimit = 600.0f;
  float outputLimit = 1000.0f;
};

class SpeedPi {
 public:
  explicit SpeedPi(const PiGains& gains = PiGains());

  float update(float targetMmS, float measuredMmS, float dtSeconds, bool allowIntegrate);
  void reset() { integral_ = 0.0f; }
  float integral() const { return integral_; }

 private:
  PiGains gains_;
  float integral_ = 0.0f;
};

class SpeedEstimator {
 public:
  explicit SpeedEstimator(float alpha = 0.35f) : alpha_(alpha) {}

  float update(int64_t count, uint32_t dtMs, float countsPerMm);
  void rebase(int64_t count);
  float value() const { return value_; }

 private:
  float alpha_;
  bool primed_ = false;
  int64_t last_ = 0;
  float value_ = 0.0f;
};

}
