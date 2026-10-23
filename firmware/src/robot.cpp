#include "robot.h"

#include <Arduino.h>
#include <esp_system.h>
#include <string.h>

#include "config.h"

namespace pebble {

namespace {

constexpr size_t kBleSlot = 2;
constexpr int kNodDegrees = 10;
constexpr uint32_t kNodMs = 600;

}

void Robot::setup() {
  motors_.begin();
  store_.begin();
  store_.load(settings_);
  secret_.present = store_.loadLinkKey(secret_.key, LinkSecret::kSize);
  encoders_.begin();
  bump_.begin();
  pack_.begin();
  dock_.begin();
  tilt_.begin(TiltLimits{settings_.tmin, settings_.tmax, settings_.trim}, settings_.rest);
  links_.add(&usb_);
  links_.add(&tcp_);
  links_.add(&ble_);
  links_.begin();
  ranging_.begin();
  air_.begin(millis());
  applySettings();
  wifi_.begin(settings_);
  uint32_t now = millis();
  encoders_.read(encLeft_, encRight_);
  lastControl_ = now;
  lastStatus_ = now;
  TextWriter boot(out_, sizeof(out_));
  if (formatEvent(boot, Event::boot(kFirmwareVersion))) links_.setGreeting(boot.c_str(), boot.length());
}

void Robot::loop() {
  uint32_t now = millis();
  links_.poll(now, *this);
  pollPairing(now);
  wifi_.poll(now);
  ranging_.poll(now);
  bump_.poll(now);
  pack_.poll(now);
  dock_.poll(now, events_);
  if (static_cast<uint32_t>(now - lastControl_) >= timing::ControlMs) {
    controlTick(now);
    if (air_.poll(now, wheelsStill(now))) broadcastAir();
  }
  tilt_.poll(now);
  flushEvents();
  if (static_cast<uint32_t>(now - lastStatus_) >= timing::StatusMs) {
    lastStatus_ = now;
    broadcastStatus();
  }
  if (rebootPending_ && static_cast<int32_t>(now - rebootAt_) >= 0) {
    motors_.brake();
    ESP.restart();
  }
}

uint8_t Robot::faults() const {
  uint8_t bits = ranging_.faults();
  if (bump_.fault()) bits |= FaultBit::Bump;
  if (pack_.fault()) bits |= FaultBit::Battery;
  return bits;
}

void Robot::controlTick(uint32_t now) {
  uint32_t dt = now - lastControl_;
  lastControl_ = now;
  if (dt > 100) dt = 100;
  encoders_.read(encLeft_, encRight_);
  ReflexSense sense;
  sense.front = ranging_.front();
  sense.down = ranging_.down();
  sense.bump = bump_.state();
  sense.packMv = pack_.millivolts();
  sense.packValid = pack_.valid();
  sense.encLeft = encLeft_;
  sense.encRight = encRight_;
  sense.faults = faults();
  motors_.write(motion_.tick(now, dt, sense, motors_.last(), events_));
  Wheels applied = motors_.last();
  if (applied.left != 0 || applied.right != 0) wheelsMovedAt_ = now;
}

bool Robot::wheelsStill(uint32_t now) const {
  Wheels applied = motors_.last();
  return applied.left == 0 && applied.right == 0 && static_cast<uint32_t>(now - wheelsMovedAt_) >= air::SettleMs;
}

AirTiming Robot::airTiming() {
  AirTiming t;
  t.sampleMs = air::SampleMs;
  t.maxDeferMs = air::MaxDeferMs;
  t.retryMs = air::RetryMs;
  t.heaterC = air::HeaterC;
  t.heaterMs = air::HeaterMs;
  return t;
}

void Robot::pollPairing(uint32_t now) {
  Wheels applied = motors_.last();
  bool still = applied.left == 0 && applied.right == 0;
  bool proven = links_.proven(kBleSlot) && ble_.present();
  switch (pairing_.update(now, bump_.state() != 0, still, proven)) {
    case PairingWindow::Change::Opened: {
      ble_.setOpen(true);
      int nod = settings_.rest + kNodDegrees <= settings_.tmax ? settings_.rest + kNodDegrees : settings_.rest - kNodDegrees;
      tilt_.setTarget(nod);
      nodding_ = true;
      nodUntil_ = now + kNodMs;
      break;
    }
    case PairingWindow::Change::Closed:
      ble_.setOpen(false);
      break;
    case PairingWindow::Change::None:
      break;
  }
  if (nodding_ && static_cast<int32_t>(now - nodUntil_) >= 0) {
    nodding_ = false;
    tilt_.setTarget(settings_.rest);
  }
}

void Robot::onLine(size_t link, const char* line, uint32_t now) {
  LinkGuard* guard = links_.guard(link);
  if (guard == nullptr) return;
  LinkGuard::Inbound inbound = guard->unwrap(line, bare_, sizeof(bare_), now);
  if (inbound == LinkGuard::Inbound::Long) {
    replyError(link, lineCommandLetter(line), "long");
    return;
  }
  if (inbound == LinkGuard::Inbound::BadTag) {
    replyError(link, lineCommandLetter(line), "auth");
    return;
  }
  Command command;
  ParseResult result = parseCommand(bare_, command);
  if (result == ParseResult::Empty) return;
  if (result != ParseResult::Ok) {
    replyError(link, lineCommandLetter(bare_), parseResultReason(result));
    return;
  }
  switch (linkAccess(command.type, links_.trusted(link), guard->proven(), inbound == LinkGuard::Inbound::Tagged)) {
    case LinkAccess::NeedsProof:
      replyError(link, commandLetter(command.type), "auth");
      return;
    case LinkAccess::UsbOnly:
      replyError(link, commandLetter(command.type), "usb");
      return;
    case LinkAccess::Allowed:
      break;
  }
  handle(link, command, now);
}

void Robot::onOverlong(size_t link, const char* truncated, uint32_t) {
  replyError(link, lineCommandLetter(truncated), "long");
}

void Robot::handle(size_t link, const Command& command, uint32_t now) {
  switch (motion_.command(command, now)) {
    case MotionCore::Outcome::Accepted:
      return;
    case MotionCore::Outcome::NeedsCalibration:
      replyError(link, commandLetter(command.type), "cpm");
      return;
    case MotionCore::Outcome::NotMotion:
      break;
  }
  switch (command.type) {
    case CommandType::Drive:
    case CommandType::Speed:
      return;
    case CommandType::Tilt:
      tilt_.setTarget(command.tilt);
      return;
    case CommandType::Stop:
      motors_.write(motion_.stopNow(now));
      replyOk(link);
      return;
    case CommandType::Ping: {
      TextWriter w(out_, sizeof(out_));
      if (formatPing(w, command.token)) links_.reply(link, w.c_str(), w.length());
      return;
    }
    case CommandType::Query:
      replyStatus(link);
      return;
    case CommandType::ConfigList:
      listConfig(link);
      return;
    case CommandType::ConfigGet:
    case CommandType::ConfigSet:
      handleConfig(link, command, now);
      return;
    case CommandType::Hello:
      handleHello(link, command);
      return;
    case CommandType::Verify:
      handleVerify(link, command, now);
      return;
    case CommandType::KeySet:
    case CommandType::KeyClear:
    case CommandType::KeyQuery:
      handleKey(link, command, now);
      return;
    case CommandType::Reboot:
      motion_.halt();
      motors_.brake();
      replyOk(link);
      rebootPending_ = true;
      rebootAt_ = now + timing::RebootDelayMs;
      return;
  }
}

void Robot::handleHello(size_t link, const Command& command) {
  LinkGuard* guard = links_.guard(link);
  uint8_t nonce[LinkGuard::kNonceSize];
  esp_fill_random(nonce, sizeof(nonce));
  TextWriter w(out_, sizeof(out_));
  if (guard == nullptr || !guard->challenge(secret_, command.value, nonce, w)) {
    replyError(link, 'H', "key");
    return;
  }
  links_.reply(link, w.c_str(), w.length());
}

void Robot::handleVerify(size_t link, const Command& command, uint32_t now) {
  LinkGuard* guard = links_.guard(link);
  if (guard == nullptr || !guard->verify(command.value)) {
    replyError(link, 'V', "auth");
    return;
  }
  replyOk(link);
  guard->commit(now);
}

void Robot::handleKey(size_t link, const Command& command, uint32_t now) {
  if (command.type == CommandType::KeyQuery) {
    TextWriter w(out_, sizeof(out_));
    if (formatKeyState(w, secret_.present)) links_.reply(link, w.c_str(), w.length());
    return;
  }
  if (!writes_.take(now)) {
    replyError(link, 'K', "busy");
    return;
  }
  if (command.type == CommandType::KeyClear) {
    if (!store_.clearLinkKey()) {
      replyError(link, 'K', "nvs");
      return;
    }
    secret_ = LinkSecret();
  } else {
    LinkSecret next;
    if (!fromHex(command.value, strlen(command.value), next.key, LinkSecret::kSize)) {
      replyError(link, 'K', "value");
      return;
    }
    if (!store_.saveLinkKey(next.key, LinkSecret::kSize)) {
      replyError(link, 'K', "nvs");
      return;
    }
    next.present = true;
    secret_ = next;
  }
  for (size_t i = 0; i < LinkMux::kMaxLinks; ++i) {
    if (i != link && !links_.trusted(i)) links_.drop(i);
  }
  replyOk(link);
}

void Robot::handleConfig(size_t link, const Command& command, uint32_t now) {
  SettingKey key;
  if (!settingFromName(command.key, key)) {
    replyError(link, 'C', "key");
    return;
  }
  if (command.type == CommandType::ConfigGet) {
    replyConfig(link, key);
    return;
  }
  Settings candidate = settings_;
  SettingError error = applySetting(candidate, key, command.value);
  if (error != SettingError::None) {
    replyError(link, 'C', settingErrorReason(error));
    return;
  }
  if (sameSetting(candidate, settings_, key)) {
    replyOk(link);
    return;
  }
  if (!writes_.take(now)) {
    replyError(link, 'C', "busy");
    return;
  }
  settings_ = candidate;
  applySettings();
  if (!store_.save(settings_, key)) {
    replyError(link, 'C', "nvs");
    return;
  }
  replyOk(link);
}

void Robot::applySettings() {
  ReflexSettings reflex;
  reflex.edgeMm = settings_.edge;
  reflex.stopMm = settings_.stop;
  reflex.countsPerMm = settings_.cpm;
  motion_.configure(reflex);
  tilt_.configure(TiltLimits{settings_.tmin, settings_.tmax, settings_.trim});
}

void Robot::listConfig(size_t link) {
  for (size_t i = 0; i < kSettingCount; ++i) replyConfig(link, settingAt(i));
  replyOk(link);
}

void Robot::replyConfig(size_t link, SettingKey key) {
  char value[Settings::kPassSize + 8];
  TextWriter v(value, sizeof(value));
  formatSettingValue(settings_, key, v);
  TextWriter w(out_, sizeof(out_));
  if (formatConfig(w, settingName(key), v.c_str())) links_.reply(link, w.c_str(), w.length());
}

void Robot::replyOk(size_t link) {
  TextWriter w(out_, sizeof(out_));
  formatOk(w);
  links_.reply(link, w.c_str(), w.length());
}

void Robot::replyError(size_t link, char command, const char* reason) {
  TextWriter w(out_, sizeof(out_));
  if (formatError(w, command, reason)) links_.reply(link, w.c_str(), w.length());
}

void Robot::replyStatus(size_t link) {
  TextWriter w(out_, sizeof(out_));
  if (formatStatus(w, status())) links_.reply(link, w.c_str(), w.length());
}

StatusData Robot::status() const {
  StatusData s;
  s.ms = millis();
  s.encLeft = encLeft_;
  s.encRight = encRight_;
  s.frontMm = ranging_.front().reportMm();
  s.downMm = ranging_.down().reportMm();
  s.bump = bump_.state();
  s.dock = dock_.seated();
  s.packMv = pack_.millivolts();
  s.tilt = tilt_.position();
  s.flags = motion_.flags();
  return s;
}

void Robot::broadcastStatus() {
  if (!links_.anyConnected()) return;
  TextWriter w(out_, sizeof(out_));
  if (formatStatus(w, status())) links_.broadcast(w.c_str(), w.length());
}

void Robot::broadcastAir() {
  if (!links_.anyConnected()) return;
  TextWriter w(out_, sizeof(out_));
  if (formatAir(w, air_.data())) links_.broadcast(w.c_str(), w.length());
}

void Robot::flushEvents() {
  Event event;
  while (events_.pop(event)) {
    TextWriter w(out_, sizeof(out_));
    if (formatEvent(w, event)) links_.broadcast(w.c_str(), w.length());
  }
}

}
