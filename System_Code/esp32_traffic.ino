/* ===================== BLUETOOTH ===================== */
#include "BluetoothSerial.h"
BluetoothSerial SerialBT;

String targetDeviceName = "Emergency_Beacon";
bool beaconDetected = false;
int detectedLane = -1;
unsigned long beaconStartTime = 0;
const unsigned long BEACON_DURATION = 30000;

/* ===================== CONFIG ===================== */
#define LANES 4
#define GREEN_MIN 25
#define GREEN_MAX 35
#define YELLOW 5
#define CYCLE_TOTAL 55
#define MIN_RED_TIME 5

const int signalPins[LANES] = {27, 32, 33, 0};

/* ===================== STATE ===================== */
enum {GREEN, YELLOW1, RED, YELLOW2};
unsigned long stageDurations[LANES][4];
unsigned long stageStart[LANES];
int stageIndex[LANES];

int nextGreen[LANES];
int latency_ms = 0;

unsigned long lastDataReceivedTime = 0;
const unsigned long DATA_TIMEOUT = 10000;

static bool decisionReceivedForThisCycle = false;
static unsigned long cycleEndTime = 0;
static unsigned long lastAppliedTime = 0;
static unsigned long lastProgressTime = 0;

// ✅ Prevent premature cycle start: wait for CYCLE_OBS from Arduino
static bool waitingForCycleObs = false;
static unsigned long cycleObsRequestedAt = 0;

/* ===================== LIGHT CONTROL ===================== */
void updateLights(){
  for(int l = 0; l < LANES; l++){
    unsigned long now = millis();
    if(now - stageStart[l] >= stageDurations[l][stageIndex[l]] * 1000){
      stageIndex[l] = (stageIndex[l] + 1) % 4;
      stageStart[l] = now;
    }

    // ✅ Send request ~2s BEFORE end of RED stage (for latest data)
    if(stageIndex[l] == RED && !waitingForCycleObs && !beaconDetected) {
      unsigned long elapsed = now - stageStart[l];
      unsigned long redDurationMs = stageDurations[l][RED] * 1000;
      if(elapsed >= redDurationMs - 2000 && elapsed < redDurationMs - 1000) {
        Serial.println("REQUEST_CYCLE_END");
        waitingForCycleObs = true;
        cycleObsRequestedAt = now;
      }
    }

    switch(stageIndex[l]){
      case GREEN: digitalWrite(signalPins[l], LOW); break;
      case RED: digitalWrite(signalPins[l], HIGH); break;
      case YELLOW1:
      case YELLOW2:
        if((millis() / 75) % 2 == 0) digitalWrite(signalPins[l], HIGH);
        else digitalWrite(signalPins[l], LOW);
        break;
    }
  }
}

/* ===================== BEACON ===================== */
void checkBeacon(){
  if(!beaconDetected) return;

  if(millis() - beaconStartTime >= BEACON_DURATION){
    beaconDetected = false;
    detectedLane = -1;
    for(int l = 0; l < LANES; l++){
      stageDurations[l][GREEN] = nextGreen[l];
      stageDurations[l][YELLOW1] = YELLOW;
      stageDurations[l][RED] = CYCLE_TOTAL - nextGreen[l] - 2 * YELLOW;
      stageDurations[l][YELLOW2] = YELLOW;
    }
    Serial.println("BEACON_CLEAR");
  } else {
    int sysBase = (detectedLane < 2) ? 0 : 2;
    int otherLane = (detectedLane == sysBase) ? sysBase + 1 : sysBase;
    int otherSysBase = (sysBase == 0) ? 2 : 0;

    stageDurations[detectedLane][GREEN] = 35;
    stageDurations[detectedLane][YELLOW1] = YELLOW;
    stageDurations[detectedLane][RED] = 10;
    stageDurations[detectedLane][YELLOW2] = YELLOW;

    stageDurations[otherLane][GREEN] = 25;
    stageDurations[otherLane][YELLOW1] = YELLOW;
    stageDurations[otherLane][RED] = 20;
    stageDurations[otherLane][YELLOW2] = YELLOW;

    for(int i = 0; i < 2; i++) {
      int lane = otherSysBase + i;
      stageDurations[lane][GREEN] = nextGreen[lane];
      stageDurations[lane][YELLOW1] = YELLOW;
      stageDurations[lane][RED] = CYCLE_TOTAL - nextGreen[lane] - 2 * YELLOW;
      stageDurations[lane][YELLOW2] = YELLOW;
    }

    unsigned long now = millis();
    for(int l = 0; l < 2; l++) stageStart[l] = now;
    for(int l = 2; l < 4; l++) stageStart[l] = now;
  }
}

