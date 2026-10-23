#include <unity.h>

#include "analog_math.h"
#include "debouncer.h"
#include "drive.h"
#include "protocol.h"
#include "ramp.h"
#include "reflexes.h"
#include "settings_model.h"
#include "speed_pi.h"
#include "text_writer.h"
#include "tilt.h"

using namespace pebble;

void setUp() {}
void tearDown() {}

static void test_ramp_symmetric_limits_rate_both_ways() {
  RampLimiter ramp(2000.0f, RampLimiter::Mode::Symmetric);
  TEST_ASSERT_EQUAL_FLOAT(20.0f, ramp.step(1000.0f, 10));
  for (int i = 0; i < 48; ++i) ramp.step(1000.0f, 10);
  TEST_ASSERT_EQUAL_FLOAT(980.0f, ramp.value());
  TEST_ASSERT_EQUAL_FLOAT(1000.0f, ramp.step(1000.0f, 10));
  TEST_ASSERT_EQUAL_FLOAT(1000.0f, ramp.step(1000.0f, 10));
  TEST_ASSERT_EQUAL_FLOAT(980.0f, ramp.step(-1000.0f, 10));
  ramp.reset(10.0f);
  TEST_ASSERT_EQUAL_FLOAT(-10.0f, ramp.step(-1000.0f, 10));
}

static void test_ramp_full_swing_takes_one_second() {
  RampLimiter ramp(2000.0f, RampLimiter::Mode::Symmetric);
  ramp.reset(1000.0f);
  for (int i = 0; i < 99; ++i) ramp.step(-1000.0f, 10);
  TEST_ASSERT_TRUE(ramp.value() > -1000.0f);
  ramp.step(-1000.0f, 10);
  TEST_ASSERT_EQUAL_FLOAT(-1000.0f, ramp.value());
}

static void test_ramp_instant_toward_zero() {
  RampLimiter ramp(2000.0f, RampLimiter::Mode::InstantTowardZero);
  ramp.reset(800.0f);
  TEST_ASSERT_EQUAL_FLOAT(300.0f, ramp.step(300.0f, 10));
  TEST_ASSERT_EQUAL_FLOAT(0.0f, ramp.step(0.0f, 10));
  TEST_ASSERT_EQUAL_FLOAT(20.0f, ramp.step(500.0f, 10));
  ramp.reset(600.0f);
  TEST_ASSERT_EQUAL_FLOAT(-20.0f, ramp.step(-600.0f, 10));
}

static void test_drive_power_ramps_and_stops_instantly() {
  DriveController drive;
  ReflexLimits open;
  drive.commandPower(1000, -1000);
  Wheels d = drive.desired(10, 0, 0, 0.0f);
  Wheels out = drive.finish(d, open, 10);
  TEST_ASSERT_EQUAL_INT(20, out.left);
  TEST_ASSERT_EQUAL_INT(-20, out.right);
  for (int i = 0; i < 49; ++i) out = drive.finish(drive.desired(10, 0, 0, 0.0f), open, 10);
  TEST_ASSERT_EQUAL_INT(1000, out.left);
  TEST_ASSERT_EQUAL_INT(-1000, out.right);
  TEST_ASSERT_TRUE(drive.commandActive());
  ReflexLimits refuse;
  refuse.refuse = true;
  out = drive.finish(drive.desired(10, 0, 0, 0.0f), refuse, 10);
  TEST_ASSERT_EQUAL_INT(0, out.left);
  TEST_ASSERT_EQUAL_INT(0, out.right);
  drive.stop();
  TEST_ASSERT_FALSE(drive.commandActive());
  out = drive.finish(drive.desired(10, 0, 0, 0.0f), open, 10);
  TEST_ASSERT_EQUAL_INT(0, out.left);
}

