import tkinter as tk
from tkinter import messagebox, ttk

from app.core.config import C, CFG, FONT as F, apply_theme, save_config
from app.core.logging import get_logger
from app.services.auth import PERMISSION_SETTINGS, has_permission
from app.services.audit import safe_record_action
from app.services.backups import create_backup, list_backups, prune_backups, restore_backup
from app.services.file_cleanup import cleanup_orphan_files, cleanup_totals, find_orphan_files
from app.services.integrity import check_database_integrity
from app.services.pass_db import connect_db, init_db
from app.services.reference_data import (REFERENCE_TITLES, add_reference_value,
                                         delete_reference_value, list_reference_values,
                                         sync_reference_values_from_passes)
from app.ui.widgets import Btn, _sep

logger = get_logger(__name__)


def _reason_title(reason):
    return {"auto": "Авто", "manual": "Вручную", "pre_restore": "Перед восстановлением"}.get(reason, reason)


def _format_size(size):
    for unit in ("Б", "КБ", "МБ", "ГБ"):
        if size < 1024 or unit == "ГБ":
            return f"{size:.1f} {unit}" if unit != "Б" else f"{size} {unit}"
        size /= 1024


def _show_integrity_check(app):
    win=app._modal("Проверка целостности базы",780,560)
    top=tk.Frame(win,bg=C["panel"])
    top.pack(fill="x",padx=24,pady=(16,8))
    tk.Label(top,text="Состояние данных",bg=C["panel"],fg=C["text"],font=(F,14,"bold")).pack(side="left")
    summary=tk.Label(top,text="",bg=C["panel"],fg=C["muted"],font=(F,10))
    summary.pack(side="right")

    tf=tk.Frame(win,bg=C["panel"])
    tf.pack(fill="both",expand=True,padx=24,pady=(0,12))
    vsb=ttk.Scrollbar(tf,orient="vertical")
    vsb.pack(side="right",fill="y")
    tree=ttk.Treeview(tf,style="T.Treeview",columns=("status","message"),show="headings",yscrollcommand=vsb.set,height=12)
    vsb.configure(command=tree.yview)
    for col,txt,w in [("status","Статус",120),("message","Проверка",560)]:
        tree.heading(col,text=txt)
        tree.column(col,width=w,minwidth=90)
    tree.tag_configure("ok",foreground=C["green"])
    tree.tag_configure("warning",foreground=C["yellow"])
    tree.tag_configure("error",foreground=C["red"])
    tree.pack(fill="both",expand=True)

    def load():
        report=check_database_integrity(app.db)
        safe_record_action(app.db, app.user, "integrity.check", "database", "passes.db", {
            "errors": report["errors"],
            "warnings": report["warnings"],
        })
        for item in tree.get_children():
            tree.delete(item)
        status_titles = {"ok": "OK", "warning": "Внимание", "error": "Ошибка"}
        for row in report["rows"]:
            level=row["level"]
            tree.insert("", "end", tags=(level,), values=(status_titles.get(level, level), row["message"]))
        color=C["red"] if report["errors"] else C["yellow"] if report["warnings"] else C["green"]
        summary.configure(
            text=f"Ошибок: {report['errors']}  Предупреждений: {report['warnings']}",
            fg=color,
        )

    load()
    bf=tk.Frame(win,bg=C["panel"])
    bf.pack(fill="x",padx=24,pady=(0,18))
    Btn(bf,text="Обновить",cmd=load,variant="primary",w=140,h=40,bg=C["panel"]).pack(side="right")
    Btn(bf,text="Закрыть",cmd=win.destroy,variant="ghost",w=140,h=40,bg=C["panel"]).pack(side="right",padx=(0,8))


