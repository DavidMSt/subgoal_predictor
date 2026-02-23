from PIL import Image


def convert_image_to_bitmap(input_file, output_folder):

    # Load image, convert to 1-bit
    im = Image.open(input_file).convert('1')

    # Resize just in case
    im = im.resize((128, 32))

    output_file = f"{output_folder}/oled_image.c"
    # Save as raw bytes
    with open(output_file, "w") as f:
        f.write("const unsigned char my_bitmap[] = {\n")
        pixels = list(im.getdata())
        for y in range(0, 32):
            for x_byte in range(0, 128, 8):
                byte = 0
                for bit in range(8):
                    pixel_index = y * 128 + x_byte + bit
                    if pixels[pixel_index] == 0:  # black pixel
                        byte |= (1 << bit)
                f.write(f"0x{byte:02X},")
            f.write("\n")
        f.write("};\n")


if __name__ == '__main__':
    convert_image_to_bitmap('/Users/lehmann/Desktop/bilbo_bitmap.png', '/Users/lehmann/Desktop')