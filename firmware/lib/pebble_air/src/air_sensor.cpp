#include "air_sensor.h"

#include <math.h>

namespace pebble {

namespace {

constexpr uint8_t kAddresses[] = {BME68X_I2C_ADDR_HIGH, BME68X_I2C_ADDR_LOW};
constexpr int8_t kStartAmbientC = 25;
constexpr float kMinC = -40.0f;
constexpr float kMaxC = 85.0f;
constexpr float kMinPa = 30000.0f;
constexpr float kMaxPa = 110000.0f;
constexpr float kMaxGasOhm = 2.0e9f;

int8_t ambientFrom(float celsius) {
  if (celsius < kMinC) return static_cast<int8_t>(kMinC);
  if (celsius > kMaxC) return static_cast<int8_t>(kMaxC);
  return static_cast<int8_t>(lroundf(celsius));
}

bool within(float value, float low, float high) { return isfinite(value) && value >= low && value <= high; }

}

AirSensor::AirSensor(AirBus& bus, const AirTiming& timing) : bus_(bus), timing_(timing) {}

BME68X_INTF_RET_TYPE AirSensor::readRegs(uint8_t reg, uint8_t* data, uint32_t length, void* self) {
  AirSensor* sensor = static_cast<AirSensor*>(self);
  return sensor->bus_.read(sensor->address_, reg, data, length) ? BME68X_INTF_RET_SUCCESS : -1;
}

BME68X_INTF_RET_TYPE AirSensor::writeRegs(uint8_t reg, const uint8_t* data, uint32_t length, void* self) {
  AirSensor* sensor = static_cast<AirSensor*>(self);
  return sensor->bus_.write(sensor->address_, reg, data, length) ? BME68X_INTF_RET_SUCCESS : -1;
}

void AirSensor::delay(uint32_t us, void* self) { static_cast<AirSensor*>(self)->bus_.delayUs(us); }

bool AirSensor::begin(uint32_t now) {
  lastAttempt_ = now;
  if (start(now)) return true;
  lastReport_ = now - timing_.sampleMs;
  return false;
}

bool AirSensor::start(uint32_t now) {
  phase_ = Phase::Absent;
  data_ = AirData();
  data_.ms = now;
  for (uint8_t address : kAddresses) {
    if (!bus_.probe(address)) continue;
    address_ = address;
    device_ = bme68x_dev();
    device_.intf = BME68X_I2C_INTF;
    device_.intf_ptr = this;
    device_.read = &AirSensor::readRegs;
    device_.write = &AirSensor::writeRegs;
    device_.delay_us = &AirSensor::delay;
    device_.amb_temp = kStartAmbientC;
    if (bme68x_init(&device_) != BME68X_OK || !configure()) continue;
    phase_ = Phase::Idle;
    failures_ = 0;
    due_ = false;
    startedAt_ = now;
    lastSample_ = now - timing_.sampleMs;
    return true;
  }
  address_ = 0;
  return false;
}

bool AirSensor::configure() {
  conf_ = bme68x_conf();
  conf_.filter = BME68X_FILTER_OFF;
  conf_.odr = BME68X_ODR_NONE;
  conf_.os_hum = BME68X_OS_1X;
  conf_.os_pres = BME68X_OS_4X;
  conf_.os_temp = BME68X_OS_2X;
  if (bme68x_set_conf(&conf_, &device_) != BME68X_OK) return false;
  if (!applyHeater(kStartAmbientC)) return false;
  waitMs_ = bme68x_get_meas_dur(BME68X_FORCED_MODE, &conf_, &device_) / 1000u + timing_.heaterMs + 1u;
  return true;
}

bool AirSensor::applyHeater(int8_t ambientC) {
  device_.amb_temp = ambientC;
  bme68x_heatr_conf heater = bme68x_heatr_conf();
  heater.enable = BME68X_ENABLE;
  heater.heatr_temp = timing_.heaterC;
  heater.heatr_dur = timing_.heaterMs;
  if (bme68x_set_heatr_conf(BME68X_FORCED_MODE, &heater, &device_) != BME68X_OK) return false;
  heaterAmbientC_ = ambientC;
  return true;
}

bool AirSensor::poll(uint32_t now, bool wheelsStill) {
  switch (phase_) {
    case Phase::Absent:
      if (wheelsStill && static_cast<uint32_t>(now - lastAttempt_) >= timing_.retryMs) {
        lastAttempt_ = now;
        if (start(now)) return false;
      }
      return reportAbsent(now);
    case Phase::Idle:
      if (static_cast<uint32_t>(now - lastSample_) < timing_.sampleMs) return false;
      if (!due_) {
        due_ = true;
        dueSince_ = now;
      }
      if (!wheelsStill && static_cast<uint32_t>(now - dueSince_) < timing_.maxDeferMs) return false;
      due_ = false;
      return trigger(now);
    case Phase::Measuring:
      return collect(now);
  }
  return false;
}

bool AirSensor::reportAbsent(uint32_t now) {
  if (static_cast<uint32_t>(now - lastReport_) < timing_.sampleMs) return false;
  lastReport_ = now;
  data_ = AirData();
  data_.ms = now;
  return true;
}

bool AirSensor::trigger(uint32_t now) {
  lastSample_ = now;
  uint8_t mode = 0;
  if (bme68x_get_op_mode(&mode, &device_) != BME68X_OK || mode != BME68X_SLEEP_MODE) return fail(now);
  if (data_.present) {
    int8_t ambient = ambientFrom(data_.temperatureC);
    int diff = ambient - heaterAmbientC_;
    if ((diff >= timing_.heaterRetuneC || -diff >= timing_.heaterRetuneC) && !applyHeater(ambient)) return fail(now);
  }
  if (bme68x_set_op_mode(BME68X_FORCED_MODE, &device_) != BME68X_OK) return fail(now);
  measureAt_ = now;
  phase_ = Phase::Measuring;
  return false;
}

bool AirSensor::collect(uint32_t now) {
  uint32_t elapsed = now - measureAt_;
  if (elapsed < waitMs_) return false;
  uint8_t status = 0;
  if (bme68x_get_regs(BME68X_REG_FIELD0, &status, 1, &device_) != BME68X_OK) return fail(now);
  if ((status & BME68X_NEW_DATA_MSK) == 0) {
    if (elapsed >= waitMs_ + timing_.readSlackMs) return fail(now);
    return false;
  }
  bme68x_data raw = bme68x_data();
  uint8_t fields = 0;
  if (bme68x_get_data(BME68X_FORCED_MODE, &raw, &fields, &device_) != BME68X_OK || fields == 0) return fail(now);
  if (!accept(raw, now)) return fail(now);
  return true;
}

bool AirSensor::accept(const bme68x_data& raw, uint32_t now) {
  if (!within(raw.temperature, kMinC, kMaxC)) return false;
  if (!within(raw.pressure, kMinPa, kMaxPa)) return false;
  if (!within(raw.humidity, 0.0f, 100.0f)) return false;
  bool gasOk = (raw.status & BME68X_GASM_VALID_MSK) != 0 && (raw.status & BME68X_HEAT_STAB_MSK) != 0 &&
               within(raw.gas_resistance, 0.0f, kMaxGasOhm);
  data_.ms = now;
  data_.present = true;
  data_.temperatureC = raw.temperature;
  data_.humidityPct = raw.humidity;
  data_.pressurePa = static_cast<uint32_t>(lroundf(raw.pressure));
  data_.gasOhm = gasOk ? static_cast<int32_t>(lroundf(raw.gas_resistance)) : -1;
  data_.heatedS = (now - startedAt_) / 1000u;
  failures_ = 0;
  phase_ = Phase::Idle;
  return true;
}

bool AirSensor::fail(uint32_t now) {
  phase_ = Phase::Idle;
  due_ = false;
  if (++failures_ < timing_.failLimit) return false;
  phase_ = Phase::Absent;
  lastAttempt_ = now;
  lastReport_ = now;
  data_ = AirData();
  data_.ms = now;
  return true;
}

}
