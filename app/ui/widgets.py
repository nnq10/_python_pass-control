import math
import random
import tkinter as tk
from tkinter import ttk

from app.core.config import C, CFG, FONT
from app.core.logging import get_logger


logger = get_logger(__name__)


class FloatBG(tk.Canvas):
    def __init__(self, parent, **kw):
        super().__init__(parent, bg=C["bg"], highlightthickness=0, **kw)
        self._pts = []
        self._on = False
        self.bind("<Configure>", lambda e: self._reset() if self._on else None)

    def start(self):
        self._on = True
        self._reset()
        self._tick()

    def stop(self):
        self._on = False

    def _reset(self):
        w, h = self.winfo_width(), self.winfo_height()
        if w < 10:
            return
        self.configure(bg=C["bg"])
        self.delete("all")
        self._pts = []
        tones = (
            ["#1e2a40", "#1a2236", "#1c2840"]
            if CFG["theme"] == "dark"
            else ["#dce8f8", "#ccd8f0", "#d8e4f8"]
        )
        for _ in range(10):
            r = random.randint(50, 130)
            self._pts.append(
                [
                    random.uniform(0, w),
                    random.uniform(0, h),
                    r,
                    random.uniform(-0.2, 0.2),
                    random.uniform(-0.15, 0.15),
                    random.choice(tones),
                ]
            )

    def _tick(self):
        if not self._on:
            return
        try:
            w, h = self.winfo_width(), self.winfo_height()
            if w < 10:
                self.after(60, self._tick)
                return
            self.delete("all")
            for p in self._pts:
                p[0] = (p[0] + p[3]) % w
                p[1] = (p[1] + p[4]) % h
                self.create_oval(
                    p[0] - p[2],
                    p[1] - p[2],
                    p[0] + p[2],
                    p[1] + p[2],
                    fill=p[5],
                    outline="",
                )
            self.after(48, self._tick)
        except Exception:
            logger.exception("Float background animation tick failed")


class Pulse(tk.Canvas):
    def __init__(self, parent, color=None, size=12, bg=None, **kw):
        super().__init__(
            parent,
            width=size,
            height=size,
            bg=bg or C["panel"],
            highlightthickness=0,
            **kw,
        )
        self._c = color or C["green"]
        self._sz = size
        self._ph = 0.0
        self._tick()

    def _tick(self):
        self.delete("all")
        r = self._sz / 2
        p = (1 + math.sin(self._ph)) / 2
        self.create_oval(
            r - r * (0.55 + 0.42 * p),
            r - r * (0.55 + 0.42 * p),
            r + r * (0.55 + 0.42 * p),
            r + r * (0.55 + 0.42 * p),
            outline=self._c,
            width=1,
        )
        self.create_oval(r - r * 0.32, r - r * 0.32, r + r * 0.32, r + r * 0.32, fill=self._c, outline="")
        self._ph += 0.09
        self.after(45, self._tick)


