# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**BilboLab** is a robotics framework for BILBO (Two-Wheel Inverted Pendulum Robot - TWIPR) and related robots. The system is organized as a three-layer architecture:

1. **STM32 Firmware** (Layer 1) - 100 Hz real-time control on STM32H743 (Cortex-M7)
2. **On-Robot Software** (Layer 2) - Python application on Raspberry Pi CM4/CM5
3. **RobotManager** (Layer 3) - Host-side fleet management with Vue 3 web GUI

## Repository Structure

```
/robots/                    # Robot-specific implementations
  └── bilbo/               # Primary robot (TWIPR)
      ├── firmware/        # STM32 real-time control
      ├── software/        # Raspberry Pi Python application
      ├── electronics/     # PCB schematics
      └── hardware/        # CAD models
/testbed/                  # Physical testbed infrastructure
  └── software/RobotManager/  # Host-side fleet management
/libraries/                # Shared components
  └── software/
      ├── cpp/stm32/       # STM32 HAL abstractions
      ├── python/          # Shared Python utilities
      └── matlab/          # Dynamics simulation
/experiments/              # Research experiments
/simulation/               # Physics simulations
```

## Layer-Specific Documentation

Each major subsystem has its own CLAUDE.md with detailed architecture:

- **Firmware**: `robots/bilbo/firmware/firmware/CLAUDE.md`
- **RobotManager**: `testbed/software/RobotManager/CLAUDE.md`
- **Map Visualization**: `testbed/software/RobotManager/extensions/gui/src/lib/map/CLAUDE.md`

## Build & Run Commands

### Firmware (STM32CubeIDE)
```bash
# Open ../cubeide-project/ in STM32CubeIDE
# Build Debug configuration → Output: Debug/bilbo.elf
```

### On-Robot Software (Raspberry Pi)
```bash
cd robots/bilbo/software/BILBO-Software
pip install -r requirements.txt
python main.py
```

### RobotManager (Host)
```bash
cd testbed/software/RobotManager

# Install dependencies
pip install -r requirements.txt
cd extensions/gui && npm install && cd ../..

# Run BILBO application
python applications/BILBO/bilbo_application.py

# GUI development server (port 9200)
cd extensions/gui && npm run dev
```

### Testing
```bash
pytest _tests/
```

## Communication Architecture

```
Host (RobotManager)
    ↕ WebSocket/UDP (WiFi)
Raspberry Pi (BILBO-Software)
    ↕ Serial/SPI (register-based)
STM32 Firmware (100 Hz control)
    ↕ CAN/RS485
Motor Controllers
```

## Control Hierarchy

```
Position Control → Velocity Control → Balancing Control → Motor Torque
   (XY path)        (v + yaw rate)      (LQR upright)       (τL, τR)
```

**Control Modes**: OFF, DIRECT, BALANCING, VELOCITY, POSITION

## Configuration

- **Hardware configs**: `robots/bilbo/software/BILBO-Software/configs/hardware/*.yaml`
- **Control configs**: `robots/bilbo/software/BILBO-Software/configs/control/*.yaml`
- **Testbed configs**: `testbed/software/RobotManager/applications/BILBO/configs/*.yaml`

## Core Framework Patterns

### Event-Driven Communication
```python
self.events = EventBus(
    initialized=EventFlag(id='initialized', data_type=bool)
)
self.events.initialized.on(callback=handler, once=True)
self.events.initialized.emit(True)
result = self.events.initialized.wait(timeout=5.0)
```

### Module Lifecycle
```python
class Module:
    def init(self):   # Initialize resources
    def start(self):  # Start threads
    def close(self):  # Clean shutdown
```

### YAML Configuration
```python
from dacite import from_dict
config = from_dict(data_class=ConfigClass, data=yaml_data)
```

## Technology Stack

- **Firmware**: C/C++ on STM32H743, FreeRTOS, VQF (IMU fusion)
- **On-Robot**: Python 3.12, orjson, PySerial, pygame
- **Host Backend**: Python, Flask + Flask-SocketIO, websocket-server, paramiko
- **Host Frontend**: Vue 3.5 + Vite 6, Chart.js, BabylonJS, Socket.io

## Path Conventions

The project uses symlinks between directories. Use absolute paths via:
```python
from core.utils.files import get_absolute_path
```

## Deployment

```bash
cd testbed/software/RobotManager/utilities

# Update on-robot software
python update_software.py

# Update STM32 firmware
python update_firmware.py

# Initial robot setup
python install.py
```
