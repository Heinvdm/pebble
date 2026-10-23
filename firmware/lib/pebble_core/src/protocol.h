#pragma once

#include <stddef.h>
#include <stdint.h>

#include "events.h"
#include "text_writer.h"

namespace pebble {

constexpr size_t kMaxLineLength = 96;
constexpr size_t kLineBufferSize = kMaxLineLength + 2;
constexpr size_t kNonceHexLength = 32;
constexpr size_t kKeyHexLength = 64;
constexpr int kMaxWheelPower = 1000;
constexpr int kMaxWheelSpeed = 1000;
constexpr int kMaxTiltDegrees = 90;

namespace StatusFlag {
constexpr uint8_t EdgeHold = 1;
constexpr uint8_t BumpHold = 2;
constexpr uint8_t ObstacleAhead = 4;
constexpr uint8_t Stall = 8;
constexpr uint8_t LowBattery = 16;
constexpr uint8_t Deadman = 32;
constexpr uint8_t SensorFault = 64;
constexpr uint8_t ReverseLimit = 128;
}

enum class CommandType : uint8_t {
  Drive,
  Speed,
  Tilt,
  Stop,
  Ping,
  Query,
  ConfigSet,
  ConfigGet,
  ConfigList,
  Reboot,
  Hello,
  Verify,
  KeySet,
  KeyClear,
  KeyQuery
};

struct Command {
  static constexpr size_t kKeySize = 16;
  static constexpr size_t kTokenSize = 24;

  CommandType type = CommandType::Stop;
  int left = 0;
  int right = 0;
  int tilt = 0;
  char key[kKeySize] = {0};
  char value[kLineBufferSize] = {0};
  char token[kTokenSize] = {0};
};

enum class ParseResult : uint8_t { Ok, Empty, Unknown, Syntax };

ParseResult parseCommand(const char* line, Command& out);
const char* parseResultReason(ParseResult result);
char commandLetter(CommandType type);
char lineCommandLetter(const char* line);
constexpr char kUnknownCommandLetter = '?';
bool isReverseCommand(int left, int right);

struct StatusData {
  uint32_t ms = 0;
  int64_t encLeft = 0;
  int64_t encRight = 0;
  int frontMm = -1;
  int downMm = -1;
  uint8_t bump = 0;
  bool dock = false;
  int packMv = 0;
  int tilt = 0;
  uint8_t flags = 0;
};

constexpr int kAirVersion = 1;

struct AirData {
  uint32_t ms = 0;
  bool present = false;
  float temperatureC = 0.0f;
  float humidityPct = 0.0f;
  uint32_t pressurePa = 0;
  int32_t gasOhm = -1;
  uint32_t heatedS = 0;
};

bool formatStatus(TextWriter& out, const StatusData& status);
bool formatAir(TextWriter& out, const AirData& air);
bool formatEvent(TextWriter& out, const Event& event);
bool formatPing(TextWriter& out, const char* token);
bool formatOk(TextWriter& out);
bool formatError(TextWriter& out, char command, const char* reason);
bool formatConfig(TextWriter& out, const char* key, const char* value);
bool formatChallenge(TextWriter& out, const char* nonceHex, const char* proofHex);
bool formatKeyState(TextWriter& out, bool present);

}
