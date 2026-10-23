#include <unity.h>

#include "events.h"
#include "protocol.h"
#include "reflexes.h"

using namespace pebble;

void setUp() {}
void tearDown() {}

namespace {

struct Rig {
  Reflexes reflexes;
  EventQueue events;
  ReflexSense sense;
  uint32_t now = 1000;

  Rig() {
    ReflexSettings settings;
    settings.edgeMm = 75;
    settings.stopMm = 60;
    settings.countsPerMm = 0.0f;
    reflexes.configure(settings);
    sense.front = RangeReading::valid(500);
    sense.down = RangeReading::valid(45);
    sense.packMv = 3900;
    sense.packValid = true;
    reflexes.motionKeepAlive(now);
  }

  const ReflexLimits& tick(Wheels desired, Wheels applied, bool active = true, uint32_t dt = 10) {
    now += dt;
    return reflexes.update(now, sense, desired, applied, active, events);
  }

  bool popType(EventType type, Event* out = nullptr) {
    Event e;
    while (events.pop(e)) {
      if (e.type == type) {
        if (out) *out = e;
        return true;
      }
    }
    return false;
  }

  void keepAlive() { reflexes.motionKeepAlive(now); }

  void rolled(int64_t left, int64_t right) {
    tick(W0(), W0(), false);
    sense.encLeft += left;
    sense.encRight += right;
    tick(W0(), W0(), false);
  }

  static Wheels W0() { return Wheels{}; }
};

Wheels W(int l, int r) { return Wheels{l, r}; }

}

static void test_apply_limits_passthrough() {
  ReflexLimits lim;
  Wheels w = applyLimits(W(400, -300), lim);
  TEST_ASSERT_EQUAL_INT(400, w.left);
  TEST_ASSERT_EQUAL_INT(-300, w.right);
}

static void test_apply_limits_forward_clamp_keeps_turning() {
  ReflexLimits lim;
  lim.forwardBlocked = true;
  Wheels arc = applyLimits(W(300, 500), lim);
  TEST_ASSERT_EQUAL_INT(0, arc.left + arc.right);
  TEST_ASSERT_EQUAL_INT(-100, arc.left);
  TEST_ASSERT_EQUAL_INT(100, arc.right);
  Wheels spin = applyLimits(W(-300, 300), lim);
  TEST_ASSERT_EQUAL_INT(-300, spin.left);
  TEST_ASSERT_EQUAL_INT(300, spin.right);
  Wheels back = applyLimits(W(-400, -200), lim);
  TEST_ASSERT_EQUAL_INT(-400, back.left);
  TEST_ASSERT_EQUAL_INT(-200, back.right);
  Wheels odd = applyLimits(W(301, 300), lim);
  TEST_ASSERT_TRUE(odd.left + odd.right <= 0);
}

static void test_apply_limits_cap_and_holds() {
  ReflexLimits lim;
  lim.cap = 500;
  Wheels w = applyLimits(W(1000, 500), lim);
  TEST_ASSERT_EQUAL_INT(500, w.left);
  TEST_ASSERT_EQUAL_INT(250, w.right);
  lim.cap = 1000;
  lim.holdRight = true;
  lim.forwardBlocked = true;
  Wheels h = applyLimits(W(300, -300), lim);
  TEST_ASSERT_EQUAL_INT(0, h.left);
  TEST_ASSERT_EQUAL_INT(0, h.right);
  lim.refuse = true;
  Wheels r = applyLimits(W(-300, -300), lim);
  TEST_ASSERT_EQUAL_INT(0, r.left);
  TEST_ASSERT_EQUAL_INT(0, r.right);
}

