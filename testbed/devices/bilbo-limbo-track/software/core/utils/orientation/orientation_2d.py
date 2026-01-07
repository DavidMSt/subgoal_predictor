import dataclasses

import numpy as np
from core.utils.orientation.plot_2d.static.static_plot_2d import plot_2d


@dataclasses.dataclass
class CoordinateSystem:
    origin: np.ndarray
    x_axis: np.ndarray
    y_axis: np.ndarray

    def __init__(self, origin: (tuple, list, np.ndarray),
                 x_axis: (tuple, list, np.ndarray),
                 y_axis: (tuple, list, np.ndarray)):
        self.origin = np.asarray(origin)
        self.x_axis = np.asarray(x_axis)
        self.y_axis = np.asarray(y_axis)


GLOBAL_COORDINATE_SYSTEM = CoordinateSystem(origin=(0, 0),
                                            x_axis=(1, 0),
                                            y_axis=(0, 1))


@dataclasses.dataclass
class Vector_2D:
    vector: np.ndarray
    origin: np.ndarray = None


def calculate_rotation_angle(vector: np.ndarray,
                             coordinate_system: CoordinateSystem = GLOBAL_COORDINATE_SYSTEM) -> float:
    """
    Calculates the rotation angle of a given 2D vector relative to the x-axis of the provided coordinate system.

    :param vector: A 2D numpy array representing the vector (x, y)
    :param coordinate_system: A CoordinateSystem defining the x and y axes
    :return: The angle in radians between the vector and the x-axis
    """
    # Extract x-axis from the coordinate system
    x_axis = np.array(coordinate_system.x_axis)

    # Compute the angle using arctan2
    angle = np.arctan2(vector[1], vector[0])

    return angle


def fix_coordinate_axes(x, y, exact_axis='x'):
    """
    Adjusts the coordinate system so that the two input vectors are perpendicular,
    keeping one axis fixed.

    Parameters:
    x, y : array-like
        Input 2D vectors that define the coordinate system.
    exact_axis : str, optional
        Specifies which axis should remain unchanged ('x' or 'y'). Default is 'x'.

    Returns:
    tuple
        Rectangularized coordinate system as two perpendicular vectors.
    """
    x = np.array(x, dtype=np.float64)
    y = np.array(y, dtype=np.float64)

    if exact_axis == 'x':
        x_unit = x / np.linalg.norm(x)  # Normalize x
        y_proj = y - np.dot(y, x_unit) * x_unit  # Remove component along x
        y_rect = y_proj / np.linalg.norm(y_proj) * np.linalg.norm(y)  # Preserve magnitude
    elif exact_axis == 'y':
        y_unit = y / np.linalg.norm(y)  # Normalize y
        x_proj = x - np.dot(x, y_unit) * y_unit  # Remove component along y
        x_rect = x_proj / np.linalg.norm(x_proj) * np.linalg.norm(x)  # Preserve magnitude
    else:
        raise ValueError("exact_axis must be 'x' or 'y'")

    return (x, y_rect) if exact_axis == 'x' else (x_rect, y)


def rotate_coordinate_system(coord_system: CoordinateSystem, psi: float) -> CoordinateSystem:
    """
    Rotate a coordinate system by a given angle around the z-axis.

    :param coord_system: The coordinate system to rotate.
    :param psi: The rotation angle in radians.
    :return: A new CoordinateSystem object representing the rotated system.
    """
    # Rotation matrix for the z-axis
    rotation_matrix = np.array([
        [np.cos(psi), -np.sin(psi)],
        [np.sin(psi), np.cos(psi)]
    ])

    # Rotate the axes
    new_x_axis = rotation_matrix @ coord_system.x_axis
    new_y_axis = rotation_matrix @ coord_system.y_axis

    # Return the new coordinate system
    return CoordinateSystem(origin=coord_system.origin, x_axis=new_x_axis, y_axis=new_y_axis)


def translate_coordinate_system(coord_system: CoordinateSystem, translation: np.ndarray) -> CoordinateSystem:
    """
    Translate a coordinate system by a given vector.

    :param coord_system: The coordinate system to translate.
    :param translation: The translation vector in the reference frame.
    :return: A new CoordinateSystem object representing the translated system.
    """
    # Translate the origin
    new_origin = coord_system.origin + translation

    # Return the new coordinate system
    return CoordinateSystem(origin=new_origin, x_axis=coord_system.x_axis, y_axis=coord_system.y_axis)


