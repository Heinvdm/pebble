#include <math.h>
#include <stdio.h>
#include <string.h>
#include <unity.h>

#include "air_sensor.h"
#include "protocol.h"
#include "text_writer.h"

using namespace pebble;

namespace {

const uint8_t kCoeff1[23] = {0x65, 0x67, 0x03, 0x00, 0x41, 0x8F, 0xED, 0xD6, 0x58, 0x00, 0x8E, 0x1C,
                             0x7F, 0xFF, 0x2E, 0x1E, 0x00, 0x00, 0x97, 0xF3, 0xB5, 0xF6, 0x1E};
const uint8_t kCoeff2[14] = {0x40, 0x54, 0x2A, 0x00, 0x2D, 0x14, 0x78, 0x9C, 0xB9, 0x65, 0x4E, 0x9F, 0xE2, 0x12};
const uint8_t kCoeff3[5] = {0x30, 0x00, 0x10, 0x00, 0x00};
const uint8_t kField[17] = {0x80, 0x00, 0x56, 0x4C, 0xD0, 0x7A, 0x5F, 0x80, 0x4A,
                            0x4B, 0x00, 0x00, 0x00, 0x00, 0x00, 0xB2, 0x39};

constexpr uint8_t kRegField = 0x1D;
constexpr uint8_t kRegCtrlMeas = 0x74;
constexpr uint8_t kRegSoftReset = 0xE0;

class FakeBme688 : public AirBus {
 public:
  uint8_t regs[256];
  uint8_t field[17];
  uint8_t address = BME68X_I2C_ADDR_HIGH;
  bool present = true;
  bool readsFail = false;
  bool measures = true;
  int probes = 0;
  int writes = 0;
  int measurements = 0;
  uint32_t delayedUs = 0;

  FakeBme688() {
    memset(regs, 0, sizeof(regs));
    memcpy(&regs[0x8A], kCoeff1, sizeof(kCoeff1));
    memcpy(&regs[0xE1], kCoeff2, sizeof(kCoeff2));
    memcpy(&regs[0x00], kCoeff3, sizeof(kCoeff3));
    regs[0xD0] = BME68X_CHIP_ID;
    regs[0xF0] = BME68X_VARIANT_GAS_HIGH;
    memcpy(field, kField, sizeof(field));
  }

  bool probe(uint8_t a) override {
    ++probes;
    return present && a == address;
  }

  bool read(uint8_t a, uint8_t reg, uint8_t* data, uint32_t length) override {
    if (!present || readsFail || a != address) return false;
    for (uint32_t i = 0; i < length; ++i) data[i] = regs[(reg + i) & 0xFF];
    return true;
  }

  bool write(uint8_t a, uint8_t reg, const uint8_t* data, uint32_t length) override {
    if (!present || a != address || length == 0) return false;
    ++writes;
    put(reg, data[0]);
    for (uint32_t i = 1; i + 1 < length; i += 2) put(data[i], data[i + 1]);
    return true;
  }

  void delayUs(uint32_t us) override { delayedUs += us; }

 private:
  void put(uint8_t reg, uint8_t value) {
    if (reg == kRegSoftReset && value == 0xB6) {
      memset(&regs[0x50], 0, 0x26);
      regs[kRegField] = 0;
      return;
    }
    regs[reg] = value;
    if (reg != kRegCtrlMeas || (value & 0x03) != BME68X_FORCED_MODE) return;
    regs[kRegField] &= static_cast<uint8_t>(~BME68X_NEW_DATA_MSK);
    if (!measures) return;
    memcpy(&regs[kRegField], field, sizeof(field));
    regs[kRegCtrlMeas] = static_cast<uint8_t>(value & ~0x03);
    ++measurements;
  }
};

AirTiming timing() { return AirTiming(); }

uint32_t readOnce(AirSensor& air, uint32_t at) {
  TEST_ASSERT_FALSE(air.poll(at, true));
  TEST_ASSERT_EQUAL(AirSensor::Phase::Measuring, air.phase());
  TEST_ASSERT_FALSE(air.poll(at + air.waitMs() - 1, true));
  TEST_ASSERT_TRUE(air.poll(at + air.waitMs(), true));
  return at + air.waitMs();
}

}

