#include "line_assembler.h"

namespace pebble {

void LineAssembler::reset() {
  length_ = 0;
  overflow_ = false;
  buffer_[0] = '\0';
}

LineAssembler::Result LineAssembler::push(char c) {
  if (c == '\r' || c == '\0') return Result::Pending;
  if (c == '\n') {
    bool overflowed = overflow_;
    buffer_[length_] = '\0';
    length_ = 0;
    overflow_ = false;
    if (overflowed) return Result::TooLong;
    return Result::Line;
  }
  if (overflow_) return Result::Pending;
  if (length_ >= kMaxLineLength) {
    overflow_ = true;
    return Result::Pending;
  }
  buffer_[length_++] = c;
  buffer_[length_] = '\0';
  return Result::Pending;
}

}
