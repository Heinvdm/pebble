#include "tilt_servo.h"

#include <Arduino.h>

#include "config.h"

namespace pebble {

namespace {

constexpr uint32_t kPeriodUs = 1000000u / servo::PwmHz;
constexpr uint32_t kDutyRange = 1u << servo::PwmBits;

}

void TiltServo::begin(const TiltLimits& limits, int restDeg) {
  slew_ = TiltSlew(servo::SlewDegPerSecond);
  slew_.configure(limits);
  slew_.jumpTo(static_cast<float>(restDeg));
  ledcSetup(servo::Channel, servo::PwmHz, servo::PwmBits);
  ledcAttachPin(pins::Servo, servo::Channel);
  lastUpdate_ = millis();
  writePulse();
}

void TiltServo::configure(const TiltLimits& limits) {
  slew_.configure(limits);
  writePulse();
}

void TiltServo::poll(uint32_t now) {
  uint32_t dt = now - lastUpdate_;
  if (dt < timing::ServoMs) return;
  lastUpdate_ = now;
  slew_.update(dt);
  writePulse();
}

int TiltServo::position() const {
  float p = slew_.position();
  return static_cast<int>(p < 0.0f ? p - 0.5f : p + 0.5f);
}

void TiltServo::writePulse() {
  int us = tiltPulseMicros(slew_.position(), slew_.limits().trimDeg, servo::Direction, servo::CentreUs,
                           servo::UsPer90Deg, servo::MinUs, servo::MaxUs);
  if (us == lastPulseUs_) return;
  lastPulseUs_ = us;
  uint32_t duty = static_cast<uint32_t>((static_cast<uint64_t>(us) * kDutyRange + kPeriodUs / 2) / kPeriodUs);
  ledcWrite(servo::Channel, duty);
}

}
