import json
import os
import shutil
import sqlite3
import tkinter as tk
from datetime import datetime
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageTk

from app.core.config import C, FONT as F
from app.core.logging import get_logger
from app.services.audit import action_title, list_entity_actions, safe_record_action
from app.services.camera import CameraUnavailable, frame_to_image, open_capture, save_camera_temp_image
from app.services.default_photo import pass_photo_source
from app.services.pass_db import (CI, PASS_TYPE_REGULAR, PASS_TYPE_SEMIANNUAL, create_pass,
                     delete_pass_forever, fetch_pass_by_qr, pass_status, search_passes,
                     soft_delete_pass, update_pass)
from app.services.qr_codes import save_qr_code
from app.services.temporary_passes import is_temporary_pass
from app.services.validation import ValidationError, format_validation_errors, validate_pass_data
from app.core.paths import app_path, photo_file_path, qr_code_path
from app.ui.widgets import Btn, _field

logger = get_logger(__name__)

PASS_PAGE_CONFIGS = {
    PASS_TYPE_REGULAR: {
        "title": "Временные",
        "heading": "Временные пропуска",
        "add_title": "Новый временный пропуск",
        "edit_title": "Редактирование временного пропуска",
        "create_button": "Создать временный пропуск",
        "new_button": "Новый временный",
        "days": 30,
        "days_label": "Месяц",
        "photo": False,
        "qr_prefix": "EMP",
    },
    PASS_TYPE_SEMIANNUAL: {
        "title": "Полугодовые",
        "heading": "Полугодовые пропуска",
        "add_title": "Новый полугодовой пропуск",
        "edit_title": "Редактирование полугодового пропуска",
        "create_button": "Создать полугодовой пропуск",
        "new_button": "Новый полугодовой",
        "days": 180,
        "days_label": "6 месяцев",
        "photo": True,
        "qr_prefix": "HY",
    },
}


def _copy_photo_for_qr(source, qr_code, current=None):
    if not source:
        return None
    source_path = app_path(source)
    if not source_path.exists():
        return current
    ext = source_path.suffix or ".jpg"
    dest = photo_file_path(qr_code, ext)
    if source_path.resolve() != dest.resolve():
        shutil.copy2(source_path, dest)
    return str(dest)


def _photo_label(path, empty_text="не выбрано"):
    return f"Фото: {os.path.basename(path) if path else empty_text}"


def _capture_photo(app, on_selected):
    try:
        capture = open_capture()
    except CameraUnavailable as ex:
        messagebox.showerror("Камера", str(ex))
        return
    except Exception as ex:
        logger.exception("Failed to open camera")
        messagebox.showerror("Камера", f"Не удалось открыть камеру:\n{ex}")
        return

    win=app._modal("Фото с камеры",760,620)
    win._camera_images=[]
    state={"frame": None, "captured": None, "paused": False, "closed": False}

    preview=tk.Label(win,text="Запуск камеры...",bg=C["input"],fg=C["muted"],font=(F,12))
    preview.pack(fill="both",expand=True,padx=24,pady=(18,10))
    status=tk.Label(win,text="",bg=C["panel"],fg=C["muted"],font=(F,10))
    status.pack(fill="x",padx=24,pady=(0,10))

    def render(image):
        shown=image.copy()
        shown.thumbnail((700,420))
        tk_image=ImageTk.PhotoImage(shown)
        win._camera_images=[tk_image]
        preview.configure(image=tk_image,text="")

    def update():
        if state["closed"] or not win.winfo_exists():
            return
        if not state["paused"]:
            ok, frame = capture.read()
            if ok:
                state["frame"] = frame
                try:
                    render(frame_to_image(frame))
                    status.configure(text="Камера активна")
                except Exception:
                    logger.exception("Failed to render camera frame")
                    status.configure(text="Не удалось показать кадр",fg=C["red"])
            else:
                status.configure(text="Камера не отдаёт изображение",fg=C["red"])
        win.after(40, update)

    def snap():
        if state["frame"] is None:
            app._toast("Кадр ещё не получен")
            return
        try:
            image=frame_to_image(state["frame"]).copy()
        except Exception as ex:
            logger.exception("Failed to capture camera frame")
            messagebox.showerror("Камера", f"Не удалось сделать снимок:\n{ex}")
            return
        state["captured"]=image
        state["paused"]=True
        render(image)
        status.configure(text="Снимок сделан. Можно использовать или переснять.",fg=C["green"])

    def retake():
        state["captured"]=None
        state["paused"]=False
        status.configure(text="Камера активна",fg=C["muted"])

    def close():
        state["closed"]=True
        try:
            capture.release()
        except Exception:
            logger.exception("Failed to release camera")
        win.destroy()

    def use_photo():
        if state["captured"] is None:
            snap()
        if state["captured"] is None:
            return
        try:
            path=save_camera_temp_image(state["captured"])
        except Exception as ex:
            logger.exception("Failed to save camera photo")
            messagebox.showerror("Камера", f"Не удалось сохранить снимок:\n{ex}")
            return
        on_selected(path)
        close()

    win.protocol("WM_DELETE_WINDOW", close)
    buttons=tk.Frame(win,bg=C["panel"])
    buttons.pack(fill="x",padx=24,pady=(0,18))
    Btn(buttons,text="Закрыть",cmd=close,variant="ghost",w=120,h=40,bg=C["panel"]).pack(side="right")
    Btn(buttons,text="Использовать",cmd=use_photo,variant="success",w=150,h=40,bg=C["panel"]).pack(side="right",padx=(0,8))
    Btn(buttons,text="Переснять",cmd=retake,variant="ghost",w=130,h=40,bg=C["panel"]).pack(side="left",padx=(0,8))
    Btn(buttons,text="Сделать снимок",cmd=snap,variant="primary",w=160,h=40,bg=C["panel"]).pack(side="left")
    update()


