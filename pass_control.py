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
from app.services.sounds import ensure_sounds_hint_file
from app.core.paths import app_path, ensure_data_dirs
from app.ui.widgets import FloatBG, _sep
from app.pages import audit, import_page, layout, login, passes, print_page, scanner, settings, stats, temporary, trash, users

logger = get_logger(__name__)
MIN_APP_WIDTH = 1100
MIN_APP_HEIGHT = 700

class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Контроль пропусков")
        self._apply_app_icon()
        self.configure(fg_color=C["bg"])
        self._is_fullscreen = False
        self._configure_main_window()
        self._apply_tree_style()
        self.db = connect_db()
        init_db(self.db)
        ensure_data_dirs()
        ensure_sounds_hint_file()
        self._auto_backup()
        self.user     = None
        self._bgcv    = None
        self._imgs    = []   # защита от GC
        self.show_login()

    def _configure_main_window(self):
        screen_w = max(800, self.winfo_screenwidth())
        screen_h = max(600, self.winfo_screenheight())
        min_w = min(MIN_APP_WIDTH, max(800, screen_w - 40))
        min_h = min(MIN_APP_HEIGHT, max(600, screen_h - 80))
        self.minsize(min_w, min_h)
        self.resizable(True, True)
        self.geometry(f"{min(screen_w, 1366)}x{min(screen_h, 768)}+0+0")
        self.after(50, self._maximize_window)
        self.after(350, self._ensure_large_window)
        self.bind("<F11>", self._toggle_fullscreen)
        self.bind("<Escape>", self._exit_fullscreen)

    def _maximize_window(self):
        try:
            self.update_idletasks()
            self.state("zoomed")
            return
        except tk.TclError:
            logger.info("Window zoomed state is unavailable, using geometry fallback")
        except Exception:
            logger.exception("Failed to maximize application window")
        self._fit_to_screen()

    def _fit_to_screen(self):
        screen_w = max(800, self.winfo_screenwidth())
        screen_h = max(600, self.winfo_screenheight())
        self.geometry(f"{screen_w}x{screen_h}+0+0")

    def _ensure_large_window(self):
        try:
            self.update_idletasks()
            screen_w = max(800, self.winfo_screenwidth())
            screen_h = max(600, self.winfo_screenheight())
            if self.winfo_width() < screen_w * 0.85 or self.winfo_height() < screen_h * 0.85:
                self._fit_to_screen()
        except Exception:
            logger.exception("Failed to verify application window size")

    def _toggle_fullscreen(self, _event=None):
        self._is_fullscreen = not self._is_fullscreen
        try:
            self.attributes("-fullscreen", self._is_fullscreen)
        except tk.TclError:
            logger.info("Fullscreen attribute is unavailable")
            self._maximize_window()

    def _exit_fullscreen(self, _event=None):
        if not self._is_fullscreen:
            return
        self._is_fullscreen = False
        try:
            self.attributes("-fullscreen", False)
        except tk.TclError:
            logger.info("Fullscreen attribute is unavailable")
        self._maximize_window()

    def _apply_app_icon(self):
        png_path = app_path("assets/app_icon.png")
        ico_path = app_path("assets/app_icon.ico")
        try:
            if ico_path.exists():
                self.iconbitmap(str(ico_path))
        except Exception:
            logger.exception("Failed to apply app ico: %s", ico_path)
        try:
            if png_path.exists():
                self._app_icon_image = tk.PhotoImage(file=str(png_path))
                self.iconphoto(True, self._app_icon_image)
        except Exception:
            logger.exception("Failed to apply app png icon: %s", png_path)

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
        width=min(w,int(screen_w*0.94),screen_w-40)
        height=min(h,int(screen_h*0.92),screen_h-60)
        x=max(20,(screen_w-width)//2)
        y=max(20,(screen_h-height)//2)
        win.geometry(f"{width}x{height}+{x}+{y}"); win.configure(bg=C["panel"])
        win.minsize(min(width,420),min(height,320))
        win.maxsize(screen_w-20,screen_h-40)
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
