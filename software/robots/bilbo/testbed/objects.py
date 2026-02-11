import abc
import dataclasses

from robots.bilbo.definitions import BoxObstacle_Config, BoxObstacle_State
from robots.bilbo.robot.bilbo import BILBO
from robots.bilbo.robot.bilbo_data import BILBO_DynamicState
from robots.bilbo.robot.bilbo_definitions import BILBO_Config
from robots.bilbo.simulation.virtual_testbed import SimulatedBILBO
from robots.bilbo.simulation.virtual_testbed import SimulatedBoxObstacle
from robots.bilbo.testbed.tracker.tracked_objects import TrackedBILBO, TrackedLimboBar, TrackedBox


# ======================================================================================================================
class TestbedBILBO:
    id: str
    state: BILBO_DynamicState
    config: BILBO_Config | None


class RealTestbedBILBO(TestbedBILBO):
    tracked_object: TrackedBILBO
    robot: BILBO

    def __init__(self, id: str,
                 robot: BILBO,
                 config: BILBO_Config,
                 tracked_object: TrackedBILBO):
        self.id = id
        self.robot = robot
        self.config = config
        self.tracked_object = tracked_object

    @property
    def state(self) -> BILBO_DynamicState:
        state = BILBO_DynamicState(
            x=self.tracked_object.state.x,
            y=self.tracked_object.state.y,
            v=self.robot.data.estimation.state.v,
            theta=self.robot.data.estimation.state.theta,
            theta_dot=self.robot.data.estimation.state.theta_dot,
            psi=self.tracked_object.state.psi,
            psi_dot=self.robot.data.estimation.state.psi_dot
        )
        return state


# ----------------------------------------------------------------------------------------------------------------------
class VirtualTestbedBILBO(TestbedBILBO):
    simulation_object: SimulatedBILBO

    def __init__(self, id: str, config: None, simulation_object: SimulatedBILBO):
        self.id = id
        self.simulation_object = simulation_object
        self.config = None

    @property
    def state(self) -> BILBO_DynamicState:
        return self.simulation_object.get_state()


# ======================================================================================================================
class Obstacle(abc.ABC):
    id: str
    config: BoxObstacle_Config
    state: BoxObstacle_State

    @abc.abstractmethod
    def to_dict(self) -> dict:
        ...


class BoxObstacle(Obstacle):

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'type': 'box',
            'x': self.state.x,
            'y': self.state.y,
            'psi': self.state.psi,
            'width': self.config.width,
            'height': self.config.height
        }


class RealBoxObstacle(BoxObstacle):
    tracked_object: TrackedBox

    def __init__(self, id: str, config: BoxObstacle_Config, tracked_object: TrackedBox):
        self.id = id
        self.config = config
        self.tracked_object = tracked_object

    @property
    def state(self) -> BoxObstacle_State:
        return BoxObstacle_State(
            x=self.tracked_object.state.x,
            y=self.tracked_object.state.y,
            psi=self.tracked_object.state.psi
        )


class VirtualTestbedBoxObstacle(BoxObstacle):
    simulation_object: SimulatedBoxObstacle

    def __init__(self, id: str, config: BoxObstacle_Config, simulation_object: SimulatedBoxObstacle):
        self.id = id
        self.config = config
        self.simulation_object = simulation_object

    @property
    def state(self) -> BoxObstacle_State:
        return BoxObstacle_State(
            x=self.simulation_object.state.x,
            y=self.simulation_object.state.y,
            psi=self.simulation_object.state.psi
        )


# ======================================================================================================================
# class WallObstacle(BoxObstacle):
#     ...


# ======================================================================================================================
# @dataclasses.dataclass
# class CircleObstacle_Config:
#     x: float
#     y: float
#     radius: float


# class CircleObstacle(Obstacle):
#     ...


# ======================================================================================================================

