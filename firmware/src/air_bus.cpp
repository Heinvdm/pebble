#include "air_bus.h"

#include <Arduino.h>
#include <Wire.h>

namespace pebble {

namespace {

constexpr uint32_t kMaxTransfer = 32;

}

bool WireAirBus::probe(uint8_t address) {
  Wire.beginTransmission(address);
  return Wire.endTransmission() == 0;
}

bool WireAirBus::read(uint8_t address, uint8_t reg, uint8_t* data, uint32_t length) {
  if (length == 0 || length > kMaxTransfer) return false;
  Wire.beginTransmission(address);
  Wire.write(reg);
  if (Wire.endTransmission(false) != 0) return false;
  size_t got = Wire.requestFrom(address, static_cast<size_t>(length), true);
  if (got != length) {
    while (Wire.available()) Wire.read();
    return false;
  }
  for (uint32_t i = 0; i < length; ++i) data[i] = static_cast<uint8_t>(Wire.read());
  return true;
}

bool WireAirBus::write(uint8_t address, uint8_t reg, const uint8_t* data, uint32_t length) {
  if (length > kMaxTransfer) return false;
  Wire.beginTransmission(address);
  Wire.write(reg);
  if (length > 0) Wire.write(data, length);
  return Wire.endTransmission() == 0;
}

void WireAirBus::delayUs(uint32_t us) {
  if (us >= 1000) {
    delay(us / 1000);
    us %= 1000;
  }
  if (us > 0) delayMicroseconds(us);
}

}