def coordinate_system_from_3_points(origin: np.ndarray, point_x: np.ndarray, point_y: np.ndarray,
                                    exact_axis: str) -> CoordinateSystem:
    """
    Create a coordinate system from an origin and two measured points.

    Args:
        origin (np.ndarray): The origin point as a numpy array.
        point_x (np.ndarray): A point roughly along the x-axis.
        point_y (np.ndarray): A point roughly along the y-axis.
        exact_axis (str): Specifies which axis ('x' or 'y') should be exact.

    Returns:
        CoordinateSystem: The coordinate system with adjusted x and y axes.
    """
    origin = np.asarray(origin)
    point_x = np.asarray(point_x)
    point_y = np.asarray(point_y)

    # Compute raw vectors from origin to the points
    vector_x = point_x - origin
    vector_y = point_y - origin

    # Normalize the exact axis
    if exact_axis == 'x':
        x_axis = vector_x / np.linalg.norm(vector_x)
        # Project vector_y onto x_axis to remove its component along x_axis
        projection = np.dot(vector_y, x_axis) * x_axis
        adjusted_y = vector_y - projection
        y_axis = adjusted_y / np.linalg.norm(adjusted_y)
    elif exact_axis == 'y':
        y_axis = vector_y / np.linalg.norm(vector_y)
        # Project vector_x onto y_axis to remove its component along y_axis
        projection = np.dot(vector_x, y_axis) * y_axis
        adjusted_x = vector_x - projection
        x_axis = adjusted_x / np.linalg.norm(adjusted_x)
    else:
        raise ValueError("exact_axis must be 'x' or 'y'")

    return CoordinateSystem(origin=origin, x_axis=x_axis, y_axis=y_axis)


def get_rotation_between_coordinate_systems(system_from: CoordinateSystem, system_to: CoordinateSystem) -> float:
    """
    Calculate the rotation angle around the z-axis from one coordinate system to another.

    :param system_from: The initial coordinate system.
    :param system_to: The target coordinate system.
    :return: The rotation angle in radians.
    """
    # Normalize axes to ensure they are unit vectors
    from_x_normalized = system_from.x_axis / np.linalg.norm(system_from.x_axis)
    to_x_normalized = system_to.x_axis / np.linalg.norm(system_to.x_axis)

    # Calculate the angle between the x-axes of the two systems
    angle = np.arctan2(to_x_normalized[1], to_x_normalized[0]) - np.arctan2(from_x_normalized[1], from_x_normalized[0])

    # Normalize the angle to the range [-pi, pi]
    angle = (angle + np.pi) % (2 * np.pi) - np.pi

    return angle


def get_virtual_intersection_point(axis_1_point_1, axis_1_point_2, axis_2_point_1, axis_2_point_2):
    """
    Calculate the virtual intersection point of two lines defined by two sets of 3D points.

    Parameters:
    axis_1_point_1, axis_1_point_2: Tuple of floats (x, y, z) - two points defining the first line.
    axis_2_point_1, axis_2_point_2: Tuple of floats (x, y, z) - two points defining the second line.

    Returns:
    Tuple of floats (x, y, z) - the virtual intersection point.
    """
    # Convert input points to numpy arrays
    p1 = np.array(axis_1_point_1)
    p2 = np.array(axis_1_point_2)
    q1 = np.array(axis_2_point_1)
    q2 = np.array(axis_2_point_2)

    # Direction vectors of the two lines
    d1 = p2 - p1
    d2 = q2 - q1

    # Normalize direction vectors to avoid scaling issues
    d1 /= np.linalg.norm(d1)
    d2 /= np.linalg.norm(d2)

    # Construct matrices for least-squares solution
    A = np.stack([d1, -d2]).T
    b = q1 - p1

    # Solve the least-squares problem to find the closest points on the two lines
    t, s = np.linalg.lstsq(A, b, rcond=None)[0]

    # Closest points on the two lines
    closest_point_line_1 = p1 + t * d1
    closest_point_line_2 = q1 + s * d2

    # The virtual intersection point is the midpoint of these closest points
    virtual_intersection_point = (closest_point_line_1 + closest_point_line_2) / 2

    return tuple(virtual_intersection_point)


def vector_from_2_points(point1: (tuple, list, np.ndarray), point2: (tuple, list, np.ndarray)) -> np.ndarray:
    point1 = np.asarray(point1)
    point2 = np.asarray(point2)

    return point2 - point1


