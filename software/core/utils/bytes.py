from datetime import datetime


def bytearray_to_string(data, pos=False):
    """

    :param data:
    :param pos:
    :return:
    """
    if isinstance(data, int):
        data = bytes([data])

    if pos:
        data = " ".join("0x{:02X}({:d})".format(b, i) for (i, b) in enumerate(data))
    else:
        data = " ".join("0x{:02X}".format(b) for b in data)

    return data


def print_byte_array(client_data, client_ip=None, pos=False):
    """
    print incoming data to console (used for debugging onl)
    :param pos: if true, add number of each byte, which makes debugging easier
    :param client_ip: ip of client
    :param client_data: data that has been sent
    :return: nothing
    """
    if pos:
        client_data = " ".join("0x{:02X}({:d})".format(b, i) for (i, b) in enumerate(client_data))
    else:
        client_data = " ".join("0x{:02X}".format(b) for b in client_data)
    time = datetime.now().strftime("%H:%M:%S:")
    if client_ip is None:
        string = "{}: {}".format(time, client_data)
    else:
        string = "{} from {}: {}".format(time, client_ip, client_data)
    print(string)
