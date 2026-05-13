import re
from datetime import date, datetime

from app.services.pass_db import fetch_pass_by_qr


ALLOWED_PASS_DAYS = set(range(1, 11)) | {30, 180}
QR_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{3,64}$")
PHONE_PATTERN = re.compile(r"^[0-9+()\-\s]{1,32}$")


class ValidationError(ValueError):
    def __init__(self, errors):
        self.errors = list(errors)
        super().__init__("\n".join(self.errors))


def _clean_text(value):
    if value is None:
        return ""
    return " ".join(str(value).strip().split())


def format_validation_errors(error):
    errors = error.errors if isinstance(error, ValidationError) else [str(error)]
    return "\n".join(f"- {message}" for message in errors)


def normalize_qr(value):
    qr_code = _clean_text(value)
    errors = []
    if not qr_code:
        errors.append("QR-код обязателен")
    elif not QR_PATTERN.fullmatch(qr_code):
        errors.append("QR-код должен быть 3-64 символа: латиница, цифры, '.', '_', ':' или '-'")
    if errors:
        raise ValidationError(errors)
    return qr_code


def normalize_date(value, field_name="Дата выдачи"):
    if isinstance(value, datetime):
        return value.date().strftime("%Y-%m-%d")
    if isinstance(value, date):
        return value.strftime("%Y-%m-%d")

    raw = _clean_text(value)
    if not raw:
        raise ValidationError([f"{field_name} обязательна"])

    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%Y.%m.%d"):
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    raise ValidationError([f"{field_name} должна быть в формате ГГГГ-ММ-ДД"])


def normalize_pass_days(value):
    raw = _clean_text(value)
    if not raw:
        raise ValidationError(["Срок пропуска обязателен"])
    try:
        numeric = float(raw.replace(",", "."))
    except ValueError as exc:
        raise ValidationError(["Срок пропуска должен быть числом"]) from exc
    if not numeric.is_integer():
        raise ValidationError(["Срок пропуска должен быть целым числом"])

    days = int(numeric)
    if days not in ALLOWED_PASS_DAYS:
        raise ValidationError(["Срок пропуска должен быть от 1 до 10 суток, 30 дней или 180 дней"])
    return days


def normalize_phone(value):
    phone = _clean_text(value)
    if not phone:
        return ""
    if not PHONE_PATTERN.fullmatch(phone):
        raise ValidationError(["Телефон может содержать только цифры, пробелы, '+', '-', '(' и ')'"])
    return phone


def validate_pass_data(data, db=None, existing_qr=None, require_photo=False):
    errors = []
    cleaned = {}

    try:
        cleaned["qr_code"] = normalize_qr(data.get("qr_code"))
    except ValidationError as error:
        errors.extend(error.errors)

    for key, required_message, required in [
        ("district", "Округ обязателен", True),
        ("unit", "В/ч обязательна", True),
        ("rank", "", False),
        ("last_name", "Фамилия обязательна", True),
        ("first_name", "", False),
        ("middle_name", "", False),
    ]:
        cleaned[key] = _clean_text(data.get(key))
        if required and not cleaned[key]:
            errors.append(required_message)

    try:
        cleaned["phone"] = normalize_phone(data.get("phone"))
    except ValidationError as error:
        errors.extend(error.errors)

    try:
        cleaned["issued_date"] = normalize_date(data.get("issued_date"))
    except ValidationError as error:
        errors.extend(error.errors)

    try:
        cleaned["days_count"] = normalize_pass_days(data.get("days_count", 30))
    except ValidationError as error:
        errors.extend(error.errors)

    cleaned["photo_path"] = data.get("photo_path")
    if require_photo and not cleaned["photo_path"]:
        errors.append("Фото обязательно")
    cleaned["active"] = int(bool(data.get("active", 1)))

    qr_code = cleaned.get("qr_code")
    if db is not None and qr_code and qr_code != existing_qr:
        if fetch_pass_by_qr(db, qr_code, include_deleted=True):
            errors.append("Такой QR-код уже существует")

    if errors:
        raise ValidationError(errors)
    return cleaned
