# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**BilboLab** is a comprehensive robotics framework for BILBO (Two-Wheel Inverted Pendulum Robot - TWIPR) and related research robots. The system is organized as a three-layer architecture with firmware on microcontrollers, on-robot Python software, and a host-side management system with web UI.

**Three-layer architecture:**
1. **STM32 Firmware** (Layer 1) - 100 Hz real-time control on STM32H743 (Cortex-M7)
2. **On-Robot Software** (Layer 2) - Python 3.12 application on Raspberry Pi CM4/CM5
3. **RobotManager** (Layer 3) - Host-side fleet management with Vue 3 web GUI

## Repository Structure

```
/software/                  # RobotManager (host fleet management)
  ├── core/                # Shared framework utilities (~45 modules)
  ├── extensions/          # GUI, OptiTrack, joystick, CLI, simulation
  ├── robots/bilbo/        # BILBO robot interface classes
  ├── applications/BILBO/  # BILBO-specific application (experiments, testbed)
  ├── projects/            # Research projects
  └── utilities/           # Deployment and update scripts

/robots/bilbo/             # BILBO robot subsystems
  ├── firmware/            # STM32H743 real-time control code
  │   ├── cubeide-project/ # STM32CubeIDE project files
  │   ├── firmware/        # Main firmware source (C/C++)
  │   └── precompiled-firmware/  # Pre-built binaries
  ├── software/BILBO-Software/  # Raspberry Pi Python application
  ├── electronics/         # PCB designs (KiCad)
  └── hardware/            # CAD models and mechanical design

/libraries/                # Shared component libraries
  └── software/
      ├── cpp/stm32/       # STM32 HAL C++ abstractions
      └── python/          # Shared Python utilities

/testbed/                  # Physical testbed hardware configurations
/experiments/              # Research experiments
/electronics/              # BMS and other electronics documentation
```

## Layer-Specific Documentation

Each major subsystem has dedicated CLAUDE.md files with detailed architecture:

- **RobotManager (Host)**: `software/CLAUDE.md` - Event system, callbacks, device discovery, module patterns
- **STM32 Firmware**: `robots/bilbo/firmware/firmware/CLAUDE.md` - Control modes, register map, estimation
- **Map Visualization**: `software/extensions/gui/src/lib/map/CLAUDE.md` - 2D rendering system, coordinate transforms

## Build & Run Commands

### Firmware (STM32CubeIDE)

```bash
# Open project in STM32CubeIDE
open robots/bilbo/firmware/cubeide-project/ -a "STM32CubeIDE"

# Or build from command line (requires STM32CubeIDE CLI)
# Build output: robots/bilbo/firmware/cubeide-project/Debug/bilbo.elf
```

### On-Robot Software (Raspberry Pi)

```bash
cd robots/bilbo/software/BILBO-Software

# Install dependencies
pip install -r requirements.txt

# Run the application
python main.py
```

### RobotManager (Host)

```bash
cd software

# Install dependencies
pip install -r requirements.txt

# Install GUI dependencies
cd extensions/gui && npm install && cd ../..

# Run BILBO application
python robots/bilbo/applications/bilbo_general_application.py
```

### Frontend Development (GUI)

```bash
cd software/extensions/gui

# Development server (hot reload on http://localhost:9200)
npm run dev

# Build for production
npm run build

# Preview production build locally
npm run serve
```

### Testing

```bash
# Tests are distributed throughout the codebase
# Run pytest from specific directories as needed
cd software
pytest core/utils/network/test.py -v
```

## Communication Architecture

```
Host (RobotManager)
    ↕ WebSocket (port 8080-8100, TCP)
    ↕ UDP Broadcast (discovery, 9200)
Raspberry Pi (BILBO-Software)
    ↕ Serial (/dev/ttyUSB0, register-based protocol, ~10 Hz)
    ↕ SPI (high-speed DMA, 100 Hz)
STM32 Firmware
    ↕ CAN/RS485
Motor Controllers (SimplexMotion SimplexDrive)
```

**Key protocols:**
- **UDP Broadcast**: Robot discovery and presence announcements
- **WebSocket**: Bidirectional control/telemetry streaming (all layers)
- **Serial Register Protocol**: Command interface between Pi and STM32 (register addresses 0x00-0xFF)
- **SPI/DMA**: High-speed trajectory injection and sensor sample extraction

## Control Hierarchy

Controls are hierarchically composed; position commands generate velocity targets, which generate pitch/yaw targets, which are regulated by balancing control:

```
Position Control (XY path following)
    ↓ generates velocity command
Velocity Control (forward v + yaw rate, PID with feedforward)
    ↓ generates desired pitch angle
Balancing Control (LQR state feedback for upright balance)
    ↓ generates motor torques
Motor Torque Output (τ_left, τ_right)
```

**Control Modes** (set via `bilbo.control.set_mode()`):
- `OFF` - Motors disabled
- `DIRECT` - Raw torque passthrough
- `BALANCING` - State feedback (pitch/roll stabilization)
- `VELOCITY` - Forward velocity + yaw rate commands
- `POSITION` - XY position + heading (with trajectory playback)