static void test_edge_stops_reverses_and_holds() {
  Rig rig;
  rig.tick(W(400, 400), W(400, 400));
  rig.sense.down = RangeReading::valid(120);
  const ReflexLimits& lim = rig.tick(W(400, 400), W(400, 400));
  TEST_ASSERT_TRUE(lim.cancelCommand);
  TEST_ASSERT_TRUE(lim.maneuver);
  TEST_ASSERT_TRUE(lim.maneuverPower.left < 0 && lim.maneuverPower.right < 0);
  TEST_ASSERT_TRUE(rig.reflexes.edgeHold());
  TEST_ASSERT_TRUE(rig.popType(EventType::Edge));
  TEST_ASSERT_TRUE(rig.reflexes.flags() & StatusFlag::EdgeHold);
  rig.sense.down = RangeReading::valid(45);
  for (int i = 0; i < 100; ++i) {
    rig.keepAlive();
    rig.sense.encLeft -= 10;
    rig.sense.encRight -= 10;
    rig.tick(W(0, 0), W(-450, -450), false);
  }
  TEST_ASSERT_FALSE(rig.reflexes.stalled(Wheel::Left));
  TEST_ASSERT_FALSE(rig.reflexes.maneuverActive());
  const ReflexLimits& held = rig.tick(W(300, 300), W(0, 0));
  Wheels out = applyLimits(W(300, 300), held);
  TEST_ASSERT_EQUAL_INT(0, out.left + out.right);
  rig.reflexes.motionCommanded(-200, -200);
  TEST_ASSERT_FALSE(rig.reflexes.edgeHold());
}

static void test_edge_reverse_distance_uses_encoders() {
  Rig rig;
  ReflexSettings settings;
  settings.countsPerMm = 10.0f;
  rig.reflexes.configure(settings);
  rig.sense.down = RangeReading::noTarget();
  rig.tick(W(300, 300), W(300, 300));
  TEST_ASSERT_TRUE(rig.reflexes.maneuverActive());
  rig.sense.encLeft = -390;
  rig.sense.encRight = -390;
  rig.tick(W(0, 0), W(-450, -450), false);
  TEST_ASSERT_TRUE(rig.reflexes.maneuverActive());
  rig.sense.encLeft = -400;
  rig.sense.encRight = -400;
  rig.tick(W(0, 0), W(-450, -450), false);
  TEST_ASSERT_FALSE(rig.reflexes.maneuverActive());
}

static void test_edge_ignored_when_reversing_or_still() {
  Rig rig;
  rig.sense.down = RangeReading::noTarget();
  const ReflexLimits& lim = rig.tick(W(-300, -300), W(-300, -300));
  TEST_ASSERT_FALSE(lim.cancelCommand);
  TEST_ASSERT_FALSE(rig.reflexes.edgeHold());
  rig.tick(W(0, 0), W(0, 0), false);
  TEST_ASSERT_FALSE(rig.reflexes.edgeHold());
  TEST_ASSERT_FALSE(rig.popType(EventType::Edge));
}

static void test_edge_cleared_by_x() {
  Rig rig;
  rig.sense.down = RangeReading::valid(200);
  rig.tick(W(300, 300), W(300, 300));
  TEST_ASSERT_TRUE(rig.reflexes.edgeHold());
  rig.reflexes.clearHolds(rig.now);
  TEST_ASSERT_FALSE(rig.reflexes.edgeHold());
  TEST_ASSERT_FALSE(rig.reflexes.maneuverActive());
}

static void test_bump_reverses_and_holds_forward_for_one_second() {
  Rig rig;
  rig.sense.bump = 1;
  const ReflexLimits& lim = rig.tick(W(300, 300), W(300, 300));
  TEST_ASSERT_TRUE(lim.cancelCommand);
  TEST_ASSERT_TRUE(lim.maneuver);
  Event e;
  TEST_ASSERT_TRUE(rig.popType(EventType::Bump, &e));
  TEST_ASSERT_EQUAL_INT(1, e.value);
  rig.sense.bump = 0;
  for (int i = 0; i < 50; ++i) {
    rig.keepAlive();
    rig.sense.encLeft -= 10;
    rig.sense.encRight -= 10;
    rig.tick(W(0, 0), W(-450, -450), false);
  }
  TEST_ASSERT_TRUE(rig.reflexes.bumpHold());
  TEST_ASSERT_TRUE(rig.reflexes.flags() & StatusFlag::BumpHold);
  for (int i = 0; i < 60; ++i) {
    rig.keepAlive();
    rig.tick(W(0, 0), W(0, 0), false);
  }
  TEST_ASSERT_FALSE(rig.reflexes.bumpHold());
  const ReflexLimits& free = rig.tick(W(300, 300), W(0, 0));
  Wheels out = applyLimits(W(300, 300), free);
  TEST_ASSERT_EQUAL_INT(300, out.left);
}

