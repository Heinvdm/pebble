#pragma once

#include "air_sensor.h"

namespace pebble {

class WireAirBus : public AirBus {
 public:
  bool probe(uint8_t address) override;
  bool read(uint8_t address, uint8_t reg, uint8_t* data, uint32_t length) override;
  bool write(uint8_t address, uint8_t reg, const uint8_t* data, uint32_t length) override;
  void delayUs(uint32_t us) override;
};

}
