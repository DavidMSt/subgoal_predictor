import time

from core.utils.network.network import getHostIP
from core.utils.websockets import WebsocketClient

if __name__ == '__main__':
    ip = getHostIP()
    client = WebsocketClient(ip, 5006)
    client.connect()


    def on_message(msg):
        print(msg)

        client.send({'response': [12,3,4,5,6]})


    # client.callbacks.message.register(on_message)
    client.events.message.on(on_message)

    client.callbacks.disconnected.register(lambda: print('disconnected'))

    while True:
        time.sleep(1)