static void test_bump_while_still_only_holds() {
  Rig rig;
  rig.sense.bump = 2;
  const ReflexLimits& lim = rig.tick(W(0, 0), W(0, 0), false);
  TEST_ASSERT_TRUE(lim.cancelCommand);
  TEST_ASSERT_FALSE(lim.maneuver);
  TEST_ASSERT_TRUE(rig.reflexes.bumpHold());
  Event e;
  TEST_ASSERT_TRUE(rig.popType(EventType::Bump, &e));
  TEST_ASSERT_EQUAL_INT(2, e.value);
}

static void test_obstacle_clamps_forward_with_hysteresis() {
  Rig rig;
  rig.rolled(2000, 2000);
  rig.sense.front = RangeReading::valid(50);
  const ReflexLimits& lim = rig.tick(W(400, 400), W(400, 400));
  TEST_ASSERT_TRUE(lim.forwardBlocked);
  TEST_ASSERT_FALSE(lim.cancelCommand);
  Event e;
  TEST_ASSERT_TRUE(rig.popType(EventType::Obstacle, &e));
  TEST_ASSERT_EQUAL_INT(50, e.value);
  Wheels out = applyLimits(W(400, 400), lim);
  TEST_ASSERT_EQUAL_INT(0, out.left);
  TEST_ASSERT_EQUAL_INT(0, out.right);
  Wheels back = applyLimits(W(-300, -300), lim);
  TEST_ASSERT_EQUAL_INT(-300, back.left);
  rig.sense.front = RangeReading::valid(65);
  rig.tick(W(0, 0), W(0, 0));
  TEST_ASSERT_TRUE(rig.reflexes.obstacle());
  rig.sense.front = RangeReading::valid(80);
  rig.tick(W(0, 0), W(0, 0));
  TEST_ASSERT_FALSE(rig.reflexes.obstacle());
  rig.sense.front = RangeReading::noTarget();
  rig.tick(W(0, 0), W(0, 0));
  TEST_ASSERT_FALSE(rig.reflexes.obstacle());
}

static void test_stall_stops_one_wheel_for_one_second() {
  Rig rig;
  for (int i = 0; i < 40; ++i) {
    rig.keepAlive();
    rig.sense.encLeft += 50;
    rig.tick(W(500, 500), W(500, 500));
  }
  TEST_ASSERT_FALSE(rig.reflexes.stalled(Wheel::Right));
  rig.keepAlive();
  rig.sense.encLeft += 50;
  const ReflexLimits& lim = rig.tick(W(500, 500), W(500, 500));
  TEST_ASSERT_TRUE(lim.holdRight);
  TEST_ASSERT_FALSE(lim.holdLeft);
  Event e;
  TEST_ASSERT_TRUE(rig.popType(EventType::Stall, &e));
  TEST_ASSERT_EQUAL_INT(static_cast<int>(Wheel::Right), e.value);
  TEST_ASSERT_TRUE(rig.reflexes.flags() & StatusFlag::Stall);
  for (int i = 0; i < 99; ++i) {
    rig.keepAlive();
    rig.sense.encLeft += 50;
    rig.tick(W(500, 500), W(500, 0));
  }
  TEST_ASSERT_TRUE(rig.reflexes.stalled(Wheel::Right));
  rig.keepAlive();
  rig.tick(W(500, 500), W(500, 0));
  TEST_ASSERT_FALSE(rig.reflexes.stalled(Wheel::Right));
}

static void test_stall_needs_power_above_threshold() {
  Rig rig;
  for (int i = 0; i < 100; ++i) {
    rig.keepAlive();
    rig.tick(W(300, 300), W(300, 300));
  }
  TEST_ASSERT_FALSE(rig.reflexes.stalled(Wheel::Left));
  TEST_ASSERT_FALSE(rig.reflexes.stalled(Wheel::Right));
}

