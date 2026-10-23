#include "motion.h"

namespace pebble {

MotionCore::MotionCore() : MotionCore(DriveTuning(), ReflexTuning()) {}

MotionCore::MotionCore(const DriveTuning& drive, const ReflexTuning& reflex) : drive_(drive), reflexes_(reflex) {}

void MotionCore::configure(const ReflexSettings& settings) {
  countsPerMm_ = settings.countsPerMm;
  reflexes_.configure(settings);
}

MotionCore::Outcome MotionCore::command(const Command& command, uint32_t now) {
  switch (command.type) {
    case CommandType::Drive:
      reflexes_.motionCommanded(command.left, command.right);
      reflexes_.motionKeepAlive(now);
      drive_.commandPower(command.left, command.right);
      return Outcome::Accepted;
    case CommandType::Speed:
      if (countsPerMm_ <= 0.0f) return Outcome::NeedsCalibration;
      reflexes_.motionCommanded(command.left, command.right);
      reflexes_.motionKeepAlive(now);
      drive_.commandSpeed(command.left, command.right, countsPerMm_);
      return Outcome::Accepted;
    default:
      return Outcome::NotMotion;
  }
}

Wheels MotionCore::stopNow(uint32_t now) {
  drive_.stop();
  reflexes_.clearHolds(now);
  return drive_.finish(Wheels{}, reflexes_.limits(), 0);
}

void MotionCore::halt() { drive_.stop(); }

Wheels MotionCore::tick(uint32_t now, uint32_t dtMs, const ReflexSense& sense, Wheels applied, EventQueue& events) {
  Wheels desired = drive_.desired(dtMs, sense.encLeft, sense.encRight, countsPerMm_);
  const ReflexLimits& limits = reflexes_.update(now, sense, desired, applied, drive_.commandActive(), events);
  if (limits.cancelCommand) {
    drive_.stop();
    desired = Wheels{};
  }
  return drive_.finish(desired, limits, dtMs);
}

}
