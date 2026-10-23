#pragma once

#include <stddef.h>
#include <stdint.h>

#include "bme68x.h"
#include "protocol.h"

namespace pebble {

class AirBus {
 public:
  virtual ~AirBus() = default;
  virtual bool probe(uint8_t address) = 0;
  virtual bool read(uint8_t address, uint8_t reg, uint8_t* data, uint32_t length) = 0;
  virtual bool write(uint8_t address, uint8_t reg, const uint8_t* data, uint32_t length) = 0;
  virtual void delayUs(uint32_t us) = 0;
};

struct AirTiming {
  uint32_t sampleMs = 3000;
  uint32_t maxDeferMs = 3000;
  uint32_t retryMs = 30000;
  uint32_t readSlackMs = 100;
  uint8_t failLimit = 3;
  uint16_t heaterC = 320;
  uint16_t heaterMs = 150;
  int8_t heaterRetuneC = 5;
};

class AirSensor {
 public:
  enum class Phase : uint8_t { Absent, Idle, Measuring };

  explicit AirSensor(AirBus& bus, const AirTiming& timing = AirTiming());

  bool begin(uint32_t now);
  bool poll(uint32_t now, bool wheelsStill);

  Phase phase() const { return phase_; }
  bool present() const { return phase_ != Phase::Absent; }
  uint8_t address() const { return address_; }
  uint8_t variant() const { return device_.variant_id; }
  uint32_t waitMs() const { return waitMs_; }
  uint8_t failures() const { return failures_; }
  const AirData& data() const { return data_; }
  const bme68x_dev& device() const { return device_; }

 private:
  static BME68X_INTF_RET_TYPE readRegs(uint8_t reg, uint8_t* data, uint32_t length, void* self);
  static BME68X_INTF_RET_TYPE writeRegs(uint8_t reg, const uint8_t* data, uint32_t length, void* self);
  static void delay(uint32_t us, void* self);

  bool start(uint32_t now);
  bool configure();
  bool applyHeater(int8_t ambientC);
  bool trigger(uint32_t now);
  bool collect(uint32_t now);
  bool fail(uint32_t now);
  bool reportAbsent(uint32_t now);
  bool accept(const bme68x_data& raw, uint32_t now);

  AirBus& bus_;
  AirTiming timing_;
  bme68x_dev device_ = {};
  bme68x_conf conf_ = {};
  AirData data_;
  Phase phase_ = Phase::Absent;
  uint8_t address_ = 0;
  uint8_t failures_ = 0;
  int8_t heaterAmbientC_ = 25;
  uint32_t waitMs_ = 0;
  uint32_t startedAt_ = 0;
  uint32_t lastSample_ = 0;
  uint32_t measureAt_ = 0;
  uint32_t dueSince_ = 0;
  uint32_t lastAttempt_ = 0;
  uint32_t lastReport_ = 0;
  bool due_ = false;
};

}
