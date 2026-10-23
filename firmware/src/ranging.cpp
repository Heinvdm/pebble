#include "ranging.h"

#include <Arduino.h>
#include <Wire.h>

#include "config.h"

namespace pebble {

namespace {

constexpr uint8_t kRangeCompleteCode = 11;
constexpr uint32_t kXshutSettleMs = 3;
constexpr uint32_t kHaltMs = 50;

bool probe(uint8_t address) {
  Wire.beginTransmission(address);
  return Wire.endTransmission() == 0;
}

void holdDropOff() {
  pinMode(pins::DropXshut, OUTPUT);
  digitalWrite(pins::DropXshut, LOW);
}

void releaseDropFloating() { pinMode(pins::DropXshut, INPUT); }

void releaseDropDriven() {
  pinMode(pins::DropXshut, OUTPUT);
  digitalWrite(pins::DropXshut, HIGH);
}

}

void RangeSensors::begin() {
  front_.budgetUs = ranging::FrontBudgetUs;
  drop_.budgetUs = ranging::DropBudgetUs;
  holdDropOff();
  startSequence(millis());
  while (phase_ != Phase::Running) {
    delay(1);
    advance(millis());
  }
}

void RangeSensors::markFailed(Channel& channel) {
  channel.running = false;
  channel.reading = RangeReading::unknown();
}

uint8_t RangeSensors::faults() const {
  uint8_t bits = 0;
  if (!front_.running) bits |= FaultBit::Front;
  if (!drop_.running) bits |= FaultBit::Drop;
  return bits;
}

bool RangeSensors::configure(Channel& channel) {
  channel.device.setTimeout(ranging::SensorTimeoutMs);
  if (!channel.device.init(true)) return false;
  if (!channel.device.setMeasurementTimingBudget(channel.budgetUs)) return false;
  channel.device.startContinuous(0);
  return channel.device.last_status == 0;
}

bool RangeSensors::startFront() {
  if (probe(ranging::FrontAddress)) {
    front_.device.setAddress(ranging::FrontAddress);
  } else if (probe(ranging::DefaultAddress)) {
    front_.device.setAddress(ranging::FrontAddress);
    if (!probe(ranging::FrontAddress)) return false;
  } else {
    return false;
  }
  return configure(front_);
}

bool RangeSensors::startDrop() {
  if (!probe(ranging::DefaultAddress)) return false;
  drop_.device.setAddress(ranging::DefaultAddress);
  return configure(drop_);
}

void RangeSensors::enter(Phase phase, uint32_t waitMs) {
  phase_ = phase;
  phaseSince_ = millis();
  phaseWaitMs_ = waitMs;
}

void RangeSensors::startSequence(uint32_t now) {
  lastAttempt_ = now;
  markFailed(front_);
  markFailed(drop_);
  holdDropOff();
  Wire.end();
  Wire.begin(pins::Sda, pins::Scl, ranging::I2cHz);
  Wire.setTimeOut(ranging::I2cTimeoutMs);
  enter(Phase::HoldDrop, kXshutSettleMs);
}

void RangeSensors::finishSequence(uint32_t now) {
  front_.lastSample = now;
  drop_.lastSample = now;
  lastAttempt_ = now;
  phase_ = Phase::Running;
}

void RangeSensors::bringUpFront() {
  front_.running = startFront();
  releaseDropFloating();
  enter(Phase::ReleaseDrop, kXshutSettleMs);
}

void RangeSensors::advance(uint32_t now) {
  if (static_cast<uint32_t>(now - phaseSince_) < phaseWaitMs_) return;
  switch (phase_) {
    case Phase::HoldDrop:
      if (probe(ranging::FrontAddress)) {
        front_.device.setAddress(ranging::FrontAddress);
        front_.device.writeReg(VL53L0X::SYSRANGE_START, 0x01);
        enter(Phase::HaltFront, kHaltMs);
        return;
      }
      bringUpFront();
      return;
    case Phase::HaltFront:
      front_.device.writeReg(VL53L0X::SYSTEM_INTERRUPT_CLEAR, 0x01);
      bringUpFront();
      return;
    case Phase::ReleaseDrop:
      if (probe(ranging::DefaultAddress)) {
        drop_.running = startDrop();
        finishSequence(millis());
        return;
      }
      releaseDropDriven();
      enter(Phase::DriveDrop, kXshutSettleMs);
      return;
    case Phase::DriveDrop:
      drop_.running = startDrop();
      finishSequence(millis());
      return;
    case Phase::Running:
      return;
  }
}

void RangeSensors::pollChannel(Channel& channel, uint32_t now) {
  if (!channel.running) return;
  VL53L0X& dev = channel.device;
  uint8_t interrupt = dev.readReg(VL53L0X::RESULT_INTERRUPT_STATUS);
  if (dev.last_status != 0) {
    markFailed(channel);
    return;
  }
  if ((interrupt & 0x07) == 0) {
    if (static_cast<uint32_t>(now - channel.lastSample) > ranging::StaleMs) markFailed(channel);
    return;
  }
  uint8_t rangeStatus = dev.readReg(VL53L0X::RESULT_RANGE_STATUS);
  bool ok = dev.last_status == 0;
  uint16_t mm = dev.readReg16Bit(VL53L0X::RESULT_RANGE_STATUS + 10);
  ok = ok && dev.last_status == 0;
  dev.writeReg(VL53L0X::SYSTEM_INTERRUPT_CLEAR, 0x01);
  ok = ok && dev.last_status == 0;
  if (!ok) {
    markFailed(channel);
    return;
  }
  uint8_t code = static_cast<uint8_t>((rangeStatus & 0x78) >> 3);
  if (code >= 1 && code <= 3) {
    markFailed(channel);
    return;
  }
  channel.lastSample = now;
  bool valid = code == kRangeCompleteCode && mm > 0 && mm < ranging::NoTargetMm;
  channel.reading = valid ? RangeReading::valid(mm) : RangeReading::noTarget();
}

void RangeSensors::poll(uint32_t now) {
  if (phase_ != Phase::Running) {
    advance(now);
    return;
  }
  if (faults() != 0 && static_cast<uint32_t>(now - lastAttempt_) >= ranging::RetryMs) {
    startSequence(now);
    return;
  }
  if (static_cast<uint32_t>(now - lastPoll_) < ranging::PollIntervalMs) return;
  lastPoll_ = now;
  pollChannel(pollFront_ ? front_ : drop_, now);
  pollFront_ = !pollFront_;
}

}