def _parse_iso_date(value):
    if not value:
        return None
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def _pass_units(app, pass_type=PASS_TYPE_REGULAR):
    units = set()
    for row in search_passes(app.db, "", deleted=0, pass_type=pass_type):
        if row[CI["unit"]]:
            units.add(row[CI["unit"]])
    return ["Все"] + sorted(units)


def _pass_counts(app, pass_type):
    counts = {"total": 0, "active": 0, "inactive": 0}
    for row in search_passes(app.db, "", deleted=0, pass_type=pass_type):
        active, _left, _expires = pass_status(app.db, row)
        counts["total"] += 1
        counts["active" if active else "inactive"] += 1
    return counts


def _update_pass_stats(app):
    labels = getattr(app, "_pass_stat_labels", None)
    pass_type = getattr(app, "_pass_list_type", PASS_TYPE_REGULAR)
    if not labels:
        return
    counts = _pass_counts(app, pass_type)
    for key, label in labels.items():
        label.configure(text=str(counts.get(key, 0)))


def show_list(app):
    return _show_passes(app, PASS_TYPE_REGULAR)


def show_semiannual(app):
    return _show_passes(app, PASS_TYPE_SEMIANNUAL)


def _show_passes(app, pass_type):
    config = PASS_PAGE_CONFIGS[pass_type]
    app._pass_list_type = pass_type
    app._clr(app.content)
    app._pgtitle.configure(text=config["title"])
    wrap=tk.Frame(app.content,bg=C["bg"])
    wrap.pack(fill="both",expand=True,padx=36,pady=20)

    # Поиск
    top=tk.Frame(wrap,bg=C["bg"]); top.pack(fill="x",pady=(0,12))
    tk.Label(top,text=config["heading"],bg=C["bg"],fg=C["text"],font=(F,16,"bold")).pack(side="left")
    sf=tk.Frame(top,bg=C["input"],highlightthickness=1,highlightbackground=C["border"])
    sf.pack(side="right")
    sv=tk.StringVar()
    se=tk.Entry(sf,bg=C["input"],fg=C["text"],insertbackground=C["accent"],
                textvariable=sv,relief="flat",font=(F,12),width=24)
    se.pack(side="left",ipady=7,padx=(10,4))
    se.bind("<Return>",lambda e:app._load_list(sv.get()))
    Btn(sf,text="Поиск",cmd=lambda:app._load_list(sv.get()),
        variant="primary",w=80,h=34,fs=10,bg=C["input"]).pack(side="left",padx=3)

    stats=tk.Frame(wrap,bg=C["panel"],highlightthickness=1,highlightbackground=C["border"])
    stats.pack(fill="x",pady=(0,12))
    app._pass_stat_labels={}
    for key,title,color in [("total","Всего",C["mid"]),("active","Активных",C["green"]),("inactive","Неактивных",C["red"])]:
        cell=tk.Frame(stats,bg=C["panel"])
        cell.pack(side="left",fill="x",expand=True,padx=12,pady=10)
        tk.Label(cell,text=title,bg=C["panel"],fg=C["muted"],font=(F,9)).pack(anchor="w")
        label=tk.Label(cell,text="0",bg=C["panel"],fg=color,font=(F,18,"bold"))
        label.pack(anchor="w")
        app._pass_stat_labels[key]=label

    filters=tk.Frame(wrap,bg=C["bg"])
    filters.pack(fill="x",pady=(0,12))
    app._pass_search=sv
    app._pass_status=tk.StringVar(value=getattr(app, "_pass_status_value", "Все"))
    app._pass_unit=tk.StringVar(value=getattr(app, "_pass_unit_value", "Все"))
    app._pass_date_from=tk.StringVar(value=getattr(app, "_pass_date_from_value", ""))
    app._pass_date_to=tk.StringVar(value=getattr(app, "_pass_date_to_value", ""))
    app._pass_sort=tk.StringVar(value=getattr(app, "_pass_sort_value", "Дата: новые"))

    def apply_filters(*_):
        app._pass_status_value=app._pass_status.get()
        app._pass_unit_value=app._pass_unit.get()
        app._pass_date_from_value=app._pass_date_from.get()
        app._pass_date_to_value=app._pass_date_to.get()
        app._pass_sort_value=app._pass_sort.get()
        app._load_list(sv.get())

    for title,var,values,width in [
        ("Статус",app._pass_status,["Все","Активные","Истекшие"],12),
        ("В/ч",app._pass_unit,_pass_units(app, pass_type),16),
        ("Сортировка",app._pass_sort,["Дата: новые","Дата: старые","ФИО","В/ч","Статус"],16),
    ]:
        group=tk.Frame(filters,bg=C["bg"])
        group.pack(side="left",padx=(0,10))
        tk.Label(group,text=title,bg=C["bg"],fg=C["muted"],font=(F,9)).pack(anchor="w")
        box=ttk.Combobox(group,textvariable=var,values=values,state="readonly",width=width)
        box.pack(ipady=3)
        box.bind("<<ComboboxSelected>>",apply_filters)

    for title,var in [("С даты",app._pass_date_from),("По дату",app._pass_date_to)]:
        group=tk.Frame(filters,bg=C["bg"])
        group.pack(side="left",padx=(0,10))
        tk.Label(group,text=title,bg=C["bg"],fg=C["muted"],font=(F,9)).pack(anchor="w")
        entry=tk.Entry(group,bg=C["input"],fg=C["text"],insertbackground=C["accent"],
                       textvariable=var,relief="flat",font=(F,11),width=12)
        entry.pack(ipady=5)
        entry.bind("<Return>",apply_filters)

    Btn(filters,text="Применить",cmd=apply_filters,variant="primary",w=110,h=34,fs=10,bg=C["bg"]).pack(side="left",padx=(0,8),pady=(17,0))
    Btn(filters,text="Сброс",cmd=lambda:(
        app._pass_status.set("Все"),
        app._pass_unit.set("Все"),
        app._pass_date_from.set(""),
        app._pass_date_to.set(""),
        app._pass_sort.set("Дата: новые"),
        apply_filters()
    ),variant="ghost",w=90,h=34,fs=10,bg=C["bg"]).pack(side="left",pady=(17,0))

    # Таблица
    tf=tk.Frame(wrap,bg=C["panel"]); tf.pack(fill="both",expand=True)
    vsb=ttk.Scrollbar(tf,orient="vertical"); vsb.pack(side="right",fill="y")
    cols=("qr","district","unit","rank","name","phone","issued","days","status")
    app.tree=ttk.Treeview(tf,style="T.Treeview",columns=cols,show="headings",yscrollcommand=vsb.set)
    vsb.configure(command=app.tree.yview)
    for col,txt,w in [("qr","QR",120),("district","Округ",100),("unit","В/ч",90),
                       ("rank","Звание",90),("name","ФИО",170),("phone","Телефон",110),
                       ("issued","Выдан",90),("days","Срок",65),("status","Статус",80)]:
        app.tree.heading(col,text=txt); app.tree.column(col,width=w,minwidth=40)
    app.tree.tag_configure("a",foreground=C["green"])
    app.tree.tag_configure("i",foreground=C["red"])
    app.tree.pack(fill="both",expand=True)
    app.tree.bind("<Double-1>",lambda e:app._card(app.tree))
    app._load_list()

    bf=tk.Frame(wrap,bg=C["bg"]); bf.pack(pady=10)
    Btn(bf,text=config["new_button"],cmd=lambda:show_add(app, pass_type),
        variant="success",w=170,h=38,bg=C["bg"]).pack(side="left",padx=6)
    Btn(bf,text="Карточка",cmd=lambda:app._card(app.tree),
        variant="ghost",w=150,h=38,bg=C["bg"]).pack(side="left",padx=6)
    if app.user["role"]=="admin":
        Btn(bf,text="Изменить",cmd=lambda:app._edit(app.tree),
            variant="primary",w=150,h=38,bg=C["bg"]).pack(side="left",padx=6)
        Btn(bf,text="История",cmd=lambda:app._history(app.tree),
            variant="ghost",w=150,h=38,bg=C["bg"]).pack(side="left",padx=6)
        Btn(bf,text="Удалить",cmd=lambda:app._del(app.tree),
            variant="danger",w=150,h=38,bg=C["bg"]).pack(side="left",padx=6)


