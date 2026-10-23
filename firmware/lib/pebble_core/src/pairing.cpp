#include "pairing.h"

namespace pebble {

PairingWindow::Change PairingWindow::update(uint32_t now, bool bumperHeld, bool wheelsStill, bool proven) {
  bool held = bumperHeld && wheelsStill;
  if (!held) {
    holding_ = false;
    spent_ = false;
  } else if (!holding_) {
    holding_ = true;
    heldSince_ = now;
  }
  if (holding_ && !spent_ && static_cast<uint32_t>(now - heldSince_) >= timing_.holdMs) {
    spent_ = true;
    bool was = open_;
    open_ = true;
    openedAt_ = now;
    if (!was) return Change::Opened;
  }
  if (open_ && !proven && static_cast<uint32_t>(now - openedAt_) >= timing_.openMs) {
    open_ = false;
    return Change::Closed;
  }
  return Change::None;
}

bool RateLimiter::take(uint32_t now) {
  if (!started_) {
    started_ = true;
    tokens_ = burst_;
    last_ = now;
  }
  uint32_t gained = static_cast<uint32_t>(now - last_) / intervalMs_;
  if (gained > 0) {
    tokens_ = tokens_ + gained > burst_ ? burst_ : tokens_ + gained;
    last_ += gained * intervalMs_;
  }
  if (tokens_ == 0) return false;
  --tokens_;
  return true;
}

}
