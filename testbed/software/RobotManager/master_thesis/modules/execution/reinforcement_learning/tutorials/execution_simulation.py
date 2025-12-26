from stable_baselines3 import PPO
from master_thesis.execution.reinforcement_learning.rl_gym_wrapper import FrodoRLEnv
from master_thesis.general.general_simulation import FRODO_general_Simulation
import time

def run_policy():
    sim = FRODO_general_Simulation(Ts=0.1)
    sim.init()

    env = FrodoRLEnv(sim)
    model = PPO.load("ppo_frodo_subgoal")

    obs, _ = env.reset()

    for _ in range(2000):
        action, _ = model.predict(obs, deterministic=True)
        obs, reward, terminated, truncated, info = env.step(action)

        if terminated or truncated:
            break

        time.sleep(0.05)   # slow for visualization

if __name__ == "__main__":
    run_policy()