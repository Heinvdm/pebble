#include "encoders.h"

#include <ESP32Encoder.h>

#include "config.h"

namespace pebble {

namespace {

ESP32Encoder leftEncoder;
ESP32Encoder rightEncoder;

}

void Encoders::begin() {
  ESP32Encoder::useInternalWeakPullResistors = puType::up;
  leftEncoder.attachFullQuad(pins::LeftEncoderA, pins::LeftEncoderB);
  rightEncoder.attachFullQuad(pins::RightEncoderA, pins::RightEncoderB);
  leftEncoder.setFilter(encoder::GlitchFilter);
  rightEncoder.setFilter(encoder::GlitchFilter);
  leftEncoder.clearCount();
  rightEncoder.clearCount();
}

void Encoders::read(int64_t& left, int64_t& right) {
  int64_t l = leftEncoder.getCount();
  int64_t r = rightEncoder.getCount();
  left = encoder::LeftReversed ? -l : l;
  right = encoder::RightReversed ? -r : r;
}

}
