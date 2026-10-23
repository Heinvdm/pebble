#pragma once

#include <stdint.h>

namespace pebble {

template <typename T>
class Debouncer {
 public:
  Debouncer(T initial, uint32_t stableMs) : state_(initial), candidate_(initial), stableMs_(stableMs) {}

  bool update(T sample, uint32_t now) {
    if (!started_) {
      started_ = true;
      candidate_ = sample;
      since_ = now;
    }
    if (sample != candidate_) {
      candidate_ = sample;
      since_ = now;
    }
    if (candidate_ != state_ && static_cast<uint32_t>(now - since_) >= stableMs_) {
      state_ = candidate_;
      return true;
    }
    return false;
  }

  T state() const { return state_; }
  void force(T value) {
    state_ = value;
    candidate_ = value;
  }

 private:
  T state_;
  T candidate_;
  uint32_t stableMs_;
  uint32_t since_ = 0;
  bool started_ = false;
};

}
