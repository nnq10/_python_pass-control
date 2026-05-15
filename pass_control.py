"""Desktop application entry point for pass control."""
import tkinter as tk
from datetime import datetime
from tkinter import ttk

import customtkinter as ctk

from app.core.config import C, FONT as F
from app.core.logging import get_logger
from app.services.audit import safe_record_action
from app.services.backups import create_daily_backup_if_needed
from app.services.pass_db import connect_db, init_db
from app.core.paths import ensure_data_dirs
from app.ui.widgets import FloatBG, _sep
from app.pages import audit, import_page, layout, login, passes, print_page, scanner, settings, stats, temporary, trash, users

logger = get_logger(__name__)

class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Контроль пропусков")
        self.configure(fg_color=C["bg"])
        self.attributes("-fullscreen", True)
        self.bind("<Escape>", lambda e: self.attributes("-fullscreen", False))
        self._apply_tree_style()
        self.db = connect_db()
        init_db(self.db)
        ensure_data_dirs()
        self._auto_backup()
        self.user     = None
        self._bgcv    = None
        self._imgs    = []   # защита от GC
        self.show_login()

    # СТИЛИ
    def _apply_tree_style(self):
        s=ttk.Style(); s.theme_use("clam")
        s.configure("T.Treeview",background=C["panel"],foreground=C["text"],
                    fieldbackground=C["panel"],bordercolor=C["border"],
                    rowheight=32,font=(F,11))
        s.configure("T.Treeview.Heading",background=C["input"],foreground=C["mid"],
                    relief="flat",font=(F,11,"bold"))
        s.map("T.Treeview",background=[("selected",C["border"])],
              foreground=[("selected",C["accent"])])
        s.configure(
            "TCombobox",
            background=C["input"],
            fieldbackground=C["input"],
            foreground=C["text"],
            arrowcolor=C["accent"],
            bordercolor=C["border"],
            lightcolor=C["border"],
            darkcolor=C["border"],
            insertcolor=C["text"],
            padding=(8, 5),
        )
        s.map(
            "TCombobox",
            fieldbackground=[("readonly", C["input"]), ("focus", C["input"])],
            background=[("readonly", C["input"]), ("active", C["panel"])],
            foreground=[("readonly", C["text"])],
            bordercolor=[("focus", C["accent"]), ("readonly", C["border"])],
            lightcolor=[("focus", C["accent"]), ("readonly", C["border"])],
            darkcolor=[("focus", C["accent"]), ("readonly", C["border"])],
        )
        self.option_add("*TCombobox*Listbox.background", C["input"])
        self.option_add("*TCombobox*Listbox.foreground", C["text"])
        self.option_add("*TCombobox*Listbox.selectBackground", C["accent"])
        self.option_add("*TCombobox*Listbox.selectForeground", "#ffffff")

    def _auto_backup(self):
        try:
            path = create_daily_backup_if_needed(self.db)
            if path:
                safe_record_action(self.db, None, "backup.auto", "backup", path.name)
                logger.info("Daily backup created: %s", path)
        except Exception:
            logger.exception("Automatic backup failed")

    # ── БД ───────────────────────────────────
    # ── утилиты ──────────────────────────────
    def _clr(self, w):
        for ch in w.winfo_children(): ch.destroy()

    def _start_bg(self, parent):
        if self._bgcv:
            try:
                self._bgcv.stop(); self._bgcv.destroy()
            except Exception:
                logger.exception("Failed to stop previous background canvas")
        self._bgcv=FloatBG(parent)
        self._bgcv.place(x=0,y=0,relwidth=1,relheight=1)
        self._bgcv.after(120,self._bgcv.start)

    def _toast(self, msg, color=None):
        clr=color or C["red"]
        t=tk.Frame(self,bg=C["panel"],highlightthickness=1,highlightbackground=clr)
        t.place(relx=0.5,rely=0.94,anchor="center")
        tk.Label(t,text=f"  {msg}  ",bg=C["panel"],fg=clr,font=(F,12,"bold")).pack(padx=8,pady=10)
        def rm(n=12):
            if n>0: t.after(80,lambda:rm(n-1))
            else:
                try:
                    t.destroy()
                except Exception:
                    logger.exception("Failed to destroy toast widget")
        t.after(2200,rm)

    def _modal(self, title, w=540, h=640, scroll=False):
        win=tk.Toplevel(self); win.title(title)
        screen_w=max(800,self.winfo_screenwidth())
        screen_h=max(600,self.winfo_screenheight())
        width=min(w,screen_w-80)
        height=min(h,screen_h-80)
        x=max(20,(screen_w-width)//2)
        y=max(20,(screen_h-height)//2)
        win.geometry(f"{width}x{height}+{x}+{y}"); win.configure(bg=C["panel"])
        win.minsize(min(width,420),min(height,320))
        win.resizable(True,True)
        win.transient(self)
        win.lift()
        win.focus_force()

        def close_modal():
            if not win.winfo_exists():
                return
            win.destroy()

        win.protocol("WM_DELETE_WINDOW", close_modal)
        win.bind("<Escape>",lambda _e:close_modal())
        win._modal_close=close_modal
        hdr=tk.Frame(win,bg=C["input"])
        hdr.pack(fill="x")
        tk.Label(hdr,text=title,bg=C["input"],fg=C["text"],font=(F,13,"bold")).pack(side="left",padx=20,pady=14)
        close_btn=tk.Label(hdr,text="×",bg=C["input"],fg=C["muted"],font=(F,18,"bold"),cursor="hand2")
        close_btn.pack(side="right",padx=16,pady=8)
        close_btn.bind("<Enter>",lambda _e:close_btn.configure(fg=C["red"]))
        close_btn.bind("<Leave>",lambda _e:close_btn.configure(fg=C["muted"]))
        close_btn.bind("<ButtonRelease-1>",lambda _e:close_modal())
        _sep(win).pack(fill="x")
        if not scroll:
            return win

        shell=tk.Frame(win,bg=C["panel"])
        shell.pack(fill="both",expand=True)
        canvas=tk.Canvas(shell,bg=C["panel"],highlightthickness=0,bd=0)
        vsb=ttk.Scrollbar(shell,orient="vertical",command=canvas.yview)
        body=tk.Frame(canvas,bg=C["panel"])
        canvas_id=canvas.create_window((0,0),window=body,anchor="nw")
        canvas.configure(yscrollcommand=vsb.set)
        canvas.pack(side="left",fill="both",expand=True)
        vsb.pack(side="right",fill="y")

        def refresh_scroll(_event=None):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def resize_body(event):
            canvas.itemconfigure(canvas_id,width=event.width)

        def wheel(event):
            canvas.yview_scroll(int(-1*(event.delta/120)),"units")

        def bind_wheel(_event=None):
            win.bind_all("<MouseWheel>",wheel)

        def unbind_wheel(_event=None):
            try:
                win.unbind_all("<MouseWheel>")
            except tk.TclError:
                pass

        def cleanup(event):
            if event.widget is win:
                unbind_wheel()

        body.bind("<Configure>",refresh_scroll)
        canvas.bind("<Configure>",resize_body)
        canvas.bind("<Enter>",bind_wheel)
        canvas.bind("<Leave>",unbind_wheel)
        body.bind("<Enter>",bind_wheel)
        body.bind("<Leave>",unbind_wheel)
        win.bind("<Destroy>",cleanup,add="+")

        body._modal_window=win
        body._modal_close=close_modal
        return body

    def _close_modal(self, modal):
        close=getattr(modal,"_modal_close",None)
        if close:
            close()
            return
        try:
            modal.destroy()
        except tk.TclError:
            pass

    def _go(self, cb):
        ov=tk.Frame(self,bg=C["bg"]); ov.place(x=0,y=0,relwidth=1,relheight=1); ov.lift()
        def done(n=6):
            if n>0: ov.after(16,lambda:done(n-1))
            else: ov.destroy(); cb()
        ov.after(70,done)


    #  ЛОГИН
  
    def _tick(self):
        try:
            self._clklbl.configure(text=datetime.now().strftime("%d.%m.%Y  %H:%M:%S"))
            self.after(1000,self._tick)
        except Exception:
            logger.exception("Clock tick failed")

  
    #  НАСТРОЙКИ
    

    def show_login(self):
        return login.show_login(self)

    def show_main(self):
        return layout.show_main(self)

    def _nav_row(self, parent, text, cmd):
        return layout._nav_row(self, parent, text, cmd)

    def _gear_row(self, parent):
        return layout._gear_row(self, parent)

    def show_settings(self):
        return settings.show_settings(self)

    def show_scanner(self):
        return scanner.show_scanner(self)

    def _idle(self):
        return scanner._idle(self)

    def _scan(self, ev=None):
        return scanner._scan(self, ev)

    def _log(self, qr, name, ok):
        return scanner._log(self, qr, name, ok)

    def show_list(self):
        return passes.show_list(self)

    def show_semiannual(self):
        return passes.show_semiannual(self)

    def show_temporary(self):
        return temporary.show_temporary(self)

    def _load_list(self, search=""):
        return passes._load_list(self, search)

    def _card(self, tree):
        return passes._card(self, tree)

    def _edit(self, tree):
        return passes._edit(self, tree)

    def _history(self, tree):
        return passes._history(self, tree)

    def _del(self, tree):
        return passes._del(self, tree)

    def show_add(self):
        return passes.show_add(self)

    def show_import(self):
        return import_page.show_import(self)

    def show_print(self):
        return print_page.show_print(self)

    def show_stats(self):
        return stats.show_stats(self)

    def _export(self):
        return stats._export(self)

    def show_users(self):
        return users.show_users(self)

    def _user_modal(self, username=None, on_saved=None):
        return users._user_modal(self, username, on_saved)

    def show_audit(self):
        return audit.show_audit(self)

    def show_trash(self):
        return trash.show_trash(self)

    def _load_trash(self, search, tree):
        return trash._load_trash(self, search, tree)

    def _restore(self, tree):
        return trash._restore(self, tree)

    def _delete_forever(self, tree):
        return trash._delete_forever(self, tree)

    def _clear_trash(self, tree):
        return trash._clear_trash(self, tree)
    

if __name__ == "__main__":
    app = App()
    app.mainloop()
