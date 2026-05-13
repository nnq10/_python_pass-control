import tkinter as tk
from tkinter import ttk

from app.core.config import C, FONT as F
from app.services.auth import PERMISSION_AUDIT, has_permission
from app.services.audit import action_title, list_actions
from app.ui.widgets import Btn


def show_audit(app):
    if not has_permission(app.user, PERMISSION_AUDIT):
        app._toast("Недостаточно прав")
        return

    app._clr(app.content)
    app._pgtitle.configure(text="Аудит")
    wrap = tk.Frame(app.content, bg=C["bg"])
    wrap.pack(fill="both", expand=True, padx=36, pady=20)

    top = tk.Frame(wrap, bg=C["bg"])
    top.pack(fill="x", pady=(0, 12))
    tk.Label(top, text="Аудит действий", bg=C["bg"], fg=C["text"], font=(F, 16, "bold")).pack(side="left")

    sf = tk.Frame(top, bg=C["input"], highlightthickness=1, highlightbackground=C["border"])
    sf.pack(side="right")
    sv = tk.StringVar()
    se = tk.Entry(
        sf,
        bg=C["input"],
        fg=C["text"],
        insertbackground=C["accent"],
        textvariable=sv,
        relief="flat",
        font=(F, 12),
        width=28,
    )
    se.pack(side="left", ipady=7, padx=(10, 4))

    tf = tk.Frame(wrap, bg=C["panel"])
    tf.pack(fill="both", expand=True)
    vsb = ttk.Scrollbar(tf, orient="vertical")
    vsb.pack(side="right", fill="y")
    tree = ttk.Treeview(
        tf,
        style="T.Treeview",
        columns=("time", "user", "action", "entity", "details"),
        show="headings",
        yscrollcommand=vsb.set,
    )
    vsb.configure(command=tree.yview)
    for col, txt, width in [
        ("time", "Время", 150),
        ("user", "Пользователь", 150),
        ("action", "Действие", 170),
        ("entity", "Объект", 180),
        ("details", "Детали", 360),
    ]:
        tree.heading(col, text=txt)
        tree.column(col, width=width, minwidth=60)
    tree.pack(fill="both", expand=True)

    def load():
        for item in tree.get_children():
            tree.delete(item)
        for ts, username, role, action, entity_type, entity_id, details in list_actions(app.db, sv.get().strip()):
            actor = username or ""
            if role and role != "unknown":
                actor = f"{actor} ({role})" if actor else role
            entity = " / ".join(part for part in [entity_type, entity_id] if part)
            tree.insert("", "end", values=(ts, actor, action_title(action), entity, details or ""))

    se.bind("<Return>", lambda e: load())
    Btn(sf, text="Поиск", cmd=load, variant="primary", w=80, h=34, fs=10, bg=C["input"]).pack(
        side="left", padx=3
    )

    Btn(wrap, text="Обновить", cmd=load, variant="primary", w=140, h=38, fs=11, bg=C["bg"]).pack(
        anchor="e", pady=12
    )
    load()