static void test_low_battery_caps_after_five_seconds() {
  Rig rig;
  rig.sense.packMv = 3250;
  for (int i = 0; i < 500; ++i) {
    rig.keepAlive();
    rig.tick(W(0, 0), W(0, 0), false);
  }
  TEST_ASSERT_FALSE(rig.reflexes.lowBattery());
  rig.keepAlive();
  const ReflexLimits& lim = rig.tick(W(0, 0), W(0, 0), false);
  TEST_ASSERT_TRUE(rig.reflexes.lowBattery());
  TEST_ASSERT_EQUAL_INT(500, lim.cap);
  Event e;
  TEST_ASSERT_TRUE(rig.popType(EventType::LowBat, &e));
  TEST_ASSERT_EQUAL_INT(3250, e.value);
  TEST_ASSERT_TRUE(rig.reflexes.flags() & StatusFlag::LowBattery);
  Wheels out = applyLimits(W(1000, 1000), lim);
  TEST_ASSERT_EQUAL_INT(500, out.left);
  rig.sense.packMv = 3350;
  for (int i = 0; i < 1000; ++i) rig.tick(W(0, 0), W(0, 0), false);
  TEST_ASSERT_TRUE(rig.reflexes.lowBattery());
  rig.sense.packMv = 3500;
  for (int i = 0; i < 501; ++i) rig.tick(W(0, 0), W(0, 0), false);
  TEST_ASSERT_FALSE(rig.reflexes.lowBattery());
}

static void test_brief_sag_is_not_low_battery() {
  Rig rig;
  rig.sense.packMv = 3200;
  for (int i = 0; i < 300; ++i) rig.tick(W(0, 0), W(0, 0), false);
  rig.sense.packMv = 3700;
  rig.tick(W(0, 0), W(0, 0), false);
  rig.sense.packMv = 3200;
  for (int i = 0; i < 300; ++i) rig.tick(W(0, 0), W(0, 0), false);
  TEST_ASSERT_FALSE(rig.reflexes.lowBattery());
}

static void test_critical_battery_refuses_wheels() {
  Rig rig;
  rig.sense.packMv = 3000;
  for (int i = 0; i < 50; ++i) {
    rig.keepAlive();
    rig.tick(W(300, 300), W(300, 300));
  }
  TEST_ASSERT_FALSE(rig.reflexes.criticalBattery());
  rig.keepAlive();
  const ReflexLimits& lim = rig.tick(W(300, 300), W(300, 300));
  TEST_ASSERT_TRUE(rig.reflexes.criticalBattery());
  TEST_ASSERT_TRUE(lim.refuse);
  TEST_ASSERT_TRUE(lim.cancelCommand);
  TEST_ASSERT_TRUE(rig.popType(EventType::LowBat));
  Wheels out = applyLimits(W(-300, -300), lim);
  TEST_ASSERT_EQUAL_INT(0, out.left);
}

static void test_deadman_fires_once() {
  Rig rig;
  rig.tick(W(300, 300), W(300, 300), true, 10);
  const ReflexLimits& early = rig.tick(W(300, 300), W(300, 300), true, 480);
  TEST_ASSERT_FALSE(early.cancelCommand);
  const ReflexLimits& late = rig.tick(W(300, 300), W(300, 300), true, 10);
  TEST_ASSERT_TRUE(late.cancelCommand);
  TEST_ASSERT_TRUE(rig.popType(EventType::Deadman));
  TEST_ASSERT_TRUE(rig.reflexes.flags() & StatusFlag::Deadman);
  rig.tick(W(300, 300), W(0, 0), true, 100);
  TEST_ASSERT_FALSE(rig.popType(EventType::Deadman));
  rig.keepAlive();
  TEST_ASSERT_FALSE(rig.reflexes.flags() & StatusFlag::Deadman);
}

static void test_deadman_quiet_when_idle() {
  Rig rig;
  const ReflexLimits& lim = rig.tick(W(0, 0), W(0, 0), false, 2000);
  TEST_ASSERT_FALSE(lim.cancelCommand);
  TEST_ASSERT_FALSE(rig.popType(EventType::Deadman));
}