def _show_file_cleanup(app):
    win=app._modal("Чистка файлов",760,560)
    top=tk.Frame(win,bg=C["panel"])
    top.pack(fill="x",padx=24,pady=(16,8))
    title=tk.Label(top,text="Лишние файлы",bg=C["panel"],fg=C["text"],font=(F,14,"bold"))
    title.pack(side="left")
    summary=tk.Label(top,text="",bg=C["panel"],fg=C["muted"],font=(F,10))
    summary.pack(side="right")

    tf=tk.Frame(win,bg=C["panel"])
    tf.pack(fill="both",expand=True,padx=24,pady=(0,12))
    vsb=ttk.Scrollbar(tf,orient="vertical")
    vsb.pack(side="right",fill="y")
    tree=ttk.Treeview(tf,style="T.Treeview",columns=("kind","name","size","path"),show="headings",yscrollcommand=vsb.set,height=12)
    vsb.configure(command=tree.yview)
    for col,txt,w in [("kind","Тип",90),("name","Файл",220),("size","Размер",90),("path","Путь",420)]:
        tree.heading(col,text=txt); tree.column(col,width=w,minwidth=70)
    tree.pack(fill="both",expand=True)
    files=[]

    def load():
        nonlocal files
        files=find_orphan_files(app.db)
        for item in tree.get_children(): tree.delete(item)
        for index,item in enumerate(files):
            tree.insert("", "end", iid=str(index), values=(
                "Фото" if item["kind"]=="photos" else "QR",
                item["name"],
                _format_size(item["size"]),
                str(item["path"]),
            ))
        totals=cleanup_totals(files)
        summary.configure(text=f"{totals['count']} файлов, {_format_size(totals['bytes'])}")

    def clean():
        if not files:
            app._toast("Лишних файлов нет",C["green"])
            return
        totals=cleanup_totals(files)
        if not messagebox.askyesno("Удалить лишние файлы",
                f"Удалить {totals['count']} лишних файлов на {_format_size(totals['bytes'])}?\n\n"
                "Будут удалены только файлы без связи с пропусками."):
            return
        result=cleanup_orphan_files(app.db)
        safe_record_action(app.db, app.user, "files.cleanup", "files", "orphans", {
            "deleted": len(result["deleted"]),
            "errors": len(result["errors"]),
            "bytes": result["bytes"],
        })
        load()
        if result["errors"]:
            messagebox.showwarning("Чистка завершена", f"Удалено: {len(result['deleted'])}\nОшибок: {len(result['errors'])}")
        else:
            app._toast(f"Удалено файлов: {len(result['deleted'])}",C["green"])

    load()
    bf=tk.Frame(win,bg=C["panel"])
    bf.pack(fill="x",padx=24,pady=(0,18))
    Btn(bf,text="Удалить лишние",cmd=clean,variant="danger",w=180,h=40,bg=C["panel"]).pack(side="left",padx=(0,8))
    Btn(bf,text="Обновить",cmd=load,variant="primary",w=140,h=40,bg=C["panel"]).pack(side="right")


