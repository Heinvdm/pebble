#pragma once

#include <stdint.h>

#include "events.h"

namespace pebble {

enum class RangeState : uint8_t { Unknown, Valid, NoTarget };

struct RangeReading {
  RangeState state = RangeState::Unknown;
  int mm = -1;

  static RangeReading valid(int mm) { return RangeReading{RangeState::Valid, mm}; }
  static RangeReading noTarget() { return RangeReading{RangeState::NoTarget, -1}; }
  static RangeReading unknown() { return RangeReading{RangeState::Unknown, -1}; }
  int reportMm() const { return state == RangeState::Valid ? mm : -1; }
};

namespace FaultBit {
constexpr uint8_t Front = 1;
constexpr uint8_t Drop = 2;
constexpr uint8_t Bump = 4;
constexpr uint8_t Battery = 8;
constexpr uint8_t All = Front | Drop | Bump | Battery;
}

const char* faultName(uint8_t bit);

struct Wheels {
  int left = 0;
  int right = 0;
};

inline bool anyForward(const Wheels& w) { return w.left > 0 || w.right > 0; }

struct ReflexTuning {
  uint32_t deadmanMs = 500;
  int edgeReverseMm = 40;
  int bumpReverseMm = 30;
  uint32_t bumpHoldMs = 1000;
  int obstacleHysteresisMm = 10;
  int stallPower = 300;
  uint32_t stallWindowMs = 400;
  int stallMinCounts = 2;
  uint32_t stallHoldMs = 1000;
  int lowMv = 3300;
  uint32_t lowMs = 5000;
  int lowClearMv = 3400;
  uint32_t lowClearMs = 5000;
  int lowCap = 500;
  int criticalMv = 3100;
  uint32_t criticalMs = 500;
  int criticalClearMv = 3200;
  uint32_t criticalClearMs = 2000;
  int reversePower = 450;
  int reverseMmPerSecond = 90;
  uint32_t maneuverTimeoutMs = 2500;
  int reverseCap = 450;
  int reverseCreditMaxMm = 500;
  int64_t reverseCreditMaxCounts = 10000;
  int64_t turnResetCounts = 40;
};

struct ReflexSettings {
  int edgeMm = 75;
  int stopMm = 60;
  float countsPerMm = 0.0f;
};

struct ReflexSense {
  RangeReading front;
  RangeReading down;
  uint8_t bump = 0;
  int packMv = 0;
  bool packValid = false;
  int64_t encLeft = 0;
  int64_t encRight = 0;
  uint8_t faults = 0;
};

struct ReflexLimits {
  bool refuse = false;
  bool maneuver = false;
  Wheels maneuverPower;
  bool forwardBlocked = false;
  bool holdLeft = false;
  bool holdRight = false;
  int cap = 1000;
  bool reverseBlocked = false;
  int reverseCap = 1000;
  bool cancelCommand = false;
};

Wheels applyLimits(Wheels desired, const ReflexLimits& limits);

class Reflexes {
 public:
  Reflexes();
  explicit Reflexes(const ReflexTuning& tuning);

  void configure(const ReflexSettings& settings) { settings_ = settings; }
  void motionKeepAlive(uint32_t now);
  void clearHolds(uint32_t now);
  void motionCommanded(int left, int right);

  const ReflexLimits& update(uint32_t now, const ReflexSense& sense, Wheels desired, Wheels applied, bool commandActive,
                             EventQueue& events);

  const ReflexLimits& limits() const { return limits_; }
  uint8_t flags() const;
  bool edgeHold() const { return edgeHold_; }
  bool bumpHold() const { return bumpHoldActive_; }
  bool obstacle() const { return obstacle_; }
  bool lowBattery() const { return low_; }
  bool criticalBattery() const { return critical_; }
  bool deadmanTripped() const { return deadmanTripped_; }
  bool maneuverActive() const { return maneuver_.active; }
  bool stalled(Wheel wheel) const { return stall_[static_cast<int>(wheel)].holding; }
  int64_t reverseCredit() const { return reverseCredit_; }
  bool reverseRefused() const { return reverseRefused_; }

 private:
  struct Timer {
    bool armed = false;
    uint32_t since = 0;
  };

  struct StallTracker {
    bool primed = false;
    int64_t windowCount = 0;
    uint32_t windowStart = 0;
    bool holding = false;
    uint32_t until = 0;
  };

  struct Maneuver {
    bool active = false;
    uint32_t start = 0;
    int64_t startLeft = 0;
    int64_t startRight = 0;
    int distanceMm = 0;
  };

  static bool elapsed(uint32_t now, uint32_t since, uint32_t duration);
  static bool before(uint32_t now, uint32_t until);
  static void arm(Timer& timer, bool condition, uint32_t now);

  void updateFaults(const ReflexSense& sense, EventQueue& events, bool& cancel);
  void updateBattery(uint32_t now, const ReflexSense& sense, EventQueue& events, bool& cancel);
  void updateDeadman(uint32_t now, bool commandActive, EventQueue& events, bool& cancel);
  void updateBump(uint32_t now, const ReflexSense& sense, Wheels desired, Wheels applied, EventQueue& events,
                  bool& cancel);
  void updateObstacle(const ReflexSense& sense, EventQueue& events);
  void updateStall(StallTracker& tracker, Wheel wheel, int power, int64_t count, uint32_t now, EventQueue& events);
  void updateManeuver(uint32_t now, const ReflexSense& sense);
  void updateReverse(const ReflexSense& sense, Wheels desired);
  int64_t reverseCreditMax() const;
  void updateEdge(uint32_t now, const ReflexSense& sense, Wheels desired, Wheels applied, EventQueue& events,
                  bool& cancel);
  void startManeuver(uint32_t now, const ReflexSense& sense, int distanceMm);
  void buildLimits(bool cancel);

  ReflexTuning tuning_;
  ReflexSettings settings_;
  ReflexLimits limits_;

  uint8_t activeFaults_ = 0;
  uint32_t lastMotion_ = 0;
  bool deadmanTripped_ = false;
  uint8_t lastBump_ = 0;
  bool bumpHoldActive_ = false;
  uint32_t bumpHoldUntil_ = 0;
  bool edgeHold_ = false;
  bool obstacle_ = false;
  bool low_ = false;
  bool critical_ = false;
  Timer lowTimer_;
  Timer lowClearTimer_;
  Timer criticalTimer_;
  Timer criticalClearTimer_;
  StallTracker stall_[2];
  Maneuver maneuver_;
  bool encodersSeen_ = false;
  int64_t lastEncLeft_ = 0;
  int64_t lastEncRight_ = 0;
  int64_t reverseCredit_ = 0;
  int64_t turned_ = 0;
  bool reverseRefused_ = false;
};

}