static void test_fault_stops_and_reports_once() {
  Rig rig;
  rig.sense.faults = FaultBit::Drop;
  const ReflexLimits& lim = rig.tick(W(300, 300), W(300, 300));
  TEST_ASSERT_TRUE(lim.refuse);
  TEST_ASSERT_TRUE(lim.cancelCommand);
  Event e;
  TEST_ASSERT_TRUE(rig.popType(EventType::Fault, &e));
  TEST_ASSERT_EQUAL_STRING("drop", e.text);
  rig.keepAlive();
  rig.tick(W(0, 0), W(0, 0), false);
  TEST_ASSERT_FALSE(rig.popType(EventType::Fault));
  TEST_ASSERT_TRUE(rig.reflexes.flags() & StatusFlag::SensorFault);
  rig.sense.faults = 0;
  const ReflexLimits& ok = rig.tick(W(0, 0), W(0, 0), false);
  TEST_ASSERT_FALSE(ok.refuse);
  rig.sense.faults = FaultBit::Front | FaultBit::Bump;
  rig.tick(W(0, 0), W(0, 0), false);
  TEST_ASSERT_TRUE(rig.popType(EventType::Fault, &e));
  TEST_ASSERT_EQUAL_STRING("front", e.text);
  TEST_ASSERT_TRUE(rig.popType(EventType::Fault, &e));
  TEST_ASSERT_EQUAL_STRING("bump", e.text);
}

static void test_fault_aborts_maneuver() {
  Rig rig;
  rig.sense.bump = 3;
  rig.tick(W(300, 300), W(300, 300));
  TEST_ASSERT_TRUE(rig.reflexes.maneuverActive());
  rig.sense.faults = FaultBit::Battery;
  const ReflexLimits& lim = rig.tick(W(0, 0), W(-450, -450), false);
  TEST_ASSERT_FALSE(lim.maneuver);
  TEST_ASSERT_TRUE(lim.refuse);
}

static void test_reverse_needs_forward_travel_first() {
  Rig rig;
  const ReflexLimits& lim = rig.tick(W(-300, -300), W(0, 0));
  TEST_ASSERT_TRUE(lim.reverseBlocked);
  Wheels out = applyLimits(W(-300, -300), lim);
  TEST_ASSERT_EQUAL_INT(0, out.left);
  TEST_ASSERT_EQUAL_INT(0, out.right);
  Wheels arc = applyLimits(W(-300, -100), lim);
  TEST_ASSERT_EQUAL_INT(0, arc.left + arc.right);
  TEST_ASSERT_EQUAL_INT(-100, arc.left);
  Wheels spin = applyLimits(W(-300, 300), lim);
  TEST_ASSERT_EQUAL_INT(-300, spin.left);
  TEST_ASSERT_EQUAL_INT(300, spin.right);
  TEST_ASSERT_TRUE(rig.reflexes.flags() & StatusFlag::ReverseLimit);
  rig.tick(W(0, 0), W(0, 0), false);
  TEST_ASSERT_FALSE(rig.reflexes.flags() & StatusFlag::ReverseLimit);
}

static void test_reverse_is_slow_and_retraces_forward_travel() {
  Rig rig;
  rig.rolled(500, 500);
  TEST_ASSERT_EQUAL_INT(500, static_cast<int>(rig.reflexes.reverseCredit()));
  const ReflexLimits& lim = rig.tick(W(-800, -800), W(0, 0));
  TEST_ASSERT_FALSE(lim.reverseBlocked);
  Wheels out = applyLimits(W(-800, -800), lim);
  TEST_ASSERT_EQUAL_INT(-450, out.left);
  TEST_ASSERT_EQUAL_INT(-450, out.right);
  Wheels forward = applyLimits(W(800, 800), lim);
  TEST_ASSERT_EQUAL_INT(800, forward.left);
  rig.sense.encLeft -= 400;
  rig.sense.encRight -= 400;
  rig.tick(W(-450, -450), W(-450, -450));
  TEST_ASSERT_EQUAL_INT(100, static_cast<int>(rig.reflexes.reverseCredit()));
  rig.sense.encLeft -= 150;
  rig.sense.encRight -= 150;
  const ReflexLimits& after = rig.tick(W(-450, -450), W(-450, -450));
  TEST_ASSERT_EQUAL_INT(0, static_cast<int>(rig.reflexes.reverseCredit()));
  TEST_ASSERT_TRUE(after.reverseBlocked);
}

