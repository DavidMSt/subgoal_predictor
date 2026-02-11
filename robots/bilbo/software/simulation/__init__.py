"""
BILBO Digital Twin - Simulated Firmware Backend

Provides a complete simulation of the STM32 firmware control hierarchy,
allowing the BILBO Software stack to run without physical hardware.

Usage:
    Run `python main_simulation.py [--robot <robot_id>]` instead of `main.py`.

Modules:
    dynamics           - Non-linear 3D BILBO dynamics (Euler integration)
    control            - PID, Feedforward, LQR balancing, velocity control, TIC/VIC
    position_control   - Dense path following, turn-to-heading, drive-to-point
    firmware           - Main simulated firmware (100 Hz control loop)
    simulated_board    - Mock hardware board (no-op GPIO, LEDs, buzzer)
    simulated_communication - Mock communication layer (routes serial to firmware sim)
"""
