import json
from datetime import datetime

from app.core.logging import get_logger


logger = get_logger(__name__)

ACTION_TITLES = {
    "backup.auto": "Автобэкап",
    "backup.create": "Бэкап создан",
    "backup.prune": "Бэкапы очищены",
    "backup.restore": "Бэкап восстановлен",
    "files.cleanup": "Файлы очищены",
    "import.excel": "Импорт Excel",
    "integrity.check": "Проверка данных",
    "pass.create": "Пропуск создан",
    "pass.delete": "Пропуск в корзине",
    "pass.delete_forever": "Пропуск удалён",
    "pass.import_create": "Пропуск импортирован",
    "pass.restore": "Пропуск восстановлен",
    "pass.update": "Пропуск изменён",
    "print.pdf": "PDF для печати",
    "print.png": "PNG для печати",
    "print.batch_pdf": "Пакетный PDF",
    "print.batch_send": "Пакетная печать",
    "print.send": "Отправлено на печать",
    "references.add": "Значение добавлено в справочник",
    "references.delete": "Значение удалено из справочника",
    "references.sync": "Справочники обновлены",
    "settings.update": "Настройки изменены",
    "template.update": "Шаблон изменён",
    "temp.issue": "Временный пропуск выдан",
    "temp.lost": "Временный пропуск утерян",
    "temp.book_create": "QR-книга временных пропусков создана",
    "temp.pool_create": "Пул временных QR создан",
    "temp.return": "Временный пропуск возвращён",
    "user.create": "Пользователь создан",
    "user.delete": "Пользователь удалён",
    "user.update": "Пользователь изменён",
}


def _actor(user):
    if not user:
        return "system", "system"
    return (
        user.get("username") or user.get("name") or "unknown",
        user.get("role") or "unknown",
    )


def action_title(action):
    return ACTION_TITLES.get(action, action)


def details_text(details):
    if not details:
        return ""
    if isinstance(details, str):
        return details
    return json.dumps(details, ensure_ascii=False, sort_keys=True, default=str)


def record_action(db, user, action, entity_type="", entity_id="", details=None):
    username, role = _actor(user)
    db.execute(
        """INSERT INTO audit_logs
           (timestamp, username, role, action, entity_type, entity_id, details)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            username,
            role,
            action,
            entity_type or "",
            str(entity_id or ""),
            details_text(details),
        ),
    )
    db.commit()


def safe_record_action(db, user, action, entity_type="", entity_id="", details=None):
    try:
        record_action(db, user, action, entity_type, entity_id, details)
    except Exception:
        logger.exception("Failed to record audit action: %s %s", action, entity_id)


def list_actions(db, search="", limit=300):
    clauses = []
    params = []
    if search:
        like = f"%{search}%"
        clauses.append(
            "(username LIKE ? OR action LIKE ? OR entity_type LIKE ? OR entity_id LIKE ? OR details LIKE ?)"
        )
        params.extend([like, like, like, like, like])
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.append(limit)
    cursor = db.cursor()
    cursor.execute(
        f"""SELECT timestamp, username, role, action, entity_type, entity_id, details
            FROM audit_logs
            {where}
            ORDER BY id DESC
            LIMIT ?""",
        params,
    )
    return cursor.fetchall()


def list_entity_actions(db, entity_type, entity_id, limit=100):
    cursor = db.cursor()
    cursor.execute(
        """SELECT timestamp, username, role, action, entity_type, entity_id, details
           FROM audit_logs
           WHERE entity_type=? AND entity_id=?
           ORDER BY id DESC
           LIMIT ?""",
        (entity_type, str(entity_id), limit),
    )
    return cursor.fetchall()
