# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**RobotManager** is a comprehensive multi-robot control and orchestration framework for the BILBO Two-Wheel Inverted Pendulum Robot (TWIPR). It provides the host-side management layer for robot fleets, implementing device discovery, web-based GUI, experiment orchestration, real-time visualization, and data logging.

This is the **third layer** in BILBO's three-layer architecture:
1. **STM32 Firmware** (100 Hz real-time control) → See `/robots/bilbo/firmware/firmware/CLAUDE.md`
2. **Raspberry Pi Software** (on-robot control application)
3. **RobotManager** (this repository - host-side fleet management)

## Build & Run Commands

### Setup
```bash
# Install Python dependencies
pip install -r requirements.txt

# Install GUI dependencies
cd extensions/gui
npm install
```

### Run Application
```bash
# Run BILBO application with GUI
python applications/BILBO/bilbo_application.py
```

### GUI Development
```bash
cd extensions/gui

# Development server (port 9200)
npm run dev

# Production build
npm run build

# Preview production build
npm run serve
```

### Testing
```bash
# Run tests
pytest _tests/
```

### Deployment Scripts
```bash
# Update on-robot software (Raspberry Pi)
python utilities/update_software.py

# Update STM32 firmware
python utilities/update_firmware.py

# Initial installation on new robot
python utilities/install.py
```

## Architecture Overview

### Directory Structure

```
/applications/          # Robot-specific application implementations
  └── BILBO/           # BILBO robot application (GUI, experiments, testbed)
/robots/               # Robot hardware abstractions for RobotManager
  └── bilbo/           # BILBO robot interface classes
      ├── robot/       # Core robot modules (control, estimation, data, interfaces)
      └── manager/     # Fleet management, joystick control, CLI
/core/                 # Shared framework utilities (~45 modules)
  ├── utils/           # Callbacks, events, logging, networking, data handling
  └── communication/   # Device server, protocols, WiFi/UDP communication
/extensions/           # Modular system extensions
  ├── gui/            # Vue 3 + Vite web GUI with WebSocket (see gui/src/lib/map/CLAUDE.md)
  ├── optitrack/      # Motion capture integration
  ├── simulation/     # Robot simulation
  ├── testbed/        # Physical testbed management
  ├── teleplot/       # Real-time data plotting
  ├── cli/            # Command-line interface
  └── joystick/       # Joystick control support
/projects/             # Research and application projects
/utilities/            # Deployment and maintenance scripts
```

### Communication Architecture

```
Host (RobotManager) ←→ WebSocket/UDP (WiFi) ←→ Raspberry Pi (BILBO-Software)
                                                     ↕ Serial/SPI
                                              STM32 Firmware (100 Hz control)
                                                     ↕ CAN/RS485
                                              Motor Controllers
```

**Key Protocols:**
- **UDP Broadcast**: Device discovery and presence announcements
- **WebSocket**: Bidirectional control/data streaming between all layers
- **Serial**: Register-based communication (Raspberry Pi ↔ STM32)
- **SPI**: High-speed DMA transfers for trajectory data and sensor samples

### Three-Layer Data Flow

1. **Sensors → Estimation → Control → Motors** (100 Hz on STM32)
2. **STM32 → Raspberry Pi** (Serial samples, batched at ~10 Hz)
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
from dacite import from_dict

config = from_dict(data_class=BILBO_Config, data=yaml_data)
```

**Configuration locations:**
- `applications/BILBO/configs/hardware/` - Robot hardware configs (bilbo1.yaml, bilbo2.yaml, etc.)
- `robots/bilbo/software/BILBO-Software/configs/control/` - Control parameter configs
- `applications/BILBO/configs/testbed/` - Testbed environment configs

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

# Load config
config = load_yaml_config('configs/hardware/bilbo1.yaml')

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

The project uses **relative symlinks** between related repositories:

```
/path/to/testbed/
├── software/
│   ├── RobotManager/          # This repository
│   └── BILBO-Software/        # On-robot software
└── firmware/
    └── cubeide-project/       # STM32 firmware
```

Code frequently references sibling paths:
```python
# Go up to testbed, then down to other repos
robot_sw_path = '../../../robots/bilbo/software/BILBO-Software/'
firmware_path = '../../../robots/bilbo/firmware/firmware/'
```

When working with file paths, use `get_absolute_path()` from `core/utils/files.py`.

## Git Workflow Notes

**Active development areas** (based on recent commits):
- Control system refactoring (balancing, velocity, position split)
- Firmware-software communication protocol updates
- Joystick manager improvements
- Configuration restructuring (hardware vs control configs)

**Key branches:**
- `main` - Primary development branch

## Related Documentation

- `/extensions/gui/src/lib/map/CLAUDE.md` - Map visualization system
- `/robots/bilbo/firmware/firmware/CLAUDE.md` - STM32 firmware architecture
- `applications/BILBO/README.md` - BILBO application specifics (if exists)

## Quick Start for New Features

1. **Determine the layer**: Firmware (real-time), Software (on-robot logic), or Manager (host orchestration)
2. **For RobotManager features**:
   - Extension → Add to `/extensions/` if reusable
   - Application-specific → Add to `/applications/BILBO/`
   - Core utility → Add to `/core/utils/`
3. **Follow the init/start/close pattern**
4. **Use events for decoupled communication**
5. **Register exit callbacks for cleanup**
6. **Add WebSocket endpoints** for GUI integration
7. **Document complex interactions** in module docstrings

## Common Pitfalls

- **Path confusion**: RobotManager has two working directories (via Seafile sync). Always use `os.path.abspath()`.
- **Event timing**: Use `events.wait()` with timeouts for initialization dependencies.
- **WebSocket ports**: GUI desktop (8098), mobile (8599), map varies by app.
- **Callback parameter mismatch**: Use `discard_inputs=True` if callback signature differs from event data.
- **Config loading**: Use `dacite.from_dict()` for automatic dataclass conversion, not manual dict access.
