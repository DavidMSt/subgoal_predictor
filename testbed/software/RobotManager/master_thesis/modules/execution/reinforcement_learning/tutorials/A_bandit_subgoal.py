"""
This is a first and *very* simple implementation of a subgoal planner trained using reinforcement learning.

The agent is supposed to learn how to plan subgoals given a start and end point which are both randomly sampled.
Currently this will give almost no for a single agent, but could lead to performance improvements for multi-agent systems, 
because we can consider other agents current position and goal as well.

Also we just assume this scenario as a bandit. Meaning we only have a single simulation step - just for first testing the gymnasium API and such
Note: PPO is not a good choice here since one could say we even have a supervised setting (one single step, immediate reward on the picked action)

Later, this approach is to be extended to function in our Task assignment setting with the created agent classes
"""
 
import gymnasium as gym
from gymnasium.utils.env_checker import check_env
from dataclasses import dataclass, field
import numpy as np
from typing import Any

@dataclass(frozen=True, slots=True)
class Range2D:
    min: np.ndarray
    max: np.ndarray

    def __post_init__(self):
        object.__setattr__(self, "min", np.asarray(self.min, dtype=np.float32))
        object.__setattr__(self, "max", np.asarray(self.max, dtype=np.float32))
        
@dataclass(frozen=True, slots = True)
class Range4D:
    range2d_1: Range2D
    range2d_2: Range2D
    # get min max values in the post init function
    min: np.ndarray = field(init=False)
    max: np.ndarray = field(init=False)

    def __post_init__(self):
        # bypass frozen attribute
        object.__setattr__(self, "min", np.concatenate([self.range2d_1.min, self.range2d_2.min], dtype = np.float32))
        object.__setattr__(self, "max", np.concatenate([self.range2d_1.max, self.range2d_2.max], dtype = np.float32))

    # @property
    # def min(self) -> np.ndarray:
    #     return np.concatenate([self.range2d_1.min, self.range2d_2.min], dtype = np.float32)
    
    # @property
    # def max(self) -> np.ndarray:
    #     return np.concatenate([self.range2d_1.max, self.range2d_2.max], dtype = np.float32) 

@dataclass(frozen=True, slots = True)
class Limits:
    action: Range2D
    position: Range2D
    goal: Range2D
    observation: Range4D


class SubgoalBanditEnv(gym.Env):
    def __init__(self) -> None:

        pos _limits = Range2D((-1.0, -1.0), (1.0, 1.0)) # type: ignore[arg-type]
        goal_limits = Range2D((-1.0, -1.0), (1.0, 1.0)) # type: ignore[arg-type]
        action_limits = Range2D((-1.0, -1.0), (1.0, 1.0)) # type: ignore[arg-type]

        self.limits = Limits(
            action=action_limits,
            position=pos_limits,
            goal=goal_limits,
            observation=Range4D(pos_limits, goal_limits)
        )

        # x, y, g_x, g_y
        self.observation_space = gym.spaces.Box(
            low=self.limits.observation.min,
            high=self.limits.observation.max,
            shape=(4,),
            dtype=np.float32,
        )

        # intermediate goal coordinates: s_x, s_y 
        self.action_space = gym.spaces.Box(
            low=self.limits.action.min,
            high=self.limits.action.max,
            shape=(2,),
            dtype=np.float32,
        )

        # nice to have, not needed but gives better control and can be used during runs after training in gym happened
        self.np_rng = np.random.default_rng(seed=1234)

        self.pos = np.empty((2,), dtype=np.float32)
        self.goal = np.empty((2,), dtype=np.float32)

    def reset(self, *, seed: int | None = None, options: dict[str, Any] | None = None) -> tuple[np.ndarray, dict[str, Any]]:
        # reset the internal gymnasium rng
        super().reset(seed = seed)
        if seed is not None:
            self.np_rng = np.random.default_rng(seed=seed)

        self.pos = self.np_rng.uniform(
            self.limits.position.min, self.limits.position.max, size=(2,)
        ).astype(np.float32)
        self.goal = self.np_rng.uniform(
            self.limits.goal.min, self.limits.goal.max, size=(2,)
        ).astype(np.float32)

        self.obs = np.concatenate([self.pos, self.goal], dtype= np.float32)
        info = {}

        return self.obs, info

        
    def step(self, action: np.ndarray) -> tuple[np.ndarray, float, bool, bool, dict[str, Any]]:
        
        # make sure the action does not exceed bounds, clip if necessary 
        action = np.clip(action, a_min=self.limits.action.min, a_max = self.limits.action.max, dtype=np.float32)

        # define cost as triangle distance
        cost = np.array(np.linalg.norm(self.pos - action) + np.linalg.norm(action - self.goal), dtype = np.float32)

        # we want to minimize cost 
        reward = -cost

        # agent reached terminal state (in our case this is a single prediction of subgoal made)
        terminated = True

        # No timelimit has been exceeded or agent moved out of specified bounds
        truncated = False

        info = {'cost': cost}

        # observation remains unchanged since we do not change our position or goal
        obs = self.obs

        return obs, float(reward), terminated, truncated, info
    

from stable_baselines3 import PPO
from stable_baselines3.common.env_checker import check_env as check_env_sb3


if __name__ == "__main__":

    env = SubgoalBanditEnv()

    # get the initial observation
    obs, info = env.reset()
    print("Initial obs:", obs.shape, obs)
    print("Env having complications: ", "gym: ",check_env(env), ", stable-baselines: ", check_env_sb3(env))

    # PPO is meant to run primarily on the cpu
    model = PPO("MlpPolicy", env=env, device="cpu", verbose = 1)
    # one update is standard as 2048 steps, we want to perform ten episodes 
    model.learn(total_timesteps=2048*10)
    model.save('bandit_subgoal')
    del(model)

    model = PPO.load('bandit_subgoal', env = env)
    

    # action = env.action_space.sample()
    # obs, reward, terminated, truncated, info = env.step(action)
    # print("Action:", action.shape, action, "\t\t datatype: ", type(action))
    # print("Reward:", reward.shape, reward, "\t\t datatype: ", type(reward))
    # print("Info:", info, "\t\t  datatype: ", type(info))
    # print('types of truncated and terminated: ', type(truncated), type(terminated))
