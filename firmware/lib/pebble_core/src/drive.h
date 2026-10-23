#pragma once

#include <stdint.h>

#include "ramp.h"
#include "reflexes.h"
#include "speed_pi.h"

namespace pebble {

struct DriveTuning {
  float powerRatePerSecond = 2000.0f;
  float outputRatePerSecond = 2000.0f;
  float speedRatePerSecond = 600.0f;
  float speedFilterAlpha = 0.35f;
  PiGains gains;
};

enum class DriveMode : uint8_t { Idle, Power, Speed };

class DriveController {
 public:
  explicit DriveController(const DriveTuning& tuning = DriveTuning());

  void commandPower(int left, int right);
  bool commandSpeed(int left, int right, float countsPerMm);
  void stop();

  DriveMode mode() const { return mode_; }
  bool commandActive() const;
  Wheels target() const { return target_; }

  Wheels desired(uint32_t dtMs, int64_t encLeft, int64_t encRight, float countsPerMm);
  Wheels finish(Wheels desired, const ReflexLimits& limits, uint32_t dtMs);

  Wheels output() const { return output_; }
  float speedLeft() const { return speedLeft_.value(); }
  float speedRight() const { return speedRight_.value(); }

 private:
  struct Side {
    RampLimiter power;
    RampLimiter setpoint;
    RampLimiter output;
    SpeedPi pi;
    bool limited = false;

    Side(const DriveTuning& t)
        : power(t.powerRatePerSecond, RampLimiter::Mode::Symmetric),
          setpoint(t.speedRatePerSecond, RampLimiter::Mode::Symmetric),
          output(t.outputRatePerSecond, RampLimiter::Mode::InstantTowardZero),
          pi(t.gains) {}
  };

  int sideDesired(Side& side, int target, float measured, uint32_t dtMs);

  DriveTuning tuning_;
  DriveMode mode_ = DriveMode::Idle;
  Wheels target_;
  Wheels output_;
  Side left_;
  Side right_;
  SpeedEstimator speedLeft_;
  SpeedEstimator speedRight_;
};

}