void setUp() {}
void tearDown() {}

static void test_recorded_calibration_parses() {
  FakeBme688 bus;
  AirSensor air(bus, timing());
  TEST_ASSERT_TRUE(air.begin(1000));
  TEST_ASSERT_EQUAL_HEX8(0x77, air.address());
  TEST_ASSERT_EQUAL_UINT8(BME68X_VARIANT_GAS_HIGH, air.variant());
  const bme68x_calib_data& c = air.device().calib;
  TEST_ASSERT_EQUAL_UINT16(26041, c.par_t1);
  TEST_ASSERT_EQUAL_INT16(26469, c.par_t2);
  TEST_ASSERT_EQUAL_INT8(3, c.par_t3);
  TEST_ASSERT_EQUAL_UINT16(36673, c.par_p1);
  TEST_ASSERT_EQUAL_INT16(-10515, c.par_p2);
  TEST_ASSERT_EQUAL_INT8(88, c.par_p3);
  TEST_ASSERT_EQUAL_INT16(7310, c.par_p4);
  TEST_ASSERT_EQUAL_INT16(-129, c.par_p5);
  TEST_ASSERT_EQUAL_INT8(30, c.par_p6);
  TEST_ASSERT_EQUAL_INT8(46, c.par_p7);
  TEST_ASSERT_EQUAL_INT16(-3177, c.par_p8);
  TEST_ASSERT_EQUAL_INT16(-2379, c.par_p9);
  TEST_ASSERT_EQUAL_UINT8(30, c.par_p10);
  TEST_ASSERT_EQUAL_UINT16(676, c.par_h1);
  TEST_ASSERT_EQUAL_UINT16(1029, c.par_h2);
  TEST_ASSERT_EQUAL_INT8(0, c.par_h3);
  TEST_ASSERT_EQUAL_INT8(45, c.par_h4);
  TEST_ASSERT_EQUAL_INT8(20, c.par_h5);
  TEST_ASSERT_EQUAL_UINT8(120, c.par_h6);
  TEST_ASSERT_EQUAL_INT8(-100, c.par_h7);
  TEST_ASSERT_EQUAL_INT8(-30, c.par_gh1);
  TEST_ASSERT_EQUAL_INT16(-24754, c.par_gh2);
  TEST_ASSERT_EQUAL_INT8(18, c.par_gh3);
  TEST_ASSERT_EQUAL_UINT8(1, c.res_heat_range);
  TEST_ASSERT_EQUAL_INT8(48, c.res_heat_val);
  TEST_ASSERT_EQUAL_INT8(0, c.range_sw_err);
}

static void test_configuration_registers() {
  FakeBme688 bus;
  AirSensor air(bus, timing());
  TEST_ASSERT_TRUE(air.begin(0));
  TEST_ASSERT_EQUAL_HEX8(0x01, bus.regs[0x72] & 0x07);
  TEST_ASSERT_EQUAL_HEX8(0x4C, bus.regs[kRegCtrlMeas] & 0xFC);
  TEST_ASSERT_EQUAL_HEX8(0x00, bus.regs[0x75] & 0x1C);
  TEST_ASSERT_EQUAL_HEX8(0x65, bus.regs[0x64]);
  TEST_ASSERT_EQUAL_HEX8(0x20, bus.regs[0x71] & 0x30);
  TEST_ASSERT_EQUAL_HEX8(0x00, bus.regs[0x70] & 0x08);
  TEST_ASSERT_TRUE(bus.regs[0x5A] > 0);
  TEST_ASSERT_TRUE(air.waitMs() >= 160 && air.waitMs() <= 180);
}

