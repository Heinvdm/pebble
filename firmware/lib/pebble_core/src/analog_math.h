#pragma once

#include <stdint.h>

namespace pebble {

enum class BumpSample : uint8_t { None = 0, Left = 1, Right = 2, Both = 3, Fault = 4 };

struct BumpThresholds {
  int faultBelowMv = 400;
  int bothBelowMv = 960;
  int leftBelowMv = 1520;
  int rightBelowMv = 2640;
};

BumpSample classifyBumpMv(int millivolts, const BumpThresholds& thresholds = BumpThresholds());

class LowPassFilter {
 public:
  explicit LowPassFilter(float timeConstantMs) : tauMs_(timeConstantMs) {}

  float update(float sample, uint32_t dtMs);
  bool primed() const { return primed_; }
  float value() const { return value_; }
  void reset() { primed_ = false; }

 private:
  float tauMs_;
  bool primed_ = false;
  float value_ = 0.0f;
};

int packMillivolts(int adcMillivolts, float dividerRatio, float calibration);

}
