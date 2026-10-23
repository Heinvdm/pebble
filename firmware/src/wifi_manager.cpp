#include "wifi_manager.h"

#include <ESPmDNS.h>
#include <WiFi.h>

#include "config.h"

namespace pebble {

void WifiManager::begin(const Settings& settings) {
  credentials_ = settings;
  enabled_ = settings.ssid[0] != '\0';
  if (!enabled_) {
    WiFi.mode(WIFI_OFF);
    return;
  }
  WiFi.persistent(false);
  WiFi.setHostname(kHostName);
  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  connect(millis());
}

void WifiManager::connect(uint32_t now) {
  lastAttempt_ = now;
  WiFi.disconnect(false, false);
  WiFi.begin(credentials_.ssid, credentials_.pass[0] ? credentials_.pass : nullptr);
}

bool WifiManager::connected() const { return enabled_ && WiFi.status() == WL_CONNECTED; }

void WifiManager::poll(uint32_t now) {
  if (!enabled_) return;
  bool up = WiFi.status() == WL_CONNECTED;
  if (up) {
    if (!mdnsStarted_ && MDNS.begin(kHostName)) {
      MDNS.addService("pebble", "tcp", kTcpPort);
      mdnsStarted_ = true;
    }
    wasConnected_ = true;
    lastAttempt_ = now;
    return;
  }
  uint32_t wait = wasConnected_ ? wifi::RetryMs : wifi::ConnectTimeoutMs;
  if (static_cast<uint32_t>(now - lastAttempt_) >= wait) connect(now);
}

}
