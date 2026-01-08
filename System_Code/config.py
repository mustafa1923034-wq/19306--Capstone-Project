# config.py
# SHARED CONFIGURATION FOR ALL MODULES
# ====================================================

# CYCLE TIMING (MUST BE CONSISTENT ACROSS ALL MODULES)
CYCLE_TOTAL = 55.0      # Total cycle time in seconds
YELLOW_TIME = 5.0       # Yellow time in seconds (2 yellows per cycle)
GREEN_MIN = 25          # Minimum green time in seconds
GREEN_MAX = 35          # Maximum green time in seconds
MIN_RED_TIME = 5        # Minimum red time in seconds

# JUNCTION MAPPING
JUNCTION_MAPPING = {
    0: {"name": "J6", "in_edge": "E1", "out_edge": "E6"},
    1: {"name": "J26", "in_edge": "E15", "out_edge": "E16"},
    2: {"name": "J16", "in_edge": "E8", "out_edge": "E13"},
    3: {"name": "J41", "in_edge": "E22", "out_edge": "E23"}
}

# SYSTEM PAIRING (for beacon priority)
SYSTEM_PAIRS = {
    "A": [0, 1],  # J6, J26
    "B": [2, 3]   # J16, J41
}

# OBSERVATION NORMALIZATION (match SUMO training)
MAX_DENSITY = 50.0      # Maximum vehicles for density normalization
MAX_HALTING = 50.0      # Maximum vehicles for halting normalization

# NETWORK CONFIG
BACKEND_HOST = "0.0.0.0"
BACKEND_PORT = 5000
BACKEND_URL = f"http://localhost:{BACKEND_PORT}"

# SERIAL CONFIG
SERIAL_PORT = "COM6"    # Windows: COM6, Linux: /dev/ttyUSB0, Mac: /dev/tty.usbserial-*
BAUD_RATE = 115200

# BEACON CONFIG
BEACON_DURATION = 30    # Beacon duration in seconds

# MODEL PATHS
MODEL_PATH = "./models/ppo_sumo_final.zip"
CHECKPOINT_DIR = "./models/"