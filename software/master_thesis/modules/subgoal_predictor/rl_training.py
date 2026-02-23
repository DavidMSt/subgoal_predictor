import time
import numpy as np
from stable_baselines3 import PPO

from master_thesis.general.general_simulation import FRODO_general_Simulation
from master_thesis.modules.subgoal_predictor.rl_gym_wrapper import FrodoRLEnv
from master_thesis.general.general_obstacle import Obstacle_Config


def main():
    # === 1) Create simulation ===
    sim = FRODO_general_Simulation(Ts=0.1)
    sim.init()

    # === 2) Define environment (agents + obstacles) ===
    # Agent
    agent = sim.new_agent(
        agent_id="agent1",
        start_config=(0.0, 0.0, 0.0)
    )

    # One obstacle for minimal scenario
    sim.new_obstacle(
        obstacle_id="obs1",
        config=Obstacle_Config(),
    )

    # Goal (fixed)
    sim.goal = np.array([5.0, 5.0], dtype=float)

    # === 3) Wrap as Gym environment ===
    env = FrodoRLEnv(sim)

    # === 4) Create PPO model ===
    model = PPO(
        policy="MlpPolicy",
        env=env,
        verbose=1,
    )

    # === 5) Train ===
    model.learn(total_timesteps=50_000)

    # === 6) Save ===
    model.save("ppo_frodo_subgoal")

    print("Training finished. Saved as ppo_frodo_subgoal.zip")


if __name__ == "__main__":
    main()