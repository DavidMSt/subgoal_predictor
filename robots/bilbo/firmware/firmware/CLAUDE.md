# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

BILBO firmware for a Two-Wheel Inverted Pendulum Robot (TWIPR). Runs on STM32H743VITx (Cortex-M7 @ 200MHz) with FreeRTOS. The firmware implements real-time balancing control, state estimation, motor control, and trajectory playback at 100 Hz.

## Build System

This project uses **STM32CubeIDE** (managed make with ARM GCC toolchain).

**Build from IDE:** Open `../cubeide-project/` in STM32CubeIDE and build the Debug configuration.

**Output:** `Debug/bilbo.elf` (also converted to Intel HEX)

**Key compiler settings:**
- MCU: STM32H743VITx
- FPU: FPv5-D16 (hard float ABI)
- Float printf enabled
- C++ mixed with C (HAL in C, firmware logic in C++)

## Directory Structure

```
firmware/           # Main firmware source (this directory)
├── control/        # Control modules (balancing, velocity, position)
├── communication/  # UART/SPI/CAN communication with host
├── estimation/     # State estimation and sensor fusion
├── drive/          # Motor driver abstraction (CAN/RS485)
├── safety/         # Supervisor and safety monitoring
├── sequencer/      # Trajectory playback
├── logging/        # Telemetry and data logging
├── io/             # GPIO and peripheral initialization
├── model/          # Robot physical model definitions
├── errors/         # Error handling
├── firmware.cpp    # Main entry point
└── firmware_settings.h  # Build-time configuration

../cubeide-project/ # STM32CubeIDE project files
├── Core/           # CubeMX-generated HAL init code
├── Drivers/        # STM32 HAL and CMSIS
└── Middlewares/    # FreeRTOS
```

## Architecture

### Main Components

1. **TWIPR_Firmware** (`firmware.cpp/hpp`) - Main firmware class
   - `init()` initializes all modules
   - `start()` starts sensors, estimation, control loops
   - `task()` is the 100 Hz control loop
   - `helperTask()` handles LED updates and background tasks

2. **BILBO_Control** (`control/bilbo_control.h`) - Control system
   - Modes: OFF, DIRECT, BALANCING, VELOCITY, POSITION
   - Hierarchical: position → velocity → balancing → torque output
   - Sub-controllers: TWIPR_BalancingControl, BILBO_VelocityControl, BILBO_PositionControl

3. **TWIPR_Estimation** (`estimation/twipr_estimation.h`) - State estimation
   - IMU fusion via VQF (Vectorial Quaternion Filter)
   - State: [x, y, v, θ (pitch), ω, ψ (yaw), ψ̇]

4. **TWIPR_CommunicationManager** (`communication/twipr_communication.h`)
   - UART: Register-based commands from host (CM4)
   - SPI: High-speed trajectory input, sample output (DMA)
   - CAN: Motor control

5. **BILBO_Drive** (`drive/bilbo_drive.h`) - Motor abstraction
   - SimplexMotion motors via CAN (default) or RS485

### Control Loop Flow

```
100 Hz task():
  sequencer.update()     # Inject trajectory commands
  control.update()       # Run active controller cascade
  logging.collectSamples()
```

### Register Map Interface

External control via 256 registers (`firmware_addresses.h`):
- `0x01-0x0F`: System (state, tick, revision)
- `0x20-0x2F`: Control core (mode, gains, inputs)
- `0x30-0x3F`: Control config (velocity, position, TIC/VIC)
- `0x40-0x4F`: Sequencer (load, start, stop)
- `0x50-0x5F`: Estimation (theta offset, position state)
- `0xF0`: Firmware reset

## Key Configuration

`firmware_settings.h`:
```c
#define BILBO_DRIVE_SIMPLEXMOTION_CAN  // or _RS485
#define BILBO_MODEL_NORMAL             // or _SMALL, _BIG
#define TWIPR_CONTROL_TASK_FREQ 100    // Hz
#define TWIPR_SAFETY_MAX_WHEEL_SPEED 75 // rad/s
```

## External Libraries

Linked as symlinks in the CubeIDE project:
- `robot-control_std_lib`: Control primitives (PID, filters)
- `stm32_core_cpp_lib`: Hardware abstractions (GPIO, UART, SPI, CAN, DMA)
- VQF: IMU sensor fusion
- ModbusMaster: RS485 motor control (if enabled)

## Firmware States

`TWIPR_FIRMWARE_STATE_NONE` → `TWIPR_FIRMWARE_STATE_RUNNING` → (error) `TWIPR_FIRMWARE_STATE_ERROR`

On error: red LED, motors disabled, requires reset via register `0xF0`.

## Control Modes

- **OFF**: Motors disabled
- **DIRECT**: Raw torque passthrough (left/right)
- **BALANCING**: State feedback control for upright balance
- **VELOCITY**: Forward velocity + yaw rate control
- **POSITION**: XY position + heading control (with trajectory)