# === LIMBO BAR ========================================================================================================
@dataclasses.dataclass
class LimboBarGeometry:
    start_x: float | None = None
    end_x: float | None = None
    length: float | None = None
    start_y: float | None = None
    end_y: float | None = None
    height: float | None = None


class LimboBar:
    tracked_object: TrackedLimboBar
    geometry: LimboBarGeometry
    hit: bool = False

    def __init__(self, geometry: LimboBarGeometry, tracked_object: TrackedLimboBar = None):
        self.geometry = geometry
        self.tracked_object = tracked_object

    def reset(self):
        self.hit = False

    def update(self, robot: 'TestbedBILBO'):

        if self.tracked_object is not None:
            self.geometry.start_x = self.tracked_object.state.x
            self.geometry.end_x = self.geometry.length if self.geometry.length is not None else 1.0

        if self.hit:
            return
        self.hit = self._check_collision(robot)

    def _check_collision(self, robot: 'TestbedBILBO') -> bool:
        """
        Check collision between the robot and the limbo bar.

        Robot geometry:
        - Reference point (px, py) is between wheel midpoints at axle height (z = wheel_radius above ground)
        - Body is a box centered at reference point, tilts with theta (pitch)
        - Wheels are cylinders that stay on ground, rotate only with psi (yaw)

        Limbo bar is a horizontal line segment at height z (above ground).
        """
        import math

        # Robot state (from TestbedBILBO.state — works for both real and simulated)
        px = robot.state.x
        py = robot.state.y
        theta = robot.state.theta  # pitch angle (forward tilt)
        psi = robot.state.psi  # yaw angle (rotation around global z)

        # Robot dimensions (from TestbedBILBO.config)
        wheel_radius = robot.config.model.wheel_diameter / 2
        wheel_thickness = 0.02  # m
        body_height = robot.config.model.height
        body_width = robot.config.model.width  # robot y-axis (between wheels)
        body_depth = robot.config.model.depth  # robot x-axis (forward/backward)

        # Limbo bar geometry (height is in global frame, above ground)
        bar_z = self.geometry.height
        bar_x1, bar_y1 = self.geometry.start_x, self.geometry.start_y
        bar_x2, bar_y2 = self.geometry.end_x, self.geometry.end_y

        # Precompute trig values
        cos_psi, sin_psi = math.cos(psi), math.sin(psi)
        cos_theta, sin_theta = math.cos(theta), math.sin(theta)

        # Helper: minimum distance from point to line segment in 2D
        def point_to_segment_dist(px, py, x1, y1, x2, y2):
            dx, dy = x2 - x1, y2 - y1
            len_sq = dx * dx + dy * dy
            if len_sq == 0:
                return math.hypot(px - x1, py - y1)
            t = max(0, min(1, ((px - x1) * dx + (py - y1) * dy) / len_sq))
            return math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))

        # ==================== WHEEL COLLISION ====================
        # Wheels stay on ground, only rotate with psi (not theta)
        # Wheel center is at height wheel_radius (global z)
        # Wheel spans z ∈ [0, 2*wheel_radius] in global frame

        for side in [-1, 1]:  # left (-1) and right (+1) wheel
            # Wheel y-offset in robot frame (wheels start at body_width/2 boundary)
            wheel_y_local = side * (body_width / 2 + wheel_thickness / 2)

            # Transform wheel center to global XY (only psi rotation, no theta)
            # Point (0, wheel_y_local) in robot frame -> global frame
            wheel_x_global = px - wheel_y_local * sin_psi
            wheel_y_global = py + wheel_y_local * cos_psi

            # Check if bar height intersects wheel's z-range [0, 2*wheel_radius]
            if 0 <= bar_z <= 2 * wheel_radius:
                # At bar_z, compute the wheel's cross-section (chord of circle)
                dz = bar_z - wheel_radius  # distance from wheel center height
                if abs(dz) <= wheel_radius:
                    # Half-length of chord at this height
                    chord_half = math.sqrt(wheel_radius ** 2 - dz ** 2)

                    # Distance from wheel center (XY) to bar line segment
                    dist_xy = point_to_segment_dist(
                        wheel_x_global, wheel_y_global,
                        bar_x1, bar_y1, bar_x2, bar_y2
                    )

                    # Collision if bar passes through wheel cross-section
                    # Add wheel_thickness/2 to account for wheel width
                    if dist_xy <= chord_half + wheel_thickness / 2:
                        return True

        # ==================== BODY COLLISION (OBB) ====================
        # Body is a box that tilts with theta around the robot y-axis
        # In local frame (reference at origin, z=0 at axle height):
        #   x ∈ [-body_depth/2, +body_depth/2]
        #   y ∈ [-body_width/2, +body_width/2]
        #   z ∈ [0, body_height]
        # In global frame, reference point is at z = wheel_radius

        def local_to_global(lx, ly, lz):
            """Transform point from robot local frame to global frame."""
            # 1. Apply theta rotation (pitch around robot y-axis)
            x_pitched = lx * cos_theta + lz * sin_theta
            z_pitched = -lx * sin_theta + lz * cos_theta
            y_pitched = ly  # y unchanged by pitch

            # 2. Apply psi rotation (yaw around global z-axis) and translate
            x_global = px + x_pitched * cos_psi - y_pitched * sin_psi
            y_global = py + x_pitched * sin_psi + y_pitched * cos_psi

            # 3. Add wheel_radius to convert local z=0 (axle) to global z
            z_global = z_pitched + wheel_radius

            return x_global, y_global, z_global

        # Compute all 8 body corners in global frame
        # Corner indexing (based on loop order):
        # idx 0: (-d/2, -w/2, 0)    idx 1: (-d/2, -w/2, h)
        # idx 2: (-d/2, +w/2, 0)    idx 3: (-d/2, +w/2, h)
        # idx 4: (+d/2, -w/2, 0)    idx 5: (+d/2, -w/2, h)
        # idx 6: (+d/2, +w/2, 0)    idx 7: (+d/2, +w/2, h)
        body_corners = []
        for dx in [-body_depth / 2, body_depth / 2]:
            for dy in [-body_width / 2, body_width / 2]:
                for dz in [0, body_height]:
                    corner = local_to_global(dx, dy, dz)
                    body_corners.append(corner)

        # Find z-extent of body in global frame
        z_values = [c[2] for c in body_corners]
        body_z_min, body_z_max = min(z_values), max(z_values)

        # Check if bar height intersects body's z-range
        if body_z_min <= bar_z <= body_z_max:
            # Compute the exact cross-section polygon at bar_z by finding
            # where the plane z=bar_z intersects the box edges

            # Define all 12 edges of the box as pairs of corner indices
            box_edges = [
                # "Vertical" edges (connect bottom to top at each corner)
                (0, 1), (2, 3), (4, 5), (6, 7),
                # Bottom face edges (z=0 corners before transform)
                (0, 2), (2, 6), (6, 4), (4, 0),
                # Top face edges (z=h corners before transform)
                (1, 3), (3, 7), (7, 5), (5, 1),
            ]

            # Find intersection points with plane z = bar_z
            cross_section_points = []
            for i1, i2 in box_edges:
                p1 = body_corners[i1]
                p2 = body_corners[i2]
                z1, z2 = p1[2], p2[2]

                # Check if edge crosses or touches the bar height
                z_min_edge, z_max_edge = min(z1, z2), max(z1, z2)
                if z_min_edge <= bar_z <= z_max_edge:
                    if abs(z2 - z1) < 1e-12:
                        # Edge is horizontal at bar_z height - add both endpoints
                        cross_section_points.append((p1[0], p1[1]))
                        cross_section_points.append((p2[0], p2[1]))
                    else:
                        # Interpolate to find intersection point
                        t = (bar_z - z1) / (z2 - z1)
                        x_int = p1[0] + t * (p2[0] - p1[0])
                        y_int = p1[1] + t * (p2[1] - p1[1])
                        cross_section_points.append((x_int, y_int))

            # Remove duplicate points (within tolerance)
            unique_points = []
            for pt in cross_section_points:
                is_duplicate = False
                for upt in unique_points:
                    if abs(pt[0] - upt[0]) < 1e-9 and abs(pt[1] - upt[1]) < 1e-9:
                        is_duplicate = True
                        break
                if not is_duplicate:
                    unique_points.append(pt)

            if len(unique_points) >= 3:
                # Sort points to form a convex polygon (counter-clockwise)
                polygon = self._sort_convex_polygon(unique_points)

                # Check if bar segment intersects this polygon
                if self._segment_intersects_convex_polygon(
                        bar_x1, bar_y1, bar_x2, bar_y2, polygon):
                    return True

        return False

    def _sort_convex_polygon(self, points: list) -> list:
        """Sort points counter-clockwise around their centroid to form convex polygon."""
        import math

        if len(points) < 3:
            return points

        # Compute centroid
        cx = sum(p[0] for p in points) / len(points)
        cy = sum(p[1] for p in points) / len(points)

        # Sort by angle from centroid
        def angle_from_centroid(p):
            return math.atan2(p[1] - cy, p[0] - cx)

        return sorted(points, key=angle_from_centroid)

    def _segment_intersects_convex_polygon(self, x1, y1, x2, y2, polygon: list) -> bool:
        """Check if line segment (x1,y1)-(x2,y2) intersects a convex polygon."""
        if len(polygon) < 3:
            return False

        # Helper: cross product for orientation
        def cross(ox, oy, ax, ay, bx, by):
            return (ax - ox) * (by - oy) - (ay - oy) * (bx - ox)

        # Helper: check if point is inside convex polygon (using cross products)
        def point_in_polygon(px, py):
            n = len(polygon)
            for i in range(n):
                x_i, y_i = polygon[i]
                x_j, y_j = polygon[(i + 1) % n]
                if cross(x_i, y_i, x_j, y_j, px, py) < 0:
                    return False  # Point is on the right side of this edge
            return True

        # Check if either endpoint is inside the polygon
        if point_in_polygon(x1, y1) or point_in_polygon(x2, y2):
            return True

        # Helper: check if two segments intersect
        def segments_intersect(ax1, ay1, ax2, ay2, bx1, by1, bx2, by2):
            d1 = cross(bx1, by1, bx2, by2, ax1, ay1)
            d2 = cross(bx1, by1, bx2, by2, ax2, ay2)
            d3 = cross(ax1, ay1, ax2, ay2, bx1, by1)
            d4 = cross(ax1, ay1, ax2, ay2, bx2, by2)

            if ((d1 > 0 and d2 < 0) or (d1 < 0 and d2 > 0)) and \
                    ((d3 > 0 and d4 < 0) or (d3 < 0 and d4 > 0)):
                return True

            # Collinear cases
            def on_segment(px, py, qx, qy, rx, ry):
                return (min(px, rx) <= qx <= max(px, rx) and
                        min(py, ry) <= qy <= max(py, ry))

            if d1 == 0 and on_segment(bx1, by1, ax1, ay1, bx2, by2):
                return True
            if d2 == 0 and on_segment(bx1, by1, ax2, ay2, bx2, by2):
                return True
            if d3 == 0 and on_segment(ax1, ay1, bx1, by1, ax2, ay2):
                return True
            if d4 == 0 and on_segment(ax1, ay1, bx2, by2, ax2, ay2):
                return True

            return False

        # Check if segment intersects any polygon edge
        n = len(polygon)
        for i in range(n):
            ex1, ey1 = polygon[i]
            ex2, ey2 = polygon[(i + 1) % n]
            if segments_intersect(x1, y1, x2, y2, ex1, ey1, ex2, ey2):
                return True

        return False