static void test_drive_resumes_with_ramp_after_safety_cut() {
  DriveController drive;
  ReflexLimits open;
  drive.commandPower(600, 600);
  Wheels out;
  for (int i = 0; i < 40; ++i) out = drive.finish(drive.desired(10, 0, 0, 0.0f), open, 10);
  TEST_ASSERT_EQUAL_INT(600, out.left);
  ReflexLimits hold;
  hold.holdLeft = true;
  out = drive.finish(drive.desired(10, 0, 0, 0.0f), hold, 10);
  TEST_ASSERT_EQUAL_INT(0, out.left);
  TEST_ASSERT_EQUAL_INT(600, out.right);
  out = drive.finish(drive.desired(10, 0, 0, 0.0f), open, 10);
  TEST_ASSERT_EQUAL_INT(20, out.left);
}

static void test_drive_speed_requires_calibration() {
  DriveController drive;
  TEST_ASSERT_FALSE(drive.commandSpeed(100, 100, 0.0f));
  TEST_ASSERT_TRUE(drive.commandSpeed(100, 100, 10.0f));
  TEST_ASSERT_EQUAL(DriveMode::Speed, drive.mode());
  drive.desired(10, 0, 0, 0.0f);
  TEST_ASSERT_EQUAL(DriveMode::Idle, drive.mode());
}

static void test_drive_speed_pushes_forward_from_rest() {
  DriveController drive;
  ReflexLimits open;
  drive.commandSpeed(150, 150, 10.0f);
  int64_t counts = 0;
  Wheels out;
  for (int i = 0; i < 20; ++i) out = drive.finish(drive.desired(10, counts, counts, 10.0f), open, 10);
  TEST_ASSERT_TRUE(out.left > 0);
  TEST_ASSERT_EQUAL_INT(out.left, out.right);
}

static void test_speed_pi_behaviour() {
  PiGains gains;
  gains.feedForward = 4.0f;
  gains.kp = 2.0f;
  gains.ki = 10.0f;
  SpeedPi pi(gains);
  TEST_ASSERT_EQUAL_FLOAT(0.0f, pi.update(0.0f, 50.0f, 0.01f, true));
  float first = pi.update(100.0f, 100.0f, 0.01f, true);
  TEST_ASSERT_EQUAL_FLOAT(400.0f, first);
  float low = pi.update(100.0f, 50.0f, 0.01f, true);
  TEST_ASSERT_TRUE(low > first);
  float integral = pi.integral();
  pi.update(100.0f, 50.0f, 0.01f, false);
  TEST_ASSERT_EQUAL_FLOAT(integral, pi.integral());
  TEST_ASSERT_EQUAL_FLOAT(1000.0f, pi.update(1000.0f, 0.0f, 0.01f, true));
}

static void test_speed_estimator() {
  SpeedEstimator est(1.0f);
  TEST_ASSERT_EQUAL_FLOAT(0.0f, est.update(0, 10, 10.0f));
  TEST_ASSERT_EQUAL_FLOAT(100.0f, est.update(10, 10, 10.0f));
  TEST_ASSERT_EQUAL_FLOAT(-200.0f, est.update(-10, 10, 10.0f));
}

static void test_tilt_slew_and_clamp() {
  TiltSlew slew(120.0f);
  slew.configure(TiltLimits{-35, 90, 0});
  slew.jumpTo(8.0f);
  TEST_ASSERT_EQUAL_FLOAT(8.0f, slew.position());
  slew.setTarget(-80.0f);
  TEST_ASSERT_EQUAL_FLOAT(-35.0f, slew.target());
  slew.update(100);
  TEST_ASSERT_EQUAL_FLOAT(-4.0f, slew.position());
  slew.update(1000);
  TEST_ASSERT_EQUAL_FLOAT(-35.0f, slew.position());
  slew.configure(TiltLimits{-10, 30, 0});
  TEST_ASSERT_EQUAL_FLOAT(-10.0f, slew.target());
}

static void test_tilt_pulse_mapping() {
  TEST_ASSERT_EQUAL_INT(1500, tiltPulseMicros(0.0f, 0, 1));
  TEST_ASSERT_EQUAL_INT(2500, tiltPulseMicros(90.0f, 0, 1));
  TEST_ASSERT_EQUAL_INT(500, tiltPulseMicros(-90.0f, 0, 1));
  TEST_ASSERT_EQUAL_INT(1611, tiltPulseMicros(8.0f, 2, 1));
  TEST_ASSERT_EQUAL_INT(1389, tiltPulseMicros(8.0f, 2, -1));
  TEST_ASSERT_EQUAL_INT(2500, tiltPulseMicros(90.0f, 30, 1));
}

