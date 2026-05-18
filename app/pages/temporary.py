import tkinter as tk
from datetime import datetime
from tkinter import messagebox, ttk

from app.core.config import C, FONT as F
from app.core.logging import get_logger
from app.services.audit import safe_record_action
from app.services.auth import PERMISSION_TEMPORARY, has_permission
from app.services.pass_db import CI, PASS_TYPE_TEMPORARY
from app.services.reference_data import list_reference_values
from app.services.temporary_passes import (
    TEMP_POOL_SIZE,
    TEMP_STATUS_EXPIRED,
    TEMP_STATUS_FREE,
    TEMP_STATUS_ISSUED,
    TEMP_STATUS_LOST,
    TemporaryPassError,
    active_temporary_book,
    create_temporary_pool,
    issue_temporary_pass,
    list_temporary_passes,
    next_free_temporary_pass,
    temporary_counts,
    temporary_book_no,
    temporary_book_title,
    temporary_status,
    temporary_status_title,
)
from app.services.validation import ValidationError, format_validation_errors
from app.pages.print_page import open_print_dialog
from app.ui.widgets import Btn, FilterChip, _field, _suggest_field, accent_bar


logger = get_logger(__name__)

STATUS_FILTERS = {
    "Все": "all",
    "Свободные": TEMP_STATUS_FREE,
    "Выданные": TEMP_STATUS_ISSUED,
    "Истёкшие": TEMP_STATUS_EXPIRED,
    "Утерянные": TEMP_STATUS_LOST,
}


def _name(row):
    return " ".join(filter(None, [row[CI["ln"]], row[CI["fn"]], row[CI["mn"]]]))


def _selected_qr(app, tree):
    sel = tree.selection()
    if not sel:
        app._toast("Выберите временный QR")
        return None
    return tree.item(sel[0])["values"][1]


def _selected_qrs(app, tree):
    selection = tree.selection()
    if not selection:
        app._toast("Выберите один или несколько временных пропусков")
        return []
    return [tree.item(item)["values"][1] for item in selection]


def _print_selected(app, tree):
    qrs = _selected_qrs(app, tree)
    if not qrs:
        return
    open_print_dialog(app, qrs, template_profile=PASS_TYPE_TEMPORARY)


def _print_qr_book(app, on_saved=None):
    created = create_temporary_pool(app.db, TEMP_POOL_SIZE)
    if created:
        book = active_temporary_book(app.db)
        safe_record_action(app.db, app.user, "temp.book_create", "temporary_book", book[0] if book else "TMP", {"created": len(created), "reason": "print_book"})
        if on_saved:
            on_saved()
    book = active_temporary_book(app.db)
    book_no = book[0] if book else None
    qrs = [row[CI["qr"]] for row in list_temporary_passes(app.db, "", "all", book_no=book_no)]
    if not qrs:
        app._toast("Нет QR для печати книги")
        return
    open_print_dialog(
        app,
        qrs,
        template_profile=PASS_TYPE_TEMPORARY,
        title=f"Печать QR-книги {temporary_book_title(book_no)} — {len(qrs)} разовых пропусков",
    )


def _status_tag(status):
    return {
        TEMP_STATUS_FREE: "free",
        TEMP_STATUS_ISSUED: "issued",
        TEMP_STATUS_EXPIRED: "expired",
        TEMP_STATUS_LOST: "lost",
    }.get(status, "")


def _next_free_row(app):
    row = next_free_temporary_pass(app.db)
    if row:
        return row
    created = create_temporary_pool(app.db, TEMP_POOL_SIZE)
    if created:
        book = active_temporary_book(app.db)
        safe_record_action(app.db, app.user, "temp.book_create", "temporary_book", book[0] if book else "TMP", {"created": len(created), "reason": "auto"})
        return next_free_temporary_pass(app.db)
    return None


