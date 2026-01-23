# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**RobotManager** is the host-side fleet management layer for the BILBO Two-Wheel Inverted Pendulum Robot (TWIPR). It implements device discovery, web-based GUI, experiment orchestration, real-time visualization, and data logging.

This is **Layer 3** in BILBO's three-layer architecture:
1. **STM32 Firmware** (100 Hz real-time control) → See `../robots/bilbo/firmware/firmware/CLAUDE.md`
2. **Raspberry Pi Software** (on-robot control application) → See `../robots/bilbo/software/BILBO-Software/`
3. **RobotManager** (this directory - host-side fleet management)

## Build & Run Commands

### Setup
```bash
pip install -r requirements.txt
cd extensions/gui && npm install && cd ../..
```

### Run Application
```bash
# Main BILBO application (recommended entry point)
python robots/bilbo/applications/bilbo_general_application.py
```

### GUI Development
```bash
cd extensions/gui
npm run dev      # Development server (http://localhost:9200)
npm run build    # Production build
npm run serve    # Preview production build
```

### Deployment to Robots
```bash
cd utilities
python update_software.py --robot bilbo1   # Update Pi software
python update_firmware.py --robot bilbo1   # Update STM32 firmware
python install.py --robot bilbo1           # Initial robot setup
```

## Directory Structure

```
/robots/bilbo/             # BILBO robot implementation
  ├── robot/               # Core robot modules (control, estimation, data)
  ├── manager/             # Fleet management, joystick control
  ├── applications/        # Application entry points (bilbo_general_application.py)
  ├── configs/             # Robot and testbed YAML configurations
  │   ├── robots/          # Per-robot hardware configs (bilbo1.yaml, bilbo2.yaml)
  │   └── testbeds/        # Testbed environment definitions
  ├── gui/                 # BILBO-specific GUI components
  ├── testbed/             # Physical testbed management
  └── simulation/          # Robot simulation
/core/                     # Shared framework utilities (~60 modules)
  ├── utils/               # Callbacks, events, logging, networking, data handling
  └── communication/       # Device server, protocols, WiFi/UDP communication
/extensions/               # Modular system extensions
  ├── gui/                 # Vue 3 + Vite web GUI (see gui/src/lib/map/CLAUDE.md)
  ├── optitrack/           # Motion capture integration
  ├── joystick/            # Joystick control support
  ├── cli/                 # Command-line interface
  └── teleplot/            # Real-time data plotting
/projects/                 # Research projects (Dissertation, SS25_Navigation, etc.)
/simulation/               # Physics-based simulation framework
/utilities/                # Deployment and maintenance scripts
```

## Communication Architecture

```
Host (RobotManager)
    ↕ WebSocket (port 8098 desktop, 8599 mobile)
    ↕ UDP Broadcast (discovery, port 9200)
Raspberry Pi (BILBO-Software)
    ↕ Serial (register-based protocol, ~10 Hz)
    ↕ SPI/DMA (high-speed, 100 Hz)
STM32 Firmware (100 Hz control)
    ↕ CAN/RS485
Motor Controllers (SimplexMotion)
```

**Data Flow:**
1. **Sensors → Estimation → Control → Motors** (100 Hz on STM32)
2. **STM32 → Raspberry Pi** (Serial samples batched at ~10 Hz)
3. **Raspberry Pi → RobotManager** (WebSocket streaming, UDP broadcast)
4. **RobotManager → Web GUI** (Socket.io, real-time visualization)

## Core Framework Architecture

### Event-Driven System (`core/utils/events.py`)

The framework uses a sophisticated event system for decoupled communication:

```python
# Event declaration
class MyClass:
    def __init__(self):
        self.events = EventBus(
            initialized=EventFlag(id='initialized', data_type=bool),
            error=EventFlag(id='error', data_type=str)
        )

# Event subscription with callbacks
obj.events.initialized.on(callback=my_callback, once=True)

# Event emission
self.events.initialized.emit(True)

# Wait for event with timeout
result = self.events.initialized.wait(timeout=5.0)
```

