import json
import os
import re
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

from app.core.paths import PRINTS_DIR, TEMPLATES_DIR, ensure_data_dirs
from app.services.default_photo import pass_photo_source
from app.services.pass_db import (CI, PASS_TYPE_REGULAR, PASS_TYPE_SEMIANNUAL,
                                  PASS_TYPE_TEMPORARY, fetch_pass_by_qr)
from app.services.qr_codes import create_qr_image


SUPPORTED_TEMPLATE_EXTENSIONS = {".png", ".jpg", ".jpeg"}
DEFAULT_DPI = 300
CM_PER_INCH = 2.54
A4_SIZE_CM = (21.0, 29.7)
PRINT_PASS_SIZE_CM = (10.0, 6.0)
A4_BATCH_COLUMNS = 2
A4_BATCH_ROWS = 4
A4_BATCH_CAPACITY = A4_BATCH_COLUMNS * A4_BATCH_ROWS
TEMPORARY_STUB_PRINT_SIZE_CM = (20.0, 7.0)
TEMPORARY_STUB_BINDING_MARGIN_CM = 1.5
TEMPORARY_STUB_TEMPLATE_VERSION = 4


def _cm_to_px(value, dpi=DEFAULT_DPI):
    return int(round(float(value) / CM_PER_INCH * dpi))


A4_PAGE_SIZE_PX = tuple(_cm_to_px(value) for value in A4_SIZE_CM)
A4_LANDSCAPE_PAGE_SIZE_PX = tuple(_cm_to_px(value) for value in reversed(A4_SIZE_CM))
PRINT_PASS_SIZE_PX = tuple(_cm_to_px(value) for value in PRINT_PASS_SIZE_CM)
TEMPLATE_PROFILE_KEYWORDS = {
    PASS_TYPE_TEMPORARY: ("tmp", "temp", "temporary", "one", "once", "1-10", "однораз", "разов"),
    PASS_TYPE_REGULAR: ("regular", "month", "monthly", "30", "времен", "месяц"),
    PASS_TYPE_SEMIANNUAL: ("semi", "half", "halfyear", "180", "6", "полугод"),
}
TEMPORARY_STUB_TEMPLATE_NAME = "temporary_razovy_kpoop.png"
TEMPORARY_STUB_CONFIG_NAME = "temporary_razovy_kpoop.json"
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


def _draw_line(draw, xy, fill=(0, 0, 0, 255), width=2):
    draw.line(xy, fill=fill, width=width)


def _draw_center(draw, xy, text, font, fill=(0, 0, 0, 255)):
    bbox = draw.textbbox((0, 0), text, font=font)
    x, y = xy
    draw.text((x - (bbox[2] - bbox[0]) / 2, y), text, fill=fill, font=font)


def _temporary_stub_template_config():
    return {
        "template_version": TEMPORARY_STUB_TEMPLATE_VERSION,
        "base_size": [2000, 700],
        "print_size_cm": list(TEMPORARY_STUB_PRINT_SIZE_CM),
        "binding_margin_left_cm": TEMPORARY_STUB_BINDING_MARGIN_CM,
        "qr": {"enabled": False},
        "qr_codes": [
            {
                "title": "QR корешок",
                "x": 760,
                "y": 80,
                "size": 185,
                "background": True,
                "background_padding": 8,
            },
            {
                "title": "QR пропуск",
                "x": 1760,
                "y": 80,
                "size": 185,
                "background": True,
                "background_padding": 8,
            },
        ],
        "fields": {},
        "photo": dict(DEFAULT_PHOTO_CONFIG),
    }