def _load_list(app,search=""):
    for i in app.tree.get_children(): app.tree.delete(i)
    pass_type=getattr(app, "_pass_list_type", PASS_TYPE_REGULAR)
    status_filter=getattr(app, "_pass_status", tk.StringVar(value="Все")).get()
    unit_filter=getattr(app, "_pass_unit", tk.StringVar(value="Все")).get()
    date_from=_parse_iso_date(getattr(app, "_pass_date_from", tk.StringVar(value="")).get())
    date_to=_parse_iso_date(getattr(app, "_pass_date_to", tk.StringVar(value="")).get())
    sort_mode=getattr(app, "_pass_sort", tk.StringVar(value="Дата: новые")).get()
    rows=[]
    for row in search_passes(app.db, search, deleted=0, pass_type=pass_type):
        ok,left,_ = pass_status(app.db, row)
        name=f"{row[CI['ln']] or ''} {row[CI['fn']] or ''} {row[CI['mn']] or ''}".strip()
        issued_date=_parse_iso_date(row[CI["issued"]])
        if status_filter=="Активные" and not ok:
            continue
        if status_filter=="Истекшие" and ok:
            continue
        if unit_filter!="Все" and (row[CI["unit"]] or "")!=unit_filter:
            continue
        if date_from and (not issued_date or issued_date < date_from):
            continue
        if date_to and (not issued_date or issued_date > date_to):
            continue
        dc=row[CI["days"]] or 30
        dl="Мес." if dc==30 else f"{dc}сут"
        try:
            iss=datetime.strptime(row[CI["issued"]][:10],"%Y-%m-%d").strftime("%d.%m.%y")
        except Exception:
            logger.warning("Invalid issued_date format in pass list: %s", row[CI["issued"]])
            iss=row[CI["issued"]] or ""
        rows.append({
            "ok": ok,
            "issued_date": issued_date,
            "name": name,
            "unit": row[CI["unit"]] or "",
            "values": (row[CI["qr"]],row[CI["district"]],row[CI["unit"]],
                       row[CI["rank"]],name,row[CI["phone"]],
                       iss,dl,"✓" if ok else "✗"),
        })
    if sort_mode=="Дата: старые":
        rows.sort(key=lambda item: item["issued_date"] or datetime.min.date())
    elif sort_mode=="ФИО":
        rows.sort(key=lambda item: item["name"].lower())
    elif sort_mode=="В/ч":
        rows.sort(key=lambda item: item["unit"].lower())
    elif sort_mode=="Статус":
        rows.sort(key=lambda item: item["ok"], reverse=True)
    else:
        rows.sort(key=lambda item: item["issued_date"] or datetime.min.date(), reverse=True)
    for item in rows:
        app.tree.insert("","end",tags=("a" if item["ok"] else "i",),values=item["values"])
    _update_pass_stats(app)


