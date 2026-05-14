import os
import tkinter as tk
from datetime import datetime
from tkinter import filedialog, messagebox

from app.core.config import C, FONT as F
from app.core.logging import get_logger
from app.services.audit import safe_record_action
from app.services.auth import PERMISSION_IMPORT, has_permission
from app.services.pass_db import delete_pass_forever, insert_pass_ignore
from app.services.qr_codes import save_qr_code
from app.services.validation import ValidationError, validate_pass_data
from app.ui.widgets import Btn, _sep

logger = get_logger(__name__)

try:
    import openpyxl
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    HAS_XL = True
except ImportError:
    HAS_XL = False

def show_import(app):
    if not has_permission(app.user, PERMISSION_IMPORT):
        app._toast("Недостаточно прав")
        return
    if not HAS_XL:
        messagebox.showerror("Ошибка","Установите openpyxl:\npip install openpyxl"); return

    win=app._modal("📥  Импорт из Excel",780,780)

    # Инструкция
    inf=tk.Frame(win,bg=C["input"],highlightthickness=1,highlightbackground=C["border"])
    inf.pack(fill="x",padx=24,pady=(12,16))
    tk.Label(inf,bg=C["input"],fg=C["mid"],font=(F,10),justify="left",
             text="Ожидаемые колонки (первая строка — заголовок, пропускается):\n"
                  "Округ  |  В/ч  |  Звание  |  Фамилия  |  Имя  |  Отчество  |  "
                  "Номер телефона  |  Дата получения  |  Количество суток\n"
                  "Дата: ДД.ММ.ГГГГ или ГГГГ-ММ-ДД.  Суток: 1–10 или 30 (месяц).").pack(padx=12,pady=10)

    # Путь
    tk.Label(win,text="Файл Excel",bg=C["panel"],fg=C["muted"],font=(F,9)).pack(anchor="w",padx=28,pady=(0,4))
    pf=tk.Frame(win,bg=C["panel"]); pf.pack(fill="x",padx=28)
    pv=tk.StringVar()
    pe=tk.Entry(pf,bg=C["input"],fg=C["text"],insertbackground=C["accent"],
                textvariable=pv,relief="flat",font=(F,11),
                highlightthickness=1,highlightbackground=C["border"])
    pe.pack(side="left",fill="x",expand=True,ipady=7,padx=(0,8))
    def browse():
        f=filedialog.askopenfilename(filetypes=[("Excel","*.xlsx")])
        if f: pv.set(f)
    Btn(pf,text="Обзор",cmd=browse,variant="ghost",w=80,h=36,fs=10,bg=C["panel"]).pack(side="left")

    _sep(win).pack(fill="x",padx=24,pady=12)

    tk.Label(win,text="Журнал импорта",bg=C["panel"],fg=C["muted"],font=(F,9)).pack(anchor="w",padx=28,pady=(0,4))
    logf=tk.Frame(win,bg=C["input"]); logf.pack(fill="both",expand=True,padx=28)
    logt=tk.Text(logf,bg=C["input"],fg=C["text"],font=(F,10),
                 relief="flat",state="disabled",height=7,wrap="word",highlightthickness=0)
    logt.pack(fill="both",expand=True,padx=6,pady=6)

    def log(msg,color=None):
        logt.configure(state="normal")
        tag=f"c{color or 'def'}"
        logt.tag_configure(tag,foreground=color or C["text"])
        logt.insert("end",msg+"\n",tag); logt.see("end")
        logt.configure(state="disabled")

    def do_import():
        path=pv.get().strip()
        if not path or not os.path.exists(path):
            app._toast("Выберите файл"); return
        logt.configure(state="normal"); logt.delete("1.0","end"); logt.configure(state="disabled")
        try:
            wb=openpyxl.load_workbook(path,read_only=True,data_only=True)
            ws=wb.active; rows=iter(ws.iter_rows(values_only=True))
            next(rows)  # заголовок
            added=skipped=errors=0
            for rn,row in enumerate(rows,2):
                if not any(row): continue
                try:
                    def cell(index, default=""):
                        return row[index] if index < len(row) else default

                    qid=f"EMP-{datetime.now().strftime('%Y%m%d%H%M%S%f')}-{rn}"
                    data = {
                        "qr_code": qid,
                        "district": cell(0),
                        "unit": cell(1),
                        "rank": cell(2),
                        "last_name": cell(3),
                        "first_name": cell(4),
                        "middle_name": cell(5),
                        "phone": cell(6),
                        "issued_date": cell(7) or datetime.now().strftime("%Y-%m-%d"),
                        "days_count": cell(8) if cell(8) not in (None, "") else 30,
                    }
                    try:
                        data = validate_pass_data(data, app.db)
                    except ValidationError as ex:
                        log(f"  Строка {rn}: пропущена ({'; '.join(ex.errors)})",C["yellow"])
                        skipped+=1
                        continue

                    full=f"{data['last_name']} {data['first_name']} {data['middle_name']}".strip()
                    inserted = insert_pass_ignore(app.db, data)
                    dl="месяц" if data["days_count"]==30 else f"{data['days_count']}сут"
                    if inserted:
                        try:
                            save_qr_code(data["qr_code"])
                        except Exception:
                            delete_pass_forever(app.db, data["qr_code"])
                            raise
                        safe_record_action(app.db, app.user, "pass.import_create", "pass", data["qr_code"], {
                            "name": full,
                            "source": os.path.basename(path),
                        })
                        log(f"  ✓  {full}  [{data['district']} / {data['unit']}]  {dl}",C["green"]); added+=1
                    else:
                        log(f"  Строка {rn}: пропущена (дубликат QR)",C["yellow"]); skipped+=1
                except Exception as ex:
                    logger.exception("Failed to import Excel row %s", rn)
                    log(f"  ✗  Строка {rn}: {ex}",C["red"]); errors+=1

            log(f"\n─── Итого: добавлено {added}, пропущено {skipped}, ошибок {errors} ───",C["accent"])
            safe_record_action(app.db, app.user, "import.excel", "file", os.path.basename(path), {
                "added": added,
                "skipped": skipped,
                "errors": errors,
            })
            if added: app._toast(f"Импортировано {added} записей",C["green"])
        except Exception as ex:
            logger.exception("Excel import failed for file: %s", path)
            log(f"Ошибка файла: {ex}",C["red"])

    Btn(win,text="Начать импорт",cmd=do_import,variant="primary",
        w=612,h=44,fs=13,bg=C["panel"]).pack(padx=28,pady=10)
