from datetime import datetime

from PIL import Image

from app.core.paths import PHOTOS_DIR


class CameraUnavailable(RuntimeError):
    pass


def _load_cv2():
    try:
        import cv2
    except ModuleNotFoundError as exc:
        raise CameraUnavailable("Для камеры установите зависимость: pip install -r requirements.txt") from exc
    return cv2


def open_capture(camera_index=0):
    cv2 = _load_cv2()
    backend = cv2.CAP_DSHOW if hasattr(cv2, "CAP_DSHOW") else 0
    capture = cv2.VideoCapture(camera_index, backend)
    if not capture or not capture.isOpened():
        raise CameraUnavailable("Камера не найдена или занята другой программой")
    capture.set(getattr(cv2, "CAP_PROP_FRAME_WIDTH", 3), 1280)
    capture.set(getattr(cv2, "CAP_PROP_FRAME_HEIGHT", 4), 720)
    return capture


def frame_to_image(frame):
    cv2 = _load_cv2()
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    return Image.fromarray(rgb)


def save_camera_temp_image(image):
    PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
    path = PHOTOS_DIR / f"_camera_{datetime.now().strftime('%Y%m%d%H%M%S%f')}.jpg"
    image.convert("RGB").save(path, "JPEG", quality=92)
    return str(path)
