#pragma once

#include <stddef.h>
#include <stdint.h>

#include "protocol.h"
#include "sha256.h"
#include "text_writer.h"

namespace pebble {

struct LinkSecret {
  static constexpr size_t kSize = 32;

  bool present = false;
  uint8_t key[kSize] = {0};
};

enum class LinkAccess : uint8_t { Allowed, NeedsProof, UsbOnly };

LinkAccess linkAccess(CommandType type, bool usb, bool proven, bool tagged);

class LinkGuard {
 public:
  static constexpr size_t kNonceSize = 16;
  static constexpr size_t kProofSize = 16;
  static constexpr size_t kTagSize = 6;
  static constexpr size_t kTagHexLength = kTagSize * 2;
  static constexpr size_t kSuffixMax = 2 + 10 + 1 + kTagHexLength;
  static constexpr size_t kWireLineLength = kMaxLineLength + kSuffixMax;
  static constexpr uint32_t kProveWithinMs = 5000;
  static constexpr uint32_t kHeldForMs = 2000;
  static constexpr uint8_t kMaxFailures = 3;

  enum class Inbound : uint8_t { Plain, Tagged, BadTag, Long };

  void reset(uint32_t now);
  bool proven() const { return state_ == State::Proven; }
  bool challenged() const { return state_ == State::Challenged; }
  bool expired(uint32_t now) const;
  bool holding(uint32_t now) const;
  bool failedTooOften() const { return failures_ >= kMaxFailures; }

  Inbound unwrap(const char* line, char* out, size_t capacity, uint32_t now);
  bool challenge(const LinkSecret& secret, const char* phoneNonceHex, const uint8_t bodyNonce[kNonceSize],
                 TextWriter& reply);
  bool verify(const char* proofHex);
  void commit(uint32_t now);
  bool seal(const char* text, size_t length, TextWriter& out);

  static void sessionKey(const LinkSecret& secret, const char* phoneNonceHex, const char* bodyNonceHex,
                         uint8_t out[Sha256::kDigestSize]);
  static void proof(const uint8_t session[Sha256::kDigestSize], const char* who, uint8_t out[kProofSize]);
  static void tag(const uint8_t session[Sha256::kDigestSize], char direction, uint32_t counter, const char* text,
                  size_t length, char out[kTagHexLength + 1]);

 private:
  enum class State : uint8_t { Open, Challenged, Proven };

  State state_ = State::Open;
  uint8_t session_[Sha256::kDigestSize] = {0};
  uint32_t received_ = 0;
  uint32_t sent_ = 0;
  uint32_t openedAt_ = 0;
  uint32_t lastGood_ = 0;
  uint8_t failures_ = 0;
};

}
