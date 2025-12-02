import os
import numpy as np
from stable_baselines3 import PPO
from stable_baselines3.common.callbacks import CheckpointCallback
from stable_baselines3.common.vec_env import DummyVecEnv
from stable_baselines3.common.monitor import Monitor
from sumo_env import SumoTrafficEnv  

# -------------------- Environment --------------------
def make_env():
    env = SumoTrafficEnv(
        lateral_resolution=0.2,
        yellow=5.0,
        zero_vehicle_restart_seconds=600.0,
        retry_start_attempts=3
    )
    env = Monitor(env)  
    return env

env = DummyVecEnv([make_env])

# -------------------- Training parameters --------------------
num_cycles = 5000
cycle_length = int(env.envs[0].unwrapped.cycle)
 

total_timesteps = num_cycles * cycle_length
print(f"[TRAIN] Total timesteps: {total_timesteps} ({num_cycles} cycles)")

# -------------------- Checkpoints --------------------
CHECKPOINT_DIR = './models/'
CHECKPOINT_FILE = os.path.join(CHECKPOINT_DIR, 'ppo_sumo_latest.zip')
os.makedirs(CHECKPOINT_DIR, exist_ok=True)

checkpoint_callback = CheckpointCallback(
    save_freq=10000,  
    save_path=CHECKPOINT_DIR,
    name_prefix='ppo_sumo'
)

# -------------------- Load or create model --------------------
if os.path.exists(CHECKPOINT_FILE):
    print(f"[TRAIN] Deleting old model and starting fresh training: {CHECKPOINT_FILE}")
    os.remove(CHECKPOINT_FILE)

print("[TRAIN] Creating new model...")
model = PPO(
    policy='MlpPolicy',
    env=env,
    verbose=1,
    n_steps=cycle_length, 
    batch_size=64,
    learning_rate=3e-4,
    gamma=0.99
)

# -------------------- Training --------------------
try:
    model.learn(total_timesteps=total_timesteps, callback=checkpoint_callback)
except KeyboardInterrupt:
    print("[TRAIN] Training interrupted by user.")
finally:
    final_model_path = os.path.join(CHECKPOINT_DIR, 'ppo_sumo_final.zip')
    model.save(final_model_path)
    print(f"[TRAIN] Final model saved at {final_model_path}")
    # إغلاق SUMO بأمان
    for e in env.envs:
        e._close_sumo()