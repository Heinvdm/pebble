#pragma once

#include <stdint.h>

#include "air_bus.h"
#include "air_sensor.h"
#include "ble_link.h"
#include "body_inputs.h"
#include "encoders.h"
#include "events.h"
#include "link_guard.h"
#include "link_mux.h"
#include "motion.h"
#include "motors.h"
#include "pairing.h"
#include "protocol.h"
#include "ranging.h"
#include "settings_model.h"
#include "settings_store.h"
#include "tcp_link.h"
#include "tilt_servo.h"
#include "usb_link.h"
#include "wifi_manager.h"

namespace pebble {

class Robot : public LineSink {
 public:
  void setup();
  void loop();

  void onLine(size_t link, const char* line, uint32_t now) override;
  void onOverlong(size_t link, const char* truncated, uint32_t now) override;

 private:
  void handle(size_t link, const Command& command, uint32_t now);
  void handleConfig(size_t link, const Command& command, uint32_t now);
  void handleHello(size_t link, const Command& command);
  void handleVerify(size_t link, const Command& command, uint32_t now);
  void handleKey(size_t link, const Command& command, uint32_t now);
  void pollPairing(uint32_t now);
  void listConfig(size_t link);
  void replyConfig(size_t link, SettingKey key);
  void replyOk(size_t link);
  void replyError(size_t link, char command, const char* reason);
  void replyStatus(size_t link);
  void applySettings();
  void controlTick(uint32_t now);
  void broadcastStatus();
  void broadcastAir();
  bool wheelsStill(uint32_t now) const;
  static AirTiming airTiming();
  void flushEvents();
  uint8_t faults() const;
  StatusData status() const;

  Settings settings_;
  SettingsStore store_;
  Motors motors_;
  Encoders encoders_;
  RangeSensors ranging_;
  WireAirBus airBus_;
  AirSensor air_{airBus_, airTiming()};
  BumpSensor bump_;
  PackMonitor pack_;
  DockSensor dock_;
  TiltServo tilt_;
  MotionCore motion_;
  EventQueue events_;
  UsbLink usb_;
  TcpLink tcp_;
  BleLink ble_;
  LinkMux links_;
  WifiManager wifi_;
  LinkSecret secret_;
  PairingWindow pairing_;
  RateLimiter writes_{4, 4};

  int64_t encLeft_ = 0;
  int64_t encRight_ = 0;
  uint32_t lastControl_ = 0;
  uint32_t lastStatus_ = 0;
  uint32_t wheelsMovedAt_ = 0;
  bool rebootPending_ = false;
  uint32_t rebootAt_ = 0;
  bool nodding_ = false;
  uint32_t nodUntil_ = 0;
  char out_[kLineBufferSize + 8] = {0};
  char bare_[kLineBufferSize + 8] = {0};
};

}
