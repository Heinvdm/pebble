#include "tcp_link.h"

#include <WiFi.h>
#include <errno.h>
#include <lwip/sockets.h>
#include <string.h>

#include "config.h"

namespace pebble {

namespace {

bool wouldBlock(int error) { return error == EAGAIN || error == EWOULDBLOCK || error == EINPROGRESS; }

void makeNonBlocking(int fd) {
  int flags = lwip_fcntl(fd, F_GETFL, 0);
  lwip_fcntl(fd, F_SETFL, flags | O_NONBLOCK);
}

}

void TcpLink::openListener() {
  int fd = lwip_socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
  if (fd < 0) return;
  int yes = 1;
  lwip_setsockopt(fd, SOL_SOCKET, SO_REUSEADDR, &yes, sizeof(yes));
  sockaddr_in address;
  memset(&address, 0, sizeof(address));
  address.sin_family = AF_INET;
  address.sin_port = htons(kTcpPort);
  address.sin_addr.s_addr = htonl(INADDR_ANY);
  if (lwip_bind(fd, reinterpret_cast<sockaddr*>(&address), sizeof(address)) != 0 || lwip_listen(fd, 1) != 0) {
    lwip_close(fd);
    return;
  }
  makeNonBlocking(fd);
  listener_ = fd;
}

void TcpLink::closeListener() {
  if (listener_ < 0) return;
  lwip_close(listener_);
  listener_ = -1;
}

void TcpLink::closeClient() {
  if (client_ < 0) return;
  lwip_close(client_);
  client_ = -1;
  rxHead_ = 0;
  rxCount_ = 0;
  txCount_ = 0;
  ++session_;
}

void TcpLink::acceptClient() {
  sockaddr_in peer;
  socklen_t length = sizeof(peer);
  int fd = lwip_accept(listener_, reinterpret_cast<sockaddr*>(&peer), &length);
  if (fd < 0) {
    if (!wouldBlock(errno)) closeListener();
    return;
  }
  if (held_ && client_ >= 0) {
    lwip_close(fd);
    return;
  }
  closeClient();
  makeNonBlocking(fd);
  int yes = 1;
  lwip_setsockopt(fd, IPPROTO_TCP, TCP_NODELAY, &yes, sizeof(yes));
  lwip_setsockopt(fd, SOL_SOCKET, SO_KEEPALIVE, &yes, sizeof(yes));
  int idle = 5;
  int interval = 2;
  int count = 3;
  lwip_setsockopt(fd, IPPROTO_TCP, TCP_KEEPIDLE, &idle, sizeof(idle));
  lwip_setsockopt(fd, IPPROTO_TCP, TCP_KEEPINTVL, &interval, sizeof(interval));
  lwip_setsockopt(fd, IPPROTO_TCP, TCP_KEEPCNT, &count, sizeof(count));
  client_ = fd;
  ++session_;
}

void TcpLink::receive() {
  while (client_ >= 0 && rxCount_ < kRxSize) {
    size_t tail = (rxHead_ + rxCount_) % kRxSize;
    size_t space = tail >= rxHead_ ? kRxSize - tail : rxHead_ - tail;
    int n = lwip_recv(client_, rx_ + tail, space, MSG_DONTWAIT);
    if (n > 0) {
      rxCount_ += static_cast<size_t>(n);
      continue;
    }
    if (n == 0 || !wouldBlock(errno)) closeClient();
    return;
  }
}

void TcpLink::flush() {
  if (client_ < 0 || txCount_ == 0) return;
  int n = lwip_send(client_, tx_, txCount_, MSG_DONTWAIT);
  if (n > 0) {
    size_t sent = static_cast<size_t>(n);
    memmove(tx_, tx_ + sent, txCount_ - sent);
    txCount_ -= sent;
  } else if (n < 0 && !wouldBlock(errno)) {
    closeClient();
  }
}

void TcpLink::poll(uint32_t) {
  if (WiFi.status() != WL_CONNECTED) {
    closeClient();
    closeListener();
    return;
  }
  if (listener_ < 0) openListener();
  if (listener_ >= 0) acceptClient();
  receive();
  flush();
}

int TcpLink::read() {
  if (rxCount_ == 0) return -1;
  uint8_t c = rx_[rxHead_];
  rxHead_ = (rxHead_ + 1) % kRxSize;
  --rxCount_;
  return c;
}

void TcpLink::sendLine(const char* text, size_t length) {
  if (client_ < 0 || txCount_ + length + 1 > kTxSize) return;
  memcpy(tx_ + txCount_, text, length);
  tx_[txCount_ + length] = '\n';
  txCount_ += length + 1;
  flush();
}

}
