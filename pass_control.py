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

    # ── стиль таблиц ─────────────────────────
    def _apply_tree_style(self):
        s=ttk.Style(); s.theme_use("clam")
        s.configure("T.Treeview",background=C["panel"],foreground=C["text"],
                    fieldbackground=C["panel"],bordercolor=C["border"],
                    rowheight=32,font=(F,11))
        s.configure("T.Treeview.Heading",background=C["input"],foreground=C["mid"],
                    relief="flat",font=(F,11,"bold"))
        s.map("T.Treeview",background=[("selected",C["border"])],
              foreground=[("selected",C["accent"])])

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

    def _modal(self, title, w=540, h=640):
        win=ctk.CTkToplevel(self); win.title(title)
        win.geometry(f"{w}x{h}"); win.configure(fg_color=C["panel"])
        win.transient(self); win.grab_set()
        hdr=tk.Frame(win,bg=C["input"])
        hdr.pack(fill="x")
        tk.Label(hdr,text=title,bg=C["input"],fg=C["text"],font=(F,13,"bold")).pack(side="left",padx=20,pady=14)
        _sep(win).pack(fill="x")
        return win

    def _go(self, cb):
        ov=tk.Frame(self,bg=C["bg"]); ov.place(x=0,y=0,relwidth=1,relheight=1); ov.lift()
        def done(n=6):
            if n>0: ov.after(16,lambda:done(n-1))
            else: ov.destroy(); cb()
        ov.after(70,done)

    # ─────────────────────────────────────────
    #  ЛОГИН
    # ─────────────────────────────────────────
    def _tick(self):
        try:
            self._clklbl.configure(text=datetime.now().strftime("%d.%m.%Y  %H:%M:%S"))
            self.after(1000,self._tick)
        except Exception:
            logger.exception("Clock tick failed")

    # ─────────────────────────────────────────
    #  НАСТРОЙКИ
    # ─────────────────────────────────────────

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
