import os
import threading
import time
import webbrowser

from core.utils.exit import register_exit_callback
from core.utils.websockets import WebsocketServer

from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Union, Any


# -----------------------------------------------------------------------------
# Plottable Elements with only the essential properties.
# (Any properties you do not want to send on every update are omitted.)
# -----------------------------------------------------------------------------

@dataclass
class Point:
    id: str  # Unique identifier (and display label) for the point.
    x: float  # X-coordinate.
    y: float  # Y-coordinate.
    color: Optional[List[float]] = None  # Optional RGB color (normalized values).
    alpha: Optional[float] = 1  # Transparency (default 1 = opaque).
    dim: bool = False  # Flag to “dim” the element.
    size: float = 1


@dataclass
class Agent:
    id: str  # Unique identifier for the agent.
    position: List[float]  # (x, y) position.
    psi: float  # Heading (in radians).
    color: Optional[List[float]] = None  # Optional RGB color.
    text: Optional[str] = None  # Optional extra text.
    alpha: Optional[float] = 1  # Transparency.
    size: float = 1
    shape: str = 'circle'  # circle, square, triangle


@dataclass
class VisionAgent(Agent):
    vision_radius: float = 0  # Radius of vision.
    vision_fov: float = 0  # Field-of-view (in radians).


@dataclass
class Vector:
    id: str  # Unique identifier for the vector.
    origin: List[float]  # Starting point.
    vec: List[float]  # Displacement vector.
    color: Optional[List[float]] = None  # Optional color.
    text: Optional[str] = None  # Optional text label.


@dataclass
class CoordinateSystem:
    id: str  # Unique identifier.
    origin: List[float]  # Origin.
    ex: List[float]  # X-axis unit vector.
    ey: List[float]  # Y-axis unit vector.
    colors: Optional[Dict[str, List[float]]] = None  # Optional colors for the axes.
    text: Optional[str] = None  # Optional text label.


@dataclass
class Line:
    id: str  # Unique identifier for the line.
    start: Union[str, List[float]]  # Either a coordinate pair or a string reference.
    end: Union[str, List[float]]  # Either a coordinate pair or a string reference.
    color: Optional[List[float]] = None  # Optional color.
    text: Optional[str] = None  # Optional text label.
    # thickness: Optional[float] = None  # Optional line thickness.


@dataclass
class Rectangle:
    id: str  # Unique identifier for the rectangle.
    mid: List[float]  # Center (midpoint).
    x: float  # Width.
    y: Optional[float] = None  # Height; if omitted, it may be assumed equal to x.
    fill: Optional[List[float]] = None  # Optional fill color.
    linecolor: Optional[List[float]] = None  # Optional outline color.


@dataclass
class Circle:
    id: str  # Unique identifier for the circle.
    mid: List[float]  # Center.
    diameter: float  # Diameter.
    fill: Optional[List[float]] = None  # Optional fill color.
    linecolor: Optional[List[float]] = None  # Optional outline color.


# -----------------------------------------------------------------------------
# Group Container with add functions, helper methods, and a to_dict method.
# -----------------------------------------------------------------------------