class Btn(tk.Frame):
    @staticmethod
    def _mix(a, b, t):
        return (
            f"#{int(int(a[1:3], 16) + t * (int(b[1:3], 16) - int(a[1:3], 16))):02x}"
            f"{int(int(a[3:5], 16) + t * (int(b[3:5], 16) - int(a[3:5], 16))):02x}"
            f"{int(int(a[5:7], 16) + t * (int(b[5:7], 16) - int(a[5:7], 16))):02x}"
        )

    def __init__(self, parent, text="", cmd=None, variant="primary", w=180, h=40, fs=12, bg=None, **kw):
        palette = {
            "primary": (C["accent"], "#fff"),
            "success": (C["green"], "#fff"),
            "danger": (C["red"], "#fff"),
            "ghost": (C["border"], C["mid"]),
            "warn": (C["yellow"], "#fff"),
        }
        self._bc, self._tc = palette.get(variant, palette["primary"])
        self._bcmd = cmd
        super().__init__(parent, width=w, height=h, bg=bg or C["bg"], highlightthickness=0, cursor="hand2", **kw)
        self.pack_propagate(False)
        self._inn = tk.Frame(self, bg=C["input"], highlightthickness=1, highlightbackground=self._bc)
        self._inn.pack(fill="both", expand=True)
        self._lbl = tk.Label(self._inn, text=text, bg=C["input"], fg=C["mid"], font=(FONT, fs, "bold"), cursor="hand2")
        self._lbl.pack(fill="both", expand=True)
        for widget in (self, self._inn, self._lbl):
            widget.bind("<Enter>", self._enter)
            widget.bind("<Leave>", self._leave)
            widget.bind("<ButtonPress-1>", self._press)
            widget.bind("<ButtonRelease-1>", self._rel)

    def _enter(self, e=None):
        self._inn.configure(bg=self._bc, highlightbackground=self._bc)
        self._lbl.configure(bg=self._bc, fg="#ffffff")

    def _leave(self, e=None):
        self._inn.configure(bg=C["input"], highlightbackground=self._bc)
        self._lbl.configure(bg=C["input"], fg=C["mid"])

    def _press(self, e=None):
        darker = self._mix(self._bc, "#000000", 0.2)
        self._inn.configure(bg=darker, highlightbackground=darker)
        self._lbl.configure(bg=darker, fg="#fff")

    def _rel(self, e=None):
        self._enter()
        if self._bcmd:
            self._bcmd()


def typewrite(lbl, text, delay=30, i=0):
    try:
        if not lbl.winfo_exists():
            return
        if i <= len(text):
            lbl.configure(text=text[:i] + ("▌" if i < len(text) else ""))
            lbl.after(delay, lambda: typewrite(lbl, text, delay, i + 1))
    except tk.TclError:
        return


def _sep(parent, color=None):
    return tk.Frame(parent, bg=color or C["border"], height=1)


def accent_bar(parent, height=3):
    bar = tk.Frame(parent, bg=C["panel"], height=height)
    bar.pack_propagate(False)
    for shade in ["#2255cc", "#3366ee", "#4477ff", "#3366ee", "#2255cc"]:
        tk.Frame(bar, bg=shade, height=height).pack(side="left", fill="both", expand=True)
    return bar


class FilterChip(tk.Frame):
    def __init__(self, parent, text, variable, value, command=None, width=None, bg=None, **kw):
        super().__init__(
            parent,
            bg=bg or C["panel"],
            highlightthickness=1,
            highlightbackground=C["border"],
            cursor="hand2",
            **kw,
        )
        self._text = text
        self._variable = variable
        self._value = value
        self._command = command
        self._hover = False
        self._label = tk.Label(
            self,
            text=text,
            bg=C["input"],
            fg=C["mid"],
            font=(FONT, 10, "bold"),
            padx=12,
            pady=8,
            cursor="hand2",
        )
        self._label.pack(fill="both", expand=True)
        if width:
            self.configure(width=width)
            self.pack_propagate(False)
        self._trace = variable.trace_add("write", lambda *_: self.refresh())
        for widget in (self, self._label):
            widget.bind("<Enter>", self._enter)
            widget.bind("<Leave>", self._leave)
            widget.bind("<ButtonRelease-1>", self._pick)
        self.bind("<Destroy>", self._cleanup, add="+")
        self.refresh()

    def refresh(self):
        active = self._variable.get() == self._value
        if active:
            fill = C["accent"]
            border = C["accent"]
            fg = "#ffffff"
        elif self._hover:
            fill = C["panel"]
            border = C["accent"]
            fg = C["text"]
        else:
            fill = C["input"]
            border = C["border"]
            fg = C["mid"]
        self.configure(bg=fill, highlightbackground=border)
        self._label.configure(bg=fill, fg=fg)

    def _enter(self, _event=None):
        self._hover = True
        self.refresh()

    def _leave(self, _event=None):
        self._hover = False
        self.refresh()

    def _pick(self, _event=None):
        if self._variable.get() != self._value:
            self._variable.set(self._value)
        if self._command:
            self._command()

    def _cleanup(self, event):
        if event.widget is self:
            try:
                self._variable.trace_remove("write", self._trace)
            except (tk.TclError, ValueError):
                pass