def _show_backups(app):
    win=app._modal("Восстановление из бэкапа",760,560)
    top=tk.Frame(win,bg=C["panel"])
    top.pack(fill="x",padx=24,pady=(16,8))
    tk.Label(top,text="Архивы",bg=C["panel"],fg=C["text"],font=(F,14,"bold")).pack(side="left")

    tf=tk.Frame(win,bg=C["panel"])
    tf.pack(fill="both",expand=True,padx=24,pady=(0,12))
    vsb=ttk.Scrollbar(tf,orient="vertical")
    vsb.pack(side="right",fill="y")
    tree=ttk.Treeview(tf,style="T.Treeview",columns=("date","reason","name"),show="headings",yscrollcommand=vsb.set,height=12)
    vsb.configure(command=tree.yview)
    for col,txt,w in [("date","Дата",160),("reason","Причина",150),("name","Файл",380)]:
        tree.heading(col,text=txt); tree.column(col,width=w,minwidth=80)
    tree.pack(fill="both",expand=True)
    backups=[]

    def load():
        nonlocal backups
        backups=list_backups()
        for item in tree.get_children(): tree.delete(item)
        for idx,backup in enumerate(backups):
            tree.insert("", "end", iid=str(idx), values=(backup["created_at"], _reason_title(backup["reason"]), backup["name"]))

    def selected_backup():
        sel=tree.selection()
        if not sel:
            app._toast("Выберите бэкап"); return None
        return backups[int(sel[0])]

    def restore_selected():
        backup=selected_backup()
        if not backup: return
        if not messagebox.askyesno("Восстановить бэкап", f"Восстановить данные из «{backup['name']}»?\n\nТекущее состояние будет сохранено в отдельный бэкап."):
            return
        try:
            create_backup(app.db, "pre_restore", prune=False)
            app.db.close()
            restore_backup(backup["path"])
            app.db=connect_db()
            init_db(app.db)
            safe_record_action(app.db, app.user, "backup.restore", "backup", backup["name"])
            win.destroy()
            app._toast("Бэкап восстановлен",C["green"])
            app.show_main()
        except Exception as ex:
            logger.exception("Failed to restore backup: %s", backup["path"])
            messagebox.showerror("Ошибка", f"Не удалось восстановить бэкап:\n{ex}")
            try:
                app.db=connect_db()
                init_db(app.db)
            except Exception:
                logger.exception("Failed to reconnect database after restore error")

    def prune_now():
        removed=prune_backups()
        safe_record_action(app.db, app.user, "backup.prune", "backup", "old", {
            "removed": len(removed),
            "files": [path.name for path in removed],
        })
        load()
        app._toast(f"Удалено старых бэкапов: {len(removed)}", C["green"])

    load()
    bf=tk.Frame(win,bg=C["panel"])
    bf.pack(fill="x",padx=24,pady=(0,18))
    Btn(bf,text="Восстановить",cmd=restore_selected,variant="danger",w=180,h=40,bg=C["panel"]).pack(side="left",padx=(0,8))
    Btn(bf,text="Очистить старые",cmd=prune_now,variant="ghost",w=180,h=40,bg=C["panel"]).pack(side="left",padx=8)
    Btn(bf,text="Обновить",cmd=load,variant="primary",w=140,h=40,bg=C["panel"]).pack(side="right")


