import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from app.services.camera import CameraUnavailable, open_capture, save_camera_temp_image


class CameraTests(unittest.TestCase):
    def test_save_camera_temp_image_writes_jpeg(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch("app.services.camera.PHOTOS_DIR", Path(tmp)):
                path = Path(save_camera_temp_image(Image.new("RGB", (16, 16), "white")))

                self.assertTrue(path.exists())
                self.assertEqual(path.suffix.lower(), ".jpg")
                self.assertGreater(path.stat().st_size, 0)

    def test_open_capture_reports_missing_opencv(self):
        with patch.dict(sys.modules, {"cv2": None}):
            with self.assertRaises(CameraUnavailable):
                open_capture()


if __name__ == "__main__":
    unittest.main()