def rotate_vector(vector: np.ndarray, angle: float) -> np.ndarray:
    """
    Rotates a 2D vector by a given angle.

    Parameters:
    vector (np.ndarray): A 2D vector represented as a NumPy array [x, y].
    angle (float): The angle in radians by which to rotate the vector (counterclockwise).

    Returns:
    np.ndarray: The rotated 2D vector.
    """
    vector = np.asarray(vector)
    if vector.shape != (2,):
        raise ValueError("Input vector must be a 2D vector represented as a NumPy array of shape (2,).")

    # Rotation matrix
    rotation_matrix = np.array([
        [np.cos(angle), -np.sin(angle)],
        [np.sin(angle), np.cos(angle)]
    ])

    # Perform the rotation
    rotated_vector = np.dot(rotation_matrix, vector)

    return rotated_vector


def translate_point(point: (tuple, list, np.ndarray), translation: (tuple, list, np.ndarray)) -> np.ndarray:
    return np.asarray(point) + np.asarray(translation)


def get_point_in_coordinate_system(point: (tuple, list, np.ndarray),
                                   target_system: CoordinateSystem,
                                   source_system: CoordinateSystem = GLOBAL_COORDINATE_SYSTEM) -> np.ndarray:
    """
    Convert a point's coordinates from the source coordinate system to the target coordinate system.

    :param point: The coordinates of the point in the source coordinate system (tuple, list, or np.ndarray).
    :param target_system: The target coordinate system.
    :param source_system: The source coordinate system. Defaults to the global coordinate system.
    :return: The coordinates of the point in the target coordinate system.
    """
    # Ensure point is a numpy array
    point = np.array(point)

    # Get the transformation matrix for the source system to the global system
    source_to_global_matrix = np.column_stack((source_system.x_axis, source_system.y_axis))

    # Add the origin of the source system
    point_in_global = source_system.origin + source_to_global_matrix @ point

    # Get the transformation matrix for the global system to the target system
    global_to_target_matrix = np.linalg.inv(np.column_stack((target_system.x_axis, target_system.y_axis)))

    # Subtract the origin of the target system to find the point relative to it
    point_relative_to_target = point_in_global - target_system.origin

    # Transform the point into the target coordinate system
    point_in_target = global_to_target_matrix @ point_relative_to_target

    return point_in_target


def project_3d_to_2d(point):
    return np.array([point[0], point[1]])


def optitrack_to_2d(point):
    point = np.array([point[0], -point[2]])
    return point


def optitrack_2d_to_testbed_origin(point_optitrack):
    ...


def calculate_projection(line_start, line_end, point):
    """
    Projects a 2D point onto a line segment defined by two points.

    Parameters:
    line_start (tuple): (x, y) coordinates of the start of the line segment.
    line_end (tuple): (x, y) coordinates of the end of the line segment.
    point (tuple): (x, y) coordinates of the point to be projected.

    Returns:
    tuple: (x, y) coordinates of the projected point on the line.
    """
    # Convert to numpy arrays
    A = np.array(line_start)
    B = np.array(line_end)
    P = np.array(point)

    # Compute the line vector and point vector
    AB = B - A
    AP = P - A

    # Compute the projection scalar t
    t = np.dot(AP, AB) / np.dot(AB, AB)

    # Compute the projected point
    projection = A + t * AB

    return projection


def angle_between_two_vectors(vec1, vec2):
    """
    Calculates the angle in radians between two 2D vectors.

    Parameters:
    vec1 (tuple): (x, y) components of the first vector.
    vec2 (tuple): (x, y) components of the second vector.

    Returns:
    float: Angle in radians between the two vectors.
    """
    # Convert to numpy arrays
    v1 = np.array(vec1)
    v2 = np.array(vec2)

    # Compute the dot product and magnitudes
    dot_product = np.dot(v1, v2)
    magnitude_product = np.linalg.norm(v1) * np.linalg.norm(v2)

    # Compute the angle in radians
    angle = np.arccos(dot_product / magnitude_product)

    return angle


if __name__ == '__main__':
    coord_system_1 = rotate_coordinate_system(CoordinateSystem(origin=(1, 1),
                                                               x_axis=(1, 0),
                                                               y_axis=(0, 1)), psi=np.pi / 8)
    point_in_target = (0.5, 0.5)
    point_in_global = get_point_in_coordinate_system(point_in_target, target_system=GLOBAL_COORDINATE_SYSTEM,
                                                     source_system=coord_system_1)
    # psi = get_rotation_between_coordinate_systems(coord_system_1, GLOBAL_COORDINATE_SYSTEM)
    print(point_in_global)
    plot_2d(coordinate_systems={'global': GLOBAL_COORDINATE_SYSTEM, 'target': coord_system_1},
            points={'1': point_in_global},
            lines={('global', '1')},
            limits={'x': [-1, 3], 'y': [-1, 3]}
            , )
