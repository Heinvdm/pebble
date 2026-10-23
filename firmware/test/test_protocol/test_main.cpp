#include <string.h>
#include <unity.h>

#include "events.h"
#include "line_assembler.h"
#include "protocol.h"
#include "text_writer.h"

using namespace pebble;

void setUp() {}
void tearDown() {}

static void test_drive_parses_and_clamps() {
  Command c;
  TEST_ASSERT_EQUAL(ParseResult::Ok, parseCommand("D 300 -250", c));
  TEST_ASSERT_EQUAL(CommandType::Drive, c.type);
  TEST_ASSERT_EQUAL_INT(300, c.left);
  TEST_ASSERT_EQUAL_INT(-250, c.right);
  TEST_ASSERT_EQUAL(ParseResult::Ok, parseCommand("  D   5000   -9999  \r", c));
  TEST_ASSERT_EQUAL_INT(1000, c.left);
  TEST_ASSERT_EQUAL_INT(-1000, c.right);
}

static void test_drive_rejects_bad_arguments() {
  Command c;
  TEST_ASSERT_EQUAL(ParseResult::Syntax, parseCommand("D 10", c));
  TEST_ASSERT_EQUAL(ParseResult::Syntax, parseCommand("D 10 20 30", c));
  TEST_ASSERT_EQUAL(ParseResult::Syntax, parseCommand("D 1x 20", c));
  TEST_ASSERT_EQUAL(ParseResult::Syntax, parseCommand("D - 20", c));
  TEST_ASSERT_EQUAL(ParseResult::Syntax, parseCommand("D 99999999999999 0", c));
}

static void test_speed_and_tilt() {
  Command c;
  TEST_ASSERT_EQUAL(ParseResult::Ok, parseCommand("M -120 80", c));
  TEST_ASSERT_EQUAL(CommandType::Speed, c.type);
  TEST_ASSERT_EQUAL_INT(-120, c.left);
  TEST_ASSERT_EQUAL_INT(80, c.right);
  TEST_ASSERT_EQUAL(ParseResult::Ok, parseCommand("T -35", c));
  TEST_ASSERT_EQUAL(CommandType::Tilt, c.type);
  TEST_ASSERT_EQUAL_INT(-35, c.tilt);
  TEST_ASSERT_EQUAL(ParseResult::Ok, parseCommand("T 200", c));
  TEST_ASSERT_EQUAL_INT(90, c.tilt);
  TEST_ASSERT_EQUAL(ParseResult::Syntax, parseCommand("T", c));
}

static void test_simple_commands() {
  Command c;
  TEST_ASSERT_EQUAL(ParseResult::Ok, parseCommand("X", c));
  TEST_ASSERT_EQUAL(CommandType::Stop, c.type);
  TEST_ASSERT_EQUAL(ParseResult::Ok, parseCommand("Q", c));
  TEST_ASSERT_EQUAL(CommandType::Query, c.type);
  TEST_ASSERT_EQUAL(ParseResult::Ok, parseCommand("R", c));
  TEST_ASSERT_EQUAL(CommandType::Reboot, c.type);
  TEST_ASSERT_EQUAL(ParseResult::Syntax, parseCommand("X now", c));
  TEST_ASSERT_EQUAL(ParseResult::Empty, parseCommand("   ", c));
  TEST_ASSERT_EQUAL(ParseResult::Empty, parseCommand("", c));
  TEST_ASSERT_EQUAL(ParseResult::Unknown, parseCommand("Z 1", c));
  TEST_ASSERT_EQUAL(ParseResult::Unknown, parseCommand("DRIVE 1 2", c));
  TEST_ASSERT_EQUAL(ParseResult::Unknown, parseCommand("d 1 2", c));
}

static void test_ping_echoes_token() {
  Command c;
  TEST_ASSERT_EQUAL(ParseResult::Ok, parseCommand("P 42", c));
  TEST_ASSERT_EQUAL(CommandType::Ping, c.type);
  TEST_ASSERT_EQUAL_STRING("42", c.token);
  TEST_ASSERT_EQUAL(ParseResult::Syntax, parseCommand("P", c));
  TEST_ASSERT_EQUAL(ParseResult::Syntax, parseCommand("P abc", c));
  char buf[64];
  TextWriter w(buf, sizeof(buf));
  TEST_ASSERT_TRUE(formatPing(w, "42"));
  TEST_ASSERT_EQUAL_STRING("p 42", w.c_str());
}

