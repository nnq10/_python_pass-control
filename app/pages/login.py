import tkinter as tk

from app.core.config import C, FONT as F
from app.services.auth import authenticate
from app.ui.widgets import Btn, _field, _sep, typewrite

def show_login(app):
    app._clr(app); app._start_bg(app)
    card=tk.Frame(app,bg=C["panel"],highlightthickness=1,highlightbackground=C["border"])
    card.place(relx=0.5,rely=0.75,anchor="center",width=420,height=460)

    # Анимка
    def _slide(r=0.75,t=0.5):
        n=r+(t-r)*0.18
        card.place(relx=0.5,rely=n,anchor="center",width=420,height=460)
        if abs(n-t)>0.003: card.after(15,lambda:_slide(n,t))
        else: card.place(relx=0.5,rely=t,anchor="center",width=420,height=460)
    card.after(40,_slide)

    # Градик
    bar_f=tk.Frame(card,bg=C["panel"]); bar_f.pack(fill="x")
    for i,shade in enumerate(["#2255cc","#3366ee","#4477ff","#3366ee","#2255cc"]):
        tk.Frame(bar_f,bg=shade,height=3).pack(side="left",fill="x",expand=True)

    tk.Label(card,text="Контроль пропусков",bg=C["panel"],
             fg=C["text"],font=(F,21,"bold")).pack(pady=(26,3))
    sub=tk.Label(card,text="",bg=C["panel"],fg=C["muted"],font=(F,11))
    sub.pack(pady=(0,18))
    card.after(600,lambda:typewrite(sub,"Авторизуйтесь для входа",delay=38))

    _sep(card).pack(fill="x",padx=24)

    u_e=_field(card,"Логин",bg=C["panel"],placeholder="Имя пользователя")
    p_e=_field(card,"Пароль",show="●",bg=C["panel"],placeholder="Пароль")

    err=tk.Label(card,text="",bg=C["panel"],fg=C["red"],font=(F,10))
    err.pack(pady=(8,2))

    def login(ev=None):
        u="" if getattr(u_e, "_placeholder_on", False) else u_e.get().strip()
        p="" if getattr(p_e, "_placeholder_on", False) else p_e.get().strip()
        user = authenticate(u, p)
        if user:
            app.user=user
            app._go(app.show_main)
        else:
            err.configure(text="Неверный логин или пароль")
            card.after(2500,lambda:err.configure(text=""))

    p_e.bind("<Return>",login)
    u_e.bind("<Return>",lambda e:p_e.focus())

    Btn(card,text="Войти",cmd=login,variant="primary",
        w=364,h=44,fs=13,bg=C["panel"]).pack(padx=28,pady=12)
    # Нижний таскбар
    bar_b=tk.Frame(card,bg=C["panel"]); bar_b.pack(fill="x",side="bottom")
    for shade in ["#2255cc","#3366ee","#4477ff","#3366ee","#2255cc"]:
        tk.Frame(bar_b,bg=shade,height=3).pack(side="left",fill="x",expand=True)