/* ===================== BLUETOOTH BEACON ===================== */
void checkBluetoothBeacon(){
  if (SerialBT.hasClient()) {
    String received = SerialBT.readString();
    received.trim();
    if (received.startsWith("EMERGENCY_LANE:")) {
      int lane = received.substring(15).toInt();
      if (lane >= 0 && lane < LANES) {
        detectedLane = lane;
        beaconDetected = true;
        beaconStartTime = millis();
        Serial.print("PRIORITY:");
        Serial.println(lane);
      }
    }
  }
}

/* ===================== COMMUNICATION ===================== */
void readController(){
  if (Serial.available()) {
    static String buffer = "";
    unsigned long start = millis();
    while (Serial.available() && (millis() - start) < 50) {
      char c = Serial.read();
      if (c == '\n') {
        String line = buffer;
        buffer = "";
        line.trim();
        if (line.isEmpty()) continue;

        if(line.startsWith("NEXT_GREEN:")){
          String data = line.substring(11);
          int idx = 0;
          int start = 0;
          for(int i = 0; i <= data.length(); i++){
            if(i == data.length() || data.charAt(i) == ','){
              if(idx < LANES) {
                nextGreen[idx] = data.substring(start, i).toInt();
              }
              start = i + 1;
              idx++;
            }
          }

          for(int l = 0; l < LANES; l++){
            int safe_green = nextGreen[l];
            if(safe_green < GREEN_MIN) safe_green = GREEN_MIN;
            else if(safe_green > GREEN_MAX) safe_green = GREEN_MAX;

            int red_time = CYCLE_TOTAL - safe_green - 2 * YELLOW;
            if(red_time < MIN_RED_TIME) {
              red_time = MIN_RED_TIME;
              safe_green = CYCLE_TOTAL - red_time - 2 * YELLOW;
              if(safe_green < GREEN_MIN) safe_green = GREEN_MIN;
              else if(safe_green > GREEN_MAX) safe_green = GREEN_MAX;
            }

            stageDurations[l][GREEN] = safe_green;
            stageDurations[l][YELLOW1] = YELLOW;
            stageDurations[l][RED] = red_time;
            stageDurations[l][YELLOW2] = YELLOW;
          }

          lastDataReceivedTime = millis();
          decisionReceivedForThisCycle = true;

          if(cycleEndTime > 0) {
            unsigned long now = millis();
            unsigned long latency = now - cycleEndTime;
            Serial.print("LATENCY:");
            Serial.println(latency);
            cycleEndTime = 0;
          }

          unsigned long now = millis();
          for(int l = 0; l < 2; l++) stageStart[l] = now;
          for(int l = 2; l < 4; l++) stageStart[l] = now;

        } else if(line.startsWith("PRIORITY:")){
          detectedLane = line.substring(9).toInt();
          beaconDetected = true;
          beaconStartTime = millis();
        } else if(line == "CYCLE_OBS:"){
          waitingForCycleObs = false;  // ✅ Confirm observation received
        } else if(line == "EXTEND_BEACON"){
          if(beaconDetected){
            beaconStartTime = millis() - (BEACON_DURATION - 30000);
            Serial.println("BEACON_EXTENDED");
          }
        } else if(line.startsWith("CYCLE_END:")){
          int firstColon = line.indexOf(':');
          int secondColon = line.indexOf(':', firstColon + 1);
          if(secondColon != -1) {
            String tsStr = line.substring(firstColon + 1, secondColon);
            cycleEndTime = tsStr.toInt();
          }
        }

      } else if (c != '\r') {
        buffer += c;
        if (buffer.length() > 100) buffer = "";
      }
    }
  }
}