static void test_config_forms() {
  Command c;
  TEST_ASSERT_EQUAL(ParseResult::Ok, parseCommand("C ?", c));
  TEST_ASSERT_EQUAL(CommandType::ConfigList, c.type);
  TEST_ASSERT_EQUAL(ParseResult::Ok, parseCommand("C edge", c));
  TEST_ASSERT_EQUAL(CommandType::ConfigGet, c.type);
  TEST_ASSERT_EQUAL_STRING("edge", c.key);
  TEST_ASSERT_EQUAL(ParseResult::Ok, parseCommand("C ssid My Home  Net  ", c));
  TEST_ASSERT_EQUAL(CommandType::ConfigSet, c.type);
  TEST_ASSERT_EQUAL_STRING("ssid", c.key);
  TEST_ASSERT_EQUAL_STRING("My Home  Net", c.value);
  TEST_ASSERT_EQUAL(ParseResult::Syntax, parseCommand("C", c));
  TEST_ASSERT_EQUAL(ParseResult::Syntax, parseCommand("C ? extra", c));
}

static void test_error_command_letters() {
  TEST_ASSERT_EQUAL_CHAR('D', lineCommandLetter("D 1"));
  TEST_ASSERT_EQUAL_CHAR('M', lineCommandLetter("  M x y"));
  TEST_ASSERT_EQUAL_CHAR('C', lineCommandLetter("C"));
  TEST_ASSERT_EQUAL_CHAR('?', lineCommandLetter("Z 1"));
  TEST_ASSERT_EQUAL_CHAR('?', lineCommandLetter("d 1 2"));
  TEST_ASSERT_EQUAL_CHAR('?', lineCommandLetter("DRIVE 1 2"));
  TEST_ASSERT_EQUAL_CHAR('?', lineCommandLetter(""));
  TEST_ASSERT_EQUAL_CHAR('M', commandLetter(CommandType::Speed));
  TEST_ASSERT_EQUAL_CHAR('C', commandLetter(CommandType::ConfigGet));
  TEST_ASSERT_EQUAL_CHAR('C', commandLetter(CommandType::ConfigList));
  TEST_ASSERT_EQUAL_CHAR('X', commandLetter(CommandType::Stop));
}

static void test_reverse_command_detection() {
  TEST_ASSERT_TRUE(isReverseCommand(-100, -100));
  TEST_ASSERT_TRUE(isReverseCommand(0, -100));
  TEST_ASSERT_FALSE(isReverseCommand(0, 0));
  TEST_ASSERT_FALSE(isReverseCommand(-100, 100));
  TEST_ASSERT_FALSE(isReverseCommand(100, 100));
}

static void test_status_format() {
  char buf[128];
  TextWriter w(buf, sizeof(buf));
  StatusData s;
  s.ms = 123456;
  s.encLeft = -42;
  s.encRight = 9000000000LL;
  s.frontMm = 210;
  s.downMm = -1;
  s.bump = 3;
  s.dock = true;
  s.packMv = 3987;
  s.tilt = -12;
  s.flags = StatusFlag::EdgeHold | StatusFlag::SensorFault;
  TEST_ASSERT_TRUE(formatStatus(w, s));
  TEST_ASSERT_EQUAL_STRING("S 123456 -42 9000000000 210 -1 3 1 3987 -12 65", w.c_str());
  TEST_ASSERT_TRUE(w.length() <= kMaxLineLength);
}

static void test_status_worst_case_fits() {
  char buf[256];
  TextWriter w(buf, sizeof(buf));
  StatusData s;
  s.ms = 4294967295u;
  s.encLeft = -9223372036854775807LL - 1;
  s.encRight = 9223372036854775807LL;
  s.frontMm = 8190;
  s.downMm = 8190;
  s.bump = 3;
  s.packMv = 99999;
  s.tilt = -90;
  s.flags = 127;
  TEST_ASSERT_TRUE(formatStatus(w, s));
  TEST_ASSERT_EQUAL_STRING("S 4294967295 -9223372036854775808 9223372036854775807 8190 8190 3 0 99999 -90 127",
                           w.c_str());
}

