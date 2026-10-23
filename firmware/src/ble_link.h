#pragma once

#include "link.h"

namespace pebble {

class BleLink : public Link {
 public:
  void begin() override;
  void poll(uint32_t now) override;
  int read() override;
  bool connected() const override;
  uint32_t session() const override;
  void sendLine(const char* text, size_t length) override;
  void drop() override;
  bool present() const override;
  void setOpen(bool open);
  bool isOpen() const { return open_; }

 private:
  void start();

  bool started_ = false;
  bool open_ = false;
};

}
