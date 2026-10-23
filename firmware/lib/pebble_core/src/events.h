#pragma once

#include <stddef.h>
#include <stdint.h>

namespace pebble {

enum class EventType : uint8_t { Boot, Bump, Edge, Obstacle, Stall, Dock, LowBat, Deadman, Fault };

enum class Wheel : uint8_t { Left = 0, Right = 1 };

struct Event {
  EventType type = EventType::Boot;
  int32_t value = 0;
  const char* text = nullptr;

  static Event boot(const char* version) { return Event{EventType::Boot, 0, version}; }
  static Event bump(uint8_t sides) { return Event{EventType::Bump, sides, nullptr}; }
  static Event edge() { return Event{EventType::Edge, 0, nullptr}; }
  static Event obstacle(int mm) { return Event{EventType::Obstacle, mm, nullptr}; }
  static Event stall(Wheel wheel) { return Event{EventType::Stall, static_cast<int32_t>(wheel), nullptr}; }
  static Event dock(bool seated) { return Event{EventType::Dock, seated ? 1 : 0, nullptr}; }
  static Event lowBat(int mv) { return Event{EventType::LowBat, mv, nullptr}; }
  static Event deadman() { return Event{EventType::Deadman, 0, nullptr}; }
  static Event fault(const char* what) { return Event{EventType::Fault, 0, what}; }
};

class EventQueue {
 public:
  static constexpr size_t kCapacity = 16;

  bool push(const Event& event);
  bool pop(Event& out);
  size_t size() const { return count_; }
  uint32_t dropped() const { return dropped_; }
  void clear();

 private:
  Event items_[kCapacity];
  size_t head_ = 0;
  size_t count_ = 0;
  uint32_t dropped_ = 0;
};

}
