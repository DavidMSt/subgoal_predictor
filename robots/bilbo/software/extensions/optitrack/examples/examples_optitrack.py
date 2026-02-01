import time
import math

from extensions.optitrack.optitrack import OptiTrack, RigidBodySample
from core.utils.websockets import WebsocketServer
from core.utils.orientation.orientation_2d import calculate_projection, angle_between_two_vectors

data = {}


def optitrack_callback(sample, *args, **kwargs):
    global data
    data = sample


def example_optitrack():
    optitrack = OptiTrack(server_address="127.0.0.1", local_address="127.0.0.1", multicast_address="239.255.42.99")
    optitrack.callbacks.sample.register(optitrack_callback)
    optitrack.start()

    server = WebsocketServer(host='localhost', port=8000)
    server.start()

    # time.sleep(1)
    # optitrack.natnetclient.sendCommand(command=optitrack.natnetclient.NAT_REQUEST_MODELDEF, commandStr="", )

    while True:

        if data is not None and 'frodo1' in data:
            plot_data = {
                'points': {

                },
                'lines': {},
                'coordinate_systems': {}
            }

            frodo_data: RigidBodySample = data['frodo1']
            marker_data = frodo_data.markers
            marker_data_raw = frodo_data.markers_raw

            for key, value in marker_data.items():
                plot_data['points'][key] = {
                    'x': value[0],
                    'y': value[1],
                }

            plot_data['points']['O'] = {
                'x': frodo_data.position[0],
                'y': frodo_data.position[1],
                'color': [0, 0, 0.8]
            }

            plot_data['coordinate_systems']['global'] = {
                'origin': [0, 0],
                'ex': [0.1, 0],
                'ey': [0, 0.1]
            }

            marker_2_2d = frodo_data.markers[2][0:2]
            marker_3_2d = frodo_data.markers[4][0:2]
            marker_5_2d = frodo_data.markers[3][0:2]

            # Calculate the projection of marker 5 onto the line formed by markers 2 and 3

            projection_of_marker_5 = calculate_projection(line_start=marker_2_2d, line_end=marker_3_2d, point=marker_5_2d)

            vector_23 = marker_3_2d - marker_2_2d
            vector_p5 = projection_of_marker_5 - marker_5_2d

            angle_radians = angle_between_two_vectors(vector_23, vector_p5)
            angle_degrees = math.degrees(angle_radians)



            #
            # # Add projection to plot_data
            plot_data['points']['P'] = {
                'x': projection_of_marker_5[0],
                'y': projection_of_marker_5[1],
                'color': [1, 0, 0]
            }
            plot_data['lines']['23'] = {
                'start': '2',
                'end': '4',
            }
            plot_data['lines']['5P'] = {
                'start': '3',
                'end': 'P',
            }

            server.send(plot_data)
        time.sleep(0.05)


if __name__ == '__main__':
    example_optitrack()
