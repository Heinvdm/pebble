#include "motors.h"

#include <Arduino.h>

#include "config.h"

namespace pebble {

namespace {

constexpr uint32_t kFullDuty = (1u << motor::PwmBits) - 1u;

void setupChannel(uint8_t channel, int pin) {
  ledcSetup(channel, motor::PwmHz, motor::PwmBits);
  ledcAttachPin(pin, channel);
  ledcWrite(channel, kFullDuty);
}

}

void Motors::begin() {
  left_ = Bridge{motor::ChannelLeftIn1, motor::ChannelLeftIn2, motor::LeftReversed};
  right_ = Bridge{motor::ChannelRightIn1, motor::ChannelRightIn2, motor::RightReversed};
  setupChannel(left_.channelIn1, pins::LeftIn1);
  setupChannel(left_.channelIn2, pins::LeftIn2);
  setupChannel(right_.channelIn1, pins::RightIn1);
  setupChannel(right_.channelIn2, pins::RightIn2);
  ready_ = true;
  brake();
}

void Motors::drive(const Bridge& bridge, int power) {
  if (power > 1000) power = 1000;
  if (power < -1000) power = -1000;
  if (bridge.reversed) power = -power;
  uint32_t magnitude = static_cast<uint32_t>(power < 0 ? -power : power);
  uint32_t offDuty = kFullDuty - (magnitude * kFullDuty + 500u) / 1000u;
  if (power > 0) {
    ledcWrite(bridge.channelIn1, kFullDuty);
    ledcWrite(bridge.channelIn2, offDuty);
  } else if (power < 0) {
    ledcWrite(bridge.channelIn1, offDuty);
    ledcWrite(bridge.channelIn2, kFullDuty);
  } else {
    ledcWrite(bridge.channelIn1, kFullDuty);
    ledcWrite(bridge.channelIn2, kFullDuty);
  }
}

void Motors::write(const Wheels& power) {
  if (!ready_) return;
  if (power.left != last_.left) drive(left_, power.left);
  if (power.right != last_.right) drive(right_, power.right);
  last_ = power;
}

void Motors::brake() {
  if (!ready_) return;
  drive(left_, 0);
  drive(right_, 0);
  last_ = Wheels{};
}

}
