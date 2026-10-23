#pragma once

#include <stddef.h>

#include "protocol.h"

namespace pebble {

class LineAssembler {
 public:
  enum class Result : unsigned char { Pending, Line, TooLong };

  Result push(char c);
  const char* line() const { return buffer_; }
  size_t length() const { return length_; }
  void reset();

 private:
  char buffer_[kLineBufferSize] = {0};
  size_t length_ = 0;
  bool overflow_ = false;
};

}
