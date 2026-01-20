# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is the **Map module** within the RobotManager GUI extension - a real-time 2D visualization system for robotic applications. It provides a bidirectional Python/JavaScript architecture for rendering robots, trajectories, and map objects on a web canvas.

## Build Commands

From the `gui/` directory (parent of `src/`):

```bash
# Install dependencies
npm install

# Development server (port 9200)
npm run dev

# Production build (outputs to ../dist)
npm run build

# Preview production build
npm run serve
```

## Architecture

### Dual-Layer Design

The map system uses a **Python backend + JavaScript frontend** pattern with WebSocket communication:

```
Python (map.py)                    JavaScript (map.js)
├── Map class (WebSocket server)   ├── Map class (Canvas 2D renderer)
├── MapObject, MapObjectGroup      ├── MapObject subclasses (draw logic)
└── Update thread (20 Hz)          └── Render loop (30 FPS)
```

### Key Files

| File | Purpose |
|------|---------|
| `map.py` | Backend Map class with WebSocket server, update thread, configuration |
| `map.js` | Frontend canvas renderer, coordinate transforms, interaction handling |
| `map_objects.py` | Python MapObject/MapObjectGroup base classes and subtypes |
| `map_objects.js` | JavaScript rendering implementations (Point, Line, Circle, Agent, etc.) |

### Communication Flow

1. **Backend → Frontend (Data updates)**: Position changes queued in `map.update_data`, batched every 50ms
2. **Backend → Frontend (Config updates)**: Style/visibility changes via `updateConfig()` → broadcast
3. **Frontend → Backend (Events)**: User interactions sent as event messages

### Coordinate System

- Canvas uses a **rotated coordinate system** (Y-axis up, mathematically standard)
- World coordinates transformed via translate/scale/rotate stack
- Grid uses 1-based indexing

### Message Types

WebSocket messages between Python and JavaScript:
- `add` - Create new object/group
- `remove` - Delete object
- `update` - Position/data changes (batched)
- `update_config` - Style/visibility changes

### Map Object Hierarchy

```python
MapObject (abstract base)
├── Point          # Single coordinate marker
├── Line           # Line segment
├── Circle         # Circle with radius
├── Agent          # Robot with position + velocity
└── VisionAgent    # Agent with cone-based visibility

MapObjectGroup     # Container for hierarchical organization
```

### Configuration

Key configuration categories in `map.py`:
- **Geometry**: `x_limits`, `y_limits`, `origin`, `rotation`
- **Visual**: `show_grid`, `show_tiles`, `tile_color`, `grid_color`
- **Interaction**: `zoom`, `drag`, `rotation_enabled`

### Trail Rendering

Objects support trajectory trails with:
- Exponential alpha decay based on age
- Distance/time gating to avoid clutter
- Per-object trail parameters (`trail_time`, `trail_distance`)

### Click Handling

The map provides click detection with world coordinate conversion:

```javascript
// Override the on_click method to handle clicks
map.on_click = function(x, y) {
    console.log(`Clicked at world coords: ${x}, ${y}`);
};
```

Key methods:
- `on_click(x, y)` - Called when map is clicked (override this)
- `canvasPointToWorld(sx, sy)` - Convert screen coordinates to world coordinates
- `worldPointToCanvas(wx, wy)` - Convert world coordinates to screen coordinates

### Custom Cursor

The map supports custom cursors for interaction modes (e.g., placing waypoints):

```javascript
// Circle cursor (e.g., for waypoint placement)
map.change_cursor('circle', {
    color: [1, 0, 0, 1],      // RGBA outline color
    fillColor: [1, 0, 0, 0.3], // RGBA fill color (optional)
    size: 0.1,                 // Radius in world units
    lineWidth: 2               // Outline width in pixels
});

// Crosshair cursor
map.change_cursor('crosshair', {
    color: [1, 1, 1, 1],  // RGBA color
    size: 0.15,           // Half-length in world units
    lineWidth: 2
});

// Reset to default cursor
map.change_cursor('default');

// Hide cursor completely
map.change_cursor('none');
```

## Adding New Map Object Types

1. Create Python class in `map_objects.py` extending `MapObject`
2. Implement `getPayload()` for serialization
3. Create JavaScript class in `map_objects.js` extending `MapObject`
4. Implement `draw(ctx)` method for canvas rendering
5. Add to `MAP_OBJECT_MAPPING` in both files

## Parent Project Context

This map module is part of the larger GUI extension in `RobotManager/extensions/gui/`. The GUI system provides:
- Hierarchical GUI structure (Categories → Pages → Widgets)
- Grid-based widget layouts (18×50 CSS grid)
- WebSocket-based bidirectional communication
- Settings in `settings.py`: `WS_PORT_DESKTOP=8098`, `WS_PORT_MOBILE=8599`
