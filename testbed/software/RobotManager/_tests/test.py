import numpy as np

from core.utils.orientation.orientation_3d import calculate_intersection

if __name__ == '__main__':
    x_axis_point_start = np.array([1, 0, 0])
    x_axis_point_end = np.array([2, 0, 0])
    y_axis_point_start = np.array([0, 1, 0])
    y_axis_point_end = np.array([0, 20, 0])

    origin = calculate_intersection(x_axis_point_start,
                                    x_axis_point_end,
                                    y_axis_point_start,
                                    y_axis_point_end)

    print(origin)