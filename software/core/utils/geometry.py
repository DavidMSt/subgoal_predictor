import math


def is_point_in_rotated_rect(height, width, E, theta, F, *, degrees=False, inclusive=True):
    """
    Return True if point F is inside the rectangle, else False.

    Conventions:
    - E is the midpoint of segment AB (one edge of the rectangle).
    - At theta = 0, AB is parallel to the x-axis.
    - Positive theta rotates the rectangle clockwise ("to the right").
    - The rectangle extends a distance `height` in the direction perpendicular to AB,
      obtained by rotating the AB direction 90° counterclockwise.
    - If `degrees=True`, interpret theta in degrees; otherwise radians.
    - If `inclusive=True`, points on the edges count as inside.
    """
    if degrees:
        theta = math.radians(theta)

    # Local basis vectors: u along AB (edge), v perpendicular into the rectangle interior
    u = (math.cos(theta), -math.sin(theta))  # clockwise rotation of the x-axis
    v = (math.sin(theta), math.cos(theta))  # u rotated +90° CCW

    # Vector from E to F
    dx = F[0] - E[0]
    dy = F[1] - E[1]

    # Project onto local axes
    proj_u = dx * u[0] + dy * u[1]
    proj_v = dx * v[0] + dy * v[1]

    # Half-width along u, height along +v from the AB edge
    hw = width / 2.0

    if inclusive:
        inside_u = (-hw <= proj_u <= hw)
        inside_v = (0.0 <= proj_v <= height)
    else:
        inside_u = (-hw < proj_u < hw)
        inside_v = (0.0 < proj_v < height)

    return inside_u and inside_v