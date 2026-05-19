import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image, PdfParser

from app.services.pass_db import (PASS_TYPE_REGULAR, PASS_TYPE_SEMIANNUAL,
                                  PASS_TYPE_TEMPORARY, create_pass, init_db)
from app.services.print_passes import (A4_BATCH_CAPACITY, A4_PAGE_SIZE_PX,
                                       DEFAULT_TEXT_FONT,
                                       PRINT_PASS_SIZE_PX, a4_batch_positions,
                                       compose_a4_print_pages, compose_single_print_page, editable_template_config,
                                       ensure_temporary_stub_template, list_print_templates,
                                       print_batch_passes, print_image, render_print_pass, save_batch_print_pdf, save_print_pdf,
                                       save_print_png, save_template_choice,
                                       save_template_config, selected_template_for_profile,
                                       template_config_path, _fit_print_rect, _raise_if_printer_offline,
                                       _save_pdf_pages)


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

    def test_selected_template_for_profile_uses_keywords_and_saved_choice(self):
        with tempfile.TemporaryDirectory() as tmp:
            templates = Path(tmp)
            (templates / "month_card.png").write_bytes(b"png")
            (templates / "semiannual_card.png").write_bytes(b"png")
            (templates / "tmp_card.png").write_bytes(b"png")

            with patch("app.services.print_passes.TEMPLATES_DIR", templates):
                self.assertEqual(selected_template_for_profile(PASS_TYPE_REGULAR).name, "month_card.png")
                temporary_template = selected_template_for_profile(PASS_TYPE_TEMPORARY)
                self.assertEqual(temporary_template.name, "temporary_razovy_kpoop.png")
                self.assertTrue(temporary_template.exists())

                save_template_choice(PASS_TYPE_REGULAR, templates / "semiannual_card.png")

                self.assertEqual(selected_template_for_profile(PASS_TYPE_REGULAR).name, "semiannual_card.png")

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
            self.assertEqual(saved["fields"]["last_name"]["font"], DEFAULT_TEXT_FONT)

    def test_editable_template_config_keeps_custom_fields_clean(self):
        with tempfile.TemporaryDirectory() as tmp:
            template = Path(tmp) / "custom.png"
            Image.new("RGBA", (400, 240), (255, 255, 255, 255)).save(template)
            template.with_suffix(".json").write_text(
                json.dumps(
                    {
                        "base_size": [400, 240],
                        "qr": {"enabled": True, "x": 300, "y": 20, "size": 70},
                        "fields": {
                            "stub_name": {"source": "full_name", "x": 20, "y": 40, "size": 20}
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            config = editable_template_config(template)

            self.assertIn("stub_name", config["fields"])
            self.assertEqual(config["fields"]["stub_name"]["font"], DEFAULT_TEXT_FONT)
            self.assertNotIn("last_name", config["fields"])
            self.assertNotIn("first_name", config["fields"])
            self.assertNotIn("middle_name", config["fields"])

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

    def test_render_print_pass_can_repeat_source_fields_and_disable_qr(self):
        create_pass(
            self.db,
            {
                "qr_code": "TMP-DATA",
                "district": "Штаб",
                "unit": "Штаб",
                "rank": "Заявка начальника",
                "last_name": "Петров Петр Петрович",
                "issued_date": "2026-05-14",
                "days_count": 3,
                "pass_type": PASS_TYPE_TEMPORARY,
            },
        )
        with tempfile.TemporaryDirectory() as tmp:
            template = Path(tmp) / "temporary_razovy.png"
            Image.new("RGBA", (500, 220), (255, 255, 255, 255)).save(template)
            template.with_suffix(".json").write_text(
                json.dumps(
                    {
                        "base_size": [500, 220],
                        "qr": {"enabled": False},
                        "fields": {
                            "stub_name": {"source": "full_name", "x": 20, "y": 20, "size": 22},
                            "pass_name": {"source": "full_name", "x": 20, "y": 70, "size": 22},
                            "destination": {"source": "destination", "x": 20, "y": 120, "size": 22},
                            "basis": {"source": "basis", "x": 20, "y": 170, "size": 22},
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            image = render_print_pass(self.db, "TMP-DATA", template)

            has_text_pixel = any(
                image.getpixel((x, y)) == (0, 0, 0, 255)
                for y in range(image.height)
                for x in range(image.width)
            )
            qr_corner = image.crop((360, 20, 490, 150))
            has_qr_pixel = any(
                qr_corner.getpixel((x, y)) == (0, 0, 0, 255)
                for y in range(qr_corner.height)
                for x in range(qr_corner.width)
            )
            self.assertTrue(has_text_pixel)
            self.assertFalse(has_qr_pixel)

    def test_builtin_temporary_stub_template_is_created_on_demand(self):
        with tempfile.TemporaryDirectory() as tmp:
            templates = Path(tmp)

            with patch("app.services.print_passes.TEMPLATES_DIR", templates):
                template = ensure_temporary_stub_template()
                selected = selected_template_for_profile(PASS_TYPE_TEMPORARY)

            config = json.loads(template.with_suffix(".json").read_text(encoding="utf-8"))
            self.assertTrue(template.exists())
            self.assertEqual(selected.name, template.name)
            self.assertTrue(template.with_suffix(".json").exists())
            self.assertEqual(config["template_version"], 4)
            self.assertEqual(config["print_size_cm"], [20.0, 7.0])
            self.assertEqual(config["binding_margin_left_cm"], 1.5)
            self.assertEqual(config["fields"], {})
            self.assertFalse(config["qr"]["enabled"])
            self.assertEqual(len(config["qr_codes"]), 2)
            self.assertTrue(all(qr["background"] for qr in config["qr_codes"]))

    def test_builtin_temporary_stub_template_places_qr(self):
        create_pass(
            self.db,
            {
                "qr_code": "TMP-BUILTIN-QR",
                "district": "Штаб",
                "unit": "Штаб",
                "rank": "Заявка",
                "last_name": "Сидоров Сергей",
                "issued_date": "2026-05-14",
                "days_count": 2,
                "pass_type": PASS_TYPE_TEMPORARY,
            },
        )
        with tempfile.TemporaryDirectory() as tmp:
            templates = Path(tmp)

            with patch("app.services.print_passes.TEMPLATES_DIR", templates):
                template = ensure_temporary_stub_template()
                config = json.loads(template.with_suffix(".json").read_text(encoding="utf-8"))
                image = render_print_pass(self.db, "TMP-BUILTIN-QR", template)

            for qr in config["qr_codes"]:
                x, y, size = qr["x"], qr["y"], qr["size"]
                qr_area = image.crop((x, y, x + size, y + size))
                black_pixels = sum(
                    1
                    for py in range(qr_area.height)
                    for px in range(qr_area.width)
                    if qr_area.getpixel((px, py)) == (0, 0, 0, 255)
                )
                self.assertGreater(black_pixels, 1000)
            self.assertEqual(image.info["print_size_cm"], (20.0, 7.0))
            self.assertEqual(image.info["binding_margin_left_cm"], 1.5)

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
                custom_png = save_print_png(image, "EMP-PRINT", Path(tmp) / "desktop" / "custom.png")
                custom_pdf = save_print_pdf(image, "EMP-PRINT", Path(tmp) / "desktop" / "custom.pdf")

            self.assertTrue(png.exists())
            self.assertEqual(png.suffix, ".png")
            self.assertTrue(pdf.exists())
            self.assertEqual(pdf.suffix, ".pdf")
            self.assertTrue(custom_png.exists())
            self.assertTrue(custom_pdf.exists())

    def test_fit_print_rect_preserves_real_size_and_centers(self):
        rect = _fit_print_rect((300, 180), (1000, 800), (300, 300))

        self.assertEqual(rect, (350, 310, 300, 180))

    def test_offline_default_printer_is_reported_clearly(self):
        with patch("app.services.print_passes._printer_state", return_value={"attributes": 0x400, "status": 0, "jobs": 0}):
            with self.assertRaisesRegex(RuntimeError, "offline"):
                _raise_if_printer_offline("Test Printer")

    def test_print_image_uses_direct_windows_page_renderer(self):
        captured = {}

        def fake_print(pages, job_name):
            captured["pages"] = list(pages)
            captured["job_name"] = job_name
            return {"printer": "Test Printer", "pages": len(captured["pages"])}

        image = Image.new("RGBA", (300, 180), (255, 255, 255, 255))
        with patch("app.services.print_passes._print_windows_pages", side_effect=fake_print):
            result = print_image(image, "Test Job")

        self.assertEqual(result, {"printer": "Test Printer", "pages": 1})
        self.assertEqual(captured["job_name"], "Test Job")
        self.assertEqual(captured["pages"][0].size, (300, 180))

    def test_compose_a4_print_pages_uses_10x6_layout(self):
        images = [
            Image.new("RGBA", (300, 180), (index, 20, 30, 255))
            for index in range(1, A4_BATCH_CAPACITY + 2)
        ]

        pages = compose_a4_print_pages(images)
        positions = a4_batch_positions()

        self.assertEqual(len(pages), 2)
        self.assertEqual(len(positions), A4_BATCH_CAPACITY)
        self.assertEqual(pages[0].size, A4_PAGE_SIZE_PX)
        self.assertEqual(pages[1].size, A4_PAGE_SIZE_PX)
        self.assertEqual(PRINT_PASS_SIZE_PX, (1181, 709))
        self.assertEqual(pages[0].getpixel(positions[0]), (1, 20, 30))
        self.assertEqual(pages[0].getpixel(positions[-1]), (8, 20, 30))
        self.assertEqual(pages[1].getpixel(positions[0]), (9, 20, 30))

    def test_compose_a4_print_pages_uses_wider_temporary_layout(self):
        images = [
            Image.new("RGBA", (2000, 700), (index, 20, 30, 255))
            for index in range(1, 6)
        ]
        for image in images:
            image.info["print_size_cm"] = (20.0, 7.0)
            image.info["binding_margin_left_cm"] = 1.5

        pages = compose_a4_print_pages(images)

        pass_width, pass_height = 2303, 806
        margin_x = 177
        margin_y = 56
        third_row_y = margin_y + 2 * (pass_height + margin_y)

        self.assertEqual(len(pages), 2)
        self.assertEqual(pages[0].size, A4_PAGE_SIZE_PX)
        self.assertEqual(pages[0].getpixel((margin_x, margin_y)), (1, 20, 30))
        self.assertEqual(pages[0].getpixel((margin_x, third_row_y)), (3, 20, 30))
        self.assertEqual(pages[0].getpixel((margin_x, margin_y + 3 * (pass_height + margin_y))), (4, 20, 30))
        self.assertEqual(pages[1].getpixel((margin_x, margin_y)), (5, 20, 30))
        self.assertEqual(margin_x + pass_width, A4_PAGE_SIZE_PX[0])

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
                custom_path = root / "desktop" / "batch.pdf"
                pdf = save_batch_print_pdf(self.db, ["EMP-PRINT", "EMP-PRINT-2"], template, custom_path)

            self.assertTrue(pdf.exists())
            self.assertEqual(pdf, custom_path)

    def test_save_batch_print_pdf_streams_pages(self):
        calls = []

        def fake_render(_db, qr_code, _template):
            calls.append(qr_code)
            return Image.new("RGBA", (300, 180), (len(calls), 20, 30, 255))

        def fake_save(_path, pages):
            first_page = next(iter(pages))
            self.assertEqual(first_page.size, A4_PAGE_SIZE_PX)

        qr_codes = [f"TMP-{index:04d}" for index in range(A4_BATCH_CAPACITY + 5)]
        with tempfile.TemporaryDirectory() as tmp, \
             patch("app.services.print_passes.render_print_pass", side_effect=fake_render), \
             patch("app.services.print_passes._save_pdf_pages", side_effect=fake_save), \
             patch("app.services.print_passes._batch_output_path", return_value=Path(tmp) / "batch.pdf"):
            save_batch_print_pdf(self.db, qr_codes, Path("template.png"))

        self.assertEqual(calls, qr_codes[:A4_BATCH_CAPACITY])

    def test_print_batch_passes_streams_pages_to_windows_printer(self):
        calls = []

        def fake_render(_db, qr_code, _template):
            calls.append(qr_code)
            return Image.new("RGBA", (300, 180), (len(calls), 20, 30, 255))

        def fake_print(pages, job_name):
            first_page = next(iter(pages))
            self.assertEqual(first_page.size, A4_PAGE_SIZE_PX)
            return {"printer": "Test Printer", "pages": 1, "job": job_name}

        qr_codes = [f"TMP-{index:04d}" for index in range(A4_BATCH_CAPACITY + 5)]
        with patch("app.services.print_passes.render_print_pass", side_effect=fake_render), \
             patch("app.services.print_passes._print_windows_pages", side_effect=fake_print):
            result = print_batch_passes(self.db, qr_codes, Path("template.png"), "Batch Job")

        self.assertEqual(result["printer"], "Test Printer")
        self.assertEqual(result["job"], "Batch Job")
        self.assertEqual(calls, qr_codes[:A4_BATCH_CAPACITY])

    def test_save_pdf_pages_writes_single_trailer_document(self):
        pages = [
            Image.new("RGB", (80, 40), "white"),
            Image.new("RGB", (80, 40), "red"),
            Image.new("RGB", (80, 40), "blue"),
        ]

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "batch.pdf"
            _save_pdf_pages(path, pages)
            data = path.read_bytes()
            parser = PdfParser.PdfParser(filename=str(path), mode="rb")
            try:
                self.assertEqual(len(parser.pages), 3)
            finally:
                parser.close()

        self.assertEqual(data.count(b"\ntrailer\n"), 1)
        self.assertNotIn(b"/Prev", data)


if __name__ == "__main__":
    unittest.main()
