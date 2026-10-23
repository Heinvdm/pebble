#include "reflexes.h"

#include "protocol.h"

namespace pebble {

namespace {

int absInt(int v) { return v < 0 ? -v : v; }

int64_t absInt64(int64_t v) { return v < 0 ? -v : v; }

Wheels capWheels(Wheels w, int cap) {
  if (cap < 0) cap = 0;
  int peak = absInt(w.left) > absInt(w.right) ? absInt(w.left) : absInt(w.right);
  if (peak <= cap) return w;
  w.left = static_cast<int>(static_cast<int64_t>(w.left) * cap / peak);
  w.right = static_cast<int>(static_cast<int64_t>(w.right) * cap / peak);
  return w;
}

Wheels limitReverse(Wheels w, const ReflexLimits& limits) {
  if (!limits.reverseBlocked) return capWheels(w, limits.reverseCap);
  if (limits.holdLeft || limits.holdRight) return Wheels{w.left > 0 ? w.left : 0, w.right > 0 ? w.right : 0};
  int half = (w.left - w.right) / 2;
  return Wheels{half, -half};
}

}

const char* faultName(uint8_t bit) {
  switch (bit) {
    case FaultBit::Front:
      return "front";
    case FaultBit::Drop:
      return "drop";
    case FaultBit::Bump:
      return "bump";
    case FaultBit::Battery:
      return "battery";
    default:
      return "unknown";
  }
}

Wheels applyLimits(Wheels desired, const ReflexLimits& limits) {
  if (limits.refuse) return Wheels{};
  Wheels w = limits.maneuver ? limits.maneuverPower : desired;
  if (limits.holdLeft && limits.holdRight) return Wheels{};
  if (limits.holdLeft) {
    w.left = 0;
    if (limits.forwardBlocked && w.right > 0) w.right = 0;
  } else if (limits.holdRight) {
    w.right = 0;
    if (limits.forwardBlocked && w.left > 0) w.left = 0;
  } else if (limits.forwardBlocked && w.left + w.right > 0) {
    int half = (w.left - w.right) / 2;
    w.left = half;
    w.right = -half;
  }
  if (!limits.maneuver && w.left + w.right < 0) w = limitReverse(w, limits);
  return capWheels(w, limits.cap);
}

Reflexes::Reflexes() : Reflexes(ReflexTuning()) {}

Reflexes::Reflexes(const ReflexTuning& tuning) : tuning_(tuning) {}

bool Reflexes::elapsed(uint32_t now, uint32_t since, uint32_t duration) {
  return static_cast<uint32_t>(now - since) >= duration;
}

bool Reflexes::before(uint32_t now, uint32_t until) { return static_cast<int32_t>(until - now) > 0; }

void Reflexes::arm(Timer& timer, bool condition, uint32_t now) {
  if (!condition) {
    timer.armed = false;
    return;
  }
  if (!timer.armed) {
    timer.armed = true;
    timer.since = now;
  }
}

void Reflexes::motionKeepAlive(uint32_t now) {
  lastMotion_ = now;
  deadmanTripped_ = false;
}

void Reflexes::clearHolds(uint32_t now) {
  edgeHold_ = false;
  bumpHoldActive_ = false;
  bumpHoldUntil_ = now;
  maneuver_.active = false;
  deadmanTripped_ = false;
  reverseRefused_ = false;
  for (StallTracker& s : stall_) s = StallTracker();
  buildLimits(true);
}

void Reflexes::motionCommanded(int left, int right) {
  if (isReverseCommand(left, right)) edgeHold_ = false;
}

const ReflexLimits& Reflexes::update(uint32_t now, const ReflexSense& sense, Wheels desired, Wheels applied,
                                     bool commandActive, EventQueue& events) {
  bool cancel = false;
  updateFaults(sense, events, cancel);
  updateBattery(now, sense, events, cancel);
  updateDeadman(now, commandActive, events, cancel);
  updateBump(now, sense, desired, applied, events, cancel);
  updateObstacle(sense, events);
  updateStall(stall_[0], Wheel::Left, applied.left, sense.encLeft, now, events);
  updateStall(stall_[1], Wheel::Right, applied.right, sense.encRight, now, events);
  updateManeuver(now, sense);
  updateReverse(sense, desired);
  buildLimits(cancel);
  updateEdge(now, sense, cancel ? Wheels{} : desired, applied, events, cancel);
  buildLimits(cancel);
  return limits_;
}

void Reflexes::updateFaults(const ReflexSense& sense, EventQueue& events, bool& cancel) {
  uint8_t current = sense.faults & FaultBit::All;
  uint8_t fresh = static_cast<uint8_t>(current & ~activeFaults_);
  for (uint8_t bit = 1; bit != 0 && bit <= FaultBit::All; bit = static_cast<uint8_t>(bit << 1)) {
    if (fresh & bit) events.push(Event::fault(faultName(bit)));
  }
  if (fresh) cancel = true;
  activeFaults_ = current;
}

void Reflexes::updateBattery(uint32_t now, const ReflexSense& sense, EventQueue& events, bool& cancel) {
  if (!sense.packValid) return;
  int mv = sense.packMv;
  arm(lowTimer_, mv < tuning_.lowMv, now);
  arm(criticalTimer_, mv < tuning_.criticalMv, now);
  arm(lowClearTimer_, low_ && mv >= tuning_.lowClearMv, now);
  arm(criticalClearTimer_, critical_ && mv >= tuning_.criticalClearMv, now);

  if (!critical_ && criticalTimer_.armed && elapsed(now, criticalTimer_.since, tuning_.criticalMs)) {
    critical_ = true;
    cancel = true;
    criticalClearTimer_.armed = false;
    if (!low_) {
      low_ = true;
      lowClearTimer_.armed = false;
      events.push(Event::lowBat(mv));
    }
  }
  if (!low_ && lowTimer_.armed && elapsed(now, lowTimer_.since, tuning_.lowMs)) {
    low_ = true;
    lowClearTimer_.armed = false;
    events.push(Event::lowBat(mv));
  }
  if (critical_ && criticalClearTimer_.armed && elapsed(now, criticalClearTimer_.since, tuning_.criticalClearMs)) {
    critical_ = false;
    criticalClearTimer_.armed = false;
  }
  if (low_ && !critical_ && lowClearTimer_.armed && elapsed(now, lowClearTimer_.since, tuning_.lowClearMs)) {
    low_ = false;
    lowClearTimer_.armed = false;
  }
}

void Reflexes::updateDeadman(uint32_t now, bool commandActive, EventQueue& events, bool& cancel) {
  if (deadmanTripped_ || !commandActive) return;
  if (!elapsed(now, lastMotion_, tuning_.deadmanMs)) return;
  deadmanTripped_ = true;
  cancel = true;
  events.push(Event::deadman());
}

void Reflexes::updateBump(uint32_t now, const ReflexSense& sense, Wheels desired, Wheels applied,
                          EventQueue& events, bool& cancel) {
  uint8_t bump = sense.bump & 3u;
  if (bump != lastBump_) {
    if (bump != 0) events.push(Event::bump(bump));
    if (lastBump_ == 0 && bump != 0) {
      bool forward = anyForward(applied) || (!cancel && anyForward(applyLimits(desired, limits_)));
      cancel = true;
      if (forward && !maneuver_.active) startManeuver(now, sense, tuning_.bumpReverseMm);
    }
    lastBump_ = bump;
  }
  if (bump != 0) {
    bumpHoldActive_ = true;
    bumpHoldUntil_ = now + tuning_.bumpHoldMs;
  } else if (bumpHoldActive_ && !before(now, bumpHoldUntil_)) {
    bumpHoldActive_ = false;
  }
}

void Reflexes::updateObstacle(const ReflexSense& sense, EventQueue& events) {
  bool valid = sense.front.state == RangeState::Valid;
  bool below = valid && sense.front.mm < settings_.stopMm;
  bool stillNear = valid && sense.front.mm < settings_.stopMm + tuning_.obstacleHysteresisMm;
  if (!obstacle_ && below) {
    obstacle_ = true;
    events.push(Event::obstacle(sense.front.mm));
  } else if (obstacle_ && !stillNear) {
    obstacle_ = false;
  }
}

void Reflexes::updateStall(StallTracker& tracker, Wheel wheel, int power, int64_t count, uint32_t now,
                           EventQueue& events) {
  if (tracker.holding) {
    if (before(now, tracker.until)) return;
    tracker = StallTracker();
  }
  if (!tracker.primed || absInt(power) <= tuning_.stallPower ||
      absInt64(count - tracker.windowCount) >= tuning_.stallMinCounts) {
    tracker.primed = true;
    tracker.windowCount = count;
    tracker.windowStart = now;
    return;
  }
  if (elapsed(now, tracker.windowStart, tuning_.stallWindowMs)) {
    tracker.holding = true;
    tracker.until = now + tuning_.stallHoldMs;
    events.push(Event::stall(wheel));
  }
}

void Reflexes::startManeuver(uint32_t now, const ReflexSense& sense, int distanceMm) {
  maneuver_.active = true;
  maneuver_.start = now;
  maneuver_.startLeft = sense.encLeft;
  maneuver_.startRight = sense.encRight;
  maneuver_.distanceMm = distanceMm;
}

void Reflexes::updateManeuver(uint32_t now, const ReflexSense& sense) {
  if (!maneuver_.active) return;
  if (activeFaults_ != 0 || critical_) {
    maneuver_.active = false;
    return;
  }
  uint32_t ran = now - maneuver_.start;
  if (ran >= tuning_.maneuverTimeoutMs) {
    maneuver_.active = false;
    return;
  }
  float travelled;
  if (settings_.countsPerMm > 0.0f) {
    int64_t back = (maneuver_.startLeft - sense.encLeft) + (maneuver_.startRight - sense.encRight);
    travelled = static_cast<float>(back) / 2.0f / settings_.countsPerMm;
  } else {
    travelled = static_cast<float>(ran) * static_cast<float>(tuning_.reverseMmPerSecond) / 1000.0f;
  }
  if (travelled >= static_cast<float>(maneuver_.distanceMm)) maneuver_.active = false;
}

void Reflexes::updateEdge(uint32_t now, const ReflexSense& sense, Wheels desired, Wheels applied,
                          EventQueue& events, bool& cancel) {
  bool beyond = sense.down.state == RangeState::NoTarget ||
                (sense.down.state == RangeState::Valid && sense.down.mm > settings_.edgeMm);
  if (!beyond || limits_.refuse) return;
  bool forward = anyForward(applied) || anyForward(applyLimits(desired, limits_));
  if (!forward) return;
  events.push(Event::edge());
  cancel = true;
  edgeHold_ = true;
  startManeuver(now, sense, tuning_.edgeReverseMm);
}

int64_t Reflexes::reverseCreditMax() const {
  if (settings_.countsPerMm > 0.0f) {
    return static_cast<int64_t>(static_cast<float>(tuning_.reverseCreditMaxMm) * settings_.countsPerMm);
  }
  return tuning_.reverseCreditMaxCounts;
}

void Reflexes::updateReverse(const ReflexSense& sense, Wheels desired) {
  if (!encodersSeen_) {
    encodersSeen_ = true;
    lastEncLeft_ = sense.encLeft;
    lastEncRight_ = sense.encRight;
  }
  int64_t left = sense.encLeft - lastEncLeft_;
  int64_t right = sense.encRight - lastEncRight_;
  lastEncLeft_ = sense.encLeft;
  lastEncRight_ = sense.encRight;
  int64_t turn = left - right;
  int64_t move = left + right;
  if (absInt64(turn) > absInt64(move)) {
    turned_ += turn;
    if (absInt64(turned_) >= tuning_.turnResetCounts) {
      reverseCredit_ = 0;
      turned_ = 0;
    }
  } else {
    reverseCredit_ += move / 2;
  }
  int64_t most = reverseCreditMax();
  if (reverseCredit_ > most) reverseCredit_ = most;
  if (reverseCredit_ < 0) reverseCredit_ = 0;
  reverseRefused_ = !maneuver_.active && desired.left + desired.right < 0 && reverseCredit_ <= 0;
}

void Reflexes::buildLimits(bool cancel) {
  limits_.refuse = activeFaults_ != 0 || critical_;
  limits_.maneuver = maneuver_.active && !limits_.refuse;
  limits_.maneuverPower = Wheels{-tuning_.reversePower, -tuning_.reversePower};
  limits_.forwardBlocked = edgeHold_ || bumpHoldActive_ || obstacle_;
  limits_.holdLeft = stall_[0].holding;
  limits_.holdRight = stall_[1].holding;
  limits_.cap = (low_ || critical_) ? tuning_.lowCap : 1000;
  limits_.reverseBlocked = reverseCredit_ <= 0;
  limits_.reverseCap = tuning_.reverseCap;
  limits_.cancelCommand = cancel;
}

uint8_t Reflexes::flags() const {
  uint8_t f = 0;
  if (edgeHold_) f |= StatusFlag::EdgeHold;
  if (bumpHoldActive_) f |= StatusFlag::BumpHold;
  if (obstacle_) f |= StatusFlag::ObstacleAhead;
  if (stall_[0].holding || stall_[1].holding) f |= StatusFlag::Stall;
  if (low_ || critical_) f |= StatusFlag::LowBattery;
  if (deadmanTripped_) f |= StatusFlag::Deadman;
  if (activeFaults_ != 0) f |= StatusFlag::SensorFault;
  if (reverseRefused_) f |= StatusFlag::ReverseLimit;
  return f;
}

}
