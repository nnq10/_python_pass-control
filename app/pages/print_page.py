import tkinter as tk
from tkinter import messagebox, ttk

from PIL import ImageTk

from app.core.config import C, FONT as F
from app.core.paths import TEMPLATES_DIR
from app.services.audit import safe_record_action
from app.services.pass_db import CI, PASS_TYPE_TEMPORARY, pass_status, search_passes
from app.services.print_passes import (list_print_templates, print_file, render_print_pass,
                                       save_batch_print_pdf, save_print_pdf, save_print_png)
from app.pages.template_editor import open_template_editor
from app.ui.widgets import Btn, _sep


def _pass_name(row):
    return " ".join(filter(None, [row[CI["ln"]], row[CI["fn"]], row[CI["mn"]]]))


def show_print(app):
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
            safe_record_action(app.db,app.user,"print.batch_pdf","passes",len(qrs),{"file": path.name,"count": len(qrs)})
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
            safe_record_action(app.db,app.user,"print.batch_send","passes",len(qrs),{"file": path.name,"count": len(qrs)})
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
    Btn(batch_buttons,text="PDF выбранных",cmd=save_batch_pdf,variant="primary",w=150,h=38,fs=10,bg=C["panel"]).pack(side="left",padx=(0,8))
    Btn(batch_buttons,text="Печать выбранных",cmd=print_batch,variant="success",w=170,h=38,fs=10,bg=C["panel"]).pack(side="right")

    refresh_templates()
    load_passes()
