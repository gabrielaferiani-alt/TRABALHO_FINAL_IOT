import framebuf

class SSD1306(framebuf.FrameBuffer):
    def __init__(self, width, height):
        self.width = width
        self.height = height
        self.pages = height // 8
        self.buf = bytearray(self.pages * width)
        super().__init__(self.buf, width, height, framebuf.MONO_VLSB)
        self._init()

    def _init(self):
        for c in [
            0xAE, 0x20, 0x00, 0x40, 0xA1,
            0xA8, self.height - 1,
            0xC8, 0xD3, 0x00, 0xDA, 0x12,
            0xD5, 0x80, 0xD9, 0xF1, 0xDB, 0x30,
            0x81, 0xFF, 0xA4, 0xA6, 0x8D, 0x14, 0xAF
        ]:
            self.write_cmd(c)

    def show(self):
        self.write_cmd(0x21); self.write_cmd(0); self.write_cmd(self.width - 1)
        self.write_cmd(0x22); self.write_cmd(0); self.write_cmd(self.pages - 1)
        self.write_data(self.buf)

    def write_cmd(self, cmd): pass
    def write_data(self, buf): pass


class SSD1306_I2C(SSD1306):
    def __init__(self, width, height, i2c, addr=0x3c):
        self.i2c = i2c
        self.addr = addr
        super().__init__(width, height)

    def write_cmd(self, cmd):
        self.i2c.writeto(self.addr, bytes([0x80, cmd]))

    def write_data(self, buf):
        d = bytearray(len(buf) + 1)
        d[0] = 0x40
        d[1:] = buf
        self.i2c.writeto(self.addr, d)
