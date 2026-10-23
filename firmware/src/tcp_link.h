#pragma once

#include "link.h"

namespace pebble {

class TcpLink : public Link {
 public:
  void begin() override {}
  void poll(uint32_t now) override;
  int read() override;
  bool connected() const override { return client_ >= 0; }
  uint32_t session() const override { return session_; }
  void sendLine(const char* text, size_t length) override;
  void drop() override { closeClient(); }
  void hold(bool held) override { held_ = held; }

 private:
  static constexpr size_t kRxSize = 256;
  static constexpr size_t kTxSize = 1536;

  void openListener();
  void closeListener();
  void acceptClient();
  void closeClient();
  void receive();
  void flush();

  int listener_ = -1;
  int client_ = -1;
  bool held_ = false;
  uint32_t session_ = 0;
  uint8_t rx_[kRxSize];
  size_t rxHead_ = 0;
  size_t rxCount_ = 0;
  uint8_t tx_[kTxSize];
  size_t txCount_ = 0;
};

}
