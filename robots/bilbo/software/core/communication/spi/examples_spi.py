import time

import board
import busio
import ctypes


def example_spi_simple():
    # spi = busio.SPI(board.SCK_1, MOSI=board.MOSI_1, MISO=board.MISO_1)

    spi = board.SPI()
    while not spi.try_lock():
        pass
    spi.configure(baudrate=40000000)

    data = []
    for i in range(0, 100):
        data.append(i + 99)

    data2 = [0] * 20000

    # spi.write(data, start=0, end=10)
    time1 = time.time()
    spi.readinto(data2, start=0, end=5000, write_value=0)
    pass
    time2 = time.time()
    # spi.write_readinto(buffer_out=data, buffer_in=data2, out_start=0, out_end=9, in_start=0, in_end=9)
    print(f"Time: {1000 * (time2 - time1)} ms")
    print(data2[0:20])
    pass


def example_spi_write_trajectory():
    spi = board.SPI()
    while not spi.try_lock():
        pass
    spi.configure(baudrate=40000000)

    class trajectory_input(ctypes.Structure):
        _fields_ = [("index", ctypes.c_uint32), ("u1", ctypes.c_float), ("u2", ctypes.c_float)]

    input_array = []
    input_bytearray = bytearray()
    for i in range(0, 10):
        input_array.append(trajectory_input(i, 0.1 * i, -0.1 * i))

    for input in input_array:
        input_bytearray = input_bytearray + bytearray(input)

    #
    data_rx_cmd = [0] * 4
    data_tx_cmd = [0x02, 0x00, 0x00, 0x0A]
    spi.write_readinto(data_tx_cmd, data_rx_cmd, 0, 4, 0, 4)
    time.sleep(0.01)
    spi.write(input_bytearray, start=0, end=len(input_bytearray))
    # print(data_rx)


def example_read_sample_buffer():
    class sample_general(ctypes.Structure):
        _fields_ = [("tick", ctypes.c_uint32)]

    class twipr_gyr_data(ctypes.Structure):
        _fields_ = [("x", ctypes.c_float), ("y", ctypes.c_float), ("z", ctypes.c_float)]

    class twipr_acc_data(ctypes.Structure):
        _fields_ = [("x", ctypes.c_float), ("y", ctypes.c_float), ("z", ctypes.c_float)]

    class twipr_sensor_data(ctypes.Structure):
        _fields_ = [("speed_left", ctypes.c_float), ("speed_right", ctypes.c_float), ("acc", twipr_acc_data),
                    ("gyr", twipr_gyr_data)]

    class sample_sensors(ctypes.Structure):
        _fields_ = [("sensor_data", twipr_sensor_data)]

    class twipr_estimation_state(ctypes.Structure):
        _fields_ = [("v", ctypes.c_float), ("theta", ctypes.c_float), ("theta_dot", ctypes.c_float),
                    ("psi", ctypes.c_float), ("psi_dot", ctypes.c_float)]

    class sample_estimation(ctypes.Structure):
        _fields_ = [('state', twipr_estimation_state)]

    class twipr_control_input(ctypes.Structure):
        _fields_ = [("u1", ctypes.c_float), ("u2", ctypes.c_float)]

    class twipr_control_output(ctypes.Structure):
        _fields_ = [("u_left", ctypes.c_float), ("u_right", ctypes.c_float)]

    class sample_control(ctypes.Structure):
        _fields_ = [('status', ctypes.c_int8), ('mode', ctypes.c_int8), ("input", twipr_control_input),
                    ("output", twipr_control_output), ("tick", ctypes.c_uint32)]

    class twipr_sample(ctypes.Structure):
        _fields_ = [("general", sample_general), ("control", sample_control), ("estimation", sample_estimation),
                    ("sensors", sample_sensors)]

    spi = board.SPI()
    while not spi.try_lock():
        pass
    spi.configure(baudrate=40000000)

    data_rx_cmd = [0] * 4
    data_tx_cmd = [0x01, 0x00, 0x00, 0x0A]
    spi.write_readinto(data_tx_cmd, data_rx_cmd, 0, 4, 0, 4)
    time.sleep(0.01)

    data_rx_bytes = bytearray(800)

    spi.readinto(data_rx_bytes, start=0, end=80 * 10, write_value=0)

    samples = []
    for i in range(0, 10):
        samples.append(twipr_sample.from_buffer_copy(data_rx_bytes[i*80:(i+1)*80]))

    print(data_rx_bytes)
    pass


if __name__ == '__main__':
    # example_spi_simple()
    # example_spi_write_trajectory()
    example_read_sample_buffer()
