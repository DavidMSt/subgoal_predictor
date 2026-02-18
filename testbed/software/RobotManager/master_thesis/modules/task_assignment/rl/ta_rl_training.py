from __future__ import annotations

import logging
from stable_baselines3 import PPO
from stable_baselines3.common.env_checker import check_env
from stable_baselines3.common.callbacks import CheckpointCallback, EvalCallback
from stable_baselines3.common.monitor import Monitor
from master_thesis.modules.task_assignment.rl.ta_rl_gym_wrapper import RLEnvMLP


def make_env(scenario=None, render_mode=None):
    """Create and wrap the environment."""
    env = RLEnvMLP(
        max_n=10,
        limits=(((-5, 5), (-5, 5))),
        max_episode_steps=1000,
        scenario=scenario,
        render_mode=render_mode,
    )

    # Reduce logging verbosity for faster training
    env.sim.logger.setLevel(logging.WARNING)  # Only show warnings and errors
    env.sim.environment.logger.setLevel(logging.WARNING)

    env = Monitor(env)  # Wraps env to log episode statistics
    return env


def train(scenario=None, render_eval=False):
    # 1. Create environment (headless training)
    env = make_env(scenario=scenario)

    # Check if environment follows Gym API properly
    print("Checking environment...")
    check_env(env, warn=True)
    print("Environment check passed!")

    # 2. Create evaluation environment (optionally visualised)
    eval_env = make_env(
        scenario=scenario,
        render_mode="human" if render_eval else None,
    )

    # 3. Set up callbacks
    # Save model every 10k steps
    checkpoint_callback = CheckpointCallback(
        save_freq=10000,
        save_path='./logs/checkpoints/',
        name_prefix='ta_rl_model'
    )

    # Evaluate every 5k steps
    eval_callback = EvalCallback(
        eval_env,
        best_model_save_path='./logs/best_model/',
        log_path='./logs/eval/',
        eval_freq=5000,
        deterministic=True,
        render=False
    )

    # 4. Create PPO model
    model = PPO(
        "MlpPolicy",  # Use MLP policy (matches your padded observations)
        env,
        learning_rate=3e-4,
        n_steps=2048,  # Rollout buffer size
        batch_size=64,
        n_epochs=10,
        gamma=0.99,
        gae_lambda=0.95,
        clip_range=0.2,
        verbose=1,
        tensorboard_log="./logs/tensorboard/",
    )

    # 5. Train
    print("Starting training...")
    model.learn(
        total_timesteps=500,  # Adjust based on your needs
        callback=[checkpoint_callback, eval_callback],
        progress_bar=True
    )

    # 6. Save final model
    model.save("./logs/final_model/ta_rl_policy")
    print("Training complete! Model saved.")

    return model


if __name__ == "__main__":
    trained_model = train()