static void test_air_format() {
  char buf[128];
  TextWriter w(buf, sizeof(buf));
  AirData a;
  a.ms = 123456;
  a.present = true;
  a.temperatureC = 21.53f;
  a.humidityPct = 45.2f;
  a.pressurePa = 101325;
  a.gasOhm = 152340;
  a.heatedS = 412;
  TEST_ASSERT_TRUE(formatAir(w, a));
  TEST_ASSERT_EQUAL_STRING("A 1 123456 21.53 45.2 101325 152340 412", w.c_str());
  a.ms = 7;
  a.temperatureC = -4.0f;
  a.humidityPct = 50.0f;
  a.gasOhm = -1;
  a.heatedS = 0;
  TEST_ASSERT_TRUE(formatAir(w, a));
  TEST_ASSERT_EQUAL_STRING("A 1 7 -4 50 101325 -1 0", w.c_str());
  AirData none;
  none.ms = 5000;
  TEST_ASSERT_TRUE(formatAir(w, none));
  TEST_ASSERT_EQUAL_STRING("A 1 5000 none", w.c_str());
}

static void test_air_worst_case_fits() {
  char buf[256];
  TextWriter w(buf, sizeof(buf));
  AirData a;
  a.ms = 4294967295u;
  a.present = true;
  a.temperatureC = -39.99f;
  a.humidityPct = 99.99f;
  a.pressurePa = 4294967295u;
  a.gasOhm = 2147483647;
  a.heatedS = 4294967295u;
  TEST_ASSERT_TRUE(formatAir(w, a));
  TEST_ASSERT_EQUAL_STRING("A 1 4294967295 -39.99 99.99 4294967295 2147483647 4294967295", w.c_str());
  TEST_ASSERT_TRUE(w.length() <= kMaxLineLength);
}

static void test_event_format() {
  char buf[128];
  TextWriter w(buf, sizeof(buf));
  struct Case {
    Event event;
    const char* text;
  } cases[] = {
      {Event::boot("0.1.0"), "E boot 0.1.0"},
      {Event::bump(1), "E bump L"},
      {Event::bump(2), "E bump R"},
      {Event::bump(3), "E bump B"},
      {Event::edge(), "E edge"},
      {Event::obstacle(57), "E obstacle 57"},
      {Event::stall(Wheel::Left), "E stall L"},
      {Event::stall(Wheel::Right), "E stall R"},
      {Event::dock(true), "E dock 1"},
      {Event::dock(false), "E dock 0"},
      {Event::lowBat(3290), "E lowbat 3290"},
      {Event::deadman(), "E deadman"},
      {Event::fault("drop"), "E fault drop"},
  };
  for (const Case& c : cases) {
    TEST_ASSERT_TRUE(formatEvent(w, c.event));
    TEST_ASSERT_EQUAL_STRING(c.text, w.c_str());
  }
}

static void test_replies_format() {
  char buf[128];
  TextWriter w(buf, sizeof(buf));
  TEST_ASSERT_TRUE(formatOk(w));
  TEST_ASSERT_EQUAL_STRING("ok", w.c_str());
  TEST_ASSERT_TRUE(formatError(w, 'M', "cpm"));
  TEST_ASSERT_EQUAL_STRING("err M cpm", w.c_str());
  TEST_ASSERT_TRUE(formatError(w, 'C', "key"));
  TEST_ASSERT_EQUAL_STRING("err C key", w.c_str());
  TEST_ASSERT_TRUE(formatError(w, kUnknownCommandLetter, "unknown"));
  TEST_ASSERT_EQUAL_STRING("err ? unknown", w.c_str());
  TEST_ASSERT_TRUE(formatConfig(w, "edge", "75"));
  TEST_ASSERT_EQUAL_STRING("c edge 75", w.c_str());
}

