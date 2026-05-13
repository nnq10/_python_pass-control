import os
import tkinter as tk
from tkinter import messagebox, ttk

from app.core.config import C, FONT as F
from app.core.logging import get_logger
from app.services.auth import PERMISSION_TRASH, has_permission
from app.services.audit import safe_record_action
from app.services.pass_db import (CI, clear_trash, delete_pass_forever, get_photo_path,
                     list_trash_file_refs, restore_pass, search_passes,
                     trash_counts)
from app.core.paths import app_path, qr_code_path
from app.ui.widgets import Btn

logger = get_logger(__name__)

def show_trash(app):
    if not has_permission(app.user, PERMISSION_TRASH):
        app._toast("Недостаточно прав")
        return
    app._clr(app.content)
    app._pgtitle.configure(text="Корзина")
    wrap=tk.Frame(app.content,bg=C["bg"])
    wrap.pack(fill="both",expand=True,padx=36,pady=20)

    # ── Заголовок + поиск ──────────────────────────
    top=tk.Frame(wrap,bg=C["bg"]); top.pack(fill="x",pady=(0,12))
    tk.Label(top,text="Корзина",bg=C["bg"],fg=C["text"],font=(F,16,"bold")).pack(side="left")

    sf=tk.Frame(top,bg=C["input"],highlightthickness=1,highlightbackground=C["border"])
    sf.pack(side="right")
    sv=tk.StringVar()
    se=tk.Entry(sf,bg=C["input"],fg=C["text"],insertbackground=C["accent"],
                textvariable=sv,relief="flat",font=(F,12),width=24)
    se.pack(side="left",ipady=7,padx=(10,4))
    se.bind("<Return>",lambda e:app._load_trash(sv.get(),tree))
    Btn(sf,text="Поиск",cmd=lambda:app._load_trash(sv.get(),tree),
        variant="primary",w=80,h=34,fs=10,bg=C["input"]).pack(side="left",padx=3)

    # ── Таблица ────────────────────────────────────
    tf=tk.Frame(wrap,bg=C["panel"]); tf.pack(fill="both",expand=True)
    vsb=ttk.Scrollbar(tf,orient="vertical"); vsb.pack(side="right",fill="y")
    tree=ttk.Treeview(tf,style="T.Treeview",
                      columns=("qr","district","unit","name","reason"),
                      show="headings",yscrollcommand=vsb.set)
    vsb.configure(command=tree.yview)
    for col,txt,w in [("qr","QR",150),("district","Округ",110),
                      ("unit","В/ч",100),("name","ФИО",210),("reason","Причина",110)]:
        tree.heading(col,text=txt); tree.column(col,width=w,minwidth=40)
    tree.tag_configure("d",foreground=C["red"])
    tree.tag_configure("e",foreground=C["yellow"])
    tree.pack(fill="both",expand=True)
    app._load_trash("",tree)

    # ── Кнопки действий ───────────────────────────
    bf=tk.Frame(wrap,bg=C["bg"]); bf.pack(pady=12)
    Btn(bf,text="Восстановить",cmd=lambda:app._restore(tree),
        variant="success",w=180,h=40,bg=C["bg"]).pack(side="left",padx=6)
    Btn(bf,text="Удалить навсегда",cmd=lambda:app._delete_forever(tree),
        variant="danger",w=180,h=40,bg=C["bg"]).pack(side="left",padx=6)
    Btn(bf,text="Очистить корзину",cmd=lambda:app._clear_trash(tree),
        variant="danger",w=180,h=40,bg=C["bg"]).pack(side="left",padx=6)


def _load_trash(app,search,tree):
    for i in tree.get_children(): tree.delete(i)
    # Удалённые вручную
    for row in search_passes(app.db, search, deleted=1):
        name=f"{row[CI['ln']] or ''} {row[CI['fn']] or ''}".strip()
        tree.insert("","end",tags=("d",),
                    values=(row[CI["qr"]],row[CI["district"]] or "",
                            row[CI["unit"]] or "",name,"Удалён"))
    # Просроченные (deleted=0, active=0)
    for row in search_passes(app.db, search, deleted=0, active=0):
        name=f"{row[CI['ln']] or ''} {row[CI['fn']] or ''}".strip()
        tree.insert("","end",tags=("e",),
                    values=(row[CI["qr"]],row[CI["district"]] or "",
                            row[CI["unit"]] or "",name,"Просрочен"))


def _restore(app,tree):
    sel=tree.selection()
    if not sel: app._toast("Выберите запись"); return
    qr=tree.item(sel[0])["values"][0]
    name=tree.item(sel[0])["values"][3]
    restore_pass(app.db, qr)
    safe_record_action(app.db, app.user, "pass.restore", "pass", qr, {"name": name})
    app._toast("Пропуск восстановлен",C["green"])
    app.show_trash()


def _delete_forever(app,tree):
    sel=tree.selection()
    if not sel: app._toast("Выберите запись"); return
    qr   = tree.item(sel[0])["values"][0]
    name = tree.item(sel[0])["values"][3]
    if not messagebox.askyesno("Удалить навсегда",
            f"Удалить «{name}» НАВСЕГДА?\n\nЭто действие необратимо."):
        return
    # Удаляем запись и QR-файл
    photo_path = get_photo_path(app.db, qr)
    if photo_path:
        try:
            os.remove(app_path(photo_path))
        except Exception:
            logger.exception("Failed to delete photo file: %s", photo_path)
    try:
        qr_file=qr_code_path(qr)
        if qr_file.exists(): os.remove(qr_file)
    except Exception:
        logger.exception("Failed to delete QR file for %s", qr)
    delete_pass_forever(app.db, qr)
    safe_record_action(app.db, app.user, "pass.delete_forever", "pass", qr, {"name": name})
    app._toast(f"«{name}» удалён навсегда",C["red"])
    app.show_trash()


def _clear_trash(app,tree):
    # Считаем сколько записей будет удалено
    n_del,n_exp=trash_counts(app.db)
    total=n_del+n_exp
    if total==0:
        app._toast("Корзина уже пуста",C["yellow"]); return
    if not messagebox.askyesno("Очистить корзину",
            f"Будет удалено навсегда {total} записей\n"
            f"({n_del} удалённых + {n_exp} просроченных).\n\n"
            "Это действие необратимо. Продолжить?"):
        return
    # Собираем все qr для удаления файлов
    for qr,ph in list_trash_file_refs(app.db):
        try:
            ph_path = app_path(ph) if ph else None
            if ph_path and ph_path.exists(): os.remove(ph_path)
            qf=qr_code_path(qr)
            if qf.exists(): os.remove(qf)
        except Exception:
            logger.exception("Failed to delete files for trashed pass: %s", qr)
    clear_trash(app.db)
    safe_record_action(app.db, app.user, "pass.delete_forever", "trash", "clear", {
        "deleted": n_del,
        "expired": n_exp,
        "total": total,
    })
    app._toast(f"Удалено {total} записей",C["red"])
    app.show_trash()


