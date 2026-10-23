#include "drive.h"

#include <initializer_list>

namespace pebble {

namespace {

int roundToInt(float v) { return static_cast<int>(v < 0.0f ? v - 0.5f : v + 0.5f); }

}

DriveController::DriveController(const DriveTuning& tuning)
    : tuning_(tuning),
      left_(tuning),
      right_(tuning),
      speedLeft_(tuning.speedFilterAlpha),
      speedRight_(tuning.speedFilterAlpha) {}

void DriveController::commandPower(int left, int right) {
  if (mode_ != DriveMode::Power) {
    left_.power.reset(left_.output.value());
    right_.power.reset(right_.output.value());
  }
  mode_ = DriveMode::Power;
  target_ = Wheels{left, right};
}

bool DriveController::commandSpeed(int left, int right, float countsPerMm) {
  if (countsPerMm <= 0.0f) return false;
  if (mode_ != DriveMode::Speed) {
    left_.setpoint.reset(speedLeft_.value());
    right_.setpoint.reset(speedRight_.value());
    left_.pi.reset();
    right_.pi.reset();
  }
  mode_ = DriveMode::Speed;
  target_ = Wheels{left, right};
  return true;
}

void DriveController::stop() {
  mode_ = DriveMode::Idle;
  target_ = Wheels{};
  for (Side* side : {&left_, &right_}) {
    side->power.reset(0.0f);
    side->setpoint.reset(0.0f);
    side->pi.reset();
    side->limited = false;
  }
}

bool DriveController::commandActive() const {
  return mode_ != DriveMode::Idle && (target_.left != 0 || target_.right != 0);
}

int DriveController::sideDesired(Side& side, int target, float measured, uint32_t dtMs) {
  if (mode_ == DriveMode::Power) return roundToInt(side.power.step(static_cast<float>(target), dtMs));
  float setpoint = side.setpoint.step(static_cast<float>(target), dtMs);
  if (target == 0 && (setpoint > -1.0f && setpoint < 1.0f)) setpoint = 0.0f;
  float power = side.pi.update(setpoint, measured, static_cast<float>(dtMs) / 1000.0f, !side.limited);
  return roundToInt(power);
}

Wheels DriveController::desired(uint32_t dtMs, int64_t encLeft, int64_t encRight, float countsPerMm) {
  float measuredLeft = speedLeft_.update(encLeft, dtMs, countsPerMm);
  float measuredRight = speedRight_.update(encRight, dtMs, countsPerMm);
  if (mode_ == DriveMode::Speed && countsPerMm <= 0.0f) stop();
  if (mode_ == DriveMode::Idle) return Wheels{};
  return Wheels{sideDesired(left_, target_.left, measuredLeft, dtMs),
                sideDesired(right_, target_.right, measuredRight, dtMs)};
}

Wheels DriveController::finish(Wheels desired, const ReflexLimits& limits, uint32_t dtMs) {
  Wheels shaped = applyLimits(desired, limits);
  output_.left = roundToInt(left_.output.step(static_cast<float>(shaped.left), dtMs));
  output_.right = roundToInt(right_.output.step(static_cast<float>(shaped.right), dtMs));
  left_.limited = output_.left != desired.left;
  right_.limited = output_.right != desired.right;
  return output_;
}

}
