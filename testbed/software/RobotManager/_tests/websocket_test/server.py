import time

from core.utils.network.network import getHostIP
from core.utils.websockets import WebsocketServer, WebsocketServerClient

PORT = 5006

if __name__ == '__main__':
    ip = getHostIP()
    server = WebsocketServer(ip, 5006, heartbeats=False)


    def on_new_client(client: WebsocketServerClient):

        message = {
            'type': 'set_params',
            'params': {
                'x': 3,
                'y': "HALLO"
            }
        }
        client.send(message)

        def on_message(msg, *args, **kwargs):
            print(msg)

        client.callbacks.message.register(on_message)


    server.callbacks.new_client.register(on_new_client)
    server.start()

    while True:
        time.sleep(1)
