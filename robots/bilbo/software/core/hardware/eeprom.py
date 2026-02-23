import board


def write_bytes(eeprom_address, byte_address, data):
    if not (isinstance(data, (bytes, bytearray))):
        data = bytearray([data])

    i2c = board.I2C()

    buffer = bytearray([byte_address]) + data
    i2c.writeto(eeprom_address, buffer)


def read_bytes(eeprom_address, byte_address, num_bytes):
    i2c = board.I2C()

    buffer_read = bytearray([0x00]*num_bytes)
    i2c.writeto_then_readfrom(address=eeprom_address, buffer_out = bytes([byte_address]), buffer_in=buffer_read)

    if num_bytes == 1:
        return list(buffer_read)[0]
    else:
        return list(buffer_read)[:num_bytes]