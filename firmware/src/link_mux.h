#pragma once

#include <stddef.h>
#include <stdint.h>

#include "line_assembler.h"
#include "link.h"
#include "link_guard.h"

namespace pebble {

class LineSink {
 public:
  virtual ~LineSink() = default;
  virtual void onLine(size_t link, const char* line, uint32_t now) = 0;
  virtual void onOverlong(size_t link, const char* truncated, uint32_t now) = 0;
};

class LinkMux {
 public:
  static constexpr size_t kMaxLinks = 3;
  static constexpr size_t kBytesPerPoll = 256;
  static constexpr size_t kWireBufferSize = LinkGuard::kWireLineLength + 8;

  bool add(Link* link);
  void begin();
  void setGreeting(const char* text, size_t length);
  void poll(uint32_t now, LineSink& sink);
  void reply(size_t link, const char* text, size_t length);
  void broadcast(const char* text, size_t length);
  bool anyConnected() const;
  bool trusted(size_t link) const;
  bool proven(size_t link) const;
  LinkGuard* guard(size_t link);
  void drop(size_t link);

 private:
  struct Slot {
    Link* link = nullptr;
    LineAssembler assembler;
    LinkGuard guard;
    uint32_t session = 0;
    bool greeted = false;
  };

  bool listening(const Slot& slot) const;
  void send(Slot& slot, const char* text, size_t length);

  Slot slots_[kMaxLinks];
  size_t count_ = 0;
  char greeting_[kLineBufferSize] = {0};
  size_t greetingLength_ = 0;
  char wire_[kWireBufferSize] = {0};
};

}