def _create_temporary_stub_template(path):
    width, height = 2000, 700
    image = Image.new("RGBA", (width, height), "white")
    draw = ImageDraw.Draw(image)
    black = (0, 0, 0, 255)
    title_font = _font(42)
    text_font = _font(24)
    small_font = _font(17)

    for offset, line_width in [(8, 4), (18, 3), (28, 2)]:
        draw.rectangle((offset, offset, width - offset, height - offset), outline=black, width=line_width)
    _draw_line(draw, ((1000, 28), (1000, height - 28)), black, 4)
    _draw_line(draw, ((1014, 28), (1014, height - 28)), black, 2)
    draw.rectangle((32, 32, 988, height - 32), outline=black, width=3)
    draw.rectangle((1028, 32, width - 32, height - 32), outline=black, width=3)

    draw.text((54, 72), "522 ЦПООП  «___»________________20__ г.", fill=black, font=text_font)
    _draw_center(draw, (500, 140), "Корешок", title_font, black)
    _draw_center(draw, (500, 192), "разового пропуска №", title_font, black)
    draw.text((54, 318), "Выдан", fill=black, font=text_font)
    _draw_line(draw, ((150, 342), (940, 342)), black, 2)
    _draw_center(draw, (545, 350), "(кому)", small_font, black)
    draw.text((54, 398), "Роспись в получении", fill=black, font=text_font)
    _draw_line(draw, ((330, 422), (940, 422)), black, 2)
    draw.text((54, 534), "Выдал", fill=black, font=text_font)
    _draw_line(draw, ((150, 558), (940, 558)), black, 2)
    _draw_center(draw, (545, 566), "(подпись дежурного по КПП)", small_font, black)

    draw.text((1052, 72), "522 ЦПООП  «___»________________20__ г.", fill=black, font=text_font)
    _draw_center(draw, (1500, 140), "Разовый пропуск №", title_font, black)
    draw.text((1052, 260), "Разрешается пройти", fill=black, font=text_font)
    _draw_line(draw, ((1295, 284), (1940, 284)), black, 2)
    _draw_center(draw, (1617, 292), "(кому)", small_font, black)
    draw.text((1052, 348), "в", fill=black, font=text_font)
    _draw_line(draw, ((1094, 372), (1940, 372)), black, 2)
    draw.text((1052, 394), "из", fill=black, font=text_font)
    _draw_center(draw, (1517, 380), "(куда, и кому)", small_font, black)
    _draw_line(draw, ((1094, 462), (1940, 462)), black, 2)
    _draw_center(draw, (1517, 470), "(с ним следует)", small_font, black)
    draw.text((1052, 522), "Основание", fill=black, font=text_font)
    _draw_line(draw, ((1218, 546), (1940, 546)), black, 2)
    draw.text((1052, 594), "Дежурный по КПП", fill=black, font=text_font)
    _draw_line(draw, ((1315, 618), (1940, 618)), black, 2)
    _draw_center(draw, (1627, 626), "(подпись)", small_font, black)

    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format="PNG")


def ensure_temporary_stub_template():
    ensure_data_dirs()
    template_path = TEMPLATES_DIR / TEMPORARY_STUB_TEMPLATE_NAME
    config_path = TEMPLATES_DIR / TEMPORARY_STUB_CONFIG_NAME
    default_config = _temporary_stub_template_config()
    default_size = tuple(default_config["base_size"])
    reset_template = not template_path.exists()
    if template_path.exists():
        try:
            with Image.open(template_path) as image:
                reset_template = image.size != default_size
        except OSError:
            reset_template = True
    if reset_template:
        _create_temporary_stub_template(template_path)
    if not config_path.exists():
        with open(config_path, "w", encoding="utf-8") as file:
            json.dump(default_config, file, ensure_ascii=False, indent=2)
    else:
        try:
            with open(config_path, encoding="utf-8") as file:
                config = json.load(file)
        except (OSError, ValueError):
            config = {}
        if config.get("template_version") != TEMPORARY_STUB_TEMPLATE_VERSION:
            config = deepcopy(default_config)
            changed = True
        else:
            changed = False
        for key in ("template_version", "base_size", "print_size_cm", "binding_margin_left_cm", "photo"):
            if key not in config:
                config[key] = default_config[key]
                changed = True
        if config.get("qr") != default_config["qr"]:
            config["qr"] = deepcopy(default_config["qr"])
            changed = True
        if not isinstance(config.get("qr_codes"), list) or len(config["qr_codes"]) < 2:
            config["qr_codes"] = deepcopy(default_config["qr_codes"])
            changed = True
        if config.get("fields"):
            config["fields"] = {}
            changed = True
        if changed:
            with open(config_path, "w", encoding="utf-8") as file:
                json.dump(config, file, ensure_ascii=False, indent=2)
    return template_path


def list_print_templates():
    ensure_data_dirs()
    return sorted(
        [path for path in TEMPLATES_DIR.iterdir() if path.is_file() and path.suffix.lower() in SUPPORTED_TEMPLATE_EXTENSIONS],
        key=lambda path: path.name.lower(),
    )


def template_choices_path():
    return TEMPLATES_DIR / "_template_choices.json"


