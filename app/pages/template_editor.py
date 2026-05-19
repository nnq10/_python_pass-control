import tkinter as tk
from tkinter import messagebox, ttk

from PIL import Image, ImageTk

from app.core.config import C, FONT as F
from app.services.audit import safe_record_action
from app.services.print_passes import DEFAULT_TEXT_FONT, editable_template_config, save_template_config
from app.ui.widgets import Btn, _sep


FIELD_TITLES = {
    "last_name": "Фамилия",
    "first_name": "Имя",
    "middle_name": "Отчество",
    "full_name": "ФИО",
    "destination": "Куда войти",
    "basis": "Основание",
    "issued_day": "День",
    "issued_month": "Месяц",
    "issued_year": "Год",
    "issued_year_short": "Год",
}


def _qr_entries(config):
    qr_codes = config.get("qr_codes")
    if isinstance(qr_codes, list) and qr_codes:
        return [(f"qr:{index}", qr.get("title") or f"QR {index + 1}", qr) for index, qr in enumerate(qr_codes)]
    return [("qr", "QR", config.setdefault("qr", {}))]


def _qr_config(config, key):
    if key == "qr":
        return config.setdefault("qr", {})
    if key.startswith("qr:"):
        try:
            index = int(key.split(":", 1)[1])
        except ValueError:
            return None
        qr_codes = config.get("qr_codes") or []
        if 0 <= index < len(qr_codes):
            return qr_codes[index]
    return None


def _is_qr_key(key):
    return key == "qr" or str(key).startswith("qr:")


def _is_field_key(config, key):
    return key in (config.get("fields") or {})


def _qr_position(qr, image_size):
    size = int(qr.get("size", 120))
    margin = int(qr.get("margin", 30))
    raw_x = qr.get("x", "right")
    raw_y = qr.get("y", margin)
    x = image_size[0] - size - margin if raw_x == "right" else int(raw_x)
    y = image_size[1] - size - margin if raw_y == "bottom" else int(raw_y)
    return x, y, size


def _photo_position(config):
    photo = config.setdefault("photo", {})
    x = int(photo.get("x", 70))
    y = int(photo.get("y", 250))
    width = int(photo.get("width", 160))
    height = int(photo.get("height", 200))
    enabled = bool(photo.get("enabled", False))
    return x, y, width, height, enabled


def _clamp(value, low, high):
    return max(low, min(high, value))


def _field_items(config):
    return list((config.get("fields") or {}).items())


def _field_title(field, options):
    return options.get("title") or FIELD_TITLES.get(field) or FIELD_TITLES.get(options.get("source")) or field