static void test_recorded_reading_converts() {
  FakeBme688 bus;
  AirSensor air(bus, timing());
  TEST_ASSERT_TRUE(air.begin(1000));
  uint32_t at = readOnce(air, 1000);
  const AirData& d = air.data();
  TEST_ASSERT_TRUE(d.present);
  TEST_ASSERT_EQUAL_UINT32(at, d.ms);
  TEST_ASSERT_FLOAT_WITHIN(0.02f, 26.69f, d.temperatureC);
  TEST_ASSERT_FLOAT_WITHIN(0.05f, 42.402f, d.humidityPct);
  TEST_ASSERT_INT_WITHIN(8, 98712, static_cast<int>(d.pressurePa));
  TEST_ASSERT_INT_WITHIN(1, 109029, d.gasOhm);
  TEST_ASSERT_EQUAL_UINT32(0, d.heatedS);
  TEST_ASSERT_EQUAL_INT(1, bus.measurements);
  char buf[128];
  TextWriter w(buf, sizeof(buf));
  TEST_ASSERT_TRUE(formatAir(w, d));
  char expected[32];
  snprintf(expected, sizeof(expected), "A 1 %u 26.69 42.41 ", static_cast<unsigned>(at));
  TEST_ASSERT_EQUAL_STRING_LEN(expected, w.c_str(), strlen(expected));
}

static void test_gas_needs_a_stable_heater_and_a_valid_measurement() {
  FakeBme688 bus;
  bus.field[16] = static_cast<uint8_t>(bus.field[16] & ~BME68X_HEAT_STAB_MSK);
  AirSensor air(bus, timing());
  TEST_ASSERT_TRUE(air.begin(0));
  readOnce(air, 0);
  TEST_ASSERT_TRUE(air.data().present);
  TEST_ASSERT_EQUAL_INT32(-1, air.data().gasOhm);
  bus.field[16] = static_cast<uint8_t>((bus.field[16] | BME68X_HEAT_STAB_MSK) & ~BME68X_GASM_VALID_MSK);
  readOnce(air, 3000);
  TEST_ASSERT_EQUAL_INT32(-1, air.data().gasOhm);
  bus.field[16] = kField[16];
  readOnce(air, 6000);
  TEST_ASSERT_INT_WITHIN(1, 109029, air.data().gasOhm);
  TEST_ASSERT_EQUAL_UINT32(6, air.data().heatedS);
}

static void test_low_address_jumper() {
  FakeBme688 bus;
  bus.address = BME68X_I2C_ADDR_LOW;
  AirSensor air(bus, timing());
  TEST_ASSERT_TRUE(air.begin(0));
  TEST_ASSERT_EQUAL_HEX8(0x76, air.address());
  readOnce(air, 0);
  TEST_ASSERT_TRUE(air.data().present);
}

static void test_missing_sensor_reports_none_and_never_waits() {
  FakeBme688 bus;
  bus.present = false;
  AirSensor air(bus, timing());
  TEST_ASSERT_FALSE(air.begin(500));
  TEST_ASSERT_EQUAL_UINT32(0, bus.delayedUs);
  TEST_ASSERT_TRUE(air.poll(500, true));
  TEST_ASSERT_FALSE(air.data().present);
  char buf[64];
  TextWriter w(buf, sizeof(buf));
  TEST_ASSERT_TRUE(formatAir(w, air.data()));
  TEST_ASSERT_EQUAL_STRING("A 1 500 none", w.c_str());
  TEST_ASSERT_FALSE(air.poll(3499, true));
  TEST_ASSERT_TRUE(air.poll(3500, true));
  int probes = bus.probes;
  air.poll(30500, false);
  TEST_ASSERT_EQUAL_INT(probes, bus.probes);
  air.poll(30510, true);
  TEST_ASSERT_EQUAL_INT(probes + 2, bus.probes);
  TEST_ASSERT_EQUAL_UINT32(0, bus.delayedUs);
  TEST_ASSERT_EQUAL(AirSensor::Phase::Absent, air.phase());
}

static void test_sampling_never_sleeps_in_the_loop() {
  FakeBme688 bus;
  AirSensor air(bus, timing());
  TEST_ASSERT_TRUE(air.begin(0));
  uint32_t afterBegin = bus.delayedUs;
  uint32_t reports = 0;
  for (uint32_t t = 0; t < 60000; t += 10) {
    if (air.poll(t, true)) ++reports;
  }
  TEST_ASSERT_EQUAL_UINT32(afterBegin, bus.delayedUs);
  TEST_ASSERT_EQUAL_UINT32(20, reports);
  TEST_ASSERT_EQUAL_INT(20, bus.measurements);
}

