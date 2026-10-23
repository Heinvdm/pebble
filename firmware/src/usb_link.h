#pragma once

#include "link.h"

namespace pebble {

class UsbLink : public Link {
 public:
  void begin() override;
  void poll(uint32_t now) override;
  int read() override;
  bool connected() const override;
  uint32_t session() const override { return session_; }
  void sendLine(const char* text, size_t length) override;
  bool trusted() const override { return true; }

 private:
  bool wasConnected_ = false;
  uint32_t session_ = 0;
};

}
