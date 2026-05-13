import tkinter as tk
from tkinter import messagebox, ttk

from PIL import ImageTk

from app.core.config import C, FONT as F
from app.core.paths import TEMPLATES_DIR
from app.services.audit import safe_record_action
from app.services.auth import PERMISSION_PRINT, has_permission
from app.services.pass_db import (CI, PASS_TYPE_REGULAR, PASS_TYPE_SEMIANNUAL,
                                  PASS_TYPE_TEMPORARY, fetch_pass_by_qr, pass_status,
                                  search_passes)
from app.services.print_passes import (list_print_templates, print_file, render_print_pass,
                                       save_batch_print_pdf, save_print_pdf, save_print_png,
                                       save_template_choice, selected_template_for_profile)
from app.pages.template_editor import open_template_editor
from app.ui.widgets import Btn, _sep


def _pass_name(row):
    return " ".join(filter(None, [row[CI["ln"]], row[CI["fn"]], row[CI["mn"]]]))


PRINT_PROFILE_TITLES = {
    PASS_TYPE_TEMPORARY: "Одноразовые",
    PASS_TYPE_REGULAR: "Временные",
    PASS_TYPE_SEMIANNUAL: "Полугодовые",
}


def _unique_qrs(qr_codes):
    result = []
    seen = set()
    for qr_code in qr_codes or []:
        qr_code = str(qr_code or "").strip()
        if qr_code and qr_code not in seen:
            result.append(qr_code)
            seen.add(qr_code)
    return result