static void test_sampling_waits_for_still_wheels() {
  FakeBme688 bus;
  AirSensor air(bus, timing());
  TEST_ASSERT_TRUE(air.begin(0));
  readOnce(air, 0);
  int writes = bus.writes;
  TEST_ASSERT_FALSE(air.poll(3000, false));
  TEST_ASSERT_FALSE(air.poll(4500, false));
  TEST_ASSERT_EQUAL_INT(writes, bus.writes);
  TEST_ASSERT_FALSE(air.poll(4600, true));
  TEST_ASSERT_EQUAL(AirSensor::Phase::Measuring, air.phase());
  TEST_ASSERT_TRUE(air.poll(4600 + air.waitMs(), false));
  writes = bus.writes;
  TEST_ASSERT_FALSE(air.poll(7600, false));
  TEST_ASSERT_FALSE(air.poll(10599, false));
  TEST_ASSERT_EQUAL_INT(writes, bus.writes);
  TEST_ASSERT_FALSE(air.poll(10600, false));
  TEST_ASSERT_EQUAL(AirSensor::Phase::Measuring, air.phase());
}

static void test_stuck_sensor_goes_absent_then_recovers_and_rewarms() {
  FakeBme688 bus;
  AirSensor air(bus, timing());
  TEST_ASSERT_TRUE(air.begin(0));
  readOnce(air, 0);
  TEST_ASSERT_TRUE(air.data().present);
  bus.measures = false;
  uint32_t gone = 3000;
  while (!air.poll(gone, true)) {
    gone += 10;
    TEST_ASSERT_TRUE(gone < 20000);
  }
  TEST_ASSERT_EQUAL(AirSensor::Phase::Absent, air.phase());
  TEST_ASSERT_FALSE(air.data().present);
  TEST_ASSERT_EQUAL_UINT8(3, air.failures());
  bus.measures = true;
  air.poll(gone + 29990, true);
  TEST_ASSERT_EQUAL(AirSensor::Phase::Absent, air.phase());
  TEST_ASSERT_FALSE(air.poll(gone + 30000, true));
  TEST_ASSERT_EQUAL(AirSensor::Phase::Idle, air.phase());
  uint32_t at = readOnce(air, gone + 30010);
  TEST_ASSERT_TRUE(air.data().present);
  TEST_ASSERT_EQUAL_UINT32((at - (gone + 30000)) / 1000, air.data().heatedS);
}

static void test_garbage_and_bus_errors_are_never_reported() {
  FakeBme688 bus;
  AirSensor air(bus, timing());
  TEST_ASSERT_TRUE(air.begin(0));
  readOnce(air, 0);
  AirData before = air.data();
  for (size_t i = 2; i < 10; ++i) bus.field[i] = 0xFF;
  TEST_ASSERT_FALSE(air.poll(3000, true));
  TEST_ASSERT_FALSE(air.poll(3000 + air.waitMs(), true));
  TEST_ASSERT_EQUAL_UINT8(1, air.failures());
  TEST_ASSERT_EQUAL_UINT32(before.ms, air.data().ms);
  memcpy(bus.field, kField, sizeof(kField));
  TEST_ASSERT_FALSE(air.poll(6000, true));
  bus.readsFail = true;
  TEST_ASSERT_FALSE(air.poll(6000 + air.waitMs(), true));
  TEST_ASSERT_EQUAL_UINT8(2, air.failures());
  bus.readsFail = false;
  readOnce(air, 9000);
  TEST_ASSERT_EQUAL_UINT8(0, air.failures());
}

int main(int, char**) {
  UNITY_BEGIN();
  RUN_TEST(test_recorded_calibration_parses);
  RUN_TEST(test_configuration_registers);
  RUN_TEST(test_recorded_reading_converts);
  RUN_TEST(test_gas_needs_a_stable_heater_and_a_valid_measurement);
  RUN_TEST(test_low_address_jumper);
  RUN_TEST(test_missing_sensor_reports_none_and_never_waits);
  RUN_TEST(test_sampling_never_sleeps_in_the_loop);
  RUN_TEST(test_sampling_waits_for_still_wheels);
  RUN_TEST(test_stuck_sensor_goes_absent_then_recovers_and_rewarms);
  RUN_TEST(test_garbage_and_bus_errors_are_never_reported);
  return UNITY_END();
}