def _show_reference_catalogs(app):
    win=app._modal("Справочники",760,560)
    reverse_titles={title: kind for kind,title in REFERENCE_TITLES.items()}
    kind_var=tk.StringVar(value=REFERENCE_TITLES["district"])

    top=tk.Frame(win,bg=C["panel"])
    top.pack(fill="x",padx=24,pady=(16,10))
    tk.Label(top,text="Справочник",bg=C["panel"],fg=C["muted"],font=(F,9)).pack(anchor="w")
    kind_box=ttk.Combobox(top,textvariable=kind_var,values=list(reverse_titles),state="readonly",width=28)
    kind_box.pack(anchor="w",ipady=3,pady=(4,0))

    editor=tk.Frame(win,bg=C["panel"])
    editor.pack(fill="x",padx=24,pady=(0,10))
    value_var=tk.StringVar()
    value_entry=tk.Entry(editor,bg=C["input"],fg=C["text"],insertbackground=C["accent"],
                         textvariable=value_var,relief="flat",font=(F,12),
                         highlightthickness=1,highlightbackground=C["border"])
    value_entry.pack(side="left",fill="x",expand=True,ipady=8,padx=(0,8))

    tf=tk.Frame(win,bg=C["panel"])
    tf.pack(fill="both",expand=True,padx=24,pady=(0,12))
    vsb=ttk.Scrollbar(tf,orient="vertical")
    vsb.pack(side="right",fill="y")
    tree=ttk.Treeview(tf,style="T.Treeview",columns=("value",),show="headings",yscrollcommand=vsb.set,height=12)
    vsb.configure(command=tree.yview)
    tree.heading("value",text="Значение")
    tree.column("value",width=640,minwidth=240)
    tree.pack(fill="both",expand=True)

    def current_kind():
        return reverse_titles.get(kind_var.get(), "district")

    def load():
        for item in tree.get_children():
            tree.delete(item)
        for value in list_reference_values(app.db, current_kind()):
            tree.insert("", "end", values=(value,))

    def add_value():
        value=value_var.get()
        if not value.strip():
            app._toast("Введите значение")
            return
        inserted=add_reference_value(app.db, current_kind(), value)
        safe_record_action(app.db, app.user, "references.add", "reference", current_kind(), {"value": value.strip()})
        value_var.set("")
        load()
        app._toast("Добавлено в справочник" if inserted else "Такое значение уже есть", C["green"] if inserted else C["yellow"])

    def delete_selected():
        sel=tree.selection()
        if not sel:
            app._toast("Выберите значение")
            return
        value=tree.item(sel[0])["values"][0]
        if not messagebox.askyesno("Удалить из справочника", f"Убрать «{value}» из подсказок?"):
            return
        delete_reference_value(app.db, current_kind(), value)
        safe_record_action(app.db, app.user, "references.delete", "reference", current_kind(), {"value": value})
        load()
        app._toast("Удалено из справочника", C["green"])

    def sync_values():
        sync_reference_values_from_passes(app.db)
        safe_record_action(app.db, app.user, "references.sync", "reference", "passes")
        load()
        app._toast("Справочники обновлены из базы", C["green"])

    Btn(editor,text="Добавить",cmd=add_value,variant="primary",w=120,h=40,bg=C["panel"]).pack(side="left")
    kind_box.bind("<<ComboboxSelected>>",lambda _e:load())
    value_entry.bind("<Return>",lambda _e:add_value())

    bf=tk.Frame(win,bg=C["panel"])
    bf.pack(fill="x",padx=24,pady=(0,18))
    Btn(bf,text="Удалить выбранное",cmd=delete_selected,variant="danger",w=180,h=40,bg=C["panel"]).pack(side="left",padx=(0,8))
    Btn(bf,text="Собрать из базы",cmd=sync_values,variant="ghost",w=170,h=40,bg=C["panel"]).pack(side="left",padx=8)
    Btn(bf,text="Закрыть",cmd=win.destroy,variant="primary",w=130,h=40,bg=C["panel"]).pack(side="right")
    load()