def _selected_qr(app, tree):
    sel=tree.selection()
    if not sel:
        app._toast("Выберите строку")
        return None
    return tree.item(sel[0])["values"][0]


def _pass_name(row):
    return " ".join(filter(None, [row[CI["ln"]], row[CI["fn"]], row[CI["mn"]]]))


def _display_date(value):
    if not value:
        return ""
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").strftime("%d.%m.%Y")
    except (TypeError, ValueError):
        return str(value)


def _days_text(value):
    try:
        days=int(value or 30)
    except (TypeError, ValueError):
        days=30
    if days == 30:
        return "Месяц"
    if days == 180:
        return "6 месяцев"
    return f"{days} сут."


def _status_text(db, row):
    active, left, expires = pass_status(db, row)
    if active:
        if left is None:
            text = "Активен"
        elif left == 0:
            text = "Активен, истекает сегодня"
        else:
            text = f"Активен, осталось {left} дн."
        color = C["green"]
    else:
        text = "Истёк или отключён"
        color = C["red"]
    expires_text = expires.strftime("%d.%m.%Y") if expires else "не рассчитано"
    return text, expires_text, color


def _image_slot(parent, title, size=(220, 220)):
    wrap=tk.Frame(parent,bg=C["panel"])
    wrap.pack(fill="x",pady=(0,14))
    tk.Label(wrap,text=title,bg=C["panel"],fg=C["muted"],font=(F,9)).pack(anchor="w",pady=(0,5))
    box=tk.Frame(wrap,bg=C["input"],highlightthickness=1,highlightbackground=C["border"],
                 width=size[0],height=size[1])
    box.pack(anchor="w")
    box.pack_propagate(False)
    label=tk.Label(box,text="",bg=C["input"],fg=C["muted"],font=(F,11),justify="center")
    label.pack(fill="both",expand=True)
    return label


def _set_slot_image(win, label, path, missing_text, size=(210, 210)):
    if not path or not path.exists():
        label.configure(image="",text=missing_text)
        return
    try:
        image=Image.open(path).convert("RGBA")
        image.thumbnail(size)
        tk_image=ImageTk.PhotoImage(image)
        win._pass_card_images.append(tk_image)
        label.configure(image=tk_image,text="")
    except Exception as ex:
        logger.exception("Failed to show pass card image: %s", path)
        label.configure(image="",text=f"Не удалось открыть\n{ex}")


def _detail_row(parent, title, value, color=None):
    row=tk.Frame(parent,bg=C["panel"])
    row.pack(fill="x",pady=4)
    tk.Label(row,text=title,bg=C["panel"],fg=C["muted"],font=(F,10),
             width=14,anchor="w").pack(side="left")
    tk.Label(row,text=value or "—",bg=C["panel"],fg=color or C["text"],font=(F,11,"bold"),
             anchor="w",justify="left",wraplength=430).pack(side="left",fill="x",expand=True)