def _mk_entry(parent, show=None, placeholder=""):
    frm = tk.Frame(
        parent,
        bg=C["input"],
        highlightthickness=1,
        highlightbackground=C["border"],
        highlightcolor=C["accent"],
    )
    entry = tk.Entry(
        frm,
        bg=C["input"],
        fg=C["text"],
        insertbackground=C["accent"],
        relief="flat",
        font=(FONT, 12),
        highlightthickness=0,
    )
    entry._real_show = show or ""
    entry._placeholder = placeholder
    entry._placeholder_on = False

    def show_placeholder():
        if not placeholder or entry.get():
            return
        entry._placeholder_on = True
        entry.config(fg=C["muted"], show="")
        entry.insert(0, placeholder)

    def hide_placeholder():
        if not entry._placeholder_on:
            return
        entry.delete(0, tk.END)
        entry.config(fg=C["text"], show=entry._real_show)
        entry._placeholder_on = False

    if show:
        entry.config(show=show)
    entry.pack(padx=10, pady=7, fill="x")
    entry.bind("<FocusIn>", lambda ev: (frm.configure(highlightbackground=C["accent"]), hide_placeholder()))
    entry.bind("<FocusOut>", lambda ev: (frm.configure(highlightbackground=C["border"]), show_placeholder()))
    show_placeholder()
    return frm, entry


def _lbl(parent, text="", size=12, bold=False, color=None, bg=None, **kw):
    return tk.Label(
        parent,
        text=text,
        bg=bg or C["panel"],
        fg=color or C["text"],
        font=(FONT, size, "bold" if bold else "normal"),
        **kw,
    )


def _field(parent, title, default="", show=None, bg=None, placeholder=""):
    frame_bg = bg or C["panel"]
    tk.Label(parent, text=title, bg=frame_bg, fg=C["muted"], font=(FONT, 9)).pack(
        anchor="w",
        padx=28,
        pady=(10, 2),
    )
    frame, entry = _mk_entry(parent, show, placeholder)
    frame.pack(fill="x", padx=28)
    if default:
        if getattr(entry, "_placeholder_on", False):
            entry.delete(0, tk.END)
            entry.config(fg=C["text"], show=getattr(entry, "_real_show", ""))
            entry._placeholder_on = False
        entry.insert(0, default)
    return entry


def _suggest_field(parent, title, values=None, default="", bg=None):
    frame_bg = bg or C["panel"]
    all_values = list(values or [])
    tk.Label(parent, text=title, bg=frame_bg, fg=C["muted"], font=(FONT, 9)).pack(
        anchor="w",
        padx=28,
        pady=(10, 2),
    )
    frame = tk.Frame(
        parent,
        bg=C["input"],
        highlightthickness=1,
        highlightbackground=C["border"],
        highlightcolor=C["accent"],
    )
    frame.pack(fill="x", padx=28)
    box = ttk.Combobox(frame, values=all_values, state="normal", font=(FONT, 12))
    box.pack(fill="x", padx=8, pady=5, ipady=3)
    if default:
        box.set(default)

    def refresh(_event=None):
        typed = box.get().strip().casefold()
        matches = [item for item in all_values if typed in item.casefold()] if typed else all_values
        box.configure(values=matches or all_values)

    def focus_in(_event=None):
        frame.configure(highlightbackground=C["accent"])

    def focus_out(_event=None):
        frame.configure(highlightbackground=C["border"])

    box.bind("<KeyRelease>", refresh)
    box.bind("<FocusIn>", focus_in)
    box.bind("<FocusOut>", focus_out)
    box._all_suggestions = all_values
    return box
