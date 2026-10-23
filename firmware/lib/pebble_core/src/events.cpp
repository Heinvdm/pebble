#include "events.h"

namespace pebble {

bool EventQueue::push(const Event& event) {
  if (count_ >= kCapacity) {
    ++dropped_;
    return false;
  }
  items_[(head_ + count_) % kCapacity] = event;
  ++count_;
  return true;
}

bool EventQueue::pop(Event& out) {
  if (count_ == 0) return false;
  out = items_[head_];
  head_ = (head_ + 1) % kCapacity;
  --count_;
  return true;
}

void EventQueue::clear() {
  head_ = 0;
  count_ = 0;
}

}