static void test_bump_ladder_classification() {
  TEST_ASSERT_EQUAL(BumpSample::None, classifyBumpMv(3300));
  TEST_ASSERT_EQUAL(BumpSample::None, classifyBumpMv(3100));
  TEST_ASSERT_EQUAL(BumpSample::Right, classifyBumpMv(1980));
  TEST_ASSERT_EQUAL(BumpSample::Left, classifyBumpMv(1055));
  TEST_ASSERT_EQUAL(BumpSample::Both, classifyBumpMv(870));
  TEST_ASSERT_EQUAL(BumpSample::Fault, classifyBumpMv(100));
}

static void test_debouncer() {
  Debouncer<bool> d(false, 50);
  TEST_ASSERT_FALSE(d.update(true, 0));
  TEST_ASSERT_FALSE(d.update(false, 20));
  TEST_ASSERT_FALSE(d.update(true, 30));
  TEST_ASSERT_FALSE(d.update(true, 79));
  TEST_ASSERT_TRUE(d.update(true, 80));
  TEST_ASSERT_TRUE(d.state());
  TEST_ASSERT_FALSE(d.update(true, 200));
}

static void test_low_pass_filter() {
  LowPassFilter f(100.0f);
  TEST_ASSERT_EQUAL_FLOAT(4000.0f, f.update(4000.0f, 20));
  float v = f.update(3000.0f, 100);
  TEST_ASSERT_FLOAT_WITHIN(0.5f, 3500.0f, v);
  TEST_ASSERT_EQUAL_INT(3900, packMillivolts(1950, 2.0f, 1.0f));
}

static void test_settings_model() {
  Settings s;
  SettingKey key;
  TEST_ASSERT_TRUE(settingFromName("edge", key));
  TEST_ASSERT_EQUAL(SettingError::None, applySetting(s, key, "90"));
  TEST_ASSERT_EQUAL_INT(90, s.edge);
  TEST_ASSERT_EQUAL(SettingError::Range, applySetting(s, key, "5"));
  TEST_ASSERT_EQUAL(SettingError::Value, applySetting(s, key, "ten"));
  TEST_ASSERT_FALSE(settingFromName("bogus", key));
  TEST_ASSERT_EQUAL(SettingError::None, applySetting(s, SettingKey::Cpm, "12.75"));
  TEST_ASSERT_EQUAL_FLOAT(12.75f, s.cpm);
  TEST_ASSERT_EQUAL(SettingError::Range, applySetting(s, SettingKey::Tmin, "95"));
  TEST_ASSERT_EQUAL(SettingError::Range, applySetting(s, SettingKey::Tmin, "90"));
  TEST_ASSERT_EQUAL(SettingError::None, applySetting(s, SettingKey::Tmin, "-20"));
  TEST_ASSERT_EQUAL(SettingError::Range, applySetting(s, SettingKey::Tmax, "-30"));
  TEST_ASSERT_EQUAL(SettingError::None, applySetting(s, SettingKey::Ssid, "My Net"));
  TEST_ASSERT_EQUAL_STRING("My Net", s.ssid);
  TEST_ASSERT_EQUAL(SettingError::Range, applySetting(s, SettingKey::Pass, "short"));
  TEST_ASSERT_EQUAL(SettingError::None, applySetting(s, SettingKey::Pass, "longenough"));
  char buf[80];
  TextWriter w(buf, sizeof(buf));
  formatSettingValue(s, SettingKey::Pass, w);
  TEST_ASSERT_EQUAL_STRING("*", w.c_str());
  w.clear();
  formatSettingValue(s, SettingKey::Cpm, w);
  TEST_ASSERT_EQUAL_STRING("12.75", w.c_str());
  TEST_ASSERT_EQUAL(SettingError::None, applySetting(s, SettingKey::Pass, "-"));
  w.clear();
  formatSettingValue(s, SettingKey::Pass, w);
  TEST_ASSERT_EQUAL_STRING("-", w.c_str());
  TEST_ASSERT_EQUAL(SettingError::None, applySetting(s, SettingKey::Ssid, "-"));
  TEST_ASSERT_EQUAL_STRING("", s.ssid);
  TEST_ASSERT_TRUE(settingNeedsReboot(SettingKey::Ssid));
  TEST_ASSERT_FALSE(settingNeedsReboot(SettingKey::Edge));
}