**Key features:**
- Type-safe event definitions via `EventFlag`
- Callback containers with predicates, once-handlers, discard rules
- Asynchronous event waiting with timeouts
- Event history and replay capabilities
- Wildcard event matching with patterns

### Callback System (`core/utils/callbacks.py`)

Flexible callback registration with parameter injection:

```python
callback = Callback(
    function=my_function,
    inputs={'robot': bilbo_instance},  # Static inputs
    lambdas={'time': lambda: time.time()},  # Lazy evaluation
    discard_inputs=True,  # Ignore external kwargs
    once=True  # Auto-remove after first call
)
```

### Configuration Management

**YAML-based configuration** with dataclass conversion via `dacite`:

```python
from core.utils.files import load_yaml_config
from robots.bilbo.robot.bilbo_definitions import BILBO_Config
from dacite import from_dict

yaml_data = load_yaml_config('robots/bilbo/configs/robots/bilbo1.yaml')
config = from_dict(data_class=BILBO_Config, data=yaml_data)
```

**Configuration locations:**
- `robots/bilbo/configs/robots/` - Per-robot hardware configs (bilbo1.yaml, bilbo2.yaml)
- `robots/bilbo/configs/testbeds/` - Testbed environment definitions
- On-robot control params: `../robots/bilbo/software/BILBO-Software/configs/control/`

**Config structure:**
```yaml
general:          # ID, type, version, color
network:          # Address, ports, WiFi credentials
optitrack:        # Motion capture marker definitions
model:            # Physical parameters (mass, inertia, wheel diameter)
electronics:      # Board revision, shield type, display, sound
```

### Device Discovery & Management

**Device Server** (`core/communication/device_server.py`):
- Listens for UDP broadcasts from robots
- Maintains active device registry
- WebSocket connection management
- Automatic reconnection handling

**Multi-Robot Manager** (`robots/bilbo/manager/bilbo_manager.py`):
- Fleet-wide control and coordination
- Per-robot interface instances
- Command broadcast capabilities
- Joystick control arbitration

## Key Design Patterns

### 1. Hierarchical Module Structure

Most modules follow this pattern:
```python
class Module:
    def __init__(self, settings):
        self.settings = settings
        self.events = EventBus(...)
        self.callbacks = CallbackContainer()
        self.logger = Logger('ModuleName')

    def init(self):
        """Initialize resources, load configs"""
        pass

    def start(self):
        """Start threads, begin operation"""
        pass

    def close(self):
        """Clean shutdown"""
        pass
```

### 2. WebSocket-Based Widgets

GUI widgets use bidirectional WebSocket communication:

**Python Backend:**
```python
class Widget:
    def __init__(self):
        self.ws_manager = WebSocketManager(port=8098)
        self.callbacks = CallbackContainer()

    def send_update(self, data):
        self.ws_manager.broadcast({'type': 'update', 'data': data})
```

**JavaScript Frontend:**
```javascript
socket.on('update', (data) => {
    // Update UI
});

// Send to backend
socket.emit('command', {action: 'set_mode', value: 2});
```

### 3. Experiment Orchestration

Experiments defined as YAML action sequences:

```yaml
experiment:
  name: "trajectory_test"
  actions:
    - action: beep
      duration: 0.2
    - action: speak
      text: "Starting experiment"
    - action: set_mode
      mode: POSITION
    - action: run_trajectory
      file: "path/to/trajectory.csv"
```

Executed via `bilbo.experiment.run(experiment_def)`

## Control Hierarchy

```
Position Control (XY path following)
    ↓ generates velocity commands
Velocity Control (Forward velocity + yaw rate, PID + Feedforward)
    ↓ generates desired pitch angle
Balancing Control (LQR state feedback for upright balance)
    ↓ generates motor torques
Motor Torque Output
```

**Control modes** (set via `bilbo.control.set_mode()`):
- `OFF`: Motors disabled
- `DIRECT`: Raw torque passthrough
- `BALANCING`: State feedback control
- `VELOCITY`: Forward velocity + yaw rate
- `POSITION`: XY position + heading (with trajectory)

## Technology Stack

