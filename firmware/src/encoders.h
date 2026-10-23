#pragma once

#include <stdint.h>

namespace pebble {

class Encoders {
 public:
  void begin();
  void read(int64_t& left, int64_t& right);
};

}