def _history_preview(parent, rows):
    tk.Label(parent,text="Последние действия",bg=C["panel"],fg=C["muted"],font=(F,10)).pack(anchor="w",pady=(14,6))
    box=tk.Frame(parent,bg=C["input"],highlightthickness=1,highlightbackground=C["border"])
    box.pack(fill="x")
    if not rows:
        tk.Label(box,text="Истории пока нет",bg=C["input"],fg=C["muted"],font=(F,10)).pack(anchor="w",padx=12,pady=10)
        return
    for row in rows[:5]:
        timestamp, username, role, action, _entity_type, _entity_id, details = row
        actor = username if not role or role == username else f"{username} ({role})"
        item=tk.Frame(box,bg=C["input"])
        item.pack(fill="x",padx=12,pady=(8,0))
        tk.Label(item,text=f"{timestamp}  {actor}",bg=C["input"],fg=C["muted"],font=(F,9),
                 anchor="w").pack(fill="x")
        tk.Label(item,text=f"{action_title(action)}  {_compact_details(details)}".strip(),
                 bg=C["input"],fg=C["text"],font=(F,10),anchor="w",justify="left",
                 wraplength=520).pack(fill="x",pady=(1,7))


def _show_history_for_qr(app, qr):
    win=app._modal(f"История пропуска — {qr}",860,520)

    top=tk.Frame(win,bg=C["panel"])
    top.pack(fill="x",padx=24,pady=(16,8))
    tk.Label(top,text=f"QR: {qr}",bg=C["panel"],fg=C["text"],font=(F,14,"bold")).pack(side="left")

    tf=tk.Frame(win,bg=C["panel"])
    tf.pack(fill="both",expand=True,padx=24,pady=(0,12))
    vsb=ttk.Scrollbar(tf,orient="vertical")
    vsb.pack(side="right",fill="y")
    cols=("time","actor","action","details")
    history_tree=ttk.Treeview(tf,style="T.Treeview",columns=cols,show="headings",yscrollcommand=vsb.set,height=12)
    vsb.configure(command=history_tree.yview)
    for col,txt,w in [("time","Дата",150),("actor","Кто",160),("action","Действие",180),("details","Детали",360)]:
        history_tree.heading(col,text=txt)
        history_tree.column(col,width=w,minwidth=80)
    history_tree.pack(fill="both",expand=True)

    rows=list_entity_actions(app.db, "pass", qr)
    if not rows:
        history_tree.insert("", "end", values=("", "", "Истории пока нет", ""))
    for row in rows:
        timestamp, username, role, action, _entity_type, _entity_id, details = row
        actor = username if not role or role == username else f"{username} ({role})"
        history_tree.insert("", "end", values=(
            timestamp,
            actor,
            action_title(action),
            _compact_details(details),
        ))

    bf=tk.Frame(win,bg=C["panel"])
    bf.pack(fill="x",padx=24,pady=(0,18))
    Btn(bf,text="Закрыть",cmd=win.destroy,variant="primary",w=140,h=40,bg=C["panel"]).pack(side="right")