### Python (3.12.9)
- **Serialization**: `orjson` (fast JSON), `dacite` (dataclass utilities)
- **Networking**: `Flask` + `Flask-SocketIO`, `websocket-client/server`, `zeroconf`
- **Numerical**: `numpy`, `scipy`, `control` (control systems library)
- **Hardware**: `pygame` (joystick), `NatNetClient` (OptiTrack), `paramiko` (SSH), `intelhex`
- **UI/Audio**: `pyttsx3`, `gTTS`, `edge-tts`, `rich`, `prompt_toolkit`, `textual`

### JavaScript/Frontend (Vue 3 + Vite)
- **Framework**: Vue 3.5.14 (Composition API)
- **Build**: Vite 6.3.5 with ESM
- **Charts**: Chart.js 3.9.1 + streaming plugin
- **3D**: BabylonJS 6.0.0
- **Terminal**: xterm 5.3.0
- **Math**: MathJax 3.2.2
- **Communication**: Socket.io-client 4.7.5

## Working with Robot Interfaces

### Connecting to a Robot

```python
from robots.bilbo.robot.bilbo import BILBO
from robots.bilbo.robot.bilbo_definitions import BILBO_Config
from core.utils.files import load_yaml_config
from dacite import from_dict

# Load config
yaml_data = load_yaml_config('robots/bilbo/configs/robots/bilbo1.yaml')
config = from_dict(data_class=BILBO_Config, data=yaml_data)

# Create robot instance
bilbo = BILBO(config=config)

# Wait for initialization
bilbo.core.events.initialized.wait(timeout=10.0)

# Access subsystems
bilbo.control.set_mode('VELOCITY')
bilbo.estimation.get_state()
bilbo.drive.set_velocity(0.5, 0.0)
```

### Key Robot Modules

- `bilbo.core` - Core state machine, initialization
- `bilbo.control` - Control mode management, parameter updates
- `bilbo.estimation` - State estimation (position, velocity, orientation)
- `bilbo.drive` - Motor control interface
- `bilbo.logging` - Data logging and streaming
- `bilbo.experiment` - Experiment execution
- `bilbo.interfaces` - Display, buttons, sound

## Common Utilities (`core/utils/`)

**Must-know utilities** (out of 45+ modules):

- `callbacks.py` - Callback registration with parameter injection
- `events.py` - Event bus system with type-safe event flags
- `data.py` - DataPacket, DataStream for time-series data
- `logging_utils.py` - Logger wrapper with color formatting
- `loop.py` - `infinite_loop()` for main threads
- `exit.py` - `register_exit_callback()` for clean shutdown
- `network/network.py` - Network utilities (`getHostIP()`)
- `websockets.py` - WebSocket client/server managers
- `timecode/mtc.py` - MIDI Time Code for synchronization
- `joystick/` - Joystick manager with button/axis mapping
- `sound/sound.py` - Text-to-speech and sound playback

## Path Conventions

The project may be synchronized across multiple machines via Seafile. When working with file paths, always use absolute paths:

```python
from core.utils.files import get_absolute_path
import os

# Get absolute path relative to current file
config_path = get_absolute_path('robots/bilbo/configs/robots/bilbo1.yaml')

# Or use os.path.abspath
abs_path = os.path.abspath(__file__)
```

**Related repositories** (sibling to this `software/` directory):
- `../robots/bilbo/firmware/` - STM32 firmware
- `../robots/bilbo/software/BILBO-Software/` - On-robot Python application

## Related Documentation

- `extensions/gui/src/lib/map/CLAUDE.md` - Map 2D visualization system
- `../robots/bilbo/firmware/firmware/CLAUDE.md` - STM32 firmware architecture

## Common Pitfalls

- **Path confusion**: Project may exist in multiple Seafile-synced locations. Always use `os.path.abspath()` and `get_absolute_path()`.
- **Event timing**: Use `events.wait(timeout=...)` for initialization sequencing to avoid race conditions.
- **WebSocket ports**: Desktop GUI (8098), mobile (8599), map server varies by application.
- **Callback parameter mismatch**: Use `discard_inputs=True` if callback signature differs from event data.
- **Config loading**: Use `dacite.from_dict()` for automatic YAML→dataclass conversion, not manual dict access.
