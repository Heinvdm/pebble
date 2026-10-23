#include <Arduino.h>

#include "robot.h"

namespace {

pebble::Robot robot;

}

void setup() { robot.setup(); }

void loop() { robot.loop(); }