/* ===================== CYCLE OBS TIMEOUT HANDLER ===================== */
void checkCycleObsTimeout() {
  if(waitingForCycleObs && millis() - cycleObsRequestedAt > 2000) {
    Serial.println("CYCLE_OBS_TIMEOUT");
    waitingForCycleObs = false;
    unsigned long now = millis();
    for(int l = 0; l < 2; l++) stageStart[l] = now;
    for(int l = 2; l < 4; l++) stageStart[l] = now;
  }
}

/* ===================== DEFAULT TIMING (FALLBACK) ===================== */
void applyDefaultTiming(){
  for(int l = 0; l < LANES; l++){
    stageDurations[l][GREEN] = 30;
    stageDurations[l][YELLOW1] = YELLOW;
    stageDurations[l][RED] = CYCLE_TOTAL - 30 - 2 * YELLOW; // = 15
    stageDurations[l][YELLOW2] = YELLOW;
  }

  unsigned long now = millis();
  for(int l = 0; l < 2; l++) stageStart[l] = now;
  for(int l = 2; l < 4; l++) stageStart[l] = now;
}

/* ===================== SEND MONITORING DATA ===================== */
void sendAppliedCycle(){
  if(millis() - lastAppliedTime > 1000) {
    String applied = "APPLIED_CYCLE:";
    for (int l = 0; l < LANES; l++) {
      applied += String(stageDurations[l][GREEN]) + ",";
      applied += String(stageDurations[l][YELLOW1]) + ",";
      applied += String(stageDurations[l][RED]) + ",";
      applied += String(stageDurations[l][YELLOW2]);
      if (l < LANES - 1) applied += ",";
    }
    Serial.println(applied);
    lastAppliedTime = millis();
  }
}

void sendCycleProgress(){
  if(millis() - lastProgressTime > 500) {
    for (int l = 0; l < LANES; l++) {
      unsigned long elapsed = millis() - stageStart[l];
      unsigned long totalStage = stageDurations[l][stageIndex[l]] * 1000;
      int progress = (totalStage > 0) ? (int)((elapsed * 100) / totalStage) : 0;
      progress = constrain(progress, 0, 100);
      
      Serial.print("PROGRESS:");
      Serial.print(l);
      Serial.print(":");
      Serial.println(progress);
    }
    lastProgressTime = millis();
  }
}

/* ===================== SETUP ===================== */
void setup(){
  Serial.begin(115200);
  SerialBT.begin("ESP32_Beacon_Receiver");
  
  for(int i = 0; i < LANES; i++){
    pinMode(signalPins[i], OUTPUT);
    stageIndex[i] = 0;
    stageStart[i] = millis();
    stageDurations[i][GREEN] = 30;
    stageDurations[i][YELLOW1] = YELLOW;
    stageDurations[i][RED] = 15;
    stageDurations[i][YELLOW2] = YELLOW;
  }
  
  lastDataReceivedTime = millis();
  Serial.println("✅ ESP32 Beacon Receiver Ready");
  Serial.println("🔍 Searching for: Emergency_Beacon");
}

/* ===================== LOOP ===================== */
void loop(){
  checkBluetoothBeacon();

  for(int l = 0; l < LANES; l++) {
    if(stageIndex[l] == GREEN && (millis() - stageStart[l]) < 100) {
      if(!decisionReceivedForThisCycle) {
        applyDefaultTiming();
        Serial.println("FALLBACK: default cycle applied");
      }
      decisionReceivedForThisCycle = false;
      break;
    }
  }

  if(millis() - lastDataReceivedTime > DATA_TIMEOUT && !beaconDetected){
    applyDefaultTiming();
  }
  
  updateLights();
  readController();
  checkBeacon();
  checkCycleObsTimeout();
  sendAppliedCycle();
  sendCycleProgress();
}