static void test_turning_on_the_spot_spends_the_credit() {
  Rig rig;
  rig.rolled(500, 500);
  rig.rolled(15, -15);
  TEST_ASSERT_EQUAL_INT(500, static_cast<int>(rig.reflexes.reverseCredit()));
  rig.rolled(1, -1);
  rig.rolled(-1, 1);
  TEST_ASSERT_EQUAL_INT(500, static_cast<int>(rig.reflexes.reverseCredit()));
  rig.rolled(10, -10);
  TEST_ASSERT_EQUAL_INT(0, static_cast<int>(rig.reflexes.reverseCredit()));
  rig.rolled(300, 280);
  TEST_ASSERT_EQUAL_INT(290, static_cast<int>(rig.reflexes.reverseCredit()));
}

static void test_reverse_credit_is_capped() {
  Rig rig;
  rig.rolled(50000, 50000);
  TEST_ASSERT_EQUAL_INT(10000, static_cast<int>(rig.reflexes.reverseCredit()));
  ReflexSettings settings;
  settings.countsPerMm = 20.0f;
  rig.reflexes.configure(settings);
  rig.rolled(10, 10);
  TEST_ASSERT_EQUAL_INT(10000, static_cast<int>(rig.reflexes.reverseCredit()));
  settings.countsPerMm = 10.0f;
  rig.reflexes.configure(settings);
  rig.rolled(10, 10);
  TEST_ASSERT_EQUAL_INT(5000, static_cast<int>(rig.reflexes.reverseCredit()));
}

static void test_reflex_escapes_still_reverse_without_credit() {
  Rig rig;
  rig.sense.down = RangeReading::noTarget();
  const ReflexLimits& lim = rig.tick(W(300, 300), W(300, 300));
  TEST_ASSERT_TRUE(lim.maneuver);
  Wheels out = applyLimits(W(300, 300), lim);
  TEST_ASSERT_EQUAL_INT(-450, out.left);
  TEST_ASSERT_EQUAL_INT(-450, out.right);
}

static void test_reverse_block_never_drives_a_held_wheel() {
  ReflexLimits lim;
  lim.reverseBlocked = true;
  lim.holdLeft = true;
  Wheels out = applyLimits(W(-300, -300), lim);
  TEST_ASSERT_EQUAL_INT(0, out.left);
  TEST_ASSERT_EQUAL_INT(0, out.right);
  Wheels pivot = applyLimits(W(-300, 200), lim);
  TEST_ASSERT_EQUAL_INT(0, pivot.left);
  TEST_ASSERT_EQUAL_INT(200, pivot.right);
}

int main(int, char**) {
  UNITY_BEGIN();
  RUN_TEST(test_apply_limits_passthrough);
  RUN_TEST(test_apply_limits_forward_clamp_keeps_turning);
  RUN_TEST(test_apply_limits_cap_and_holds);
  RUN_TEST(test_edge_stops_reverses_and_holds);
  RUN_TEST(test_edge_reverse_distance_uses_encoders);
  RUN_TEST(test_edge_ignored_when_reversing_or_still);
  RUN_TEST(test_edge_cleared_by_x);
  RUN_TEST(test_bump_reverses_and_holds_forward_for_one_second);
  RUN_TEST(test_bump_while_still_only_holds);
  RUN_TEST(test_obstacle_clamps_forward_with_hysteresis);
  RUN_TEST(test_stall_stops_one_wheel_for_one_second);
  RUN_TEST(test_stall_needs_power_above_threshold);
  RUN_TEST(test_low_battery_caps_after_five_seconds);
  RUN_TEST(test_brief_sag_is_not_low_battery);
  RUN_TEST(test_critical_battery_refuses_wheels);
  RUN_TEST(test_deadman_fires_once);
  RUN_TEST(test_deadman_quiet_when_idle);
  RUN_TEST(test_fault_stops_and_reports_once);
  RUN_TEST(test_fault_aborts_maneuver);
  RUN_TEST(test_reverse_needs_forward_travel_first);
  RUN_TEST(test_reverse_is_slow_and_retraces_forward_travel);
  RUN_TEST(test_turning_on_the_spot_spends_the_credit);
  RUN_TEST(test_reverse_credit_is_capped);
  RUN_TEST(test_reflex_escapes_still_reverse_without_credit);
  RUN_TEST(test_reverse_block_never_drives_a_held_wheel);
  return UNITY_END();
}
