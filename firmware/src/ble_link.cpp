#include "ble_link.h"

#include <Arduino.h>
#include <NimBLEDevice.h>
#include <freertos/FreeRTOS.h>
#include <freertos/stream_buffer.h>

#include <atomic>

#include "config.h"

namespace pebble {

namespace {

constexpr const char* kServiceUuid = "6E400001-B5A3-F393-E0A9-E50E24DCCA9E";
constexpr const char* kRxUuid = "6E400002-B5A3-F393-E0A9-E50E24DCCA9E";
constexpr const char* kTxUuid = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E";
constexpr size_t kRxBufferSize = 512;
constexpr uint16_t kPreferredMtu = 247;
constexpr uint16_t kDefaultMtu = 23;
constexpr size_t kMaxChunk = 180;

StreamBufferHandle_t rxBuffer = nullptr;
NimBLEServer* server = nullptr;
NimBLECharacteristic* txCharacteristic = nullptr;
std::atomic<uint16_t> mtu{kDefaultMtu};
std::atomic<uint32_t> sessions{0};
std::atomic<bool> subscribed{false};
std::atomic<bool> linked{false};
std::atomic<uint16_t> peer{0};

class ServerCallbacks : public NimBLEServerCallbacks {
  void onConnect(NimBLEServer* s, NimBLEConnInfo& info) override {
    linked = true;
    peer = info.getConnHandle();
    mtu = info.getMTU() > 0 ? info.getMTU() : kDefaultMtu;
    sessions.fetch_add(1);
    s->updateConnParams(info.getConnHandle(), 12, 24, 0, 400);
  }

  void onDisconnect(NimBLEServer*, NimBLEConnInfo&, int) override {
    linked = false;
    subscribed = false;
    mtu = kDefaultMtu;
    sessions.fetch_add(1);
  }

  void onMTUChange(uint16_t value, NimBLEConnInfo&) override { mtu = value; }
};

class RxCallbacks : public NimBLECharacteristicCallbacks {
  void onWrite(NimBLECharacteristic* c, NimBLEConnInfo&) override {
    NimBLEAttValue value = c->getValue();
    if (rxBuffer != nullptr && value.size() > 0) xStreamBufferSend(rxBuffer, value.data(), value.size(), 0);
  }
};

class TxCallbacks : public NimBLECharacteristicCallbacks {
  void onSubscribe(NimBLECharacteristic*, NimBLEConnInfo&, uint16_t subValue) override {
    subscribed = (subValue & 0x0001) != 0;
  }
};

ServerCallbacks serverCallbacks;
RxCallbacks rxCallbacks;
TxCallbacks txCallbacks;

}

void BleLink::begin() {}

void BleLink::start() {
  if (started_) return;
  started_ = true;
  rxBuffer = xStreamBufferCreate(kRxBufferSize, 1);
  NimBLEDevice::init(kDeviceName);
  NimBLEDevice::setMTU(kPreferredMtu);
  server = NimBLEDevice::createServer();
  server->setCallbacks(&serverCallbacks, false);
  server->advertiseOnDisconnect(false);
  NimBLEService* service = server->createService(kServiceUuid);
  NimBLECharacteristic* rx = service->createCharacteristic(kRxUuid, NIMBLE_PROPERTY::WRITE | NIMBLE_PROPERTY::WRITE_NR);
  txCharacteristic = service->createCharacteristic(kTxUuid, NIMBLE_PROPERTY::NOTIFY);
  rx->setCallbacks(&rxCallbacks);
  txCharacteristic->setCallbacks(&txCallbacks);
  NimBLEAdvertising* advertising = NimBLEDevice::getAdvertising();
  advertising->setName(kDeviceName);
  advertising->addServiceUUID(kServiceUuid);
  advertising->enableScanResponse(true);
}

void BleLink::setOpen(bool open) {
  if (open == open_) return;
  open_ = open;
  if (open) {
    start();
    return;
  }
  if (!started_) return;
  NimBLEDevice::getAdvertising()->stop();
  drop();
}

void BleLink::drop() {
  if (server != nullptr && linked) server->disconnect(peer.load());
}

void BleLink::poll(uint32_t) {
  if (!started_ || !open_ || linked) return;
  NimBLEAdvertising* advertising = NimBLEDevice::getAdvertising();
  if (!advertising->isAdvertising()) advertising->start();
}

int BleLink::read() {
  if (rxBuffer == nullptr) return -1;
  uint8_t c;
  return xStreamBufferReceive(rxBuffer, &c, 1, 0) == 1 ? c : -1;
}

bool BleLink::connected() const { return linked && subscribed; }

bool BleLink::present() const { return linked; }

uint32_t BleLink::session() const { return sessions.load(); }

void BleLink::sendLine(const char* text, size_t length) {
  if (txCharacteristic == nullptr || !connected()) return;
  char line[kMaxChunk + 2];
  size_t total = length + 1;
  if (total > sizeof(line)) return;
  memcpy(line, text, length);
  line[length] = '\n';
  size_t chunk = mtu.load() > 3 ? mtu.load() - 3 : 20;
  if (chunk > kMaxChunk) chunk = kMaxChunk;
  for (size_t offset = 0; offset < total; offset += chunk) {
    size_t n = total - offset < chunk ? total - offset : chunk;
    if (!txCharacteristic->notify(reinterpret_cast<const uint8_t*>(line + offset), n)) return;
  }
}

}
