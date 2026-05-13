import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from app.services.pass_db import PASS_TYPE_SEMIANNUAL, create_pass, init_db
from app.services.print_passes import (editable_template_config, list_print_templates,
                                       render_print_pass, save_batch_print_pdf,
                                       save_print_pdf, save_print_png,
                                       save_template_config, template_config_path)


class PrintPassTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        init_db(self.db)
        create_pass(
            self.db,
            {
                "qr_code": "EMP-PRINT",
                "district": "Центральный",
                "unit": "12345",
                "last_name": "Иванов",
                "first_name": "Иван",
                "issued_date": "2026-05-08",
                "days_count": 30,
            },
        )

    def tearDown(self):
        self.db.close()

    def _template(self, root):
        template = root / "template.png"
        Image.new("RGBA", (300, 180), (12, 34, 56, 255)).save(template)
        template.with_suffix(".json").write_text(
            json.dumps({"qr": {"size": 80, "margin": 10}}, ensure_ascii=False),
            encoding="utf-8",
        )
        return template

    def test_list_print_templates_returns_supported_images(self):
        with tempfile.TemporaryDirectory() as tmp:
            templates = Path(tmp)
            (templates / "a.png").write_bytes(b"png")
            (templates / "b.jpg").write_bytes(b"jpg")
            (templates / "c.txt").write_text("skip", encoding="utf-8")

            with patch("app.services.print_passes.TEMPLATES_DIR", templates):
                names = [path.name for path in list_print_templates()]

            self.assertEqual(names, ["a.png", "b.jpg"])

    def test_editable_template_config_and_save_template_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            template = Path(tmp) / "template.png"
            Image.new("RGBA", (400, 240), (255, 255, 255, 255)).save(template)

            config = editable_template_config(template)
            config["qr"]["x"] = 260
            config["fields"]["last_name"]["x"] = 140
            config_path = save_template_config(template, config)

            self.assertEqual(config_path, template_config_path(template))
            saved = json.loads(config_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["base_size"], [400, 240])
            self.assertEqual(saved["qr"]["x"], 260)
            self.assertEqual(saved["fields"]["last_name"]["x"], 140)

    def test_render_print_pass_places_qr_over_template(self):
        with tempfile.TemporaryDirectory() as tmp:
            template = self._template(Path(tmp))

            image = render_print_pass(self.db, "EMP-PRINT", template)

            self.assertEqual(image.mode, "RGBA")
            self.assertEqual(image.getpixel((210, 10)), (12, 34, 56, 255))
            qr_area = image.crop((210, 10, 290, 90))
            has_black_pixel = False
            for y in range(qr_area.height):
                for x in range(qr_area.width):
                    if qr_area.getpixel((x, y)) == (0, 0, 0, 255):
                        has_black_pixel = True
                        break
                if has_black_pixel:
                    break
            self.assertTrue(has_black_pixel)

    def test_render_print_pass_places_photo_when_enabled(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            template = root / "template.png"
            photo = root / "person.png"
            Image.new("RGBA", (300, 180), (255, 255, 255, 255)).save(template)
            Image.new("RGBA", (60, 80), (10, 120, 200, 255)).save(photo)
            template.with_suffix(".json").write_text(
                json.dumps(
                    {
                        "base_size": [300, 180],
                        "qr": {"size": 50, "margin": 10},
                        "photo": {"enabled": True, "x": 20, "y": 30, "width": 60, "height": 80},
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            create_pass(
                self.db,
                {
                    "qr_code": "EMP-PHOTO",
                    "last_name": "Фото",
                    "issued_date": "2026-05-08",
                    "days_count": 180,
                    "photo_path": str(photo),
                    "pass_type": PASS_TYPE_SEMIANNUAL,
                },
            )

            image = render_print_pass(self.db, "EMP-PHOTO", template)

            self.assertEqual(image.getpixel((30, 40)), (10, 120, 200, 255))

    def test_render_print_pass_uses_default_photo_when_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            template = root / "template.png"
            Image.new("RGBA", (300, 180), (255, 255, 255, 255)).save(template)
            template.with_suffix(".json").write_text(
                json.dumps(
                    {
                        "base_size": [300, 180],
                        "qr": {"size": 50, "margin": 10},
                        "photo": {"enabled": True, "x": 20, "y": 30, "width": 60, "height": 80},
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            create_pass(
                self.db,
                {
                    "qr_code": "EMP-HALF-NO-PHOTO",
                    "last_name": "Полугодовой",
                    "issued_date": "2026-05-08",
                    "days_count": 180,
                    "pass_type": PASS_TYPE_SEMIANNUAL,
                },
            )

            with patch("app.services.default_photo.ASSETS_DIR", root / "assets"):
                image = render_print_pass(self.db, "EMP-HALF-NO-PHOTO", template)

            self.assertNotEqual(image.getpixel((50, 90)), (255, 255, 255, 255))

    def test_builtin_return_pass_profile_places_qr_in_circle_area(self):
        with tempfile.TemporaryDirectory() as tmp:
            template = Path(tmp) / "propusk_vozvrat.png"
            Image.new("RGBA", (994, 598), (250, 250, 220, 255)).save(template)

            image = render_print_pass(self.db, "EMP-PRINT", template)

            qr_area = image.crop((834, 43, 952, 161))
            self.assertEqual(image.getpixel((820, 30)), (250, 250, 220, 255))
            has_black_pixel = False
            for y in range(qr_area.height):
                for x in range(qr_area.width):
                    if qr_area.getpixel((x, y)) == (0, 0, 0, 255):
                        has_black_pixel = True
                        break
                if has_black_pixel:
                    break
            self.assertTrue(has_black_pixel)

    def test_save_print_outputs_png_and_pdf(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "prints"
            output_dir.mkdir()
            image = Image.new("RGBA", (300, 180), (255, 255, 255, 255))

            with patch("app.services.print_passes.PRINTS_DIR", output_dir):
                png = save_print_png(image, "EMP-PRINT")
                pdf = save_print_pdf(image, "EMP-PRINT")

            self.assertTrue(png.exists())
            self.assertEqual(png.suffix, ".png")
            self.assertTrue(pdf.exists())
            self.assertEqual(pdf.suffix, ".pdf")

    def test_save_batch_print_pdf_renders_selected_passes(self):
        create_pass(
            self.db,
            {
                "qr_code": "EMP-PRINT-2",
                "last_name": "Петров",
                "issued_date": "2026-05-08",
                "days_count": 30,
            },
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output_dir = root / "prints"
            output_dir.mkdir()
            template = root / "template.png"
            Image.new("RGBA", (300, 180), (255, 255, 255, 255)).save(template)

            with patch("app.services.print_passes.PRINTS_DIR", output_dir):
                pdf = save_batch_print_pdf(self.db, ["EMP-PRINT", "EMP-PRINT-2"], template)

            self.assertTrue(pdf.exists())
            self.assertTrue(pdf.name.startswith("batch_2_"))


if __name__ == "__main__":
    unittest.main()
