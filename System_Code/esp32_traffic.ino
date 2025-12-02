#include <Arduino.h>

// ----- إعداد الـ pins للحساسات -----
const int trigPins[8] = {2, 4, 5, 18, 19, 21, 22, 23};
const int echoPins[8] = {32, 33, 25, 26, 27, 14, 12, 13};

// ----- إعداد LEDs للإشارات -----
const int greenPins[4] = {15, 2, 4, 16};  // مثال، غيّر حسب الدائرة
const int yellowPins[4] = {17, 5, 18, 19};
const int redPins[4] = {21, 22, 23, 25};

// مدة دورة كاملة
unsigned long cycleStart = 0;

void setup() {
  Serial.begin(115200);
  // إعداد pins
  for(int i=0;i<8;i++){
    pinMode(trigPins[i], OUTPUT);
    pinMode(echoPins[i], INPUT);
  }
  for(int i=0;i<4;i++){
    pinMode(greenPins[i], OUTPUT);
    pinMode(yellowPins[i], OUTPUT);
    pinMode(redPins[i], OUTPUT);
  }
}

long measureDistance(int trigPin, int echoPin){
  digitalWrite(trigPin, LOW);
  delayMicroseconds(2);
  digitalWrite(trigPin, HIGH);
  delayMicroseconds(10);
  digitalWrite(trigPin, LOW);
  long duration = pulseIn(echoPin, HIGH, 30000);
  long cm = duration * 0.034 / 2;
  return cm;
}

void loop() {
  // 1️⃣ قراءة الحساسات
  int densities[8];
  for(int i=0;i<8;i++){
    long dist = measureDistance(trigPins[i], echoPins[i]);
    densities[i] = map(dist, 0, 200, 10, 0); // تحويل المسافة لتقدير عدد العربيات
    if(densities[i] < 0) densities[i] = 0;
  }

  // 2️⃣ إرسال البيانات للـ Python عبر Serial
  for(int i=0;i<8;i++){
    Serial.print(densities[i]);
    if(i<7) Serial.print(",");
    else Serial.println();
  }

  // 3️⃣ انتظار أوامر Python لتشغيل الإشارات
  if(Serial.available()){
    String line = Serial.readStringUntil('\n');
    int times[4];
    int idx = 0;
    char* token = strtok((char*)line.c_str(), ",");
    while(token != NULL && idx<4){
      times[idx] = atoi(token);
      token = strtok(NULL, ",");
      idx++;
    }
    // تنفيذ الأوامر على LEDs (أخضر فقط كمثال)
    for(int i=0;i<4;i++){
      digitalWrite(greenPins[i], HIGH);
      delay(times[i]*1000); // وقت الأخضر
      digitalWrite(greenPins[i], LOW);
    }
  }

  delay(100); // تأخير قصير بين القراءات
}
