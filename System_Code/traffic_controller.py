import time
import numpy as np
import serial
import pickle
import subprocess
import requests

# -----------------------------
#  Serial مع ESP32
# -----------------------------
ESP32_PORT = "COM3"
ESP32_BAUD = 115200

try:
    esp32 = serial.Serial(ESP32_PORT, ESP32_BAUD, timeout=1)
    time.sleep(2)
    print("✅ Connected to ESP32")
except Exception as e:
    print(f"❌ Failed to connect to ESP32: {e}")
    esp32 = None

# -----------------------------
# تحميل الموديل
# -----------------------------
with open("trained_model.pkl", "rb") as f:
    model = pickle.load(f)
print("✅ Loaded trained model")


# -----------------------------
# المتغيرات الأساسية
# -----------------------------
NUM_LANES = 4       # 4 طرق → IN + OUT = 8 قيم

prev_in = np.zeros(4, dtype=np.float32)
prev_out = np.zeros(4, dtype=np.float32)
prev_density = np.zeros(4, dtype=np.float32)

current_green_alloc = np.array([30., 30., 30., 30.], dtype=np.float32)
cycle_duration = 55

beacon_detected = False
priority_lane = None   # من الـ Dashboard

# -----------------------------
# دالة Beacon
# -----------------------------
def check_beacon(ssid="TRAFFIC_BEACON"):
    try:
        result = subprocess.run(
            ["netsh", "wlan", "show", "network"],
            capture_output=True, text=True
        )
        return ssid in result.stdout
    except:
        return False


# -----------------------------
# قراءة حساسات ESP32
# -----------------------------
def read_sensors():
    """
    ESP32 يرسل 8 قيم:
    [IN1, IN2, IN3, IN4, OUT1, OUT2, OUT3, OUT4]
    """
    if esp32 is None:
        return np.zeros(8, dtype=np.float32)

    line = esp32.readline().decode().strip()
    if not line:
        return np.zeros(8, dtype=np.float32)

    parts = line.split(",")
    if len(parts) != 8:
        return np.zeros(8, dtype=np.float32)

    return np.array([float(x) for x in parts], dtype=np.float32)


# -----------------------------
# حساب الكثافة
# -----------------------------
def calculate_density(values):
    IN  = values[0:4]
    OUT = values[4:8]

    density = (IN - OUT).clip(min=0)

    return IN, OUT, density


# -----------------------------
# Observation للموديل
# -----------------------------
def build_observation(density, prev_density, current_green_alloc):
    obs = []
    for i in range(4):
        stopped = 1.0 if abs(density[i] - prev_density[i]) < 0.1 else 0.0
        obs.extend([density[i], stopped])
    obs.extend(current_green_alloc)
    return np.array(obs, dtype=np.float32)


# ---------------------------------------------------------
#                     LOOP الأساسية
# ---------------------------------------------------------
while True:

    cycle_start = time.time()

    # قراءة حساسات
    raw = read_sensors()
    IN, OUT, density = calculate_density(raw)

    # تحقق من Beacon
    if not beacon_detected and check_beacon():
        beacon_detected = True
        print("📡 Beacon detected! Waiting user lane choice...")

    # --------------------------
    # نجهز حساب الدورة القادمة
    # قبل النهاية بـ 5 ثواني
    # --------------------------
    elapsed = time.time() - cycle_start
    remaining = cycle_duration - elapsed

    if remaining > 5:
        time.sleep(remaining - 5)

    # --------------------------
    # حساب توقيتات الدورة القادمة
    # --------------------------
    if beacon_detected and priority_lane is not None:
        # Override كامل
        min_green, max_green = 25, 35
        next_green = np.full(4, min_green)
        next_green[priority_lane] = max_green

    else:
        # حساب طبيعي باستخدام الموديل
        obs = build_observation(density, prev_density, current_green_alloc)
        action = model.predict(obs)
        action = np.clip(action, 0.0, 1.0)

        min_green, max_green = 25, 35
        next_green = min_green + action * (max_green - min_green)

    # --------------------------
    # حساب time_response
    # --------------------------
    time_response = time.time() - cycle_start

    # --------------------------
    # إرسال تحديث للداشبورد
    # --------------------------
    try:
        requests.post("http://127.0.0.1:5000/update", json={
            "density": density.tolist(),
            "beacon": beacon_detected,
            "time_response": time_response
        })
    except:
        print("⚠ Dashboard update failed")

    # --------------------------
    # استكمال نهاية الدورة
    # --------------------------
    remaining = cycle_duration - (time.time() - cycle_start)
    if remaining > 0:
        time.sleep(remaining)

    # --------------------------
    # تنفيذ دورة الإشارات الجديدة
    # --------------------------
    if esp32 is not None:
        msg = ",".join([f"{g:.1f}" for g in next_green]) + "\n"
        esp32.write(msg.encode())
        print("📤 Applied next cycle:", next_green)

    # --------------------------
    # تحديث القيم
    # --------------------------
    prev_in = IN
    prev_out = OUT
    prev_density = density
    current_green_alloc = next_green
