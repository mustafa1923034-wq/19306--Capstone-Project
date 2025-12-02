#include <BLEDevice.h>
#include <BLEUtils.h>
#include <BLEScan.h>

// أرقام الهوائيات
#define ANT1 25 // شمال
#define ANT2 26 // جنوب
#define ANT3 27 // شرق
#define ANT4 14 // غرب

int scanTime = 2; // مدة المسح بالثواني لكل scan
BLEScan* pBLEScan;

int closestAntenna = -1; // مؤشر الهوائي الأقرب
int prevRSSI = 0;
unsigned long lastFullScan = 0;
const unsigned long fullScanInterval = 1000; // كل ثانية نعيد full scan

void setup() {
  Serial.begin(115200);
  Serial.println("Starting Smart BLE Direction Tracker...");

  pinMode(ANT1, OUTPUT);
  pinMode(ANT2, OUTPUT);
  pinMode(ANT3, OUTPUT);
  pinMode(ANT4, OUTPUT);

  BLEDevice::init("");
  pBLEScan = BLEDevice::getScan();
  pBLEScan->setActiveScan(true);
}

int scanAntenna(int antPin) {
  digitalWrite(ANT1, LOW);
  digitalWrite(ANT2, LOW);
  digitalWrite(ANT3, LOW);
  digitalWrite(ANT4, LOW);
  digitalWrite(antPin, HIGH);
  delay(10);

  BLEScanResults foundDevices = pBLEScan->start(scanTime, false);
  int rssiSum = 0;
  bool foundBeacon = false;

  for (int i = 0; i < foundDevices.getCount(); i++) {
    BLEAdvertisedDevice device = foundDevices.getDevice(i);
    if (device.getName() == "ESP32_Beacon") {
      rssiSum += device.getRSSI();
      foundBeacon = true;
    }
  }
  pBLEScan->clearResults();
  if (!foundBeacon) return 0;
  return rssiSum;
}

String getDirectionName(int idx) {
  String dirs[4] = {"North", "South", "East", "West"};
  return dirs[idx];
}

void loop() {
  int antPins[4] = {ANT1, ANT2, ANT3, ANT4};
  unsigned long now = millis();

  // --- Full scan دوري لتحديث أقرب هوائي ---
  if (now - lastFullScan > fullScanInterval || closestAntenna == -1) {
    int rssi[4];
    for (int i = 0; i < 4; i++) rssi[i] = scanAntenna(antPins[i]);

    int maxRSSI = rssi[0];
    int newClosest = 0;
    for (int i = 1; i < 4; i++) {
      if (rssi[i] > maxRSSI) {
        maxRSSI = rssi[i];
        newClosest = i;
      }
    }

    if (maxRSSI > 0) { // اكتشفنا Beacon
      closestAntenna = newClosest;
      prevRSSI = maxRSSI;
      Serial.print("Updated closest direction: ");
      Serial.println(getDirectionName(closestAntenna));
    } else {
      Serial.println("No beacon detected in full scan...");
      closestAntenna = -1;
    }

    lastFullScan = now;
  }

  // --- إذا عندنا أقرب هوائي، نعمل scan سريع متكرر عليه ---
  if (closestAntenna != -1) {
    int rssi = scanAntenna(antPins[closestAntenna]);
    if (rssi == 0) {
      Serial.println("Beacon lost temporarily...");
    } else {
      int diff = rssi - prevRSSI;
      if (diff > 0) Serial.print("+");   // Beacon بيقرب
      else if (diff < 0) Serial.print("-"); // Beacon بيبتعد
      else Serial.print(" ");              // ما فيش تغيير

      Serial.print(getDirectionName(closestAntenna));
      Serial.print(" | RSSI: "); Serial.println(rssi);

      prevRSSI = rssi;
    }
  }

  delay(250); // كل ربع ثانية مسح سريع على الهوائي الأقرب
}
