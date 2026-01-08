import os
import numpy as np
from stable_baselines3 import PPO
from stable_baselines3.common.callbacks import CheckpointCallback
from stable_baselines3.common.vec_env import DummyVecEnv
from stable_baselines3.common.monitor import Monitor
from config import *
from sumo_env import SumoTrafficEnv

def make_env():
    """Create environment with shared configuration"""
    env = SumoTrafficEnv(
        lateral_resolution=0.2,
        yellow=YELLOW_TIME,  # Use shared constant
        zero_vehicle_restart_seconds=600.0,
        retry_start_attempts=3,
        total_training_cycles=5000,
        last_n_for_reward=5
    )
    return Monitor(env)

# Create vectorized environment
env = DummyVecEnv([lambda: make_env()])

# Ensure checkpoint directory exists
os.makedirs(CHECKPOINT_DIR, exist_ok=True)

# =============== Find Latest Checkpoint ===============
def find_latest_checkpoint():
    """Find the latest training checkpoint"""
    checkpoints = []
    for f in os.listdir(CHECKPOINT_DIR):
        if f.startswith('ppo_sumo') and f.endswith('.zip') and '_steps' in f:
            try:
                # Extract step count from filename
                parts = f.split('_')
                for part in parts:
                    if part.endswith('steps'):
                        steps = int(part.replace('steps', ''))
                        checkpoints.append((steps, os.path.join(CHECKPOINT_DIR, f)))
                        break
            except:
                pass
    
    if checkpoints:
        latest_steps, latest_path = max(checkpoints, key=lambda x: x[0])
        return latest_steps, latest_path
    return None, None

latest_steps, latest_model_path = find_latest_checkpoint()

# =============== Initialize Model ===============
if latest_model_path and os.path.exists(latest_model_path):
    print(f"✅ Found checkpoint: {os.path.basename(latest_model_path)} ({latest_steps} cycles)")
    try:
        # Load model and continue training
        model = PPO.load(latest_model_path, env=env, verbose=1)
        start_cycles = latest_steps
        print(f"   Continuing training from {start_cycles} cycles")
    except Exception as e:
        print(f"❌ Failed to load checkpoint: {e}. Starting fresh.")
        # Create new model
        model = PPO(
            'MlpPolicy', 
            env=env, 
            verbose=1,
            n_steps=20,          # Steps per update
            batch_size=64,       # Batch size
            learning_rate=3e-4,  # Learning rate
            gamma=0.99,          # Discount factor
            ent_coef=0.01,       # Entropy coefficient
            n_epochs=10,         # Number of epoch when optimizing the surrogate loss
        )
        start_cycles = 0
else:
    print("📝 No checkpoint found. Starting fresh training.")
    model = PPO(
        'MlpPolicy', 
        env=env, 
        verbose=1,
        n_steps=20,
        batch_size=64,
        learning_rate=3e-4,
        gamma=0.99,
        ent_coef=0.01,
        n_epochs=10,
    )
    start_cycles = 0

# Save initial model
if start_cycles == 0:
    initial_path = os.path.join(CHECKPOINT_DIR, "ppo_sumo_0_steps.zip")
    model.save(initial_path)
    print(f"💾 Saved initial model: {initial_path}")

# =============== Setup Callback ===============
checkpoint_callback = CheckpointCallback(
    save_freq=500,           # Save every 500 cycles
    save_path=CHECKPOINT_DIR,
    name_prefix='ppo_sumo',
    save_replay_buffer=True,
    save_vecnormalize=True,
)

# =============== Training Configuration ===============
TOTAL_TARGET_CYCLES = 5000
remaining_cycles = max(0, TOTAL_TARGET_CYCLES - start_cycles)

print("\n" + "="*50)
print("🚦 TRAINING CONFIGURATION")
print("="*50)
print(f"Start cycles:      {start_cycles}")
print(f"Target cycles:     {TOTAL_TARGET_CYCLES}")
print(f"Remaining cycles:  {remaining_cycles}")
print(f"Checkpoint dir:    {CHECKPOINT_DIR}")
print(f"Final model:       {MODEL_PATH}")
print("="*50 + "\n")

if remaining_cycles <= 0:
    print("✅ Target already reached. Saving final model.")
    model.save(MODEL_PATH)
    print(f"Final model saved: {MODEL_PATH}")
else:
    try:
        print("🎬 Starting training...")
        print("   (Press Ctrl+C to interrupt and save)")
        
        model.learn(
            total_timesteps=remaining_cycles,
            callback=checkpoint_callback,
            reset_num_timesteps=False,  # Continue from loaded timesteps
            log_interval=10,            # Log every 10 updates
            tb_log_name="ppo_sumo"      # Tensorboard log name
        )
        
        print("\n✅ Training completed successfully!")
        
    except KeyboardInterrupt:
        print("\n⚠️ Training interrupted by user.")
        
    except Exception as e:
        print(f"\n❌ Training error: {e}")
        import traceback
        traceback.print_exc()
        
    finally:
        # Always save final model
        model.save(MODEL_PATH)
        print(f"💾 Final model saved: {MODEL_PATH}")
        
        # Close environment
        env.close()
        print("🔌 Environment closed.")
        
        # Print training summary
        print("\n" + "="*50)
        print("📊 TRAINING SUMMARY")
        print("="*50)
        print(f"Total cycles trained: {start_cycles + remaining_cycles}")
        print(f"Final model: {MODEL_PATH}")
        print("="*50)