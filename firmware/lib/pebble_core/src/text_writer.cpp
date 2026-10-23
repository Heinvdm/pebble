#include "text_writer.h"

#include <math.h>

namespace pebble {

TextWriter::TextWriter(char* buffer, size_t capacity)
    : buffer_(buffer), capacity_(capacity), length_(0), overflow_(capacity == 0) {
  if (capacity_ > 0) buffer_[0] = '\0';
}

void TextWriter::clear() {
  length_ = 0;
  overflow_ = capacity_ == 0;
  if (capacity_ > 0) buffer_[0] = '\0';
}

TextWriter& TextWriter::put(char c) {
  if (length_ + 1 >= capacity_) {
    overflow_ = true;
    return *this;
  }
  buffer_[length_++] = c;
  buffer_[length_] = '\0';
  return *this;
}

TextWriter& TextWriter::put(const char* text) {
  if (text == nullptr) return *this;
  while (*text) put(*text++);
  return *this;
}

TextWriter& TextWriter::space() { return put(' '); }

TextWriter& TextWriter::putInt(int64_t value) {
  char digits[21];
  int count = 0;
  uint64_t magnitude = value < 0 ? static_cast<uint64_t>(-(value + 1)) + 1u : static_cast<uint64_t>(value);
  do {
    digits[count++] = static_cast<char>('0' + magnitude % 10u);
    magnitude /= 10u;
  } while (magnitude > 0u && count < 20);
  if (value < 0) put('-');
  while (count > 0) put(digits[--count]);
  return *this;
}

TextWriter& TextWriter::putFixed(float value, int decimals) {
  if (decimals < 0) decimals = 0;
  if (decimals > 6) decimals = 6;
  if (isnan(value) || isinf(value)) return put("0");
  int64_t scale = 1;
  for (int i = 0; i < decimals; ++i) scale *= 10;
  double scaled = static_cast<double>(value) * static_cast<double>(scale);
  int64_t rounded = static_cast<int64_t>(scaled < 0 ? scaled - 0.5 : scaled + 0.5);
  bool negative = rounded < 0;
  uint64_t magnitude = negative ? static_cast<uint64_t>(-rounded) : static_cast<uint64_t>(rounded);
  uint64_t whole = magnitude / static_cast<uint64_t>(scale);
  uint64_t fraction = magnitude % static_cast<uint64_t>(scale);
  if (negative && magnitude != 0u) put('-');
  putInt(static_cast<int64_t>(whole));
  if (decimals == 0 || fraction == 0u) return *this;
  char frac[7];
  int width = decimals;
  for (int i = width - 1; i >= 0; --i) {
    frac[i] = static_cast<char>('0' + fraction % 10u);
    fraction /= 10u;
  }
  while (width > 0 && frac[width - 1] == '0') --width;
  put('.');
  for (int i = 0; i < width; ++i) put(frac[i]);
  return *this;
}

}