def open_template_editor(app, template_path, on_saved=None):
    win=app._modal("Редактор шаблона",1280,900)
    root=tk.Frame(win,bg=C["panel"])
    root.pack(fill="both",expand=True,padx=18,pady=16)

    image=Image.open(template_path).convert("RGBA")
    config=editable_template_config(template_path)
    state={
        "config": config,
        "drag": None,
        "selected": None,
        "canvas_image": None,
        "suppress_table_event": False,
    }
    step_var=tk.IntVar(value=10)

    left=tk.Frame(root,bg=C["panel"])
    left.pack(side="left",fill="both",expand=True,padx=(0,14))
    canvas=tk.Canvas(left,bg=C["input"],highlightthickness=1,highlightbackground=C["border"])
    canvas.pack(fill="both",expand=True)

    right=tk.Frame(root,bg=C["panel"],width=340)
    right.pack(side="right",fill="y")
    right.pack_propagate(False)
    tk.Label(right,text="Элементы",bg=C["panel"],fg=C["text"],font=(F,13,"bold")).pack(anchor="w",pady=(0,10))

    table=ttk.Treeview(right,style="T.Treeview",columns=("name","x","y","size"),show="headings",height=8)
    for col,txt,w in [("name","Поле",100),("x","X",54),("y","Y",54),("size","Размер",70)]:
        table.heading(col,text=txt)
        table.column(col,width=w,minwidth=40)
    table.pack(fill="x")

    info=tk.Label(right,text="",bg=C["panel"],fg=C["muted"],font=(F,9),justify="left",wraplength=300)
    info.pack(anchor="w",pady=(12,10))
    _sep(right).pack(fill="x",pady=10)

    def display_geometry():
        max_w=max(400,canvas.winfo_width()-24)
        max_h=max(300,canvas.winfo_height()-24)
        scale=min(max_w/image.width,max_h/image.height,1.0)
        shown=image.resize((round(image.width*scale),round(image.height*scale)),Image.Resampling.LANCZOS)
        offset_x=(canvas.winfo_width()-shown.width)//2
        offset_y=(canvas.winfo_height()-shown.height)//2
        return shown,scale,offset_x,offset_y

    def to_canvas(x,y,scale,ox,oy):
        return ox+x*scale,oy+y*scale

    def init_table():
        for key,title,_qr in _qr_entries(state["config"]):
            table.insert("", "end", iid=key, values=(title, 0, 0, 0))
        table.insert("", "end", iid="photo", values=("Фото", 0, 0, 0))
        for field,options in _field_items(state["config"]):
            table.insert("", "end", iid=field, values=(_field_title(field, options), 0, 0, 0))

    def update_table_values():
        for key,title,qr in _qr_entries(state["config"]):
            qx,qy,qs=_qr_position(qr,image.size)
            table.item(key, values=(title, qx, qy, qs))
        px,py,pw,ph,enabled=_photo_position(state["config"])
        table.item("photo", values=("Фото" if enabled else "Фото выкл.", px, py, f"{pw}x{ph}"))
        for field,options in _field_items(state["config"]):
            options=state["config"]["fields"][field]
            table.item(field, values=(_field_title(field, options), int(options["x"]), int(options["y"]), int(options.get("size", 28))))

    def sync_table_selection(key):
        if not key or not table.exists(key) or table.selection() == (key,):
            return
        state["suppress_table_event"]=True
        table.selection_set(key)
        table.focus(key)
        win.after_idle(lambda: state.update({"suppress_table_event": False}))

    def set_selected(key, sync_table=True):
        state["selected"]=key
        canvas.focus_set()
        if sync_table:
            sync_table_selection(key)
        draw()

    def draw():
        canvas.delete("all")
        shown,scale,ox,oy=display_geometry()
        state["scale"]=scale
        state["offset_x"]=ox
        state["offset_y"]=oy
        state["canvas_image"]=ImageTk.PhotoImage(shown)
        canvas.create_image(ox,oy,anchor="nw",image=state["canvas_image"])

        for key,title,qr in _qr_entries(state["config"]):
            qx,qy,qs=_qr_position(qr,image.size)
            x1,y1=to_canvas(qx,qy,scale,ox,oy)
            x2,y2=to_canvas(qx+qs,qy+qs,scale,ox,oy)
            qr_color=C["green"] if state.get("selected")==key else C["accent"]
            canvas.create_rectangle(x1,y1,x2,y2,outline=qr_color,width=3,tags=("draggable",f"item:{key}"))
            canvas.create_text(x1+6,y1+6,anchor="nw",text=title,fill=qr_color,font=(F,12,"bold"),tags=("draggable",f"item:{key}"))

        px,py,pw,ph,photo_enabled=_photo_position(state["config"])
        px1,py1=to_canvas(px,py,scale,ox,oy)
        px2,py2=to_canvas(px+pw,py+ph,scale,ox,oy)
        photo_color=C["green"] if state.get("selected")=="photo" else (C["yellow"] if photo_enabled else C["red"])
        canvas.create_rectangle(px1,py1,px2,py2,outline=photo_color,width=3,dash=(6,3),tags=("draggable","item:photo"))
        canvas.create_text(px1+6,py1+6,anchor="nw",text="Фото" if photo_enabled else "Фото выкл.",
                           fill=photo_color,font=(F,12,"bold"),tags=("draggable","item:photo"))

        for field,options in _field_items(state["config"]):
            options=state["config"]["fields"][field]
            x,y=to_canvas(int(options["x"]),int(options["y"]),scale,ox,oy)
            color=C["green"] if state.get("selected")==field else C["accent"]
            title=_field_title(field, options)
            preview_size=max(8, round(int(options.get("size", 28))*scale))
            text_id=canvas.create_text(x,y,anchor="nw",text=title,fill=color,font=(DEFAULT_TEXT_FONT,preview_size,"bold"),tags=("draggable",f"item:{field}"))
            bbox=canvas.bbox(text_id)
            if bbox:
                canvas.create_rectangle(bbox[0]-5,bbox[1]-3,bbox[2]+5,bbox[3]+3,outline=color,dash=(4,2),tags=("draggable",f"item:{field}"))

        info.configure(text=f"Шаблон: {template_path.name}\nРазмер: {image.width} x {image.height} px")
        update_table_values()

    def item_from_event():
        for tag in canvas.gettags("current"):
            if tag.startswith("item:"):
                return tag.split(":",1)[1]
        return None

    def drag_start(event):
        key=item_from_event()
        if not key:
            return
        set_selected(key)
        state["drag"]=(key,event.x,event.y)

    def drag_move(event):
        drag=state.get("drag")
        if not drag:
            return
        key,last_x,last_y=drag
        scale=state["scale"]
        dx=(event.x-last_x)/scale
        dy=(event.y-last_y)/scale
        if _is_qr_key(key):
            qr=_qr_config(state["config"],key)
            if not qr:
                return
            x,y,size=_qr_position(qr,image.size)
            x=_clamp(round(x+dx),0,image.width-size)
            y=_clamp(round(y+dy),0,image.height-size)
            qr["x"]=x
            qr["y"]=y
        elif key=="photo":
            photo=state["config"].setdefault("photo", {})
            x,y,width,height,_enabled=_photo_position(state["config"])
            photo["x"]=_clamp(round(x+dx),0,image.width-width)
            photo["y"]=_clamp(round(y+dy),0,image.height-height)
        else:
            options=state["config"]["fields"][key]
            options["x"]=_clamp(round(int(options["x"])+dx),0,image.width)
            options["y"]=_clamp(round(int(options["y"])+dy),0,image.height)
        state["drag"]=(key,event.x,event.y)
        draw()

    def drag_end(_event):
        state["drag"]=None

    def resize_qr(delta):
        key=state.get("selected")
        if not _is_qr_key(key):
            entries=_qr_entries(state["config"])
            key=entries[0][0] if entries else "qr"
        qr=_qr_config(state["config"],key)
        if not qr:
            return
        x,y,size=_qr_position(qr,image.size)
        size=_clamp(size+delta,40,min(image.size))
        qr["size"]=size
        qr["x"]=_clamp(x,0,image.width-size)
        qr["y"]=_clamp(y,0,image.height-size)
        set_selected(key)

    def selected_step():
        try:
            return max(1, int(step_var.get()))
        except (TypeError, ValueError):
            return 10

    def resize_photo(delta):
        photo=state["config"].setdefault("photo", {})
        x,y,width,height,_enabled=_photo_position(state["config"])
        width=_clamp(width+delta,40,image.width)
        height=_clamp(height+delta,40,image.height)
        photo["width"]=width
        photo["height"]=height
        photo["x"]=_clamp(x,0,image.width-width)
        photo["y"]=_clamp(y,0,image.height-height)
        set_selected("photo")

    def resize_text(delta):
        key=state.get("selected")
        if not _is_field_key(state["config"], key):
            fields=_field_items(state["config"])
            if not fields:
                app._toast("В шаблоне нет текстовых полей")
                return
            key=fields[0][0]
        options=state["config"]["fields"][key]
        options["font"]=DEFAULT_TEXT_FONT
        options["size"]=_clamp(int(options.get("size", 28))+delta,6,240)
        set_selected(key)

    def toggle_photo():
        photo=state["config"].setdefault("photo", {})
        photo["enabled"]=not bool(photo.get("enabled", False))
        set_selected("photo")

    def nudge(dx,dy, amount=None):
        key=state.get("selected")
        if not key:
            return
        amount=selected_step() if amount is None else max(1, int(amount))
        dx*=amount
        dy*=amount
        if _is_qr_key(key):
            qr=_qr_config(state["config"],key)
            if not qr:
                return
            x,y,size=_qr_position(qr,image.size)
            qr["x"]=_clamp(x+dx,0,image.width-size)
            qr["y"]=_clamp(y+dy,0,image.height-size)
        elif key=="photo":
            photo=state["config"].setdefault("photo", {})
            x,y,width,height,_enabled=_photo_position(state["config"])
            photo["x"]=_clamp(x+dx,0,image.width-width)
            photo["y"]=_clamp(y+dy,0,image.height-height)
        else:
            options=state["config"]["fields"][key]
            options["x"]=_clamp(int(options["x"])+dx,0,image.width)
            options["y"]=_clamp(int(options["y"])+dy,0,image.height)
        draw()

    def keyboard_nudge(event):
        if not state.get("selected"):
            return None
        keys={
            "Left": (-1,0),
            "Right": (1,0),
            "Up": (0,-1),
            "Down": (0,1),
        }
        if event.keysym not in keys:
            return None
        amount=selected_step()
        if event.state & 0x0001:
            amount*=5
        if event.state & 0x0004:
            amount=1
        dx,dy=keys[event.keysym]
        nudge(dx,dy,amount)
        return "break"

    def save():
        state["config"]["base_size"]=[image.width,image.height]
        try:
            path=save_template_config(template_path,state["config"])
            safe_record_action(app.db,app.user,"template.update","template",template_path.name,{"config": path.name})
            app._toast("Шаблон сохранён",C["green"])
            if on_saved:
                on_saved()
            win.destroy()
        except Exception as ex:
            messagebox.showerror("Редактор шаблона",f"Не удалось сохранить шаблон:\n{ex}")

    def select_from_table(_event):
        if state.get("suppress_table_event"):
            return
        sel=table.selection()
        if sel:
            set_selected(sel[0], sync_table=False)

    canvas.bind("<Configure>",lambda e:draw())
    canvas.tag_bind("draggable","<ButtonPress-1>",drag_start)
    canvas.tag_bind("draggable","<B1-Motion>",drag_move)
    canvas.tag_bind("draggable","<ButtonRelease-1>",drag_end)
    table.bind("<<TreeviewSelect>>",select_from_table)
    for key in ("<Left>","<Right>","<Up>","<Down>"):
        win.bind(key, keyboard_nudge)
    init_table()

    step_box=tk.Frame(right,bg=C["panel"])
    step_box.pack(fill="x",pady=(0,10))
    tk.Label(step_box,text="Шаг",bg=C["panel"],fg=C["muted"],font=(F,9)).pack(anchor="w",pady=(0,5))
    step_row=tk.Frame(step_box,bg=C["panel"])
    step_row.pack(anchor="w")
    for value in (1,5,10,25):
        tk.Radiobutton(
            step_row,
            text=str(value),
            value=value,
            variable=step_var,
            bg=C["panel"],
            fg=C["text"],
            selectcolor=C["input"],
            activebackground=C["panel"],
            font=(F,10),
        ).pack(side="left",padx=(0,8))

    arrows=tk.Frame(right,bg=C["panel"])
    arrows.pack(anchor="center",pady=(0,10))
    Btn(arrows,text="↑",cmd=lambda:nudge(0,-1),variant="ghost",w=48,h=34,fs=12,bg=C["panel"]).grid(row=0,column=1,padx=3,pady=3)
    Btn(arrows,text="←",cmd=lambda:nudge(-1,0),variant="ghost",w=48,h=34,fs=12,bg=C["panel"]).grid(row=1,column=0,padx=3,pady=3)
    Btn(arrows,text="→",cmd=lambda:nudge(1,0),variant="ghost",w=48,h=34,fs=12,bg=C["panel"]).grid(row=1,column=2,padx=3,pady=3)
    Btn(arrows,text="↓",cmd=lambda:nudge(0,1),variant="ghost",w=48,h=34,fs=12,bg=C["panel"]).grid(row=2,column=1,padx=3,pady=3)

    qr_buttons=tk.Frame(right,bg=C["panel"])
    qr_buttons.pack(fill="x",pady=(0,12))
    Btn(qr_buttons,text="QR -",cmd=lambda:resize_qr(-selected_step()),variant="ghost",w=104,h=36,fs=10,bg=C["panel"]).pack(side="left",padx=(0,8))
    Btn(qr_buttons,text="QR +",cmd=lambda:resize_qr(selected_step()),variant="ghost",w=104,h=36,fs=10,bg=C["panel"]).pack(side="left")

    text_box=tk.Frame(right,bg=C["panel"])
    text_box.pack(fill="x",pady=(0,12))
    tk.Label(text_box,text=f"Шрифт: {DEFAULT_TEXT_FONT}",bg=C["panel"],fg=C["muted"],font=(F,9)).pack(anchor="w",pady=(0,5))
    text_buttons=tk.Frame(text_box,bg=C["panel"])
    text_buttons.pack(fill="x")
    Btn(text_buttons,text="Текст -",cmd=lambda:resize_text(-selected_step()),variant="ghost",w=104,h=36,fs=10,bg=C["panel"]).pack(side="left",padx=(0,8))
    Btn(text_buttons,text="Текст +",cmd=lambda:resize_text(selected_step()),variant="ghost",w=104,h=36,fs=10,bg=C["panel"]).pack(side="left")

    photo_buttons=tk.Frame(right,bg=C["panel"])
    photo_buttons.pack(fill="x",pady=(0,12))
    Btn(photo_buttons,text="Фото",cmd=toggle_photo,variant="primary",w=78,h=36,fs=10,bg=C["panel"]).pack(side="left",padx=(0,8))
    Btn(photo_buttons,text="Фото -",cmd=lambda:resize_photo(-selected_step()),variant="ghost",w=78,h=36,fs=10,bg=C["panel"]).pack(side="left",padx=(0,8))
    Btn(photo_buttons,text="Фото +",cmd=lambda:resize_photo(selected_step()),variant="ghost",w=78,h=36,fs=10,bg=C["panel"]).pack(side="left")

    tk.Frame(right,bg=C["panel"]).pack(fill="y",expand=True)
    Btn(right,text="Сохранить координаты",cmd=save,variant="success",w=300,h=42,fs=12,bg=C["panel"]).pack(fill="x",pady=(0,10))
    Btn(right,text="Закрыть",cmd=win.destroy,variant="ghost",w=300,h=38,fs=11,bg=C["panel"]).pack(fill="x")
    draw()