def _issue_modal(app, qr_code=None, on_saved=None, after_issue=None):
    if not qr_code:
        row = _next_free_row(app)
        if not row:
            app._toast("Свободных временных QR нет")
            return
        qr_code = row[CI["qr"]]

    win = app._modal(f"Выдать временный пропуск — {qr_code}", 560, 760, scroll=True)
    tk.Label(win, text=f"QR: {qr_code}", bg=C["panel"], fg=C["accent"], font=(F, 14, "bold")).pack(anchor="w", padx=28, pady=(18, 4))

    fio_e = _field(win, "ФИО *")
    destination_e = _suggest_field(win, "Куда войти *", list_reference_values(app.db, "unit"))
    basis_e = _field(win, "Основание *")
    is_e = _field(win, "Дата выдачи (ГГГГ-ММ-ДД)", datetime.now().strftime("%Y-%m-%d"))

    tk.Label(win, text="Срок временного пропуска", bg=C["panel"], fg=C["muted"], font=(F, 9)).pack(anchor="w", padx=28, pady=(12, 4))
    days_frame = tk.Frame(win, bg=C["panel"])
    days_frame.pack(anchor="w", padx=28)
    days_var = tk.IntVar(value=1)
    for value in range(1, 11):
        tk.Radiobutton(
            days_frame,
            text=str(value),
            value=value,
            variable=days_var,
            bg=C["panel"],
            fg=C["text"],
            selectcolor=C["input"],
            activebackground=C["panel"],
            font=(F, 10),
        ).pack(side="left", padx=3)

    def save():
        fio = fio_e.get().strip()
        destination = destination_e.get().strip()
        basis = basis_e.get().strip()
        if not fio:
            app._toast("Укажите ФИО")
            return
        if not destination:
            app._toast("Укажите куда войти")
            return
        if not basis:
            app._toast("Укажите основание")
            return
        data = {
            "district": destination,
            "unit": destination,
            "rank": basis,
            "last_name": fio,
            "first_name": "",
            "middle_name": "",
            "phone": "",
            "issued_date": is_e.get(),
            "days_count": days_var.get(),
        }
        try:
            row = issue_temporary_pass(app.db, qr_code, data)
            name = _name(row)
            safe_record_action(app.db, app.user, "temp.issue", "pass", qr_code, {
                "name": name,
                "destination": row[CI["unit"]],
                "basis": row[CI["rank"]],
                "days": row[CI["days"]],
            })
        except ValidationError as ex:
            messagebox.showerror("Проверьте данные", format_validation_errors(ex))
            return
        except TemporaryPassError as ex:
            messagebox.showerror("Временный пропуск", str(ex))
            return
        except Exception as ex:
            logger.exception("Failed to issue temporary pass: %s", qr_code)
            messagebox.showerror("Ошибка", f"Не удалось выдать временный пропуск:\n{ex}")
            return
        app._close_modal(win)
        app._toast(f"Выдан временный QR: {qr_code}", C["green"])
        if on_saved:
            on_saved()
        if after_issue:
            after_issue(qr_code)

    button_text = "Оформить и печатать" if after_issue else "Выдать"
    Btn(win, text=button_text, cmd=save, variant="success", w=504, h=44, fs=13, bg=C["panel"]).pack(padx=28, pady=18)


def _issue_and_print(app, on_saved=None):
    _issue_modal(
        app,
        None,
        on_saved,
        after_issue=lambda qr: open_print_dialog(
            app,
            [qr],
            template_profile=PASS_TYPE_TEMPORARY,
            title="Печать разового пропуска с корешком",
        ),
    )