def open_print_dialog(app, qr_codes, template_profile=None, title=None):
    if not has_permission(app.user, PERMISSION_PRINT):
        app._toast("Недостаточно прав")
        return
    qrs = _unique_qrs(qr_codes)
    if not qrs:
        app._toast("Выберите пропуск для печати")
        return

    profile_title = PRINT_PROFILE_TITLES.get(template_profile, "Пропуска")
    win = app._modal(title or f"Печать - {profile_title}", 980, 700)
    win._print_dialog_images = []

    body = tk.Frame(win, bg=C["panel"])
    body.pack(fill="both", expand=True, padx=18, pady=16)

    left = tk.Frame(body, bg=C["panel"], width=390)
    left.pack(side="left", fill="both", padx=(0, 14))
    left.pack_propagate(False)

    tk.Label(left, text=f"Выбрано: {len(qrs)}", bg=C["panel"], fg=C["muted"], font=(F, 10)).pack(anchor="w")
    tf = tk.Frame(left, bg=C["panel"])
    tf.pack(fill="both", expand=True, pady=(8, 12))
    vsb = ttk.Scrollbar(tf, orient="vertical")
    vsb.pack(side="right", fill="y")
    tree = ttk.Treeview(tf, style="T.Treeview", columns=("qr", "name", "unit"), show="headings",
                        yscrollcommand=vsb.set, selectmode="extended", height=12)
    vsb.configure(command=tree.yview)
    for col, text, width in [("qr", "QR", 120), ("name", "ФИО", 170), ("unit", "В/ч", 80)]:
        tree.heading(col, text=text)
        tree.column(col, width=width, minwidth=60)
    tree.pack(fill="both", expand=True)

    for qr in qrs:
        row = fetch_pass_by_qr(app.db, qr, include_deleted=True)
        tree.insert("", "end", values=(qr, _pass_name(row) if row else "", row[CI["unit"]] if row else ""))
    children = tree.get_children()
    if children:
        tree.selection_set(children)

    controls = tk.Frame(left, bg=C["panel"])
    controls.pack(fill="x")
    tk.Label(controls, text="Шаблон этой вкладки", bg=C["panel"], fg=C["muted"], font=(F, 9)).pack(anchor="w")
    template_var = tk.StringVar()
    template_box = ttk.Combobox(controls, textvariable=template_var, state="readonly", width=40)
    template_box.pack(fill="x", ipady=3, pady=(4, 8))
    template_paths = []

    right = tk.Frame(body, bg=C["panel"], highlightthickness=1, highlightbackground=C["border"])
    right.pack(side="left", fill="both", expand=True)
    tk.Label(right, text="Предпросмотр", bg=C["panel"], fg=C["muted"], font=(F, 10)).pack(anchor="w", padx=16, pady=(14, 8))
    preview = tk.Label(right, text="", bg=C["input"], fg=C["muted"], font=(F, 11))
    preview.pack(fill="both", expand=True, padx=16, pady=(0, 12))
    _sep(right).pack(fill="x", padx=16, pady=(0, 12))

    def refresh_templates():
        nonlocal template_paths
        template_paths = list_print_templates()
        names = [path.name for path in template_paths]
        template_box.configure(values=names)
        if not names:
            template_var.set("")
            preview.configure(text=f"Нет шаблонов в {TEMPLATES_DIR}", image="")
            return
        if template_var.get() not in names:
            selected = selected_template_for_profile(template_profile)
            template_var.set(selected.name if selected else names[0])

    def selected_template():
        name = template_var.get()
        for path in template_paths:
            if path.name == name:
                save_template_choice(template_profile, path)
                return path
        app._toast("Добавьте шаблон")
        return None

    def selected_qr():
        selection = tree.selection()
        if selection:
            return tree.item(selection[0])["values"][0]
        return qrs[0] if qrs else None

    def selected_qrs():
        selection = tree.selection()
        if selection:
            return [tree.item(item)["values"][0] for item in selection]
        return list(qrs)

    def build_preview():
        qr = selected_qr()
        template = selected_template()
        if not qr or not template:
            return None, None
        try:
            image = render_print_pass(app.db, qr, template)
        except Exception as ex:
            messagebox.showerror("Печать", f"Не удалось построить предпросмотр:\n{ex}")
            return None, None
        shown = image.copy()
        shown.thumbnail((500, 420))
        tk_image = ImageTk.PhotoImage(shown)
        win._print_dialog_images = [tk_image]
        preview.configure(image=tk_image, text="")
        return image, qr

    def edit_template():
        template = selected_template()
        if not template:
            return
        open_template_editor(app, template, on_saved=lambda: build_preview())

    def save_png():
        image, qr = build_preview()
        if image is None:
            return
        path = save_print_png(image, qr)
        safe_record_action(app.db, app.user, "print.png", "pass", qr, {"file": path.name, "profile": template_profile})
        app._toast(f"PNG сохранён: {path.name}", C["green"])

    def save_pdf():
        image, qr = build_preview()
        if image is None:
            return
        path = save_print_pdf(image, qr)
        safe_record_action(app.db, app.user, "print.pdf", "pass", qr, {"file": path.name, "profile": template_profile})
        app._toast(f"PDF сохранён: {path.name}", C["green"])

    def send_print():
        image, qr = build_preview()
        if image is None:
            return
        try:
            path = save_print_pdf(image, qr)
            print_file(path)
            safe_record_action(app.db, app.user, "print.send", "pass", qr, {"file": path.name, "profile": template_profile})
            app._toast("Отправлено на печать", C["green"])
        except Exception as ex:
            messagebox.showerror("Печать", f"Не удалось отправить на печать:\n{ex}")

    def save_batch_pdf():
        selected = selected_qrs()
        template = selected_template()
        if not selected or not template:
            return
        try:
            path = save_batch_print_pdf(app.db, selected, template)
            safe_record_action(app.db, app.user, "print.batch_pdf", "passes", len(selected), {
                "file": path.name,
                "count": len(selected),
                "layout": "a4_10x6",
                "profile": template_profile,
            })
            app._toast(f"PDF A4 создан: {path.name}", C["green"])
        except Exception as ex:
            messagebox.showerror("Печать A4", f"Не удалось создать PDF:\n{ex}")

    def print_batch():
        selected = selected_qrs()
        template = selected_template()
        if not selected or not template:
            return
        try:
            path = save_batch_print_pdf(app.db, selected, template)
            print_file(path)
            safe_record_action(app.db, app.user, "print.batch_send", "passes", len(selected), {
                "file": path.name,
                "count": len(selected),
                "layout": "a4_10x6",
                "profile": template_profile,
            })
            app._toast(f"Отправлено на печать: {len(selected)}", C["green"])
        except Exception as ex:
            messagebox.showerror("Печать A4", f"Не удалось отправить на печать:\n{ex}")

    template_box.bind("<<ComboboxSelected>>", lambda _e: build_preview())
    tree.bind("<<TreeviewSelect>>", lambda _e: build_preview())

    template_buttons = tk.Frame(left, bg=C["panel"])
    template_buttons.pack(fill="x", pady=(2, 10))
    Btn(template_buttons, text="Обновить", cmd=lambda: (refresh_templates(), build_preview()), variant="ghost", w=120, h=36, fs=10, bg=C["panel"]).pack(side="left")
    Btn(template_buttons, text="Редактор шаблона", cmd=edit_template, variant="primary", w=210, h=36, fs=10, bg=C["panel"]).pack(side="right")

    buttons = tk.Frame(right, bg=C["panel"])
    buttons.pack(fill="x", padx=16, pady=(0, 16))
    Btn(buttons, text="PNG", cmd=save_png, variant="ghost", w=78, h=38, fs=10, bg=C["panel"]).pack(side="left", padx=(0, 6))
    Btn(buttons, text="PDF", cmd=save_pdf, variant="ghost", w=78, h=38, fs=10, bg=C["panel"]).pack(side="left", padx=6)
    Btn(buttons, text="Печать", cmd=send_print, variant="success", w=110, h=38, fs=10, bg=C["panel"]).pack(side="left", padx=6)
    Btn(buttons, text="PDF A4", cmd=save_batch_pdf, variant="primary", w=110, h=38, fs=10, bg=C["panel"]).pack(side="right", padx=(6, 0))
    Btn(buttons, text="Печать A4", cmd=print_batch, variant="success", w=120, h=38, fs=10, bg=C["panel"]).pack(side="right", padx=6)

    bottom = tk.Frame(win, bg=C["panel"])
    bottom.pack(fill="x", padx=18, pady=(0, 16))
    Btn(bottom, text="Закрыть", cmd=win.destroy, variant="ghost", w=130, h=40, bg=C["panel"]).pack(side="right")

    refresh_templates()
    build_preview()


