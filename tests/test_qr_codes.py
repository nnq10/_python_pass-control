import tempfile
import unittest
from pathlib import Path

from PIL import Image

from app.services.qr_codes import create_qr_image, save_qr_code


class QrCodeTests(unittest.TestCase):
    def test_create_qr_image_has_transparent_background(self):
        image = create_qr_image("EMP-TRANSPARENT")

        self.assertEqual(image.mode, "RGBA")
        self.assertEqual(image.getpixel((0, 0))[3], 0)
        self.assertEqual(image.getchannel("A").getextrema(), (0, 255))

    def test_save_qr_code_writes_transparent_png(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "qr.png"

            saved_path = save_qr_code("EMP-TRANSPARENT", path)

            self.assertEqual(saved_path, path)
            with Image.open(path) as image:
                self.assertEqual(image.mode, "RGBA")
                self.assertEqual(image.getpixel((0, 0))[3], 0)


if __name__ == "__main__":
    unittest.main()