@dataclass
class Group:
    id: str  # Unique identifier for the group.
    fullPath: str = ""  # Full hierarchical path; set automatically if not provided.
    points: Dict[str, Point] = field(default_factory=dict)
    agents: Dict[str, Agent] = field(default_factory=dict)
    visionagents: Dict[str, VisionAgent] = field(default_factory=dict)
    vectors: Dict[str, Vector] = field(default_factory=dict)
    coordinate_systems: Dict[str, CoordinateSystem] = field(default_factory=dict)
    lines: Dict[str, Line] = field(default_factory=dict)
    rectangles: Dict[str, Rectangle] = field(default_factory=dict)
    circles: Dict[str, Circle] = field(default_factory=dict)
    groups: Dict[str, "Group"] = field(default_factory=dict)
    parent: Optional["Group"] = None
    name: str = ''  # Name for display purposes.

    def __post_init__(self):
        # If fullPath is not set, use the group's id.
        self.name = self.id
        if not self.fullPath:
            self.fullPath = self.id

    # Helper method: return the top-level group.
    def get_root(self) -> "Group":
        if self.parent is None:
            return self
        return self.parent.get_root()

    # Helper method: search for a target element in this group and subgroups.
    # If found, returns the absolute path as "/<group.fullPath>/<target.id>".
    def find_absolute_path(self, target) -> Optional[str]:
        # Check in each element container.
        for container in [self.points, self.agents, self.visionagents, self.vectors,
                          self.coordinate_systems, self.lines, self.rectangles, self.circles]:
            for el in container.values():
                if el is target:
                    return "/" + self.fullPath + "/" + target.column_id
        # Recurse into subgroups.
        for sub in self.groups.values():
            path = sub.find_absolute_path(target)
            if path is not None:
                return path
        return None

    # -----------------------------------------------------------------------------
    # New Method: get_element_by_id()
    #
    # This method returns an element by its path.
    # The path is a string such as "group1" or "group1/group2/point1".
    # The method works relative to the current group, so if called in group1,
    # "group2/point1" would search group1.groups["group2"] and then its points.
    #
    # If any element in the path does not exist, the method returns None.
    # -----------------------------------------------------------------------------
    def get_element_by_id(self, path: str) -> Optional[
        Union["Group", Point, Agent, VisionAgent, Vector, CoordinateSystem, Line, Rectangle, Circle]]:
        tokens = path.strip("/").split("/")
        if not tokens:
            return None
        current_group = self
        # Traverse through the tokens (except the last) assuming they represent groups.
        for token in tokens[:-1]:
            current_group = current_group.groups.get(token)
            if current_group is None:
                return None
        last_token = tokens[-1]
        # First check if the last token refers to a subgroup.
        if last_token in current_group.groups:
            return current_group.groups[last_token]
        # Otherwise, check each container.
        if last_token in current_group.points:
            return current_group.points[last_token]
        if last_token in current_group.agents:
            return current_group.agents[last_token]
        if last_token in current_group.visionagents:
            return current_group.visionagents[last_token]
        if last_token in current_group.vectors:
            return current_group.vectors[last_token]
        if last_token in current_group.coordinate_systems:
            return current_group.coordinate_systems[last_token]
        if last_token in current_group.lines:
            return current_group.lines[last_token]
        if last_token in current_group.rectangles:
            return current_group.rectangles[last_token]
        if last_token in current_group.circles:
            return current_group.circles[last_token]
        return None

        # New method: remove_element_by_id()

    def remove_element_by_id(self, path: str) -> Optional[
        Union["Group", Point, Agent, VisionAgent, Vector, CoordinateSystem, Line, Rectangle, Circle]]:
        """
        Remove an element specified by its relative path.
        Returns the removed element if found and removed, or None if not found.
        """
        tokens = path.strip("/").split("/")
        if not tokens:
            return None
        current_group = self
        # Traverse all tokens except the last, assuming they refer to subgroups.
        for token in tokens[:-1]:
            current_group = current_group.groups.get(token)
            if current_group is None:
                return None
        last_token = tokens[-1]
        # Check if the element is a subgroup.
        if last_token in current_group.groups:
            return current_group.groups.pop(last_token)
        # Otherwise, check in each element container.
        if last_token in current_group.points:
            return current_group.points.pop(last_token)
        if last_token in current_group.agents:
            return current_group.agents.pop(last_token)
        if last_token in current_group.visionagents:
            return current_group.visionagents.pop(last_token)
        if last_token in current_group.vectors:
            return current_group.vectors.pop(last_token)
        if last_token in current_group.coordinate_systems:
            return current_group.coordinate_systems.pop(last_token)
        if last_token in current_group.lines:
            return current_group.lines.pop(last_token)
        if last_token in current_group.rectangles:
            return current_group.rectangles.pop(last_token)
        if last_token in current_group.circles:
            return current_group.circles.pop(last_token)
        return None

    # Add functions for each element type. They create the element, add it to this group,
    # and return the object so you can modify it later.
    def add_point(self, id: str, x: float, y: float, **kwargs) -> Point:
        point = Point(id=id, x=x, y=y, **kwargs)
        self.points[id] = point
        return point

    def add_agent(self, id: str, position: List[float], psi: float, **kwargs) -> Agent:
        agent = Agent(id=id, position=position, psi=psi, **kwargs)
        self.agents[id] = agent
        return agent

    def add_vision_agent(self, id: str, position: List[float], psi: float,
                         vision_radius: float, vision_fov: float, **kwargs) -> VisionAgent:
        vag = VisionAgent(id=id, position=position, psi=psi,
                          vision_radius=vision_radius, vision_fov=vision_fov, **kwargs)
        self.visionagents[id] = vag
        return vag

    def add_vector(self, id: str, origin: List[float], vec: List[float], **kwargs) -> Vector:
        vector = Vector(id=id, origin=origin, vec=vec, **kwargs)
        self.vectors[id] = vector
        return vector

    def add_coordinate_system(self, id: str, origin: List[float],
                              ex: List[float], ey: List[float], **kwargs) -> CoordinateSystem:
        cs = CoordinateSystem(id=id, origin=origin, ex=ex, ey=ey, **kwargs)
        self.coordinate_systems[id] = cs
        return cs

    # Modified add_line: Accepts start and end as either a string (or coordinate list) OR an element.
    # In this version we simply store the element's id if an element is provided,
    # and later (in to_dict) we prepend the current group's fullPath.
    def add_line(self, id: str, start: Union[str, List[float], object],
                 end: Union[str, List[float], object], **kwargs) -> Line:
        if not isinstance(start, (str, list)):
            start = start.id
        if not isinstance(end, (str, list)):
            end = end.id
        line = Line(id=id, start=start, end=end, **kwargs)
        self.lines[id] = line
        return line

    def add_rectangle(self, id: str, mid: List[float], x: float, y: Optional[float] = None,
                      **kwargs) -> Rectangle:
        rect = Rectangle(id=id, mid=mid, x=x, y=y, **kwargs)
        self.rectangles[id] = rect
        return rect

    def add_circle(self, id: str, mid: List[float], diameter: float, **kwargs) -> Circle:
        circle = Circle(id=id, mid=mid, diameter=diameter, **kwargs)
        self.circles[id] = circle
        return circle

    # Modified add_group: It accepts either a Group instance or (id, name) to create a new group.
    def add_group(self, id: Union["Group", str], **kwargs) -> "Group":
        if isinstance(id, Group):
            group = id
            group.parent = self
            if self.fullPath:
                group.fullPath = self.fullPath + "/" + group.id
            else:
                group.fullPath = group.id
        else:
            group = Group(id=id, parent=self, **kwargs)
            if self.fullPath:
                group.fullPath = self.fullPath + "/" + id
            else:
                group.fullPath = id
        self.groups[group.id] = group
        return group

    def to_dict(self) -> dict:
        """
        Convert this group and its contents to a dictionary (suitable for JSON).
        Only the defined fields are included. The parent's reference is omitted to avoid recursion.
        For lines, if the start/end reference is a string that does not begin with '/' or '../',
        we assume it is relative to this group and prepend the absolute path.
        """

        def process_ref(ref):
            if isinstance(ref, str) and not (ref.startswith('/') or ref.startswith('../')):
                return "/" + self.fullPath + "/" + ref
            return ref

        group_dict = {
            "id": self.id,
            "name": self.name,
            "fullPath": self.fullPath,
            "points": {k: asdict(v) for k, v in self.points.items()},
            "agents": {k: asdict(v) for k, v in self.agents.items()},
            "visionagents": {k: asdict(v) for k, v in self.visionagents.items()},
            "vectors": {k: asdict(v) for k, v in self.vectors.items()},
            "coordinate_systems": {k: asdict(v) for k, v in self.coordinate_systems.items()},
            "lines": {k: {**asdict(v), "start": process_ref(v.start), "end": process_ref(v.end)}
                      for k, v in self.lines.items()},
            "rectangles": {k: asdict(v) for k, v in self.rectangles.items()},
            "circles": {k: asdict(v) for k, v in self.circles.items()},
            "groups": {k: v.to_dict() for k, v in self.groups.items()},
        }
        return group_dict


