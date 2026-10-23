#include "link_mux.h"

#include <string.h>

#include "text_writer.h"

namespace pebble {

bool LinkMux::add(Link* link) {
  if (link == nullptr || count_ >= kMaxLinks) return false;
  slots_[count_++].link = link;
  return true;
}

void LinkMux::begin() {
  for (size_t i = 0; i < count_; ++i) {
    slots_[i].link->begin();
    slots_[i].session = slots_[i].link->session();
    slots_[i].assembler.reset();
    slots_[i].guard.reset(0);
  }
}

void LinkMux::setGreeting(const char* text, size_t length) {
  if (length >= sizeof(greeting_)) return;
  memcpy(greeting_, text, length);
  greeting_[length] = '\0';
  greetingLength_ = length;
  for (size_t i = 0; i < count_; ++i) slots_[i].greeted = false;
}

bool LinkMux::listening(const Slot& slot) const {
  return slot.link->connected() && (slot.link->trusted() || slot.guard.proven());
}

void LinkMux::send(Slot& slot, const char* text, size_t length) {
  TextWriter w(wire_, sizeof(wire_));
  if (slot.guard.seal(text, length, w)) slot.link->sendLine(w.c_str(), w.length());
}

void LinkMux::poll(uint32_t now, LineSink& sink) {
  for (size_t i = 0; i < count_; ++i) {
    Slot& slot = slots_[i];
    slot.link->hold(slot.guard.holding(now));
    slot.link->poll(now);
    if (slot.link->session() != slot.session) {
      slot.session = slot.link->session();
      slot.assembler.reset();
      slot.guard.reset(now);
    }
    if (!slot.link->trusted() && slot.link->present() && (slot.guard.expired(now) || slot.guard.failedTooOften())) {
      slot.link->drop();
      slot.guard.reset(now);
      continue;
    }
    if (!slot.greeted && greetingLength_ > 0 && listening(slot)) {
      send(slot, greeting_, greetingLength_);
      slot.greeted = true;
    }
    for (size_t budget = kBytesPerPoll; budget > 0; --budget) {
      int c = slot.link->read();
      if (c < 0) break;
      LineAssembler::Result result = slot.assembler.push(static_cast<char>(c));
      if (result == LineAssembler::Result::Line) {
        sink.onLine(i, slot.assembler.line(), now);
      } else if (result == LineAssembler::Result::TooLong) {
        sink.onOverlong(i, slot.assembler.line(), now);
      }
    }
  }
}

void LinkMux::reply(size_t link, const char* text, size_t length) {
  if (link >= count_) return;
  if (slots_[link].link->connected()) send(slots_[link], text, length);
}

void LinkMux::broadcast(const char* text, size_t length) {
  for (size_t i = 0; i < count_; ++i) {
    if (listening(slots_[i])) send(slots_[i], text, length);
  }
}

bool LinkMux::anyConnected() const {
  for (size_t i = 0; i < count_; ++i) {
    if (listening(slots_[i])) return true;
  }
  return false;
}

bool LinkMux::trusted(size_t link) const { return link < count_ && slots_[link].link->trusted(); }

bool LinkMux::proven(size_t link) const { return link < count_ && slots_[link].guard.proven(); }

LinkGuard* LinkMux::guard(size_t link) { return link < count_ ? &slots_[link].guard : nullptr; }

void LinkMux::drop(size_t link) {
  if (link >= count_) return;
  slots_[link].link->drop();
  slots_[link].guard.reset(0);
}

}