def _card(app, tree):
    qr=_selected_qr(app, tree)
    if not qr:
        return
    row=fetch_pass_by_qr(app.db, qr, include_deleted=True)
    if not row:
        app._toast("Пропуск не найден")
        return

    name=_pass_name(row)
    status, expires_text, status_color = _status_text(app.db, row)
    win=app._modal(f"Карточка пропуска — {qr}",900,650)
    win._pass_card_images=[]

    body=tk.Frame(win,bg=C["panel"])
    body.pack(fill="both",expand=True,padx=24,pady=18)

    left=tk.Frame(body,bg=C["panel"],width=250)
    left.pack(side="left",fill="y",padx=(0,22))
    left.pack_propagate(False)
    has_photo_block=(not is_temporary_pass(row)) and row[CI["type"]] == PASS_TYPE_SEMIANNUAL
    photo_label=_image_slot(left,"Фото",(220,260)) if has_photo_block else None
    qr_label=_image_slot(left,"QR",(220,220))

    if photo_label is not None:
        photo_path=pass_photo_source(row[CI["photo"]])
        _set_slot_image(win, photo_label, photo_path, "Фото не добавлено", size=(210,250))
    qr_path=qr_code_path(qr)
    if not qr_path.exists():
        try:
            save_qr_code(qr)
        except Exception:
            logger.exception("Failed to recreate QR for pass card: %s", qr)
    _set_slot_image(win, qr_label, qr_path, "QR не найден")

    right=tk.Frame(body,bg=C["panel"])
    right.pack(side="left",fill="both",expand=True)
    tk.Label(right,text=name or "Без ФИО",bg=C["panel"],fg=C["text"],font=(F,20,"bold"),
             anchor="w").pack(fill="x")
    tk.Label(right,text=qr,bg=C["panel"],fg=C["muted"],font=(F,11),anchor="w").pack(fill="x",pady=(2,12))

    details=tk.Frame(right,bg=C["panel"])
    details.pack(fill="x")
    _detail_row(details,"Статус",status,status_color)
    _detail_row(details,"Действует до",expires_text)
    _detail_row(details,"Округ",row[CI["district"]])
    _detail_row(details,"В/ч",row[CI["unit"]])
    _detail_row(details,"Звание",row[CI["rank"]])
    _detail_row(details,"Телефон",row[CI["phone"]])
    _detail_row(details,"Выдан",_display_date(row[CI["issued"]]))
    _detail_row(details,"Срок",_days_text(row[CI["days"]]))

    _history_preview(right, list_entity_actions(app.db, "pass", qr, limit=5))

    def open_edit():
        win.destroy()
        app._edit(tree)

    def open_history():
        win.destroy()
        _show_history_for_qr(app, qr)

    def delete_current():
        if not messagebox.askyesno("Удалить",f"Переместить «{name or qr}» в корзину?"):
            return
        soft_delete_pass(app.db, qr)
        safe_record_action(app.db, app.user, "pass.delete", "pass", qr, {"name": name})
        win.destroy()
        (app.show_semiannual if row[CI["type"]] == PASS_TYPE_SEMIANNUAL else app.show_list)()

    buttons=tk.Frame(win,bg=C["panel"])
    buttons.pack(fill="x",padx=24,pady=(0,18))
    Btn(buttons,text="Закрыть",cmd=win.destroy,variant="ghost",w=130,h=40,bg=C["panel"]).pack(side="right")
    if app.user and app.user.get("role")=="admin":
        Btn(buttons,text="Удалить",cmd=delete_current,variant="danger",w=130,h=40,bg=C["panel"]).pack(side="right",padx=(0,8))
        Btn(buttons,text="История",cmd=open_history,variant="ghost",w=130,h=40,bg=C["panel"]).pack(side="right",padx=(0,8))
        Btn(buttons,text="Изменить",cmd=open_edit,variant="primary",w=130,h=40,bg=C["panel"]).pack(side="right",padx=(0,8))


def _compact_details(details):
    if not details:
        return ""
    try:
        parsed = json.loads(details)
    except (TypeError, ValueError):
        text = str(details)
    else:
        if isinstance(parsed, dict):
            labels = {
                "name": "ФИО",
                "district": "Округ",
                "unit": "В/ч",
                "active": "Активен",
                "deleted": "Удалено",
                "errors": "Ошибки",
                "warnings": "Предупреждения",
            }
            parts = []
            for key, value in parsed.items():
                if isinstance(value, bool):
                    value = "да" if value else "нет"
                parts.append(f"{labels.get(key, key)}: {value}")
            text = "; ".join(parts)
        else:
            text = str(parsed)
    return text if len(text) <= 260 else text[:257] + "..."


def _history(app, tree):
    qr=_selected_qr(app, tree)
    if qr:
        _show_history_for_qr(app, qr)


