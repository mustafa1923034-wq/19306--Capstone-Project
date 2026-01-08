/* ===================== CONFIG ===================== */
#define LANES 4
#define SENSORS 8
#define OCCUPIED_DIST 20      // Cars detected if < 20cm
#define FREE_DIST 30          // No car if > 30cm
#define DECAY_INTERVAL 25000
#define DENSITY_SEND_CYCLES 3

const int trigPins[SENSORS] = {2, 3, 4, 5, 6, 7, 8, 9};
const int echoPins[SENSORS] = {10, 11, 12, A0, A1, A2, A3, A4};

/* ===================== STATE ===================== */
int density_before_light[LANES];
int density_after_light[LANES];
bool lastOccupied[SENSORS];

// ✅ NEW: counters for accurate density_before = entered - exited
int total_entered[LANES] = {0};
int total_exited[LANES] = {0};

// For sensor health
int errorCount[SENSORS] = {0};
bool sensorStatus[SENSORS] = {true};

unsigned long lastSendTime = 0;
unsigned long lastDecayTime = 0;

// For density send every N cycles
int cycleCounter = 0;

/* ===================== UTILS ===================== */
long measureDistance(int t, int e){
  digitalWrite(t, LOW); 
  delayMicroseconds(2);
  digitalWrite(t, HIGH); 
  delayMicroseconds(10);
  digitalWrite(t, LOW);

  long d = pulseIn(e, HIGH, 30000);
  if(d == 0) {
    errorCount[t - 2]++;
    if(errorCount[t - 2] > 50) {
      sensorStatus[t - 2] = false;
    }
    return -1;
  }

  errorCount[t - 2] = 0;
  sensorStatus[t - 2] = true;

  long cm = d * 0.034 / 2;
  if(cm > 400) {
    errorCount[t - 2]++;
    if(errorCount[t - 2] > 50) {
      sensorStatus[t - 2] = false;
    }
    return -1;
  }
  return cm;
}

void updateDensities(){
  for(int l = 0; l < LANES; l++){
    int input_sensor = l * 2;
    int output_sensor = l * 2 + 1;
    
    // ✅ Measure input (before light)
    long input_dist = measureDistance(trigPins[input_sensor], echoPins[input_sensor]);
    if(input_dist > 0 && input_dist < OCCUPIED_DIST){
      if(!lastOccupied[input_sensor]){
        total_entered[l]++;  // ✅ Count every new car entering
        lastOccupied[input_sensor] = true;
      }
    }
    else if(input_dist > FREE_DIST || input_dist == -1){
      lastOccupied[input_sensor] = false;
    }

    delay(100);  // ✅ Increased to reduce crosstalk

    // ✅ Measure output (after light)
    long output_dist = measureDistance(trigPins[output_sensor], echoPins[output_sensor]);
    if(output_dist > 0 && output_dist < OCCUPIED_DIST){
      if(!lastOccupied[output_sensor]){
        total_exited[l]++;   // ✅ Count every new car exiting
        lastOccupied[output_sensor] = true;
      }
    }
    else if(output_dist > FREE_DIST || output_dist == -1){
      lastOccupied[output_sensor] = false;
    }

    delay(100);  // ✅ Increased to reduce crosstalk

    // ✅ Compute density_before as difference (entered - exited)
    density_before_light[l] = max(0, total_entered[l] - total_exited[l]);
    density_after_light[l] = total_exited[l];  // or use edge-based if preferred
  }
}

void decayDensities(){
  // ✅ Optional decay to prevent unbounded growth (keeps values stable)
  for(int l = 0; l < LANES; l++){
    if(density_before_light[l] > 0){
      density_before_light[l]--;
    }
    if(density_after_light[l] > 0){
      density_after_light[l]--;
    }
    // Note: total_entered/exited keep growing — but difference stays reasonable
  }
}

void sendToBackend(){
  Serial.print("DENSITIES:");
  for(int l = 0; l < LANES; l++){
    Serial.print(density_before_light[l]);
    Serial.print(",");
    Serial.print(density_after_light[l]);
    if(l < LANES - 1) Serial.print(",");
  }
  Serial.println();
}

void sendToController(){
  unsigned long timestamp = millis();
  Serial.print("CYCLE_OBS:");
  Serial.print(timestamp);
  Serial.print(":");
  for(int l = 0; l < LANES; l++){
    Serial.print(density_before_light[l]);
    Serial.print(",");
    Serial.print(density_after_light[l]);
    Serial.print(",0");  // halting = 0 (as agreed)
    if(l < LANES - 1) Serial.print(",");
  }
  Serial.println();
}

void sendSensorStatus(){
  Serial.print("SENSOR_STATUS:");
  for(int i = 0; i < SENSORS; i++) {
    Serial.print(sensorStatus[i] ? 1 : 0);
    if(i < SENSORS - 1) Serial.print(",");
  }
  Serial.println();
}

void handleSerial(){
  if (Serial.available()) {
    static String buffer = "";
    unsigned long start = millis();
    
    while (Serial.available() && (millis() - start) < 50) {
      char c = Serial.read();
      if (c == '\n') {
        String cmd = buffer;
        buffer = "";
        cmd.trim();
        if (cmd == "REQUEST_CYCLE_END") {
          updateDensities();  // ✅ Ensure latest counts
          sendToController();
        }
      } else if (c != '\r') {
        buffer += c;
        if (buffer.length() > 100) buffer = "";
      }
    }
  }
}

void setup(){
  Serial.begin(115200);
  for(int i=0;i<SENSORS;i++){
    pinMode(trigPins[i], OUTPUT);
    pinMode(echoPins[i], INPUT);
    lastOccupied[i] = false;
  }

  for(int l=0;l<LANES;l++){
    density_before_light[l] = 0;
    density_after_light[l] = 0;
    total_entered[l] = 0;
    total_exited[l] = 0;
  }
}

void loop(){
  handleSerial();
  updateDensities();

  unsigned long now = millis();
  
  if(now - lastDecayTime >= DECAY_INTERVAL){
    decayDensities();
    lastDecayTime = now;
  }

  static unsigned long lastDensitySend = 0;
  if(now - lastDensitySend > 3000) {
    cycleCounter++;
    if(cycleCounter >= DENSITY_SEND_CYCLES) {
      sendToBackend();
      cycleCounter = 0;
    }
    lastDensitySend = now;
  }

  static unsigned long lastStatusTime = 0;
  if(now - lastStatusTime > 10000) {
    sendSensorStatus();
    lastStatusTime = now;
  }
}