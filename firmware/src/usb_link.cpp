#include "usb_link.h"

#include <Arduino.h>

#include "config.h"

namespace pebble {

void UsbLink::begin() {
  Serial.setTxTimeoutMs(0);
  Serial.begin(kUsbBaud);
}

void UsbLink::poll(uint32_t) {
  bool now = connected();
  if (now && !wasConnected_) ++session_;
  wasConnected_ = now;
}

int UsbLink::read() { return Serial.available() > 0 ? Serial.read() : -1; }

bool UsbLink::connected() const { return static_cast<bool>(Serial); }

void UsbLink::sendLine(const char* text, size_t length) {
  if (Serial.availableForWrite() < static_cast<int>(length + 1)) return;
  Serial.write(reinterpret_cast<const uint8_t*>(text), length);
  Serial.write('\n');
}

}