static void test_text_writer_fixed_and_overflow() {
  char buf[16];
  TextWriter w(buf, sizeof(buf));
  w.putFixed(12.5f, 3);
  TEST_ASSERT_EQUAL_STRING("12.5", w.c_str());
  w.clear();
  w.putFixed(-0.25f, 3);
  TEST_ASSERT_EQUAL_STRING("-0.25", w.c_str());
  w.clear();
  w.putFixed(3.0f, 3);
  TEST_ASSERT_EQUAL_STRING("3", w.c_str());
  char tiny[4];
  TextWriter t(tiny, sizeof(tiny));
  t.put("abcdef");
  TEST_ASSERT_FALSE(t.ok());
  TEST_ASSERT_EQUAL_STRING("abc", t.c_str());
}

static LineAssembler::Result feed(LineAssembler& a, const char* text) {
  LineAssembler::Result last = LineAssembler::Result::Pending;
  for (const char* p = text; *p; ++p) {
    LineAssembler::Result r = a.push(*p);
    if (r != LineAssembler::Result::Pending) last = r;
  }
  return last;
}

static void test_line_assembler_splits_lines() {
  LineAssembler a;
  TEST_ASSERT_EQUAL(LineAssembler::Result::Pending, feed(a, "P 1"));
  TEST_ASSERT_EQUAL(LineAssembler::Result::Line, feed(a, "2\r\n"));
  TEST_ASSERT_EQUAL_STRING("P 12", a.line());
  TEST_ASSERT_EQUAL(LineAssembler::Result::Line, feed(a, "\n"));
  TEST_ASSERT_EQUAL_STRING("", a.line());
}

static void test_line_assembler_limit() {
  LineAssembler a;
  char line[kMaxLineLength + 1];
  memset(line, 'a', kMaxLineLength);
  line[kMaxLineLength] = '\0';
  feed(a, line);
  TEST_ASSERT_EQUAL(LineAssembler::Result::Line, a.push('\n'));
  TEST_ASSERT_EQUAL(kMaxLineLength, strlen(a.line()));
  feed(a, line);
  a.push('b');
  TEST_ASSERT_EQUAL(LineAssembler::Result::TooLong, a.push('\n'));
  TEST_ASSERT_EQUAL_CHAR('?', lineCommandLetter(a.line()));
  feed(a, "C ssid ");
  feed(a, line);
  TEST_ASSERT_EQUAL(LineAssembler::Result::TooLong, a.push('\n'));
  TEST_ASSERT_EQUAL_CHAR('C', lineCommandLetter(a.line()));
  TEST_ASSERT_EQUAL(LineAssembler::Result::Line, feed(a, "Q\n"));
  TEST_ASSERT_EQUAL_STRING("Q", a.line());
}

static void test_event_queue_bounds() {
  EventQueue q;
  for (size_t i = 0; i < EventQueue::kCapacity + 3; ++i) q.push(Event::obstacle(static_cast<int>(i)));
  TEST_ASSERT_EQUAL(EventQueue::kCapacity, q.size());
  TEST_ASSERT_EQUAL_UINT32(3, q.dropped());
  Event e;
  TEST_ASSERT_TRUE(q.pop(e));
  TEST_ASSERT_EQUAL_INT(0, e.value);
}

int main(int, char**) {
  UNITY_BEGIN();
  RUN_TEST(test_drive_parses_and_clamps);
  RUN_TEST(test_drive_rejects_bad_arguments);
  RUN_TEST(test_speed_and_tilt);
  RUN_TEST(test_simple_commands);
  RUN_TEST(test_ping_echoes_token);
  RUN_TEST(test_config_forms);
  RUN_TEST(test_error_command_letters);
  RUN_TEST(test_reverse_command_detection);
  RUN_TEST(test_status_format);
  RUN_TEST(test_status_worst_case_fits);
  RUN_TEST(test_air_format);
  RUN_TEST(test_air_worst_case_fits);
  RUN_TEST(test_event_format);
  RUN_TEST(test_replies_format);
  RUN_TEST(test_text_writer_fixed_and_overflow);
  RUN_TEST(test_line_assembler_splits_lines);
  RUN_TEST(test_line_assembler_limit);
  RUN_TEST(test_event_queue_bounds);
  return UNITY_END();
}
