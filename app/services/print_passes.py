import json
import os
import re
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

from app.core.paths import PRINTS_DIR, TEMPLATES_DIR, ensure_data_dirs
from app.services.default_photo import pass_photo_source
from app.services.pass_db import CI, PASS_TYPE_SEMIANNUAL, fetch_pass_by_qr
from app.services.qr_codes import create_qr_image


SUPPORTED_TEMPLATE_EXTENSIONS = {".png", ".jpg", ".jpeg"}
DEFAULT_DPI = 300
RETURN_PASS_TEMPLATE_CONFIG = {
    "base_size": [994, 598],
    "qr": {
        "x": "right",
        "y": 43,
        "size": 118,
        "margin": 32,
    },
    "fields": {
        "last_name": {"x": 445, "y": 315, "size": 28, "color": "#000000"},
        "first_name": {"x": 375, "y": 394, "size": 28, "color": "#000000"},
        "middle_name": {"x": 435, "y": 474, "size": 28, "color": "#000000"},
    },
    "photo": {
        "enabled": False,
        "x": 70,
        "y": 250,
        "width": 160,
        "height": 200,
        "shape": "rect",
    },
}
KNOWN_TEMPLATE_CONFIGS = {
    "propusk_vozvrat": RETURN_PASS_TEMPLATE_CONFIG,
    "propusk_return": RETURN_PASS_TEMPLATE_CONFIG,
    "return_pass": RETURN_PASS_TEMPLATE_CONFIG,
}
DEFAULT_FIELDS_CONFIG = {
    "last_name": {"x": 120, "y": 220, "size": 28, "color": "#000000"},
    "first_name": {"x": 120, "y": 270, "size": 28, "color": "#000000"},
    "middle_name": {"x": 120, "y": 320, "size": 28, "color": "#000000"},
}
DEFAULT_PHOTO_CONFIG = {
    "enabled": False,
    "x": 70,
    "y": 250,
    "width": 160,
    "height": 200,
    "shape": "rect",
}


def list_print_templates():
    ensure_data_dirs()
    return sorted(
        [path for path in TEMPLATES_DIR.iterdir() if path.is_file() and path.suffix.lower() in SUPPORTED_TEMPLATE_EXTENSIONS],
        key=lambda path: path.name.lower(),
    )


def template_config_path(template_path):
    return Path(template_path).with_suffix(".json")


def _safe_part(value):
    value = str(value or "").strip()
    value = re.sub(r"[^0-9A-Za-zА-Яа-яЁё_.-]+", "_", value)
    return value.strip("._-") or "pass"


def _output_path(qr_code, extension):
    ensure_data_dirs()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return PRINTS_DIR / f"{_safe_part(qr_code)}_{stamp}{extension}"


def _batch_output_path(count):
    ensure_data_dirs()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return PRINTS_DIR / f"batch_{count}_{stamp}.pdf"


def _full_name(row):
    return " ".join(filter(None, [row[CI["ln"]], row[CI["fn"]], row[CI["mn"]]]))


def _format_date(value):
    if not value:
        return ""
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").strftime("%d.%m.%Y")
    except ValueError:
        return str(value)


def _expires_date(row):
    issued = row[CI["issued"]]
    if not issued:
        return ""
    try:
        issued_date = datetime.strptime(str(issued)[:10], "%Y-%m-%d")
        return (issued_date + timedelta(days=int(row[CI["days"]] or 30))).strftime("%d.%m.%Y")
    except (TypeError, ValueError):
        return ""


def pass_fields(row):
    return {
        "qr_code": row[CI["qr"]] or "",
        "district": row[CI["district"]] or "",
        "unit": row[CI["unit"]] or "",
        "rank": row[CI["rank"]] or "",
        "last_name": row[CI["ln"]] or "",
        "first_name": row[CI["fn"]] or "",
        "middle_name": row[CI["mn"]] or "",
        "full_name": _full_name(row),
        "phone": row[CI["phone"]] or "",
        "issued_date": _format_date(row[CI["issued"]]),
        "expires_date": _expires_date(row),
        "days_count": str(row[CI["days"]] or 30),
    }


def _template_config(template_path):
    template_path = Path(template_path)
    config_path = template_config_path(template_path)
    if not config_path.exists():
        return deepcopy(KNOWN_TEMPLATE_CONFIGS.get(template_path.stem, {}))
    with open(config_path, encoding="utf-8") as file:
        return json.load(file)


def editable_template_config(template_path):
    template_path = Path(template_path)
    with Image.open(template_path) as image:
        width, height = image.size
    config = _template_config(template_path)
    config.setdefault("base_size", [width, height])
    config.setdefault(
        "qr",
        {
            "x": "right",
            "y": max(20, round(height * 0.06)),
            "size": max(100, round(min(width, height) * 0.2)),
            "margin": max(20, round(min(width, height) * 0.04)),
        },
    )
    fields = config.setdefault("fields", {})
    for name, options in DEFAULT_FIELDS_CONFIG.items():
        fields.setdefault(name, dict(options))
    config.setdefault("photo", dict(DEFAULT_PHOTO_CONFIG))
    return config


def save_template_config(template_path, config):
    config_path = template_config_path(template_path)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with open(config_path, "w", encoding="utf-8") as file:
        json.dump(config, file, ensure_ascii=False, indent=2)
    return config_path


def _scales(config, image_size):
    base_size = config.get("base_size") or []
    if len(base_size) != 2:
        return 1.0, 1.0, 1.0
    base_width, base_height = base_size
    if not base_width or not base_height:
        return 1.0, 1.0, 1.0
    scale_x = image_size[0] / base_width
    scale_y = image_size[1] / base_height
    return scale_x, scale_y, min(scale_x, scale_y)