static void test_config_list_lines_for_empty_and_set_credentials() {
  Settings s;
  char value[80];
  char line[128];
  TextWriter v(value, sizeof(value));
  TextWriter w(line, sizeof(line));
  formatSettingValue(s, SettingKey::Ssid, v);
  TEST_ASSERT_TRUE(formatConfig(w, settingName(SettingKey::Ssid), v.c_str()));
  TEST_ASSERT_EQUAL_STRING("c ssid -", w.c_str());
  v.clear();
  formatSettingValue(s, SettingKey::Pass, v);
  TEST_ASSERT_TRUE(formatConfig(w, settingName(SettingKey::Pass), v.c_str()));
  TEST_ASSERT_EQUAL_STRING("c pass -", w.c_str());
  applySetting(s, SettingKey::Ssid, "Home Net");
  applySetting(s, SettingKey::Pass, "secret-password");
  v.clear();
  formatSettingValue(s, SettingKey::Ssid, v);
  TEST_ASSERT_TRUE(formatConfig(w, settingName(SettingKey::Ssid), v.c_str()));
  TEST_ASSERT_EQUAL_STRING("c ssid Home Net", w.c_str());
  v.clear();
  formatSettingValue(s, SettingKey::Pass, v);
  TEST_ASSERT_TRUE(formatConfig(w, settingName(SettingKey::Pass), v.c_str()));
  TEST_ASSERT_EQUAL_STRING("c pass *", w.c_str());
}

static void test_settings_defaults_match_interfaces() {
  Settings s;
  TEST_ASSERT_EQUAL_FLOAT(0.0f, s.cpm);
  TEST_ASSERT_EQUAL_INT(75, s.edge);
  TEST_ASSERT_EQUAL_INT(60, s.stop);
  TEST_ASSERT_EQUAL_INT(-35, s.tmin);
  TEST_ASSERT_EQUAL_INT(90, s.tmax);
  TEST_ASSERT_EQUAL_INT(8, s.rest);
  TEST_ASSERT_EQUAL_INT(0, s.trim);
}

static void test_settings_bounds_keep_the_reflexes_on() {
  Settings s;
  TEST_ASSERT_EQUAL(SettingError::Range, applySetting(s, SettingKey::Edge, "2000"));
  TEST_ASSERT_EQUAL(SettingError::Range, applySetting(s, SettingKey::Edge, "39"));
  TEST_ASSERT_EQUAL(SettingError::None, applySetting(s, SettingKey::Edge, "40"));
  TEST_ASSERT_EQUAL(SettingError::None, applySetting(s, SettingKey::Edge, "150"));
  TEST_ASSERT_EQUAL(SettingError::Range, applySetting(s, SettingKey::Edge, "151"));
  TEST_ASSERT_EQUAL(SettingError::Range, applySetting(s, SettingKey::Stop, "0"));
  TEST_ASSERT_EQUAL(SettingError::Range, applySetting(s, SettingKey::Stop, "29"));
  TEST_ASSERT_EQUAL(SettingError::None, applySetting(s, SettingKey::Stop, "30"));
  TEST_ASSERT_EQUAL(SettingError::None, applySetting(s, SettingKey::Stop, "300"));
  TEST_ASSERT_EQUAL(SettingError::Range, applySetting(s, SettingKey::Stop, "301"));
  TEST_ASSERT_EQUAL(SettingError::None, applySetting(s, SettingKey::Cpm, "0"));
  TEST_ASSERT_EQUAL(SettingError::Range, applySetting(s, SettingKey::Cpm, "4.9"));
  TEST_ASSERT_EQUAL(SettingError::None, applySetting(s, SettingKey::Cpm, "20.7"));
  TEST_ASSERT_EQUAL(SettingError::Range, applySetting(s, SettingKey::Cpm, "60.5"));
  TEST_ASSERT_EQUAL(SettingError::Range, applySetting(s, SettingKey::Cpm, "10000"));
  TEST_ASSERT_EQUAL(SettingError::Range, applySetting(s, SettingKey::Trim, "11"));
  TEST_ASSERT_EQUAL(SettingError::None, applySetting(s, SettingKey::Trim, "-10"));
  TEST_ASSERT_EQUAL(SettingError::Range, applySetting(s, SettingKey::Tmin, "-36"));
  TEST_ASSERT_EQUAL(SettingError::Range, applySetting(s, SettingKey::Tmax, "91"));
  TEST_ASSERT_EQUAL(SettingError::Range, applySetting(s, SettingKey::Tmin, "9"));
  TEST_ASSERT_EQUAL(SettingError::Range, applySetting(s, SettingKey::Tmax, "7"));
  TEST_ASSERT_EQUAL(SettingError::Range, applySetting(s, SettingKey::Rest, "91"));
  TEST_ASSERT_EQUAL(SettingError::None, applySetting(s, SettingKey::Rest, "20"));
  TEST_ASSERT_EQUAL(SettingError::None, applySetting(s, SettingKey::Tmin, "10"));
  TEST_ASSERT_EQUAL(SettingError::Range, applySetting(s, SettingKey::Rest, "9"));
  TEST_ASSERT_TRUE(settingsSafe(s));
  Settings defaults;
  TEST_ASSERT_TRUE(settingsSafe(defaults));
  defaults.edge = 2000;
  TEST_ASSERT_FALSE(settingsSafe(defaults));
}

