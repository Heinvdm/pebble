#include "body_inputs.h"

#include <Arduino.h>
#include <esp_adc_cal.h>

#include "config.h"

namespace pebble {

namespace {

constexpr uint32_t kDefaultVrefMv = 1100;

class AdcMillivolts {
 public:
  void begin(int pin) {
    pin_ = pin;
    analogReadResolution(12);
    analogSetPinAttenuation(pin, ADC_11db);
    esp_adc_cal_characterize(ADC_UNIT_1, ADC_ATTEN_DB_12, ADC_WIDTH_BIT_12, kDefaultVrefMv, &chars_);
  }

  int read() const { return static_cast<int>(esp_adc_cal_raw_to_voltage(analogRead(pin_), &chars_)); }

 private:
  int pin_ = -1;
  esp_adc_cal_characteristics_t chars_ = {};
};

AdcMillivolts bumpAdc;
AdcMillivolts packAdc;

}

void BumpSensor::begin() {
  bumpAdc.begin(pins::Bump);
  uint32_t now = millis();
  BumpSample first = classifyBumpMv(bumpAdc.read());
  if (first != BumpSample::Fault) {
    sampleDebounce_.force(first);
    state_ = static_cast<uint8_t>(first);
  }
  lastSample_ = now;
}

void BumpSensor::poll(uint32_t now) {
  if (static_cast<uint32_t>(now - lastSample_) < analog::BumpSampleMs) return;
  lastSample_ = now;
  BumpSample sample = classifyBumpMv(bumpAdc.read());
  sampleDebounce_.update(sample, now);
  BumpSample stable = sampleDebounce_.state();
  faultDebounce_.update(stable == BumpSample::Fault, now);
  if (stable != BumpSample::Fault) state_ = static_cast<uint8_t>(stable);
}

void PackMonitor::begin() {
  packAdc.begin(pins::Pack);
  lastSample_ = millis();
  filter_.update(
      static_cast<float>(packMillivolts(packAdc.read(), analog::PackDividerRatio, analog::PackCalibration)), 0);
  millivolts_ = static_cast<int>(filter_.value() + 0.5f);
}

void PackMonitor::poll(uint32_t now) {
  uint32_t dt = now - lastSample_;
  if (dt < analog::PackSampleMs) return;
  lastSample_ = now;
  int sample = packMillivolts(packAdc.read(), analog::PackDividerRatio, analog::PackCalibration);
  millivolts_ = static_cast<int>(filter_.update(static_cast<float>(sample), dt) + 0.5f);
  faultDebounce_.update(millivolts_ > analog::PackImplausibleMv, now);
}

void DockSensor::begin() {
  pinMode(pins::Dock, INPUT_PULLUP);
  debounce_.force(digitalRead(pins::Dock) == LOW);
}

void DockSensor::poll(uint32_t now, EventQueue& events) {
  if (debounce_.update(digitalRead(pins::Dock) == LOW, now)) events.push(Event::dock(debounce_.state()));
}

}
