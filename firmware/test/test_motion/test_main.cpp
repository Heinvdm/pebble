#include <unity.h>

#include "events.h"
#include "motion.h"
#include "protocol.h"
#include "reflexes.h"

using namespace pebble;

void setUp() {}
void tearDown() {}

namespace {

struct Body {
  MotionCore motion;
  EventQueue events;
  ReflexSense sense;
  Wheels applied;
  uint32_t now = 1000;
  int deadmanEvents = 0;

  explicit Body(float cpm = 0.0f) {
    ReflexSettings settings;
    settings.countsPerMm = cpm;
    motion.configure(settings);
    sense.front = RangeReading::valid(500);
    sense.down = RangeReading::valid(45);
    sense.packMv = 3900;
    sense.packValid = true;
  }

  MotionCore::Outcome send(const char* line) {
    Command command;
    TEST_ASSERT_EQUAL(ParseResult::Ok, parseCommand(line, command));
    MotionCore::Outcome outcome = motion.command(command, now);
    if (outcome == MotionCore::Outcome::NotMotion && command.type == CommandType::Stop) applied = motion.stopNow(now);
    return outcome;
  }

  void tick() {
    now += 10;
    applied = motion.tick(now, 10, sense, applied, events);
    sense.encLeft += applied.left / 50;
    sense.encRight += applied.right / 50;
    Event e;
    while (events.pop(e)) {
      if (e.type == EventType::Deadman) ++deadmanEvents;
    }
  }

  void runFor(uint32_t ms, uint32_t everyMs = 0, const char* line = nullptr) {
    for (uint32_t t = 10; t <= ms; t += 10) {
      tick();
      if (line != nullptr && everyMs > 0 && t % everyMs == 0) send(line);
    }
  }

  bool moving() const { return applied.left != 0 || applied.right != 0; }
  bool deadmanFlag() const { return (motion.flags() & StatusFlag::Deadman) != 0; }
};

}

static void test_pings_alone_do_not_keep_wheels_running() {
  Body body;
  TEST_ASSERT_EQUAL(MotionCore::Outcome::Accepted, body.send("D 250 250"));
  body.runFor(490, 200, "P 1");
  TEST_ASSERT_TRUE(body.moving());
  TEST_ASSERT_EQUAL_INT(0, body.deadmanEvents);
  body.runFor(10);
  TEST_ASSERT_FALSE(body.moving());
  TEST_ASSERT_EQUAL_INT(1, body.deadmanEvents);
  TEST_ASSERT_TRUE(body.deadmanFlag());
  body.runFor(2000, 200, "P 2");
  TEST_ASSERT_FALSE(body.moving());
  TEST_ASSERT_EQUAL_INT(1, body.deadmanEvents);
}

static void test_other_commands_do_not_refresh_the_deadman() {
  const char* lines[] = {"Q", "T 20", "C ?", "C edge 80", "C cpm", "P 5"};
  for (const char* line : lines) {
    Body body;
    body.send("D 250 250");
    body.runFor(500, 100, line);
    TEST_ASSERT_FALSE(body.moving());
    TEST_ASSERT_EQUAL_INT(1, body.deadmanEvents);
  }
}

static void test_repeated_drive_keeps_wheels_running() {
  Body body;
  body.send("D 250 250");
  body.runFor(3000, 200, "D 250 250");
  TEST_ASSERT_EQUAL_INT(250, body.applied.left);
  TEST_ASSERT_EQUAL_INT(250, body.applied.right);
  TEST_ASSERT_EQUAL_INT(0, body.deadmanEvents);
  TEST_ASSERT_FALSE(body.deadmanFlag());
}

static void test_rejected_speed_does_not_refresh() {
  Body body;
  body.send("D 250 250");
  TEST_ASSERT_EQUAL(MotionCore::Outcome::NeedsCalibration, body.send("M 100 100"));
  body.runFor(500, 100, "M 100 100");
  TEST_ASSERT_FALSE(body.moving());
  TEST_ASSERT_EQUAL_INT(1, body.deadmanEvents);
}

static void test_speed_refreshes_when_calibrated() {
  Body body(10.0f);
  TEST_ASSERT_EQUAL(MotionCore::Outcome::Accepted, body.send("M 100 100"));
  body.runFor(2000, 200, "M 100 100");
  TEST_ASSERT_TRUE(body.moving());
  TEST_ASSERT_EQUAL_INT(0, body.deadmanEvents);
}

static void test_drive_or_stop_clears_deadman_flag() {
  Body body;
  body.send("D 250 250");
  body.runFor(600);
  TEST_ASSERT_TRUE(body.deadmanFlag());
  body.send("X");
  TEST_ASSERT_FALSE(body.deadmanFlag());
  body.send("D 250 250");
  body.runFor(600);
  TEST_ASSERT_TRUE(body.deadmanFlag());
  TEST_ASSERT_EQUAL_INT(2, body.deadmanEvents);
  body.send("D 250 250");
  TEST_ASSERT_FALSE(body.deadmanFlag());
  body.runFor(200);
  TEST_ASSERT_TRUE(body.moving());
}

int main(int, char**) {
  UNITY_BEGIN();
  RUN_TEST(test_pings_alone_do_not_keep_wheels_running);
  RUN_TEST(test_other_commands_do_not_refresh_the_deadman);
  RUN_TEST(test_repeated_drive_keeps_wheels_running);
  RUN_TEST(test_rejected_speed_does_not_refresh);
  RUN_TEST(test_speed_refreshes_when_calibrated);
  RUN_TEST(test_drive_or_stop_clears_deadman_flag);
  return UNITY_END();
}
