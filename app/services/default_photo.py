from PIL import Image, ImageDraw

from app.core.paths import ASSETS_DIR, app_path


DEFAULT_PASS_PHOTO_NAME = "default_pass_photo.png"


def _s(value):
    return int(round(value * 4))


def _ellipse(draw, box, fill, outline=None, width=1):
    draw.ellipse(tuple(_s(v) for v in box), fill=fill, outline=outline, width=_s(width))


def _rectangle(draw, box, fill, outline=None, width=1):
    draw.rectangle(tuple(_s(v) for v in box), fill=fill, outline=outline, width=_s(width))


def _polygon(draw, points, fill, outline=None):
    draw.polygon([( _s(x), _s(y)) for x, y in points], fill=fill, outline=outline)


def _line(draw, points, fill, width=1):
    draw.line([( _s(x), _s(y)) for x, y in points], fill=fill, width=_s(width), joint="curve")


def _arc(draw, box, start, end, fill, width=1):
    draw.arc(tuple(_s(v) for v in box), start, end, fill=fill, width=_s(width))


def create_default_pass_photo(size=900):
    canvas = 600
    image = Image.new("RGBA", (_s(canvas), _s(canvas)), (255, 255, 255, 255))
    draw = ImageDraw.Draw(image)

    for radius, alpha in ((270, 34), (210, 22), (150, 16)):
        _ellipse(draw, (300 - radius, 300 - radius, 300 + radius, 300 + radius), (230, 234, 224, alpha))

    # Shoulders and uniform.
    _polygon(draw, [(105, 560), (170, 420), (230, 385), (300, 520), (370, 385), (430, 420), (495, 560)],
             (61, 86, 54, 255), (18, 30, 18, 255))
    _polygon(draw, [(185, 405), (300, 560), (415, 405), (395, 560), (205, 560)],
             (50, 78, 48, 255), (13, 24, 13, 255))
    _polygon(draw, [(250, 385), (300, 515), (350, 385), (330, 560), (270, 560)],
             (224, 199, 142, 255), (100, 80, 45, 255))
    _line(draw, [(105, 560), (495, 560)], (14, 24, 14, 255), 2)
    _line(draw, [(180, 450), (205, 560)], (14, 24, 14, 255), 2)
    _line(draw, [(420, 450), (395, 560)], (14, 24, 14, 255), 2)

    # Neck and ears.
    _polygon(draw, [(250, 335), (350, 335), (345, 420), (300, 470), (255, 420)],
             (238, 133, 105, 255), (47, 22, 16, 255))
    _ellipse(draw, (145, 235, 205, 315), (238, 142, 116, 255), (34, 18, 14, 255), 2)
    _ellipse(draw, (395, 235, 455, 315), (238, 142, 116, 255), (34, 18, 14, 255), 2)
    _arc(draw, (158, 252, 198, 308), 95, 275, (216, 113, 92, 180), 3)
    _arc(draw, (402, 252, 442, 308), -95, 85, (216, 113, 92, 180), 3)

    # Hair and head.
    _polygon(draw, [(198, 205), (230, 150), (370, 150), (402, 205), (395, 275), (365, 275), (355, 175), (245, 175), (235, 275), (205, 275)],
             (61, 34, 27, 255), (25, 15, 12, 255))
    _ellipse(draw, (205, 145, 395, 405), (250, 151, 120, 255), (38, 18, 13, 255), 2)
    _ellipse(draw, (240, 165, 345, 350), (255, 172, 137, 95))
    _ellipse(draw, (350, 205, 380, 285), (255, 225, 210, 120))
    _arc(draw, (215, 260, 385, 430), 35, 145, (203, 90, 74, 120), 6)

    # Cap.
    _ellipse(draw, (115, 42, 485, 252), (78, 100, 65, 255), (11, 19, 10, 255), 3)
    _ellipse(draw, (135, 62, 465, 232), (90, 113, 76, 115))
    _rectangle(draw, (175, 150, 425, 240), (52, 74, 45, 255), (10, 18, 9, 255), 2)
    _ellipse(draw, (180, 165, 420, 248), (22, 32, 24, 230), (8, 13, 8, 255), 2)
    _arc(draw, (165, 160, 435, 275), 194, 346, (244, 166, 46, 255), 12)
    _arc(draw, (165, 160, 435, 275), 194, 346, (118, 67, 18, 255), 15)
    _arc(draw, (165, 160, 435, 275), 194, 346, (246, 177, 56, 255), 10)
    _ellipse(draw, (268, 128, 332, 192), (245, 177, 55, 255), (77, 48, 14, 255), 3)
    _ellipse(draw, (278, 138, 322, 182), (255, 201, 75, 255), (77, 48, 14, 255), 2)
    _polygon(draw, [(300, 144), (309, 166), (332, 166), (313, 179), (321, 202), (300, 188), (279, 202), (287, 179), (268, 166), (291, 166)],
             (48, 67, 39, 255), (54, 38, 10, 255))

    image = image.resize((size, size), Image.Resampling.LANCZOS).convert("RGB")
    return image


def default_pass_photo_path():
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    path = ASSETS_DIR / DEFAULT_PASS_PHOTO_NAME
    if not path.exists():
        create_default_pass_photo().save(path, "PNG")
    return path


def pass_photo_source(photo_path):
    if photo_path:
        path = app_path(photo_path)
        if path.exists():
            return path
    return default_pass_photo_path()
