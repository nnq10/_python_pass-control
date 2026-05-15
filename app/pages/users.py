import tkinter as tk
from tkinter import messagebox, ttk

from app.core.config import C, FONT as F
from app.core.logging import get_logger
from app.services.audit import safe_record_action
from app.services.auth import (PERMISSION_TITLES, PERMISSION_USERS, delete_user,
                               has_permission, list_users, normalize_permissions,
                               permissions_for_role, role_title, upsert_user)
from app.ui.widgets import Btn, _field

logger = get_logger(__name__)


def _user_error_message(error):
    messages = {
        "cannot delete the last admin": "Нельзя удалить последнего администратора",
        "cannot demote the last admin": "Нельзя понизить последнего администратора",
        "cannot delete the last user": "Нельзя удалить последнего пользователя",
    }
    return messages.get(str(error), str(error))


def show_users(app):
    if not has_permission(app.user, PERMISSION_USERS):
        app._toast("Недостаточно прав"); return
    app._clr(app.content)
    app._pgtitle.configure(text="Пользователи")
    wrap=tk.Frame(app.content,bg=C["bg"])
    wrap.pack(fill="both",expand=True,padx=36,pady=20)

    top=tk.Frame(wrap,bg=C["bg"]); top.pack(fill="x",pady=(0,12))
    tk.Label(top,text="Пользователи",bg=C["bg"],fg=C["text"],font=(F,16,"bold")).pack(side="left")
    Btn(top,text="Добавить",cmd=lambda:app._user_modal(),variant="success",
        w=140,h=38,fs=11,bg=C["bg"]).pack(side="right")

    tf=tk.Frame(wrap,bg=C["panel"]); tf.pack(fill="both",expand=True)
    tree=ttk.Treeview(tf,style="T.Treeview",
                      columns=("username","name","role","tabs"),
                      show="headings",height=12)
    for col,txt,w in [("username","Логин",150),("name","Имя",210),("role","Роль",130),("tabs","Доступные вкладки",360)]:
        tree.heading(col,text=txt); tree.column(col,width=w,minwidth=80)
    tree.pack(fill="both",expand=True)

    def load():
        for item in tree.get_children(): tree.delete(item)
        for user in list_users():
            role = role_title(user["role"])
            tabs = ", ".join(PERMISSION_TITLES[p] for p in user["permissions"] if p in PERMISSION_TITLES)
            tree.insert("", "end", values=(user["username"], user["name"], role, tabs))

    def selected_username():
        sel=tree.selection()
        if not sel:
            app._toast("Выберите пользователя"); return None
        return tree.item(sel[0])["values"][0]

    def edit():
        username=selected_username()
        if username: app._user_modal(username, load)

    def remove():
        username=selected_username()
        if not username: return
        if username == app.user.get("username"):
            app._toast("Нельзя удалить текущего пользователя"); return
        if not messagebox.askyesno("Удалить пользователя",f"Удалить пользователя «{username}»?"):
            return
        try:
            delete_user(username)
            safe_record_action(app.db, app.user, "user.delete", "user", username)
            load(); app._toast("Пользователь удалён",C["green"])
        except Exception as ex:
            logger.exception("Failed to delete user: %s", username)
            messagebox.showerror("Ошибка",_user_error_message(ex))

    load()
    tree.bind("<Double-1>",lambda e:edit())

    bf=tk.Frame(wrap,bg=C["bg"]); bf.pack(pady=12)
    Btn(bf,text="Изменить",cmd=edit,variant="primary",w=150,h=38,bg=C["bg"]).pack(side="left",padx=6)
    Btn(bf,text="Удалить",cmd=remove,variant="danger",w=150,h=38,bg=C["bg"]).pack(side="left",padx=6)


