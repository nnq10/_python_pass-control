import tkinter as tk
from datetime import datetime

from PIL import Image, ImageTk

from app.core.config import C, CFG, FONT as F
from app.core.logging import get_logger
from app.services.default_photo import pass_photo_source
from app.services.pass_db import CI, PASS_TYPE_SEMIANNUAL, fetch_pass_by_qr, log_scan, pass_status
from app.services.sounds import play_scan_sound
from app.services.validation import ValidationError, normalize_qr
from app.core.paths import app_path
from app.ui.widgets import _sep, typewrite

logger = get_logger(__name__)

def show_scanner(app):
    app._clr(app.content)
    app._pgtitle.configure(text="Сканер")
    app._imgs.clear()

    wrap=tk.Frame(app.content,bg=C["bg"])
    wrap.pack(fill="both",expand=True,padx=36,pady=28)

    # Поле ввода
    inp=tk.Frame(wrap,bg=C["panel"],highlightthickness=1,highlightbackground=C["border"])
    inp.pack(fill="x")
    tk.Label(inp,text="QR-код",bg=C["panel"],fg=C["muted"],font=(F,10)).pack(anchor="w",padx=18,pady=(14,2))
    app._qre=tk.Entry(inp,bg=C["panel"],fg=C["accent"],
                       insertbackground=C["accent"],relief="flat",
                       font=(F,22,"bold"),highlightthickness=0)
    app._qre.pack(fill="x",padx=18,ipady=8,pady=(0,4))
    app._qre.bind("<Return>",app._scan)
    app._qre.focus()
    tk.Label(inp,text="Введите или отсканируйте QR-код и нажмите Enter",
             bg=C["panel"],fg=C["muted"],font=(F,9)).pack(anchor="w",padx=18,pady=(0,12))

    _sep(wrap).pack(fill="x",pady=1)
    app._res=tk.Frame(wrap,bg=C["bg"])
    app._res.pack(fill="both",expand=True,pady=14)
    app._idle()


def _idle(app):
    app._clr(app._res)
    f=tk.Frame(app._res,bg=C["panel"],highlightthickness=1,highlightbackground=C["border"])
    f.pack(fill="both",expand=True)
    tk.Label(f,text="Ожидание сканирования...",bg=C["panel"],
             fg=C["muted"],font=(F,16)).pack(expand=True)


def _scan(app,ev=None):
    raw_qr=app._qre.get().strip()
    if not raw_qr: return
    try:
        qr=normalize_qr(raw_qr)
    except ValidationError as ex:
        app._qre.delete(0,tk.END)
        app._toast(ex.errors[0])
        return
    app._qre.delete(0,tk.END)

    row=fetch_pass_by_qr(app.db, qr)
    app._clr(app._res); app._imgs.clear()

    name,rank,unit,district,phone="Неизвестный","","","",""
    issued_str,days_lbl,days_left="","",None
    ok=False; photo=None

    if row:
        rank     = row[CI["rank"]]     or ""
        district = row[CI["district"]] or ""
        unit     = row[CI["unit"]]     or ""
        name     = f"{row[CI['ln']] or ''} {row[CI['fn']] or ''} {row[CI['mn']] or ''}".strip()
        phone    = row[CI["phone"]]    or ""
        photo    = pass_photo_source(row[CI["photo"]]) if row[CI["type"]] == PASS_TYPE_SEMIANNUAL else None
        issued_str = row[CI["issued"]] or ""
        ok, days_left, expires = pass_status(app.db, row)
        dc = row[CI["days"]] or 30
        days_lbl = "месяц" if dc==30 else f"{dc} сут."
        app._log(qr,name,ok)
    else:
        app._log(qr,"Неизвестный",False)

    play_scan_sound(ok)

    bg  = C["gg"] if ok else C["gr"]
    acc = C["green"] if ok else C["red"]
    status = "Вход разрешён  ✓" if ok else "Вход запрещён  ✗"

    # Карточка результата
    card=tk.Frame(app._res,bg=bg,highlightthickness=1,highlightbackground=acc)
    card.pack(fill="both",expand=True)

    # Цветная полоска сверху
    topbar=tk.Frame(card,bg=card["bg"]); topbar.pack(fill="x")
    for shade in (["#1db864","#2ec27e","#34d488","#2ec27e","#1db864"]
                  if ok else ["#c04455","#e05567","#f06070","#e05567","#c04455"]):
        tk.Frame(topbar,bg=shade,height=4).pack(side="left",fill="x",expand=True)

    body=tk.Frame(card,bg=bg)
    body.pack(fill="both",expand=True,padx=36,pady=18)

    # Статус — typewriter
    stlbl=tk.Label(body,text="",bg=bg,fg=acc,font=(F,28,"bold"))
    stlbl.pack(pady=(6,4))
    body.after(60,lambda:typewrite(stlbl,status,delay=22))

    _sep(body,acc).pack(fill="x",pady=10)

    # Строка: фото + данные
    row_f=tk.Frame(body,bg=bg); row_f.pack(fill="both",expand=True)

    # Фото
    if photo:
        ap=app_path(photo)
        if ap.exists():
            try:
                raw=Image.open(ap).convert("RGB").resize((170,170),Image.LANCZOS)
                tkimg=ImageTk.PhotoImage(raw); app._imgs.append(tkimg)
                pf=tk.Frame(row_f,bg=acc,padx=2,pady=2)
                pf.pack(side="left",padx=(0,22),pady=4)
                tk.Label(pf,image=tkimg,bg=acc).pack()
            except Exception:
                logger.exception("Failed to load pass photo: %s", photo)

    # Данные
    df=tk.Frame(row_f,bg=bg); df.pack(side="left",fill="both",expand=True)
    if rank:
        tk.Label(df,text=rank,bg=bg,fg=acc,font=(F,12),anchor="w").pack(anchor="w")
    tk.Label(df,text=name,bg=bg,fg=C["text"],font=(F,20,"bold"),anchor="w").pack(anchor="w",pady=(2,0))
    if district or unit:
        tk.Label(df,text="  ".join(filter(None,[district,unit])),
                 bg=bg,fg=C["mid"],font=(F,12),anchor="w").pack(anchor="w",pady=(4,0))
    if phone:
        tk.Label(df,text=f"☎  {phone}",bg=bg,fg=C["mid"],font=(F,11),anchor="w").pack(anchor="w",pady=(4,0))
    if issued_str:
        try:
            issued_fmt=datetime.strptime(issued_str[:10],"%Y-%m-%d").strftime("%d.%m.%Y")
        except Exception:
            logger.warning("Invalid issued_date format in scanner: %s", issued_str)
            issued_fmt=issued_str
        expire_txt=""
        if days_left is not None:
            expire_txt=f"   ·   осталось {days_left} дн." if days_left>=0 else "   ·   ПРОСРОЧЕН"
        tk.Label(df,text=f"Выдан: {issued_fmt}  ({days_lbl}){expire_txt}",
                 bg=bg,fg=acc,font=(F,11,"bold"),anchor="w").pack(anchor="w",pady=(8,0))

    tk.Label(body,text=datetime.now().strftime("%d.%m.%Y  %H:%M:%S"),
             bg=bg,fg=C["muted"],font=(F,10)).pack(anchor="e",pady=(8,0))

    ms=CFG.get("scan_timeout",8)*1000
    app.after(ms,app._idle)


def _log(app,qr,name,ok):
    log_scan(app.db, qr, name, ok)

# ─────────────────────────────────────────
#  СПИСОК ПРОПУСКОВ
# ─────────────────────────────────────────
