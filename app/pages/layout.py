import tkinter as tk

from app.core.config import C, FONT as F
from app.core.logging import get_logger
from app.ui.widgets import Btn, Pulse, _sep

logger = get_logger(__name__)

def show_main(app):
    app._clr(app)
    if app._bgcv:
        try:
            app._bgcv.stop()
        except Exception:
            logger.exception("Failed to stop background canvas")
        app._bgcv=None

    # ── Сайдбар ──────────────────────────
    sb=tk.Frame(app,bg=C["panel"],width=230)
    sb.pack(side="left",fill="y"); sb.pack_propagate(False)

    # градиентная шапка сайдбара
    gbar=tk.Frame(sb,bg=C["panel"])
    gbar.pack(fill="x")
    for shade in ["#1a44bb","#2255cc","#3366ee","#2255cc","#1a44bb"]:
        tk.Frame(gbar,bg=shade,height=3).pack(side="left",fill="x",expand=True)

    lf=tk.Frame(sb,bg=C["panel"])
    lf.pack(fill="x",pady=24,padx=18)
    tk.Label(lf,text="Контроль\nпропусков",bg=C["panel"],fg=C["text"],
             font=(F,14,"bold"),justify="left").pack(anchor="w")
    tk.Label(lf,text="v4.0",bg=C["panel"],fg=C["muted"],font=(F,8)).pack(anchor="w")

    _sep(sb).pack(fill="x",padx=14)

    nav=[("🏠  Сканер",    app.show_scanner),
         ("⏱  Одноразовые",app.show_temporary),
         ("📋  Временные",  app.show_list),
         ("🪪  Полугодовые",app.show_semiannual),
         ("📥  Импорт",    app.show_import),
         ("🖨  Печать",    app.show_print),
         ("📊  Статистика",app.show_stats)]
    if app.user["role"]=="admin":
        nav.append(("👤  Пользователи",app.show_users))
        nav.append(("🧾  Аудит",app.show_audit))
        nav.append(("🗑  Корзина",app.show_trash))

    app._nav_items = []
    for txt,cmd in nav:
        app._nav_row(sb,txt,cmd)

    tk.Frame(sb,bg=C["panel"]).pack(fill="y",expand=True)
    _sep(sb).pack(fill="x",padx=14)

    # Шестерёнка
    app._gear_row(sb)

    _sep(sb).pack(fill="x",padx=14)
    uf=tk.Frame(sb,bg=C["panel"])
    uf.pack(fill="x",padx=16,pady=(12,10))
    Pulse(uf,C["green"],10,bg=C["panel"]).pack(side="left",padx=(0,8))
    user_text=tk.Frame(uf,bg=C["panel"])
    user_text.pack(side="left",fill="x",expand=True)
    tk.Label(user_text,text=app.user["name"],bg=C["panel"],fg=C["text"],font=(F,11,"bold"),anchor="w").pack(anchor="w")
    tk.Label(user_text,text=("администратор" if app.user["role"]=="admin" else "охрана"),
             bg=C["panel"],fg=C["muted"],font=(F,8),anchor="w").pack(anchor="w")

    Btn(sb,text="Выйти",cmd=app.show_login,variant="ghost",
        w=196,h=36,fs=11,bg=C["panel"]).pack(padx=16,pady=(0,16))

    # нижняя полоска сайдбара
    gb2=tk.Frame(sb,bg=C["panel"])
    gb2.pack(fill="x",side="bottom")
    for shade in ["#1a44bb","#2255cc","#3366ee","#2255cc","#1a44bb"]:
        tk.Frame(gb2,bg=shade,height=3).pack(side="left",fill="x",expand=True)

    # ── Правая часть ─────────────────────
    right=tk.Frame(app,bg=C["bg"])
    right.pack(side="left",fill="both",expand=True)

    tb=tk.Frame(right,bg=C["panel"],height=50)
    tb.pack(fill="x"); tb.pack_propagate(False)

    app._pgtitle=tk.Label(tb,bg=C["panel"],fg=C["text"],text="",font=(F,14,"bold"))
    app._pgtitle.pack(side="left",padx=28,pady=13)

    app._clklbl=tk.Label(tb,bg=C["panel"],fg=C["muted"],font=(F,11))
    app._clklbl.pack(side="right",padx=24)
    app._tick()

    _sep(right).pack(fill="x")
    app.content=tk.Frame(right,bg=C["bg"])
    app.content.pack(fill="both",expand=True)
    app.show_scanner()


def _nav_row(app,parent,text,cmd):
    f=tk.Frame(parent,bg=C["panel"],cursor="hand2"); f.pack(fill="x",padx=10,pady=1)
    bar=tk.Frame(f,bg=C["panel"],width=3); bar.pack(side="left",fill="y")
    lbl=tk.Label(f,text=text,bg=C["panel"],fg=C["mid"],font=(F,12),anchor="w")
    lbl.pack(side="left",fill="x",expand=True,padx=(13,10),pady=10)
    item={"frame":f,"label":lbl,"bar":bar,"active":False}
    app._nav_items.append(item)
    def paint(active=False, hover=False):
        bg=C["input"] if active or hover else C["panel"]
        fg=C["text"] if active or hover else C["mid"]
        accent=C["accent"] if active else (C["border"] if hover else C["panel"])
        f.configure(bg=bg); lbl.configure(bg=bg,fg=fg); bar.configure(bg=accent)
    def on(e): paint(item["active"], True)
    def off(e): paint(item["active"], False)
    def click(e):
        for nav_item in app._nav_items:
            nav_item["active"] = False
            nav_item["frame"].configure(bg=C["panel"])
            nav_item["label"].configure(bg=C["panel"],fg=C["mid"])
            nav_item["bar"].configure(bg=C["panel"])
        item["active"] = True
        paint(True, False)
        app._pgtitle.configure(text=text.strip()); cmd()
    for w in (f,lbl,bar):
        w.bind("<Enter>",on); w.bind("<Leave>",off); w.bind("<Button-1>",click)


def _gear_row(app,parent):
    f=tk.Frame(parent,bg=C["panel"],cursor="hand2"); f.pack(fill="x",padx=10,pady=1)
    bar=tk.Frame(f,bg=C["panel"],width=3); bar.pack(side="left",fill="y")
    lbl=tk.Label(f,text="⚙  Настройки",bg=C["panel"],fg=C["muted"],font=(F,12),anchor="w")
    lbl.pack(side="left",fill="x",expand=True,padx=(13,10),pady=10)
    def on(e): f.configure(bg=C["input"]); lbl.configure(bg=C["input"],fg=C["text"]); bar.configure(bg=C["accent"])
    def off(e): f.configure(bg=C["panel"]); lbl.configure(bg=C["panel"],fg=C["mid"]); bar.configure(bg=C["panel"])
    for w in (f,lbl,bar):
        w.bind("<Enter>",on); w.bind("<Leave>",off)
        w.bind("<Button-1>",lambda e:app.show_settings())