def show_settings(app):
    if not has_permission(app.user, PERMISSION_SETTINGS):
        app._toast("Недостаточно прав")
        return
    win=app._modal("⚙  Настройки",480,760 if app.user and app.user.get("role")=="admin" else 360)

    tk.Label(win,text="Тема оформления",bg=C["panel"],fg=C["muted"],font=(F,9)).pack(anchor="w",padx=28,pady=(20,8))
    tf=tk.Frame(win,bg=C["panel"]); tf.pack(anchor="w",padx=28)

    for val,ico,txt in [("dark","🌙","Тёмная"),("light","☀️","Светлая")]:
        sel=CFG["theme"]==val
        fb=tk.Frame(tf,bg=C["accent"] if sel else C["input"],
                    highlightthickness=1,
                    highlightbackground=C["accent"] if sel else C["border"],
                    cursor="hand2")
        fb.pack(side="left",padx=(0,10),ipadx=16,ipady=10)
        fl=tk.Label(fb,text=f"{ico}  {txt}",
                    bg=C["accent"] if sel else C["input"],
                    fg="#fff" if sel else C["mid"],font=(F,11,"bold" if sel else "normal"))
        fl.pack()
        def click(e,v=val):
            old_theme=CFG.get("theme")
            apply_theme(v)
            safe_record_action(app.db, app.user, "settings.update", "settings", "theme", {
                "old": old_theme,
                "new": v,
            })
            win.destroy(); app.show_main()
        fb.bind("<Button-1>",click); fl.bind("<Button-1>",click)

    _sep(win).pack(fill="x",padx=28,pady=20)

    tk.Label(win,text="Время отображения результата сканирования (секунд)",
             bg=C["panel"],fg=C["muted"],font=(F,9)).pack(anchor="w",padx=28,pady=(0,6))
    sf=tk.Frame(win,bg=C["panel"]); sf.pack(fill="x",padx=28)
    tv=tk.IntVar(value=CFG["scan_timeout"])
    tl=tk.Label(sf,text=f"{CFG['scan_timeout']} сек",
                bg=C["panel"],fg=C["accent"],font=(F,14,"bold"),width=7)
    tl.pack(side="right")
    def on_slide(v):
        tv.set(int(float(v))); tl.configure(text=f"{int(float(v))} сек")
    tk.Scale(sf,from_=3,to=30,orient="horizontal",variable=tv,
             bg=C["panel"],fg=C["text"],troughcolor=C["input"],
             activebackground=C["accent"],highlightthickness=0,
             sliderrelief="flat",showvalue=False,
             command=on_slide,length=280).pack(side="left",fill="x",expand=True)

    _sep(win).pack(fill="x",padx=28,pady=16)

    if app.user and app.user.get("role")=="admin":
        tk.Label(win,text="Резервная копия",bg=C["panel"],fg=C["muted"],font=(F,9)).pack(anchor="w",padx=28,pady=(0,6))

        def backup_now():
            try:
                path = create_backup(app.db, "manual")
                safe_record_action(app.db, app.user, "backup.create", "backup", path.name, {"reason": "manual"})
                app._toast(f"Бэкап создан: {path.name}", C["green"])
            except Exception as ex:
                logger.exception("Manual backup failed")
                messagebox.showerror("Ошибка", f"Не удалось создать бэкап:\n{ex}")

        Btn(win,text="Создать бэкап",cmd=backup_now,variant="primary",
            w=424,h=40,fs=12,bg=C["panel"]).pack(padx=28,pady=(0,12))
        Btn(win,text="Восстановить из бэкапа",cmd=lambda:(win.destroy(), _show_backups(app)),variant="ghost",
            w=424,h=40,fs=12,bg=C["panel"]).pack(padx=28,pady=(0,12))
        _sep(win).pack(fill="x",padx=28,pady=12)
        tk.Label(win,text="Данные",bg=C["panel"],fg=C["muted"],font=(F,9)).pack(anchor="w",padx=28,pady=(0,6))
        Btn(win,text="Проверить целостность базы",cmd=lambda:(win.destroy(), _show_integrity_check(app)),variant="primary",
            w=424,h=40,fs=12,bg=C["panel"]).pack(padx=28,pady=(0,12))
        Btn(win,text="Найти лишние файлы",cmd=lambda:(win.destroy(), _show_file_cleanup(app)),variant="ghost",
            w=424,h=40,fs=12,bg=C["panel"]).pack(padx=28,pady=(0,12))
        Btn(win,text="Справочники автоподстановки",cmd=lambda:(win.destroy(), _show_reference_catalogs(app)),variant="primary",
            w=424,h=40,fs=12,bg=C["panel"]).pack(padx=28,pady=(0,12))
        _sep(win).pack(fill="x",padx=28,pady=12)

    def save():
        old_timeout=CFG.get("scan_timeout")
        CFG["scan_timeout"]=tv.get(); save_config(CFG)
        safe_record_action(app.db, app.user, "settings.update", "settings", "scan_timeout", {
            "old": old_timeout,
            "new": tv.get(),
        })
        win.destroy(); app._toast("Настройки сохранены",C["green"])

    Btn(win,text="Сохранить",cmd=save,variant="success",
        w=424,h=44,fs=13,bg=C["panel"]).pack(padx=28,pady=8)

# ─────────────────────────────────────────
#  СКАНЕР
# ─────────────────────────────────────────
