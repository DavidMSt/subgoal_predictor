import time

from core.utils.websockets import WebsocketServer


def main():
    server = WebsocketServer(host='localhost', port=8000)
    server.start()

    data = {
        'groups': {
            'group1': {
                'points': {
                    'X': {
                        'x': -2,
                        'y': 2,
                        'color': [0, 0, 1]
                    }
                },
                'visionagents': {
                    'vagent1': {
                        'position': [10, 2],
                        'psi': 0,
                        'color': [0, 0.25, 0],
                        'vision_radius': 2,
                        'vision_fov': 1
                    }
                },
                'groups': {
                    'group1_2': {
                        'points': {
                            'X2': {
                                'x': -2,
                                'y': 5,
                                'color': [0, 1, 1]
                            },
                            'X3': {
                                'x': 2,
                                'y': 5,
                                'color': [0, 0, 0]
                            }
                        },
                        'lines': {
                            'xx': {
                                'start': '../vagent1',
                                'end': 'X3',
                            }
                        }

                    }
                }
            },
            'group3': {
                'points': {
                    'A': {
                        'x': -4,
                        'y': 2.0,
                        'color': [1, 0, 0]
                    },

                    'B': {
                        'x': 3.0,
                        'y': 4.0,
                        'color': [0, 1, 0],
                        'alpha': 0.5
                    }
                },
                'vectors': {
                    'vectorA': {
                        'vec': [1, 3],
                        'origin': [0, 0],
                        'color': [0, 0, 0]
                    },
                    'vectorB': {
                        'vec': [1, -2],
                        'origin': [-1, -1],
                        'color': [0, 1, 0]
                    }
                },
                'coordinate_systems': {
                    'CSA': {
                        'origin': [0, 0],
                        'ex': [1, 0],
                        'ey': [0, 1],
                    }
                },
                'lines': {
                    'AB': {
                        'start': 'B',
                        'end': 'A',
                    },
                    'AB2': {
                        'start': 'CSA',
                        'end': 'B',
                        'alpha': 0.1,
                    }
                },
                'agents': {
                    'agent1': {
                        'position': [-3, -3],
                        'psi': 3.141,
                        'color': [1, 0, 0],
                        'alpha': 0.5,
                        'text': "Hallo"
                    }
                },
                'rectangles' : {
                    'rect_mat': {
                        'mid': [0,0],
                        'x': 3,
                        'y': 3,
                        'fill': [0.9,0.9,0.9]
                    }
                },
                'circles': {
                    "circle1": {
                        "mid": [2, -2],
                        "diameter": 2,
                        "linecolor": [0, 0, 0],
                        'fill': [0.5, 1, 1],
                        'alpha': 0.5
                    }
                }
            }
        },


    }

    counter = 0

    while True:
        server.send(data)
        # data['points']['A']['x'] += 0.021

        # if counter == 100:
        #     data['points'].pop('B')
        # print("Sent")
        counter += 1
        time.sleep(0.1)


if __name__ == '__main__':
    main()