def _edit(app,tree):
    sel=tree.selection()
    if not sel: app._toast("Выберите строку"); return
    qr=tree.item(sel[0])["values"][0]
    row=fetch_pass_by_qr(app.db, qr, include_deleted=True)
    if not row: return
    pass_type = row[CI["type"]] or PASS_TYPE_REGULAR
    config = PASS_PAGE_CONFIGS.get(pass_type, PASS_PAGE_CONFIGS[PASS_TYPE_REGULAR])

    win=app._modal(f"{config['edit_title']} — {qr}",560,700 if config["photo"] else 620)
    di_e=_field(win,"Округ *",       row[CI["district"]] or "")
    un_e=_field(win,"В/ч *",         row[CI["unit"]]     or "")
    rk_e=_field(win,"Звание",        row[CI["rank"]]     or "")
    ln_e=_field(win,"Фамилия *",     row[CI["ln"]]       or "")
    fn_e=_field(win,"Имя",           row[CI["fn"]]       or "")
    mn_e=_field(win,"Отчество",      row[CI["mn"]]       or "")
    ph_e=_field(win,"Телефон",       row[CI["phone"]]    or "")
    is_e=_field(win,"Дата выдачи (ГГГГ-ММ-ДД)", row[CI["issued"]] or "")

    tk.Label(win,text="Срок пропуска",bg=C["panel"],fg=C["muted"],font=(F,9)).pack(anchor="w",padx=28,pady=(10,4))
    dv=tk.IntVar(value=config["days"])
    tk.Label(win,text=config["days_label"],bg=C["panel"],fg=C["accent"],font=(F,12,"bold")).pack(anchor="w",padx=28)

    av=tk.BooleanVar(value=bool(row[CI["active"]]))
    cbf=tk.Frame(win,bg=C["panel"]); cbf.pack(anchor="w",padx=28,pady=8)
    tk.Checkbutton(cbf,text="Активен",variable=av,bg=C["panel"],fg=C["text"],
                   selectcolor=C["input"],activebackground=C["panel"],font=(F,12)).pack(side="left")

    ph=[row[CI["photo"]]]
    if config["photo"]:
        phl=tk.Label(win,text=_photo_label(ph[0], "нет"),
                     bg=C["panel"],fg=C["muted"],font=(F,9))
        phl.pack(anchor="w",padx=28)
        def pick():
            f=filedialog.askopenfilename(filetypes=[("Images","*.jpg *.png *.jpeg")])
            if f: ph[0]=f; phl.configure(text=_photo_label(f))
        def camera_pick():
            _capture_photo(app, lambda path: (ph.__setitem__(0, path), phl.configure(text=_photo_label(path))))
        photo_buttons=tk.Frame(win,bg=C["panel"])
        photo_buttons.pack(fill="x",padx=28,pady=4)
        Btn(photo_buttons,text="Сменить фото",cmd=pick,variant="ghost",w=244,h=36,bg=C["panel"]).pack(side="left")
        Btn(photo_buttons,text="С камеры",cmd=camera_pick,variant="primary",w=244,h=36,bg=C["panel"]).pack(side="right")

    def save():
        data = {
            "qr_code": qr,
            "district": di_e.get(),
            "unit": un_e.get(),
            "rank": rk_e.get(),
            "last_name": ln_e.get(),
            "first_name": fn_e.get(),
            "middle_name": mn_e.get(),
            "phone": ph_e.get(),
            "issued_date": is_e.get(),
            "days_count": dv.get(),
            "photo_path": ph[0] if config["photo"] else None,
            "active": av.get(),
        }
        try:
            data = validate_pass_data(data, app.db, existing_qr=qr, require_photo=config["photo"])
            photo_path = _copy_photo_for_qr(ph[0], qr, row[CI["photo"]]) if config["photo"] else None
            update_pass(app.db, qr, {
                "district": data["district"],
                "unit": data["unit"],
                "rank": data["rank"],
                "last_name": data["last_name"],
                "first_name": data["first_name"],
                "middle_name": data["middle_name"],
                "phone": data["phone"],
                "issued_date": data["issued_date"],
                "days_count": data["days_count"],
                "photo_path": photo_path,
                "active": data["active"],
            })
            safe_record_action(app.db, app.user, "pass.update", "pass", qr, {
                "name": f"{data['last_name']} {data['first_name']} {data['middle_name']}".strip(),
                "district": data["district"],
                "unit": data["unit"],
                "active": bool(data["active"]),
            })
        except ValidationError as ex:
            messagebox.showerror("Проверьте данные", format_validation_errors(ex))
            return
        except sqlite3.IntegrityError as ex:
            logger.exception("Failed to update pass due to database constraint: %s", qr)
            messagebox.showerror("\u041e\u0448\u0438\u0431\u043a\u0430 \u0411\u0414", f"\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u0441\u043e\u0445\u0440\u0430\u043d\u0438\u0442\u044c \u043f\u0440\u043e\u043f\u0443\u0441\u043a:\n{ex}")
            return
        except Exception as ex:
            logger.exception("Failed to update pass: %s", qr)
            messagebox.showerror("\u041e\u0448\u0438\u0431\u043a\u0430", f"\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u0441\u043e\u0445\u0440\u0430\u043d\u0438\u0442\u044c \u043f\u0440\u043e\u043f\u0443\u0441\u043a:\n{ex}")
            return
        win.destroy()
        app._toast("\u041f\u0440\u043e\u043f\u0443\u0441\u043a \u043e\u0431\u043d\u043e\u0432\u043b\u0451\u043d",C["green"])
        (app.show_semiannual if pass_type == PASS_TYPE_SEMIANNUAL else app.show_list)()
    Btn(win,text="Сохранить",cmd=save,variant="success",w=504,h=44,fs=13,
        bg=C["panel"]).pack(padx=28,pady=10)


def _del(app,tree):
    sel=tree.selection()
    if not sel: app._toast("Выберите строку"); return
    qr=tree.item(sel[0])["values"][0]
    nm=tree.item(sel[0])["values"][4]
    if messagebox.askyesno("Удалить",f"Переместить «{nm}» в корзину?"):
        row=fetch_pass_by_qr(app.db, qr, include_deleted=True)
        soft_delete_pass(app.db, qr)
        safe_record_action(app.db, app.user, "pass.delete", "pass", qr, {"name": nm})
        (app.show_semiannual if row and row[CI["type"]] == PASS_TYPE_SEMIANNUAL else app.show_list)()

# ─────────────────────────────────────────
#  ДОБАВИТЬ ПРОПУСК
# ─────────────────────────────────────────