# -----------------------------------------------------------------------------
# Dynamic2DPlotter Class
# -----------------------------------------------------------------------------

class Dynamic2DPlotter:
    server: WebsocketServer
    html_file_path: str = "plotter_2d.html"
    _thread: threading.Thread
    _exit: bool = False

    def __init__(self):
        # Initialize the WebSocket server.
        self.server = WebsocketServer(host="localhost", port=8000)
        # Create a default group for non-group elements.
        self.default_group = Group(id="default", fullPath="default")
        # Start the background thread that will send updates.
        self._thread = threading.Thread(target=self._task, daemon=True)
        register_exit_callback(self.close)

    # Add functions to add elements to the default group.
    def add_point(self, id: str, x: float, y: float, **kwargs) -> Point:
        return self.default_group.add_point(id, x, y, **kwargs)

    def add_agent(self, id: str, position: List[float], psi: float, **kwargs) -> Agent:
        return self.default_group.add_agent(id, position, psi, **kwargs)

    def add_vision_agent(self, id: str, position: List[float],
                         psi: float, vision_radius: float, vision_fov: float, **kwargs) -> VisionAgent:
        return self.default_group.add_vision_agent(id, position, psi, vision_radius, vision_fov, **kwargs)

    def add_vector(self, id: str, origin: List[float], vec: List[float], **kwargs) -> Vector:
        return self.default_group.add_vector(id, origin, vec, **kwargs)

    def add_coordinate_system(self, id: str, origin: List[float],
                              ex: List[float], ey: List[float], **kwargs) -> CoordinateSystem:
        return self.default_group.add_coordinate_system(id, origin, ex, ey, **kwargs)

    def add_line(self, id: str, start: Union[str, List[float], object],
                 end: Union[str, List[float], object], **kwargs) -> Line:
        return self.default_group.add_line(id, start, end, **kwargs)

    def add_rectangle(self, id: str, mid: List[float], x: float,
                      y: Optional[float] = None, **kwargs) -> Rectangle:
        return self.default_group.add_rectangle(id, mid, x, y, **kwargs)

    def add_circle(self, id: str, mid: List[float], diameter: float, **kwargs) -> Circle:
        return self.default_group.add_circle(id, mid, diameter, **kwargs)

    # Modified add_group: It accepts either a Group instance or an id (with a name).
    def add_group(self, id: Union[Group, str], **kwargs) -> Group:
        if isinstance(id, Group):
            group = id
            group.parent = self.default_group
            if self.default_group.fullPath:
                group.fullPath = self.default_group.fullPath + "/" + group.id
            else:
                group.fullPath = group.id
            self.default_group.groups[group.id] = group
            return group
        else:
            return self.default_group.add_group(id, **kwargs)

    # New method: get_element_by_id() in the plotter.
    # This simply delegates the search to the default group.
    def get_element_by_id(self, path: str) -> Optional[Any]:
        return self.default_group.get_element_by_id(path)

    def remove_element_by_id(self, path: str) -> Optional[Any]:
        """
        Remove an element from the plotter's default group using its relative path.
        Returns the removed element if found, or None if not.
        """
        return self.default_group.remove_element_by_id(path)

    def get_data(self) -> dict:
        """
        Transform all elements (starting from the default group) into a dictionary
        formatted for the JavaScript application.
        """
        return {"groups": {self.default_group.id: self.default_group.to_dict()}}

    def _task(self):
        while not self._exit:
            data: dict = self.get_data()
            self.server.send(data)
            time.sleep(0.05)

    def _open_plotter_html(self) -> bool:
        """
        Open the plotter_2d.html file in the default web browser.
        Returns True if successful, False otherwise.
        """
        current_dir = os.path.dirname(os.path.abspath(__file__))
        html_path = os.path.join(current_dir, self.html_file_path)
        try:
            if not os.path.exists(html_path):
                print(f"Error: File {html_path} does not exist.")
                return False
            webbrowser.open(f'file://{html_path}', new=2)
            return True
        except Exception as e:
            print(f"Error opening file: {e}")
            return False

    def start(self):
        # Start the WebSocket server, background thread, and open the HTML page.
        self.server.start()
        self._thread.start()
        self._open_plotter_html()

    def close(self, *args, **kwargs):
        print("Closing Dynamic2DPlotter")
        self._exit = True
        if self._thread is not None and self._thread.is_alive():
            self._thread.join()