def show_print(app):
    if not has_permission(app.user, PERMISSION_PRINT):
        app._toast("Недостаточно прав")
        return
    app._clr(app.content)
    app._pgtitle.configure(text="Печать")
    wrap=tk.Frame(app.content,bg=C["bg"])
    wrap.pack(fill="both",expand=True,padx=36,pady=20)

    top=tk.Frame(wrap,bg=C["bg"])
    top.pack(fill="x",pady=(0,12))
    tk.Label(top,text="Печать пропуска",bg=C["bg"],fg=C["text"],font=(F,16,"bold")).pack(side="left")

    sf=tk.Frame(top,bg=C["input"],highlightthickness=1,highlightbackground=C["border"])
    sf.pack(side="right")
    search=tk.StringVar()
    se=tk.Entry(sf,bg=C["input"],fg=C["text"],insertbackground=C["accent"],
                textvariable=search,relief="flat",font=(F,12),width=24)
    se.pack(side="left",ipady=7,padx=(10,4))

    controls=tk.Frame(wrap,bg=C["bg"])
    controls.pack(fill="x",pady=(0,12))
    tk.Label(controls,text="Шаблон",bg=C["bg"],fg=C["muted"],font=(F,9)).pack(side="left",padx=(0,8))
    template_var=tk.StringVar()
    template_box=ttk.Combobox(controls,textvariable=template_var,state="readonly",width=36)
    template_box.pack(side="left",ipady=3)
    template_paths=[]

    body=tk.Frame(wrap,bg=C["bg"])
    body.pack(fill="both",expand=True)

    left=tk.Frame(body,bg=C["bg"])
    left.pack(side="left",fill="both",expand=True,padx=(0,12))
    tf=tk.Frame(left,bg=C["panel"])
    tf.pack(fill="both",expand=True)
    vsb=ttk.Scrollbar(tf,orient="vertical")
    vsb.pack(side="right",fill="y")
    tree=ttk.Treeview(tf,style="T.Treeview",
                      columns=("qr","name","unit","issued","status"),
                      show="headings",yscrollcommand=vsb.set,selectmode="extended")
    vsb.configure(command=tree.yview)
    for col,txt,w in [("qr","QR",160),("name","ФИО",220),("unit","В/ч",110),
                      ("issued","Выдан",90),("status","Статус",90)]:
        tree.heading(col,text=txt)
        tree.column(col,width=w,minwidth=70)
    tree.tag_configure("ok",foreground=C["green"])
    tree.tag_configure("bad",foreground=C["red"])
    tree.pack(fill="both",expand=True)

    right=tk.Frame(body,bg=C["panel"],highlightthickness=1,highlightbackground=C["border"],width=470)
    right.pack(side="left",fill="both")
    right.pack_propagate(False)
    tk.Label(right,text="Предпросмотр",bg=C["panel"],fg=C["muted"],font=(F,10)).pack(anchor="w",padx=16,pady=(14,8))
    preview=tk.Label(right,text="",bg=C["input"],fg=C["muted"],font=(F,11))
    preview.pack(fill="both",expand=True,padx=16,pady=(0,12))
    _sep(right).pack(fill="x",padx=16,pady=(0,12))

    buttons=tk.Frame(right,bg=C["panel"])
    buttons.pack(fill="x",padx=16,pady=(0,16))

    def refresh_templates():
        nonlocal template_paths
        template_paths=list_print_templates()
        names=[path.name for path in template_paths]
        template_box.configure(values=names)
        if names and template_var.get() not in names:
            template_var.set(names[0])
        if not names:
            template_var.set("")
            preview.configure(text=f"Нет шаблонов в {TEMPLATES_DIR}",image="")

    def load_passes():
        for item in tree.get_children():
            tree.delete(item)
        for row in search_passes(app.db, search.get().strip(), deleted=0, pass_type=None):
            if row[CI["type"]] == PASS_TYPE_TEMPORARY:
                continue
            ok, _, _=pass_status(app.db, row)
            issued=str(row[CI["issued"]] or "")[:10]
            tree.insert("", "end", tags=("ok" if ok else "bad",),
                        values=(row[CI["qr"]], _pass_name(row), row[CI["unit"]] or "",
                                issued, "Активен" if ok else "Истёк"))

    def selected_qr():
        sel=tree.selection()
        if not sel:
            app._toast("Выберите пропуск")
            return None
        return tree.item(sel[0])["values"][0]

    def selected_qrs():
        selected = [tree.item(item)["values"][0] for item in tree.selection()]
        if not selected:
            app._toast("Выберите один или несколько пропусков")
        return selected

    def selected_template():
        name=template_var.get()
        for path in template_paths:
            if path.name == name:
                return path
        app._toast("Добавьте шаблон")
        return None

    def edit_template():
        template=selected_template()
        if not template:
            return
        open_template_editor(app,template,on_saved=lambda: build_preview() if tree.selection() else None)

    def build_preview():
        qr=selected_qr()
        template=selected_template()
        if not qr or not template:
            return None, None
        image=render_print_pass(app.db, qr, template)
        shown=image.copy()
        shown.thumbnail((430, 430))
        tk_image=ImageTk.PhotoImage(shown)
        app._print_preview_img=tk_image
        app._print_preview_source=image
        preview.configure(image=tk_image,text="")
        return image, qr

    def save_png():
        image, qr=build_preview()
        if image is None:
            return
        path=save_print_png(image, qr)
        safe_record_action(app.db, app.user, "print.png", "pass", qr, {"file": path.name})
        app._toast(f"PNG сохранён: {path.name}",C["green"])

    def save_pdf():
        image, qr=build_preview()
        if image is None:
            return
        path=save_print_pdf(image, qr)
        safe_record_action(app.db, app.user, "print.pdf", "pass", qr, {"file": path.name})
        app._toast(f"PDF сохранён: {path.name}",C["green"])

    def send_print():
        image, qr=build_preview()
        if image is None:
            return
        try:
            path=save_print_pdf(image, qr)
            print_file(path)
            safe_record_action(app.db, app.user, "print.send", "pass", qr, {"file": path.name})
            app._toast("Отправлено на печать",C["green"])
        except Exception as ex:
            messagebox.showerror("Печать",f"Не удалось отправить на печать:\n{ex}")

    def save_batch_pdf():
        qrs=selected_qrs()
        template=selected_template()
        if not qrs or not template:
            return
        try:
            path=save_batch_print_pdf(app.db,qrs,template)
            safe_record_action(app.db,app.user,"print.batch_pdf","passes",len(qrs),{"file": path.name,"count": len(qrs),"layout": "a4_10x6"})
            app._toast(f"PDF создан: {path.name}",C["green"])
        except Exception as ex:
            messagebox.showerror("Массовая печать",f"Не удалось создать PDF:\n{ex}")

    def print_batch():
        qrs=selected_qrs()
        template=selected_template()
        if not qrs or not template:
            return
        try:
            path=save_batch_print_pdf(app.db,qrs,template)
            print_file(path)
            safe_record_action(app.db,app.user,"print.batch_send","passes",len(qrs),{"file": path.name,"count": len(qrs),"layout": "a4_10x6"})
            app._toast(f"Отправлено на печать: {len(qrs)}",C["green"])
        except Exception as ex:
            messagebox.showerror("Массовая печать",f"Не удалось отправить на печать:\n{ex}")

    se.bind("<Return>",lambda e:load_passes())
    tree.bind("<Double-1>",lambda e:build_preview())
    Btn(sf,text="Поиск",cmd=load_passes,variant="primary",w=80,h=34,fs=10,bg=C["input"]).pack(side="left",padx=3)
    Btn(controls,text="Обновить шаблоны",cmd=refresh_templates,variant="ghost",w=170,h=34,fs=10,bg=C["bg"]).pack(side="left",padx=10)
    Btn(controls,text="Редактор шаблона",cmd=edit_template,variant="primary",w=170,h=34,fs=10,bg=C["bg"]).pack(side="left",padx=(0,10))

    Btn(buttons,text="Предпросмотр",cmd=build_preview,variant="primary",w=130,h=38,fs=10,bg=C["panel"]).pack(side="left",padx=(0,6))
    Btn(buttons,text="PNG",cmd=save_png,variant="ghost",w=78,h=38,fs=10,bg=C["panel"]).pack(side="left",padx=6)
    Btn(buttons,text="PDF",cmd=save_pdf,variant="ghost",w=78,h=38,fs=10,bg=C["panel"]).pack(side="left",padx=6)
    Btn(buttons,text="Печать",cmd=send_print,variant="success",w=100,h=38,fs=10,bg=C["panel"]).pack(side="right")

    batch_buttons=tk.Frame(right,bg=C["panel"])
    batch_buttons.pack(fill="x",padx=16,pady=(0,16))
    Btn(batch_buttons,text="PDF A4",cmd=save_batch_pdf,variant="primary",w=150,h=38,fs=10,bg=C["panel"]).pack(side="left",padx=(0,8))
    Btn(batch_buttons,text="Печать A4",cmd=print_batch,variant="success",w=170,h=38,fs=10,bg=C["panel"]).pack(side="right")

    refresh_templates()
    load_passes()