def show_add(app, pass_type=PASS_TYPE_REGULAR):
    config = PASS_PAGE_CONFIGS.get(pass_type, PASS_PAGE_CONFIGS[PASS_TYPE_REGULAR])
    win=app._modal(config["add_title"],560,780 if config["photo"] else 680)
    di_e=_field(win,"Округ *")
    un_e=_field(win,"В/ч *")
    rk_e=_field(win,"Звание")
    ln_e=_field(win,"Фамилия *")
    fn_e=_field(win,"Имя")
    mn_e=_field(win,"Отчество")
    ph_e=_field(win,"Телефон")
    is_e=_field(win,"Дата выдачи (ГГГГ-ММ-ДД)",datetime.now().strftime("%Y-%m-%d"))

    dv=tk.IntVar(value=config["days"])
    tk.Label(win,text="Срок пропуска",bg=C["panel"],fg=C["muted"],font=(F,9)).pack(anchor="w",padx=28,pady=(12,4))
    tk.Label(win,text=config["days_label"],bg=C["panel"],fg=C["accent"],font=(F,12,"bold")).pack(anchor="w",padx=28)

    photo=[None]
    if config["photo"]:
        phl=tk.Label(win,text="Фото: не выбрано",bg=C["panel"],fg=C["muted"],font=(F,9))
        phl.pack(anchor="w",padx=28,pady=(10,2))
        def pick():
            f=filedialog.askopenfilename(filetypes=[("Images","*.jpg *.png *.jpeg")])
            if f: photo[0]=f; phl.configure(text=_photo_label(f))
        def camera_pick():
            _capture_photo(app, lambda path: (photo.__setitem__(0, path), phl.configure(text=_photo_label(path))))
        photo_buttons=tk.Frame(win,bg=C["panel"])
        photo_buttons.pack(fill="x",padx=28,pady=4)
        Btn(photo_buttons,text="Загрузить фото",cmd=pick,variant="ghost",w=244,h=36,bg=C["panel"]).pack(side="left")
        Btn(photo_buttons,text="С камеры",cmd=camera_pick,variant="primary",w=244,h=36,bg=C["panel"]).pack(side="right")

    def save():
        qid=f"{config['qr_prefix']}-{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
        data = {
            "qr_code": qid,
            "district": di_e.get(),
            "unit": un_e.get(),
            "rank": rk_e.get(),
            "last_name": ln_e.get(),
            "first_name": fn_e.get(),
            "middle_name": mn_e.get(),
            "phone": ph_e.get(),
            "issued_date": is_e.get(),
            "days_count": dv.get(),
            "photo_path": photo[0] if config["photo"] else None,
            "pass_type": pass_type,
        }
        try:
            data = validate_pass_data(data, app.db, require_photo=config["photo"])
            qid = data["qr_code"]
            data["pass_type"] = pass_type
            create_pass(app.db, data)
            save_qr_code(qid)
            if config["photo"] and photo[0]:
                data["photo_path"] = _copy_photo_for_qr(photo[0], qid)
                update_pass(app.db, qid, {
                    "district": data["district"],
                    "unit": data["unit"],
                    "rank": data["rank"],
                    "last_name": data["last_name"],
                    "first_name": data["first_name"],
                    "middle_name": data["middle_name"],
                    "phone": data["phone"],
                    "issued_date": data["issued_date"],
                    "days_count": data["days_count"],
                    "photo_path": data["photo_path"],
                    "active": 1,
                })
            safe_record_action(app.db, app.user, "pass.create", "pass", qid, {
                "name": f"{data['last_name']} {data['first_name']} {data['middle_name']}".strip(),
                "district": data["district"],
                "unit": data["unit"],
            })
        except ValidationError as ex:
            messagebox.showerror("Проверьте данные", format_validation_errors(ex))
            return
        except sqlite3.IntegrityError as ex:
            logger.exception("Failed to create pass due to database constraint: %s", qid)
            messagebox.showerror("\u041e\u0448\u0438\u0431\u043a\u0430 \u0411\u0414", f"\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u0441\u043e\u0437\u0434\u0430\u0442\u044c \u043f\u0440\u043e\u043f\u0443\u0441\u043a:\n{ex}")
            return
        except Exception as ex:
            logger.exception("Failed to create pass: %s", qid)
            try:
                delete_pass_forever(app.db, qid)
            except Exception:
                logger.exception("Failed to rollback pass after create error: %s", qid)
            messagebox.showerror("\u041e\u0448\u0438\u0431\u043a\u0430", f"\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u0441\u043e\u0437\u0434\u0430\u0442\u044c \u043f\u0440\u043e\u043f\u0443\u0441\u043a:\n{ex}")
            return
        win.destroy()
        app._toast(f"\u0421\u043e\u0437\u0434\u0430\u043d: {qid}",C["green"])
        (app.show_semiannual if pass_type == PASS_TYPE_SEMIANNUAL else app.show_list)()
    Btn(win,text=config["create_button"],cmd=save,variant="success",w=504,h=44,fs=13,
        bg=C["panel"]).pack(padx=28,pady=12)

# ─────────────────────────────────────────
#  ИМПОРТ ИЗ EXCEL
# ─────────────────────────────────────────