static void test_tilt_range_is_stored_together() {
  Settings s;
  TEST_ASSERT_TRUE(applyTiltRange(s, 10, 40, 20));
  TEST_ASSERT_EQUAL_INT(10, s.tmin);
  TEST_ASSERT_EQUAL_INT(40, s.tmax);
  TEST_ASSERT_EQUAL_INT(20, s.rest);
  TEST_ASSERT_FALSE(applyTiltRange(s, -40, 40, 20));
  TEST_ASSERT_FALSE(applyTiltRange(s, 10, 40, 41));
  TEST_ASSERT_FALSE(applyTiltRange(s, 40, 40, 40));
  TEST_ASSERT_EQUAL_INT(10, s.tmin);
}

static void test_unchanged_settings_are_seen() {
  Settings a;
  Settings b;
  TEST_ASSERT_TRUE(sameSetting(a, b, SettingKey::Edge));
  applySetting(b, SettingKey::Edge, "80");
  TEST_ASSERT_FALSE(sameSetting(a, b, SettingKey::Edge));
  TEST_ASSERT_TRUE(sameSetting(a, b, SettingKey::Stop));
  applySetting(b, SettingKey::Pass, "longenough");
  TEST_ASSERT_FALSE(sameSetting(a, b, SettingKey::Pass));
}

int main(int, char**) {
  UNITY_BEGIN();
  RUN_TEST(test_ramp_symmetric_limits_rate_both_ways);
  RUN_TEST(test_ramp_full_swing_takes_one_second);
  RUN_TEST(test_ramp_instant_toward_zero);
  RUN_TEST(test_drive_power_ramps_and_stops_instantly);
  RUN_TEST(test_drive_resumes_with_ramp_after_safety_cut);
  RUN_TEST(test_drive_speed_requires_calibration);
  RUN_TEST(test_drive_speed_pushes_forward_from_rest);
  RUN_TEST(test_speed_pi_behaviour);
  RUN_TEST(test_speed_estimator);
  RUN_TEST(test_tilt_slew_and_clamp);
  RUN_TEST(test_tilt_pulse_mapping);
  RUN_TEST(test_bump_ladder_classification);
  RUN_TEST(test_debouncer);
  RUN_TEST(test_low_pass_filter);
  RUN_TEST(test_settings_model);
  RUN_TEST(test_config_list_lines_for_empty_and_set_credentials);
  RUN_TEST(test_settings_defaults_match_interfaces);
  RUN_TEST(test_settings_bounds_keep_the_reflexes_on);
  RUN_TEST(test_tilt_range_is_stored_together);
  RUN_TEST(test_unchanged_settings_are_seen);
  return UNITY_END();
}