def _scaled_int(value, scale, default):
    if value is None:
        return default
    try:
        return int(round(float(value) * scale))
    except (TypeError, ValueError):
        return default


def _layout_value(value, default, image_size, qr_size=0, axis="x", scale=1.0):
    if value is None:
        return default
    if isinstance(value, int):
        return int(round(value * scale))
    if isinstance(value, float):
        return int(round(value * scale))
    if value == "right":
        return image_size[0] - qr_size - default
    if value == "bottom":
        return image_size[1] - qr_size - default
    try:
        return int(round(float(value) * scale))
    except (TypeError, ValueError):
        return default


def _font(size, font_path=None):
    if font_path:
        try:
            return ImageFont.truetype(font_path, size)
        except OSError:
            pass
    for candidate in ("arial.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _color(value):
    if not value:
        return (0, 0, 0, 255)
    if isinstance(value, (list, tuple)):
        return tuple(value)
    value = str(value).lstrip("#")
    if len(value) == 6:
        return tuple(int(value[index:index + 2], 16) for index in (0, 2, 4)) + (255,)
    return (0, 0, 0, 255)


def _draw_configured_fields(image, config, row):
    fields = config.get("fields") or {}
    if not fields:
        return
    values = pass_fields(row)
    scale_x, scale_y, scale_min = _scales(config, image.size)
    draw = ImageDraw.Draw(image)
    for field_name, options in fields.items():
        text = values.get(field_name, "")
        if not text:
            continue
        size = _scaled_int(options.get("size"), scale_min, 32)
        draw.text(
            (_scaled_int(options.get("x"), scale_x, 0), _scaled_int(options.get("y"), scale_y, 0)),
            text,
            fill=_color(options.get("color")),
            font=_font(size, options.get("font")),
        )


def _photo_box(config, image_size):
    photo = config.get("photo") or {}
    scale_x, scale_y, _scale_min = _scales(config, image_size)
    width = _scaled_int(photo.get("width"), scale_x, DEFAULT_PHOTO_CONFIG["width"])
    height = _scaled_int(photo.get("height"), scale_y, DEFAULT_PHOTO_CONFIG["height"])
    x = _scaled_int(photo.get("x"), scale_x, DEFAULT_PHOTO_CONFIG["x"])
    y = _scaled_int(photo.get("y"), scale_y, DEFAULT_PHOTO_CONFIG["y"])
    return x, y, width, height


def _paste_photo(image, config, row):
    photo = config.get("photo") or {}
    if not photo.get("enabled"):
        return
    if row[CI["type"]] != PASS_TYPE_SEMIANNUAL:
        return
    source = pass_photo_source(row[CI["photo"]])
    if not source.exists():
        return

    x, y, width, height = _photo_box(config, image.size)
    if width <= 0 or height <= 0:
        return

    person = Image.open(source).convert("RGBA")
    person = ImageOps.fit(person, (width, height), method=Image.Resampling.LANCZOS)
    if photo.get("shape") == "circle":
        mask = Image.new("L", (width, height), 0)
        draw = ImageDraw.Draw(mask)
        draw.ellipse((0, 0, width - 1, height - 1), fill=255)
        person.putalpha(mask)
    image.alpha_composite(person, (x, y))


def render_print_pass(db, qr_code, template_path):
    row = fetch_pass_by_qr(db, qr_code)
    if not row:
        raise ValueError("pass not found")

    template_path = Path(template_path)
    config = _template_config(template_path)
    image = Image.open(template_path).convert("RGBA")
    scale_x, scale_y, scale_min = _scales(config, image.size)

    qr_config = config.get("qr") or {}
    default_margin = max(20, round(min(image.size) * 0.04))
    margin_x = _scaled_int(qr_config.get("margin_x", qr_config.get("margin")), scale_x, default_margin)
    margin_y = _scaled_int(qr_config.get("margin_y", qr_config.get("margin")), scale_y, default_margin)
    qr_size = _scaled_int(qr_config.get("size"), scale_min, max(120, round(min(image.size) * 0.22)))
    x = _layout_value(qr_config.get("x", "right"), margin_x, image.size, qr_size, "x", scale_x)
    y = _layout_value(qr_config.get("y"), margin_y, image.size, qr_size, "y", scale_y)

    qr_image = create_qr_image(qr_code).resize((qr_size, qr_size), Image.Resampling.NEAREST)
    image.alpha_composite(qr_image, (x, y))
    _paste_photo(image, config, row)
    _draw_configured_fields(image, config, row)
    return image


def save_print_png(image, qr_code):
    path = _output_path(qr_code, ".png")
    image.save(path, format="PNG")
    return path


def save_print_pdf(image, qr_code):
    path = _output_path(qr_code, ".pdf")
    background = Image.new("RGB", image.size, "white")
    background.paste(image, mask=image.getchannel("A"))
    background.save(path, "PDF", resolution=DEFAULT_DPI)
    return path


def _pdf_page(image):
    background = Image.new("RGB", image.size, "white")
    background.paste(image, mask=image.getchannel("A"))
    return background


def save_batch_print_pdf(db, qr_codes, template_path):
    qr_codes = list(qr_codes)
    if not qr_codes:
        raise ValueError("no passes selected")
    pages = [_pdf_page(render_print_pass(db, qr_code, template_path)) for qr_code in qr_codes]
    path = _batch_output_path(len(qr_codes))
    first, rest = pages[0], pages[1:]
    first.save(path, "PDF", resolution=DEFAULT_DPI, save_all=bool(rest), append_images=rest)
    return path


def print_file(path):
    if not hasattr(os, "startfile"):
        raise RuntimeError("Печать напрямую поддерживается только в Windows")
    os.startfile(str(path), "print")