# ======================================================================================================================
if __name__ == '__main__':
    plotter = Dynamic2DPlotter()

    # Example: Add some elements to the default group.
    p1 = plotter.add_point("p1", 1.0, 2.0, color=[1, 0, 0], size=1)
    p2 = plotter.add_point("p2", 1.0, -2.0, color=[1, 0, 0], size=0.2)

    # Create a group object and add elements to it.
    group = Group(id="group1", name="group1")
    a1 = group.add_agent("a1", [3.0, 4.0], psi=0.5, color=[0, 1, 1], size=3)
    va1 = group.add_vision_agent("va1", [5.0, 6.0], psi=0.0, vision_radius=2.0, vision_fov=2, color=[0, 0, 1])
    # Here we add a line using element objects (a1 and va1) instead of just id strings.
    # Because of our changes, the line's start/end will be stored as relative references (just the id)
    # and later, when converting to dict, the current group's fullPath will be prepended.
    group.add_line("line1", a1, va1)
    plotter.add_group(group)

    # Also add a line from a point in the default group to an element in group1.
    # plotter.add_line("line1", p1, va1, color=[0, 0, 0])
    plotter.start()

    # Example usage of get_element_by_id:
    # From the plotter (i.e., the default group) you can search for an element by path.
    # For instance, this returns the group with id "group1":
    element = plotter.get_element_by_id("group1")
    print("Found element:", element)

    # Keep the main thread alive.
    while True:
        # Uncomment the following line to animate a change in position:
        a1.position[0] += 0.005
        time.sleep(0.02)
