import gymnasium as gym
from stable_baselines3 import PPO
from sumo_env import SumoEnv


env = SumoEnv(
    sumo_cfg="4.sumocfg",
    sumo_binary="sumo-gui",
    tls_ids=("J26", "J6"),
    lane_map={"J26":"E15_0", "J6":"E1_0"},
    green_times=(5,10,15),
    step_length=0.2,
    max_episode_steps=3600
)


model = PPO.load("ppo_traffic_model", env=env)


obs, info = env.reset()
done = False

while not done:
    action, _states = model.predict(obs, deterministic=True)
    obs, reward, done, info = env.step(action)
    env.render()

env.close()