## Configuration Files

Configuration is YAML-based with dataclass conversion:

- **Robot hardware specs (host)**: `software/robots/bilbo/configs/robots/bilbo1.yaml` (dimensions, motor types, electronics revisions)
- **Control parameters (on-robot)**: `robots/bilbo/software/BILBO-Software/configs/control/` (PID gains, LQR K-matrix, filters)
- **Testbed setup**: `software/robots/bilbo/configs/testbeds/` (OptiTrack markers, environment definitions)
- **Firmware settings**: `robots/bilbo/firmware/firmware/firmware_settings.h` (compile-time motor type, model size, control frequency)

Load configs with:
```python
from core.utils.files import load_yaml_config
from robots.bilbo.robot.bilbo_definitions import BILBO_Config
from dacite import from_dict

yaml_data = load_yaml_config('robots/bilbo/configs/robots/bilbo1.yaml')
config = from_dict(data_class=BILBO_Config, data=yaml_data)
```

## Core Framework Patterns

All three layers use consistent architectural patterns (see `software/CLAUDE.md` for details):

### Event-Driven Communication
```python
# Define events with type safety
class MyModule:
    def __init__(self):
        self.events = EventBus(
            initialized=EventFlag(id='initialized', data_type=bool),
            error=EventFlag(id='error', data_type=str)
        )

# Subscribe with callbacks
obj.events.initialized.on(callback=my_handler, once=True)

# Emit events
self.events.initialized.emit(True)

# Wait for events with timeout
result = self.events.initialized.wait(timeout=5.0)
```

### Module Lifecycle Pattern
```python
class Module:
    def init(self):
        """Load configs, allocate resources, connect to hardware"""
        pass

    def start(self):
        """Start background threads, enable interrupt handlers"""
        pass

    def close(self):
        """Clean shutdown: stop threads, flush logs, reset hardware"""
        pass
```

### Callback System with Parameter Injection
```python
from core.utils.callbacks import Callback

callback = Callback(
    function=my_function,
    inputs={'robot': bilbo_instance},  # Static inputs
    lambdas={'time': lambda: time.time()},  # Lazy evaluation
    discard_inputs=True,  # Ignore external kwargs
    once=True  # Auto-remove after first call
)
```

## Technology Stack

**Firmware (STM32H743)**
- C/C++ with FreeRTOS
- VQF (Vectorial Quaternion Filter) for IMU fusion
- SimplexMotion CAN/RS485 motor drivers
- Managed via STM32CubeIDE

**On-Robot Software (Raspberry Pi, Python 3.12)**
- Core: `orjson` (fast JSON), `dacite` (dataclass utilities), `pygame` (joystick)
- Hardware: `PySerial`, `evdev` (input devices), `stm32loader` (firmware updates)
- Audio: `edge-tts`, `pyttsx3`, `pydub`
- Display: `luma.oled` (OLED screens), `pillow` (image processing)
- Logging: `h5py` (HDF5 data), `scipy` (signal processing)

**RobotManager Host (Python 3.12.9)**
- Backend: `Flask` + `Flask-SocketIO`, `websocket-server`, `zeroconf` (device discovery)
- Control: `numpy`, `scipy`, `control` (control systems library)
- Hardware: `pygame` (joystick), `NatNetClient` (OptiTrack), `paramiko` (SSH), `intelhex` (firmware flashing)
- UI: `rich`, `prompt_toolkit`, `textual` (TUI)
- Networking: `aiohttp`, `requests`

**Frontend GUI (Vue 3 + Vite)**
- Vue 3.5.14 (Composition API), Vite 6.3.5
- Charts: Chart.js 3.9.1 with streaming
- 3D: BabylonJS 6.0.0
- Terminal: xterm 5.3.0
- Math: MathJax 3.2.2
- Communication: Socket.io-client 4.7.5

## Path Conventions

The project uses **relative symlinks** between repository roots. When accessing code across layers:

```python
# From host RobotManager accessing on-robot software
robot_sw_path = '../../../robots/bilbo/software/BILBO-Software/'

# Always use absolute paths to avoid confusion
from core.utils.files import get_absolute_path
robot_sw_root = get_absolute_path('../robots/bilbo/software/BILBO-Software')
```

## Deployment & Maintenance

Update scripts in `software/utilities/`:

```bash
cd software/utilities

# Update on-robot BILBO-Software on Raspberry Pi
python update_software.py --robot bilbo1

# Update STM32 firmware on robot
python update_firmware.py --robot bilbo1

# Initial setup on new robot
python install.py --robot bilbo1
```

## Linting & Code Quality

**Python code style:**
- Follow PEP 8 conventions
- Use type hints where helpful for documentation
- Keep functions focused and well-documented

**Common issues:**
- Path confusion: Many files are synchronized via Seafile. Always use `os.path.abspath()` and `get_absolute_path()`
- Event timing: Always use `events.wait(timeout=...)` for initialization sequencing to avoid race conditions
- WebSocket ports: Desktop GUI (8098), mobile (8599), map server varies by application
- Configuration: Use `dacite.from_dict()` for automatic YAML→dataclass conversion, not manual dict access
