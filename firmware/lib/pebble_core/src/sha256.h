#pragma once

#include <stddef.h>
#include <stdint.h>

namespace pebble {

class Sha256 {
 public:
  static constexpr size_t kDigestSize = 32;
  static constexpr size_t kBlockSize = 64;

  Sha256();
  void update(const void* data, size_t length);
  void finish(uint8_t out[kDigestSize]);

 private:
  void block(const uint8_t* data);

  uint32_t state_[8];
  uint8_t buffer_[kBlockSize];
  size_t buffered_ = 0;
  uint64_t total_ = 0;
};

class HmacSha256 {
 public:
  HmacSha256(const uint8_t* key, size_t keyLength);
  void update(const void* data, size_t length);
  void update(const char* text);
  void finish(uint8_t out[Sha256::kDigestSize]);

 private:
  Sha256 inner_;
  uint8_t outerKey_[Sha256::kBlockSize];
};

bool constantTimeEqual(const uint8_t* a, const uint8_t* b, size_t length);
void toHex(const uint8_t* bytes, size_t length, char* out);
bool fromHex(const char* text, size_t textLength, uint8_t* out, size_t outLength);

}
