from pathlib import Path

import qrcode
from qrcode.constants import ERROR_CORRECT_M

from app.core.paths import qr_code_path


def create_qr_image(qr_code):
    qr = qrcode.QRCode(
        version=None,
        error_correction=ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )
    qr.add_data(qr_code)
    qr.make(fit=True)

    image = qr.make_image(fill_color="black", back_color="white").convert("RGBA")
    pixels = image.load()
    for y in range(image.height):
        for x in range(image.width):
            red, green, blue, _alpha = pixels[x, y]
            if red > 240 and green > 240 and blue > 240:
                pixels[x, y] = (255, 255, 255, 0)
            else:
                pixels[x, y] = (0, 0, 0, 255)
    return image


def save_qr_code(qr_code, path=None):
    target = Path(path) if path else qr_code_path(qr_code)
    target.parent.mkdir(parents=True, exist_ok=True)
    image = create_qr_image(qr_code)
    image.save(target, format="PNG")
    return target