def show_temporary(app):
    if not has_permission(app.user, PERMISSION_TEMPORARY):
        app._toast("Недостаточно прав")
        return
    app._clr(app.content)
    app._pgtitle.configure(text="Одноразовые")
    wrap = tk.Frame(app.content, bg=C["bg"])
    wrap.pack(fill="both", expand=True, padx=36, pady=20)

    top = tk.Frame(wrap, bg=C["bg"])
    top.pack(fill="x", pady=(0, 12))
    tk.Label(top, text="Одноразовые временные пропуска", bg=C["bg"], fg=C["text"], font=(F, 16, "bold")).pack(side="left")
    book_state_label = tk.Label(top, text="", bg=C["bg"], fg=C["muted"], font=(F, 10, "bold"))
    book_state_label.pack(side="left", padx=14)

    sf = tk.Frame(top, bg=C["input"], highlightthickness=1, highlightbackground=C["border"])
    sf.pack(side="right")
    search_var = tk.StringVar()
    search_entry = tk.Entry(sf, bg=C["input"], fg=C["text"], insertbackground=C["accent"],
                            textvariable=search_var, relief="flat", font=(F, 12), width=24)
    search_entry.pack(side="left", ipady=7, padx=(10, 4))

    stats = tk.Frame(wrap, bg=C["panel"], highlightthickness=1, highlightbackground=C["border"])
    stats.pack(fill="x", pady=(0, 12))
    stat_labels = {}
    for key, title, color in [
        (TEMP_STATUS_FREE, "Свободно", C["green"]),
        (TEMP_STATUS_ISSUED, "Выдано", C["accent"]),
        (TEMP_STATUS_EXPIRED, "Истекло", C["yellow"]),
        (TEMP_STATUS_LOST, "Утеряно", C["red"]),
    ]:
        cell = tk.Frame(stats, bg=C["panel"])
        cell.pack(side="left", fill="x", expand=True, padx=12, pady=10)
        tk.Label(cell, text=title, bg=C["panel"], fg=C["muted"], font=(F, 9)).pack(anchor="w")
        label = tk.Label(cell, text="0", bg=C["panel"], fg=color, font=(F, 18, "bold"))
        label.pack(anchor="w")
        stat_labels[key] = label

    filter_panel = tk.Frame(wrap, bg=C["panel"], highlightthickness=1, highlightbackground=C["border"])
    filter_panel.pack(fill="x", pady=(0, 12))
    accent_bar(filter_panel).pack(fill="x")
    filters = tk.Frame(filter_panel, bg=C["panel"])
    filters.pack(fill="x", padx=14, pady=12)
    status_var = tk.StringVar(value="Все")
    status_group = tk.Frame(filters, bg=C["panel"])
    status_group.pack(side="left")
    tk.Label(status_group, text="Статус", bg=C["panel"], fg=C["muted"], font=(F, 9)).pack(anchor="w", pady=(0, 4))
    status_row = tk.Frame(status_group, bg=C["panel"])
    status_row.pack(anchor="w")
    for label in STATUS_FILTERS:
        FilterChip(
            status_row,
            text=label,
            variable=status_var,
            value=label,
            command=lambda: load(),
            bg=C["panel"],
        ).pack(side="left", padx=(0, 6))

    tf = tk.Frame(wrap, bg=C["panel"])
    tf.pack(fill="both", expand=True)
    vsb = ttk.Scrollbar(tf, orient="vertical")
    vsb.pack(side="right", fill="y")
    cols = ("book", "qr", "status", "name", "unit", "issued", "days", "phone")
    tree = ttk.Treeview(tf, style="T.Treeview", columns=cols, show="headings", yscrollcommand=vsb.set)
    vsb.configure(command=tree.yview)
    for col, txt, width in [
        ("book", "Книга", 80),
        ("qr", "QR", 150),
        ("status", "Статус", 100),
        ("name", "ФИО", 220),
        ("unit", "Куда", 140),
        ("issued", "Выдан", 100),
        ("days", "Срок", 70),
        ("phone", "Телефон", 130),
    ]:
        tree.heading(col, text=txt)
        tree.column(col, width=width, minwidth=60)
    tree.tag_configure("free", foreground=C["green"])
    tree.tag_configure("issued", foreground=C["accent"])
    tree.tag_configure("expired", foreground=C["yellow"])
    tree.tag_configure("lost", foreground=C["red"])
    tree.pack(fill="both", expand=True)

    def load():
        for item in tree.get_children():
            tree.delete(item)
        counts = temporary_counts(app.db)
        active_book = counts.get("active_book")
        if active_book:
            book_state_label.configure(
                text=f"{temporary_book_title(active_book)} · свободно {counts.get('active_book_free', 0)} из {counts.get('active_book_size', TEMP_POOL_SIZE)}"
            )
        else:
            book_state_label.configure(text="QR-книга ещё не создана")
        for key, label in stat_labels.items():
            label.configure(text=str(counts.get(key, 0)))
        status = STATUS_FILTERS.get(status_var.get(), "all")
        for row in list_temporary_passes(app.db, search_var.get(), status):
            status_code = temporary_status(row)
            days = row[CI["days"]] or 1
            tree.insert("", "end", tags=(_status_tag(status_code),), values=(
                temporary_book_title(temporary_book_no(row)),
                row[CI["qr"]],
                temporary_status_title(status_code),
                _name(row),
                row[CI["unit"]] or "",
                row[CI["issued"]] or "",
                f"{days} сут.",
                row[CI["phone"]] or "",
            ))

    def generate_pool():
        if not messagebox.askyesno(
            "Создать QR-книгу",
            f"Создать недостающие QR для активной книги до {TEMP_POOL_SIZE} штук?\n\nПосле использования всех QR книга будет закрыта, а новая получит другой диапазон кодов.",
        ):
            return
        try:
            created = create_temporary_pool(app.db, TEMP_POOL_SIZE)
            book = active_temporary_book(app.db)
            safe_record_action(app.db, app.user, "temp.book_create", "temporary_book", book[0] if book else "TMP", {"created": len(created)})
            if created:
                app._toast(f"QR-книга создана: {len(created)} кодов", C["green"])
            else:
                app._toast("Активная QR-книга уже создана", C["green"])
            load()
        except Exception as ex:
            logger.exception("Failed to create temporary QR book")
            messagebox.showerror("Одноразовые", f"Не удалось создать QR-книгу:\n{ex}")

    def issue_selected():
        qr = _selected_qr(app, tree)
        if qr:
            _issue_modal(app, qr, load)

    search_entry.bind("<Return>", lambda _e: load())
    Btn(sf, text="Поиск", cmd=load, variant="primary", w=80, h=34, fs=10, bg=C["input"]).pack(side="left", padx=3)

    bf = tk.Frame(wrap, bg=C["bg"])
    bf.pack(pady=10)
    Btn(bf, text="Оформить и печать", cmd=lambda: _issue_and_print(app, load), variant="success", w=190, h=38, bg=C["bg"]).pack(side="left", padx=5)
    Btn(bf, text="Выдать следующий", cmd=lambda: _issue_modal(app, None, load), variant="primary", w=170, h=38, bg=C["bg"]).pack(side="left", padx=5)
    Btn(bf, text="Выдать выбранный", cmd=issue_selected, variant="ghost", w=170, h=38, bg=C["bg"]).pack(side="left", padx=5)
    Btn(bf, text="Печать", cmd=lambda: _print_selected(app, tree), variant="primary", w=130, h=38, bg=C["bg"]).pack(side="left", padx=5)
    Btn(bf, text="QR-книга", cmd=lambda: _print_qr_book(app, load), variant="success", w=130, h=38, bg=C["bg"]).pack(side="left", padx=5)
    if app.user and app.user.get("role") == "admin":
        Btn(bf, text="Создать QR-книгу", cmd=generate_pool, variant="ghost", w=170, h=38, bg=C["bg"]).pack(side="left", padx=5)

    load()
