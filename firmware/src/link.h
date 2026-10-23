#pragma once

#include <stddef.h>
#include <stdint.h>

namespace pebble {

class Link {
 public:
  virtual ~Link() = default;

  virtual void begin() = 0;
  virtual void poll(uint32_t now) = 0;
  virtual int read() = 0;
  virtual bool connected() const = 0;
  virtual uint32_t session() const = 0;
  virtual void sendLine(const char* text, size_t length) = 0;
  virtual bool trusted() const { return false; }
  virtual bool present() const { return connected(); }
  virtual void drop() {}
  virtual void hold(bool held) { (void)held; }
};

}
