#pragma once

#include <stddef.h>
#include <stdint.h>

namespace pebble {

class TextWriter {
 public:
  TextWriter(char* buffer, size_t capacity);

  TextWriter& put(char c);
  TextWriter& put(const char* text);
  TextWriter& putInt(int64_t value);
  TextWriter& putFixed(float value, int decimals);
  TextWriter& space();

  bool ok() const { return !overflow_; }
  size_t length() const { return length_; }
  const char* c_str() const { return buffer_; }
  void clear();

 private:
  char* buffer_;
  size_t capacity_;
  size_t length_;
  bool overflow_;
};

}
