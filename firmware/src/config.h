#pragma once

#include <stdint.h>

#ifndef PEBBLE_VERSION
#define PEBBLE_VERSION "0.0.0"
#endif

namespace pebble {

constexpr const char* kFirmwareVersion = PEBBLE_VERSION;
constexpr const char* kDeviceName = "Pebble";
constexpr const char* kHostName = "pebble";
constexpr uint16_t kTcpPort = 7777;
constexpr uint32_t kUsbBaud = 115200;

namespace pins {
constexpr int Pack = 1;
constexpr int Bump = 2;
constexpr int RightEncoderB = 3;
constexpr int Dock = 4;
constexpr int Sda = 5;
constexpr int Scl = 6;
constexpr int LeftEncoderB = 7;
constexpr int Servo = 8;
constexpr int LeftIn1 = 9;
constexpr int LeftIn2 = 10;
constexpr int RightIn1 = 11;
constexpr int RightIn2 = 12;
constexpr int LeftEncoderA = 13;
constexpr int DropXshut = 43;
constexpr int RightEncoderA = 44;
}

namespace motor {
constexpr uint32_t PwmHz = 20000;
constexpr uint8_t PwmBits = 10;
constexpr uint8_t ChannelLeftIn1 = 0;
constexpr uint8_t ChannelLeftIn2 = 1;
constexpr uint8_t ChannelRightIn1 = 2;
constexpr uint8_t ChannelRightIn2 = 3;
constexpr bool LeftReversed = false;
constexpr bool RightReversed = true;
}

namespace encoder {
constexpr bool LeftReversed = false;
constexpr bool RightReversed = true;
constexpr uint16_t GlitchFilter = 1023;
}

namespace servo {
constexpr uint8_t Channel = 4;
constexpr uint32_t PwmHz = 50;
constexpr uint8_t PwmBits = 14;
constexpr int Direction = 1;
constexpr int CentreUs = 1500;
constexpr int UsPer90Deg = 1000;
constexpr int MinUs = 500;
constexpr int MaxUs = 2500;
constexpr float SlewDegPerSecond = 120.0f;
}

namespace ranging {
constexpr uint8_t FrontAddress = 0x30;
constexpr uint8_t DefaultAddress = 0x29;
constexpr uint32_t I2cHz = 400000;
constexpr uint16_t I2cTimeoutMs = 10;
constexpr uint16_t SensorTimeoutMs = 60;
constexpr uint32_t FrontBudgetUs = 33000;
constexpr uint32_t DropBudgetUs = 20000;
constexpr uint32_t PollIntervalMs = 5;
constexpr uint32_t StaleMs = 250;
constexpr uint32_t RetryMs = 1000;
constexpr int NoTargetMm = 8190;
}

namespace analog {
constexpr uint32_t BumpSampleMs = 2;
constexpr uint32_t BumpDebounceMs = 10;
constexpr uint32_t BumpFaultMs = 30;
constexpr uint32_t PackSampleMs = 20;
constexpr float PackFilterTauMs = 400.0f;
constexpr float PackDividerRatio = 2.0f;
constexpr float PackCalibration = 1.0f;
constexpr int PackImplausibleMv = 4700;
constexpr uint32_t PackFaultMs = 500;
}

namespace air {
constexpr uint32_t SampleMs = 3000;
constexpr uint32_t MaxDeferMs = 3000;
constexpr uint32_t RetryMs = 30000;
constexpr uint32_t SettleMs = 200;
constexpr uint16_t HeaterC = 320;
constexpr uint16_t HeaterMs = 150;
}

namespace dock {
constexpr uint32_t DebounceMs = 50;
}

namespace timing {
constexpr uint32_t ControlMs = 10;
constexpr uint32_t StatusMs = 50;
constexpr uint32_t ServoMs = 20;
constexpr uint32_t RebootDelayMs = 200;
}

namespace wifi {
constexpr uint32_t ConnectTimeoutMs = 15000;
constexpr uint32_t RetryMs = 10000;
}

}