def _user_modal(app, username=None, on_saved=None):
    users={u["username"]:u for u in list_users()}
    current=users.get(username or "", {})
    win=app._modal("Пользователь",620,780, scroll=True)

    login_e=_field(win,"Логин",username or "",bg=C["panel"])
    if username:
        login_e.configure(state="disabled")
    name_e=_field(win,"Имя",current.get("name",""),bg=C["panel"])

    tk.Label(win,text="Роль",bg=C["panel"],fg=C["muted"],font=(F,9)).pack(anchor="w",padx=28,pady=(12,4))
    role=tk.StringVar(value=current.get("role","guard"))
    rf=tk.Frame(win,bg=C["panel"]); rf.pack(anchor="w",padx=28)
    for value,text in [("guard","Охрана"),("admin","Администратор")]:
        tk.Radiobutton(rf,text=text,value=value,variable=role,
                       bg=C["panel"],fg=C["text"],selectcolor=C["input"],
                       activebackground=C["panel"],font=(F,10)).pack(side="left",padx=(0,12))

    tk.Label(win,text="Доступные вкладки",bg=C["panel"],fg=C["muted"],font=(F,9)).pack(anchor="w",padx=28,pady=(14,4))
    permission_wrap=tk.Frame(win,bg=C["panel"])
    permission_wrap.pack(fill="x",padx=28)
    current_permissions=normalize_permissions(current.get("permissions"), current.get("role","guard"))
    permission_vars={}
    for index,(permission,title) in enumerate(PERMISSION_TITLES.items()):
        var=tk.BooleanVar(value=permission in current_permissions)
        permission_vars[permission]=var
        cb=tk.Checkbutton(permission_wrap,text=title,variable=var,bg=C["panel"],fg=C["text"],
                          selectcolor=C["input"],activebackground=C["panel"],font=(F,10),anchor="w")
        cb.grid(row=index//2,column=index%2,sticky="w",padx=(0,22),pady=3)
    permission_wrap.columnconfigure(0,weight=1)
    permission_wrap.columnconfigure(1,weight=1)

    preset_row=tk.Frame(win,bg=C["panel"])
    preset_row.pack(fill="x",padx=28,pady=(8,2))

    def apply_permission_preset():
        for permission,var in permission_vars.items():
            var.set(permission in permissions_for_role(role.get()))

    Btn(preset_row,text="Применить пресет роли",cmd=apply_permission_preset,variant="ghost",
        w=220,h=34,fs=10,bg=C["panel"]).pack(side="left")
    role.trace_add("write", lambda *_: apply_permission_preset())

    pwd_e=_field(win,"Новый пароль" if username else "Пароль",show="●",bg=C["panel"])
    pwd2_e=_field(win,"Повтор пароля",show="●",bg=C["panel"])

    hint="Оставьте пароль пустым, чтобы не менять" if username else "Минимум 6 символов"
    tk.Label(win,text=hint,bg=C["panel"],fg=C["muted"],font=(F,9)).pack(anchor="w",padx=28,pady=(6,0))

    def save():
        login = username or login_e.get().strip()
        password = pwd_e.get().strip()
        password2 = pwd2_e.get().strip()
        if not login:
            app._toast("Укажите логин"); return
        if password or not username:
            if len(password) < 6:
                app._toast("Пароль должен быть не короче 6 символов"); return
            if password != password2:
                app._toast("Пароли не совпадают"); return
        try:
            action = "user.update" if username else "user.create"
            permissions=[permission for permission,var in permission_vars.items() if var.get()]
            upsert_user(login, name_e.get(), role.get(), password or None, permissions=permissions)
            safe_record_action(app.db, app.user, action, "user", login, {
                "name": name_e.get().strip() or login,
                "role": role.get(),
                "permissions": permissions,
                "password_changed": bool(password),
            })
            if login == app.user.get("username"):
                app.user["name"] = name_e.get().strip() or login
                app.user["role"] = role.get()
                app.user["permissions"] = normalize_permissions(permissions, role.get())
            app._close_modal(win)
            app._toast("Пользователь сохранён",C["green"])
            if on_saved: on_saved()
            else: app.show_users()
        except Exception as ex:
            logger.exception("Failed to save user: %s", login)
            messagebox.showerror("Ошибка",_user_error_message(ex))

    Btn(win,text="Сохранить",cmd=save,variant="success",w=564,h=44,fs=13,
        bg=C["panel"]).pack(padx=28,pady=16)


