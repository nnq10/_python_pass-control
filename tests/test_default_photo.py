import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from app.services.default_photo import create_default_pass_photo, default_pass_photo_path, pass_photo_source


class DefaultPhotoTests(unittest.TestCase):
    def test_create_default_pass_photo_returns_square_image(self):
        image = create_default_pass_photo(size=300)

        self.assertEqual(image.mode, "RGB")
        self.assertEqual(image.size, (300, 300))

    def test_default_pass_photo_path_creates_asset(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch("app.services.default_photo.ASSETS_DIR", Path(tmp)):
                path = default_pass_photo_path()

                self.assertTrue(path.exists())
                self.assertEqual(path.name, "default_pass_photo.png")
                with Image.open(path) as image:
                    self.assertEqual(image.size, (900, 900))

    def test_pass_photo_source_prefers_existing_photo(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            photo = root / "person.jpg"
            Image.new("RGB", (10, 10), "white").save(photo)

            with patch("app.services.default_photo.ASSETS_DIR", root / "assets"):
                self.assertEqual(pass_photo_source(str(photo)), photo)
                self.assertEqual(pass_photo_source(None).name, "default_pass_photo.png")


if __name__ == "__main__":
    unittest.main()