def _template_choice_key(profile):
    return str(profile or "default")


def _template_choices():
    ensure_data_dirs()
    choices_path = template_choices_path()
    if not choices_path.exists():
        return {}
    try:
        with open(choices_path, encoding="utf-8") as file:
            data = json.load(file)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save_template_choice(profile, template_path):
    ensure_data_dirs()
    choices = _template_choices()
    choices[_template_choice_key(profile)] = Path(template_path).name
    choices_path = template_choices_path()
    choices_path.parent.mkdir(parents=True, exist_ok=True)
    with open(choices_path, "w", encoding="utf-8") as file:
        json.dump(choices, file, ensure_ascii=False, indent=2)
    return choices_path


def selected_template_for_profile(profile):
    if profile == PASS_TYPE_TEMPORARY:
        return ensure_temporary_stub_template()

    templates = list_print_templates()

    saved_name = _template_choices().get(_template_choice_key(profile))
    if saved_name:
        for template in templates:
            if template.name == saved_name:
                return template

    keywords = TEMPLATE_PROFILE_KEYWORDS.get(profile, ())
    for template in templates:
        name = template.stem.lower()
        if any(keyword in name for keyword in keywords):
            return template

    if not templates:
        return None

    return templates[0]


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


def _date_parts(value):
    try:
        parsed = datetime.strptime(str(value or "")[:10], "%Y-%m-%d")
    except ValueError:
        return "", "", "", ""
    return (
        f"{parsed.day:02d}",
        f"{parsed.month:02d}",
        f"{parsed.year}",
        f"{parsed.year % 100:02d}",
    )


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
    issued_day, issued_month, issued_year, issued_year_short = _date_parts(row[CI["issued"]])
    district = row[CI["district"]] or ""
    unit = row[CI["unit"]] or ""
    destination = unit or district
    if district and unit and district != unit:
        destination = f"{district}, {unit}"
    return {
        "qr_code": row[CI["qr"]] or "",
        "district": district,
        "unit": unit,
        "destination": destination,
        "basis": row[CI["rank"]] or "",
        "rank": row[CI["rank"]] or "",
        "last_name": row[CI["ln"]] or "",
        "first_name": row[CI["fn"]] or "",
        "middle_name": row[CI["mn"]] or "",
        "full_name": _full_name(row),
        "phone": row[CI["phone"]] or "",
        "issued_date": _format_date(row[CI["issued"]]),
        "issued_day": issued_day,
        "issued_month": issued_month,
        "issued_year": issued_year,
        "issued_year_short": issued_year_short,
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
    has_fields_config = "fields" in config
    fields = config.setdefault("fields", {})
    if not has_fields_config:
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


def _print_size_cm(config):
    raw = config.get("print_size_cm")
    if not isinstance(raw, (list, tuple)) or len(raw) != 2:
        return None
    try:
        width, height = float(raw[0]), float(raw[1])
    except (TypeError, ValueError):
        return None
    if width <= 0 or height <= 0:
        return None
    return width, height


def _image_print_size_cm(image):
    raw = image.info.get("print_size_cm")
    if not isinstance(raw, (list, tuple)) or len(raw) != 2:
        return None
    try:
        width, height = float(raw[0]), float(raw[1])
    except (TypeError, ValueError):
        return None
    if width <= 0 or height <= 0:
        return None
    return width, height


def _binding_margin_left_cm(config):
    try:
        value = float(config.get("binding_margin_left_cm") or 0)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, value)


def _image_binding_margin_left_cm(image):
    try:
        value = float(image.info.get("binding_margin_left_cm") or 0)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, value)


def _print_size_px_from_cm(size_cm):
    return tuple(_cm_to_px(value) for value in size_cm)


def _image_pdf_size_px(image):
    size_cm = _image_print_size_cm(image)
    return _print_size_px_from_cm(size_cm) if size_cm else image.size


def _image_batch_size_px(image):
    size_cm = _image_print_size_cm(image)
    return _print_size_px_from_cm(size_cm) if size_cm else PRINT_PASS_SIZE_PX


def _image_binding_margin_left_px(image):
    return _cm_to_px(_image_binding_margin_left_cm(image))


