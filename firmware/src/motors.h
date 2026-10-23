#pragma once

#include "reflexes.h"

namespace pebble {

class Motors {
 public:
  void begin();
  void write(const Wheels& power);
  void brake();
  Wheels last() const { return last_; }

 private:
  struct Bridge {
    uint8_t channelIn1;
    uint8_t channelIn2;
    bool reversed;
  };

  void drive(const Bridge& bridge, int power);

  Bridge left_{0, 0, false};
  Bridge right_{0, 0, false};
  Wheels last_;
  bool ready_ = false;
};

}