def _a4_page_size_for_pass(pass_size_px, binding_margin_left_px=0):
    if binding_margin_left_px:
        return A4_PAGE_SIZE_PX
    portrait_width, portrait_height = A4_PAGE_SIZE_PX
    landscape_width, landscape_height = A4_LANDSCAPE_PAGE_SIZE_PX
    required_width = pass_size_px[0] + binding_margin_left_px
    if required_width > portrait_width and required_width <= landscape_width:
        return A4_LANDSCAPE_PAGE_SIZE_PX
    if required_width > portrait_width and landscape_width > portrait_width:
        return A4_LANDSCAPE_PAGE_SIZE_PX
    return A4_PAGE_SIZE_PX


def _fit_count(total, item):
    count = max(1, total // item)
    next_count = count + 1
    overflow = next_count * item - total
    if 0 < overflow <= max(2, next_count):
        return next_count
    return count


def _fit_pass_size_to_page(pass_size_px, page_size_px, binding_margin_left_px=0):
    pass_width, pass_height = pass_size_px
    page_width, page_height = page_size_px
    available_width = max(1, page_width - binding_margin_left_px)
    scale = min(1.0, available_width / pass_width, page_height / pass_height)
    return max(1, round(pass_width * scale)), max(1, round(pass_height * scale))


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
        text = values.get(options.get("source", field_name), "")
        if not text:
            continue
        size = _scaled_int(options.get("size"), scale_min, 32)
        font = _font(size, options.get("font"))
        max_width = _scaled_int(options.get("max_width"), scale_x, 0)
        min_size = _scaled_int(options.get("min_size"), scale_min, max(12, round(size * 0.72)))
        while max_width and size > min_size and draw.textbbox((0, 0), text, font=font)[2] > max_width:
            size -= 1
            font = _font(size, options.get("font"))
        draw.text(
            (_scaled_int(options.get("x"), scale_x, 0), _scaled_int(options.get("y"), scale_y, 0)),
            text,
            fill=_color(options.get("color")),
            font=font,
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


def _qr_configs(config):
    qr_codes = config.get("qr_codes")
    if isinstance(qr_codes, list) and qr_codes:
        return [qr for qr in qr_codes if isinstance(qr, dict) and qr.get("enabled", True)]
    qr = config.get("qr") or {}
    return [qr] if qr.get("enabled", True) else []


def _paste_qr(image, config, qr_config, qr_code):
    scale_x, scale_y, scale_min = _scales(config, image.size)
    default_margin = max(20, round(min(image.size) * 0.04))
    margin_x = _scaled_int(qr_config.get("margin_x", qr_config.get("margin")), scale_x, default_margin)
    margin_y = _scaled_int(qr_config.get("margin_y", qr_config.get("margin")), scale_y, default_margin)
    qr_size = _scaled_int(qr_config.get("size"), scale_min, max(120, round(min(image.size) * 0.22)))
    x = _layout_value(qr_config.get("x", "right"), margin_x, image.size, qr_size, "x", scale_x)
    y = _layout_value(qr_config.get("y"), margin_y, image.size, qr_size, "y", scale_y)

    if qr_config.get("background"):
        padding = _scaled_int(qr_config.get("background_padding"), scale_min, 0)
        draw = ImageDraw.Draw(image)
        draw.rectangle(
            (
                max(0, x - padding),
                max(0, y - padding),
                min(image.width, x + qr_size + padding),
                min(image.height, y + qr_size + padding),
            ),
            fill=(255, 255, 255, 255),
        )
    qr_image = create_qr_image(qr_code).resize((qr_size, qr_size), Image.Resampling.NEAREST)
    image.alpha_composite(qr_image, (x, y))


def render_print_pass(db, qr_code, template_path):
    row = fetch_pass_by_qr(db, qr_code)
    if not row:
        raise ValueError("pass not found")

    template_path = Path(template_path)
    config = _template_config(template_path)
    image = Image.open(template_path).convert("RGBA")
    for qr_config in _qr_configs(config):
        _paste_qr(image, config, qr_config, qr_code)
    _paste_photo(image, config, row)
    _draw_configured_fields(image, config, row)
    print_size_cm = _print_size_cm(config)
    if print_size_cm:
        image.info["print_size_cm"] = print_size_cm
    binding_margin_left_cm = _binding_margin_left_cm(config)
    if binding_margin_left_cm:
        image.info["binding_margin_left_cm"] = binding_margin_left_cm
    return image


def save_print_png(image, qr_code):
    path = _output_path(qr_code, ".png")
    image.save(path, format="PNG")
    return path


def save_print_pdf(image, qr_code):
    path = _output_path(qr_code, ".pdf")
    page_size = _image_pdf_size_px(image)
    binding_margin_left_px = _image_binding_margin_left_px(image)
    if binding_margin_left_px:
        paper_size = _a4_page_size_for_pass(page_size, binding_margin_left_px)
        layout_size = _fit_pass_size_to_page(page_size, paper_size, binding_margin_left_px)
        positions = a4_batch_positions_for_size(layout_size, paper_size, binding_margin_left_px)
        background = Image.new("RGB", paper_size, "white")
        background.paste(_print_sized_pass(image, layout_size), positions[0])
    else:
        background = _print_sized_pass(image, page_size) if page_size != image.size else _pdf_page(image)
    background.save(path, "PDF", resolution=DEFAULT_DPI)
    return path


def _pdf_page(image):
    background = Image.new("RGB", image.size, "white")
    if image.mode == "RGBA":
        background.paste(image, mask=image.getchannel("A"))
    else:
        background.paste(image.convert("RGB"))
    return background


def a4_batch_positions_for_size(pass_size_px, page_size_px=None, binding_margin_left_px=0):
    page_width, page_height = page_size_px or A4_PAGE_SIZE_PX
    pass_width, pass_height = pass_size_px
    available_width = max(1, page_width - binding_margin_left_px)
    columns = _fit_count(available_width, pass_width)
    rows = _fit_count(page_height, pass_height)
    margin_x = binding_margin_left_px if binding_margin_left_px else max(0, (page_width - columns * pass_width) // 2)
    margin_y = max(0, (page_height - rows * pass_height) // (rows + 1))
    positions = []
    for row in range(rows):
        y = margin_y + row * (pass_height + margin_y)
        for col in range(columns):
            x = margin_x + col * pass_width
            positions.append((x, y))
    return positions


def a4_batch_positions():
    return a4_batch_positions_for_size(PRINT_PASS_SIZE_PX)


def _print_sized_pass(image, pass_size_px=None):
    pass_size_px = pass_size_px or PRINT_PASS_SIZE_PX
    source = _pdf_page(image)
    source = ImageOps.contain(source, pass_size_px, Image.Resampling.LANCZOS)
    tile = Image.new("RGB", pass_size_px, "white")
    x = (pass_size_px[0] - source.size[0]) // 2
    y = (pass_size_px[1] - source.size[1]) // 2
    tile.paste(source, (x, y))
    return tile


def _paste_clipped(page, tile, position):
    x, y = position
    width, height = tile.size
    paste_width = min(width, page.width - x)
    paste_height = min(height, page.height - y)
    if paste_width <= 0 or paste_height <= 0:
        return
    if paste_width != width or paste_height != height:
        tile = tile.crop((0, 0, paste_width, paste_height))
    page.paste(tile, (x, y))


def compose_a4_print_pages(images):
    images = list(images)
    if not images:
        raise ValueError("no passes selected")
    pass_size_px = _image_batch_size_px(images[0])
    binding_margin_left_px = _image_binding_margin_left_px(images[0])
    page_size_px = _a4_page_size_for_pass(pass_size_px, binding_margin_left_px)
    layout_size_px = _fit_pass_size_to_page(pass_size_px, page_size_px, binding_margin_left_px)
    positions = a4_batch_positions_for_size(layout_size_px, page_size_px, binding_margin_left_px)
    capacity = len(positions)
    pages = []
    for start in range(0, len(images), capacity):
        page = Image.new("RGB", page_size_px, "white")
        for image, position in zip(images[start:start + capacity], positions):
            _paste_clipped(page, _print_sized_pass(image, layout_size_px), position)
        pages.append(page)
    return pages


def save_batch_print_pdf(db, qr_codes, template_path):
    qr_codes = list(qr_codes)
    if not qr_codes:
        raise ValueError("no passes selected")
    images = [render_print_pass(db, qr_code, template_path) for qr_code in qr_codes]
    pages = compose_a4_print_pages(images)
    path = _batch_output_path(len(qr_codes))
    first, rest = pages[0], pages[1:]
    first.save(path, "PDF", resolution=DEFAULT_DPI, save_all=bool(rest), append_images=rest)
    return path


def print_file(path):
    if not hasattr(os, "startfile"):
        raise RuntimeError("Печать напрямую поддерживается только в Windows")
    os.startfile(str(path), "print")
