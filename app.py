#!/usr/bin/env python3
"""Desktop UI to publish a news item to lianeaster/bpbv via the GitHub API."""

from __future__ import annotations

import threading
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path
import tkinter as tk
from tkinter import END, StringVar, filedialog, messagebox, ttk

import github_api
from news_builder import (
    build_article_html,
    build_body_html,
    inject_article_into_index,
    inject_translation_block,
    next_card_index,
    sanitize_image_filename,
    split_title_excerpt_detail,
    translation_keys_block,
)

OWNER = "lianeaster"
REPO = "bpbv"
BRANCH = "main"
IMAGE_PREFIX = "images/news"


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("BPBV — оновлення новин")
        self.minsize(520, 640)
        self.geometry("620x720")

        self.token_var = tk_string(self)
        self.section_var = tk_string(self, value="news")
        self.day_var = tk_string(self, value=str(datetime.now().day))
        self.month_var = tk_string(self, value=str(datetime.now().month))
        self.year_var = tk_string(self, value=str(datetime.now().year))
        self.image_paths: list[Path] = []
        self.status_var = tk_string(self, value="Готово.")

        self._build()
        self._bind_clipboard()
        self._bind_context_menu()

    def _bind_clipboard(self) -> None:
        """Enable Ctrl+V / Ctrl+C / Ctrl+A / Ctrl+X on Windows (Tkinter ignores them by default)."""
        for seq, cmd in [
            ("<Control-v>", self._paste),
            ("<Control-V>", self._paste),
            ("<Control-c>", self._copy),
            ("<Control-C>", self._copy),
            ("<Control-a>", self._select_all),
            ("<Control-A>", self._select_all),
            ("<Control-x>", self._cut),
            ("<Control-X>", self._cut),
        ]:
            self.bind_all(seq, cmd)

    def _resolve_widget(self, event: tk.Event) -> tk.Widget | None:
        """On Windows event.widget can be a string path instead of an object."""
        w = event.widget
        if isinstance(w, str):
            try:
                w = self.nametowidget(w)
            except (KeyError, ValueError):
                return None
        return w

    def _widget_kind(self, w: tk.Widget) -> str:
        """Return 'entry', 'text', or 'other'."""
        cls = w.winfo_class()
        if cls in ("Entry", "TEntry"):
            return "entry"
        if cls in ("Text", "TText"):
            return "text"
        return "other"

    def _paste(self, event: tk.Event) -> str | None:
        w = self._resolve_widget(event)
        if w is None:
            return None
        try:
            text = self.clipboard_get()
        except tk.TclError:
            return None
        kind = self._widget_kind(w)
        if kind == "entry":
            try:
                if w.select_present():
                    w.delete("sel.first", "sel.last")
            except (tk.TclError, AttributeError):
                pass
            w.insert("insert", text)
            return "break"
        if kind == "text":
            try:
                w.delete("sel.first", "sel.last")
            except tk.TclError:
                pass
            w.insert("insert", text)
            return "break"
        return None

    def _copy(self, event: tk.Event) -> str | None:
        w = self._resolve_widget(event)
        if w is None:
            return None
        try:
            kind = self._widget_kind(w)
            if kind == "entry":
                if w.select_present():
                    self.clipboard_clear()
                    self.clipboard_append(w.selection_get())
                    return "break"
            elif kind == "text":
                sel = w.get("sel.first", "sel.last")
                if sel:
                    self.clipboard_clear()
                    self.clipboard_append(sel)
                    return "break"
        except tk.TclError:
            pass
        return None

    def _cut(self, event: tk.Event) -> str | None:
        w = self._resolve_widget(event)
        if w is None:
            return None
        try:
            kind = self._widget_kind(w)
            if kind == "entry":
                if w.select_present():
                    self.clipboard_clear()
                    self.clipboard_append(w.selection_get())
                    w.delete("sel.first", "sel.last")
                    return "break"
            elif kind == "text":
                sel = w.get("sel.first", "sel.last")
                if sel:
                    self.clipboard_clear()
                    self.clipboard_append(sel)
                    w.delete("sel.first", "sel.last")
                    return "break"
        except tk.TclError:
            pass
        return None

    def _select_all(self, event: tk.Event) -> str | None:
        w = self._resolve_widget(event)
        if w is None:
            return None
        kind = self._widget_kind(w)
        if kind == "entry":
            w.select_range(0, "end")
            w.icursor("end")
            return "break"
        if kind == "text":
            w.tag_add("sel", "1.0", "end")
            return "break"
        return None

    def _bind_context_menu(self) -> None:
        """Right-click context menu with Вставити/Копіювати/Вирізати for all input fields."""
        menu = tk.Menu(self, tearoff=0)
        self._ctx_menu = menu

        def _show(event: tk.Event) -> None:
            w = self._resolve_widget(event)
            if w is None:
                return
            kind = self._widget_kind(w)
            if kind not in ("entry", "text"):
                return
            menu.delete(0, "end")
            menu.add_command(label="Вставити", command=lambda: self._ctx_paste(w, kind))
            menu.add_command(label="Копіювати", command=lambda: self._ctx_copy(w, kind))
            menu.add_command(label="Вирізати", command=lambda: self._ctx_cut(w, kind))
            menu.add_separator()
            menu.add_command(label="Виділити все", command=lambda: self._ctx_select_all(w, kind))
            try:
                menu.tk_popup(event.x_root, event.y_root)
            finally:
                menu.grab_release()

        self.bind_all("<Button-3>", _show)

    def _ctx_paste(self, w: tk.Widget, kind: str) -> None:
        try:
            text = self.clipboard_get()
        except tk.TclError:
            return
        if kind == "entry":
            try:
                if w.select_present():
                    w.delete("sel.first", "sel.last")
            except (tk.TclError, AttributeError):
                pass
            w.insert("insert", text)
        elif kind == "text":
            try:
                w.delete("sel.first", "sel.last")
            except tk.TclError:
                pass
            w.insert("insert", text)

    def _ctx_copy(self, w: tk.Widget, kind: str) -> None:
        try:
            if kind == "entry" and w.select_present():
                self.clipboard_clear()
                self.clipboard_append(w.selection_get())
            elif kind == "text":
                sel = w.get("sel.first", "sel.last")
                if sel:
                    self.clipboard_clear()
                    self.clipboard_append(sel)
        except tk.TclError:
            pass

    def _ctx_cut(self, w: tk.Widget, kind: str) -> None:
        try:
            if kind == "entry" and w.select_present():
                self.clipboard_clear()
                self.clipboard_append(w.selection_get())
                w.delete("sel.first", "sel.last")
            elif kind == "text":
                sel = w.get("sel.first", "sel.last")
                if sel:
                    self.clipboard_clear()
                    self.clipboard_append(sel)
                    w.delete("sel.first", "sel.last")
        except tk.TclError:
            pass

    def _ctx_select_all(self, w: tk.Widget, kind: str) -> None:
        if kind == "entry":
            w.select_range(0, "end")
            w.icursor("end")
        elif kind == "text":
            w.tag_add("sel", "1.0", "end")

    def _build(self) -> None:
        pad = {"padx": 12, "pady": 6}

        f = ttk.Frame(self)
        f.pack(fill="both", expand=True)

        ttk.Label(f, text="Токен GitHub (classic PAT з правом repo)").grid(row=0, column=0, sticky="w", **pad)
        token_entry = ttk.Entry(f, textvariable=self.token_var, width=52, show="•")
        token_entry.grid(row=1, column=0, sticky="ew", **pad)

        ttk.Label(f, text="Секція для оновлення").grid(row=2, column=0, sticky="w", **pad)
        section = ttk.Combobox(
            f,
            textvariable=self.section_var,
            values=["Новини"],
            state="readonly",
            width=48,
        )
        section.grid(row=3, column=0, sticky="ew", **pad)
        section.current(0)

        ttk.Label(f, text="Дата (день / місяць / рік)").grid(row=4, column=0, sticky="w", **pad)
        date_row = ttk.Frame(f)
        date_row.grid(row=5, column=0, sticky="ew", **pad)
        for i, (lbl, var, w) in enumerate(
            [
                ("День", self.day_var, 6),
                ("Місяць", self.month_var, 6),
                ("Рік", self.year_var, 8),
            ]
        ):
            ttk.Label(date_row, text=lbl).grid(row=0, column=i * 2, padx=(0, 4))
            ttk.Entry(date_row, textvariable=var, width=w).grid(row=0, column=i * 2 + 1, padx=(0, 14))

        ttk.Label(
            f,
            text="Введіть текст (перший рядок — заголовок картки; далі текст анонсу та повного повідомлення)",
        ).grid(row=6, column=0, sticky="w", **pad)
        text_outer = tk.Frame(f)
        text_outer.grid(row=7, column=0, sticky="nsew", **pad)
        self.body_txt = tk.Text(text_outer, height=14, wrap="word", font=("Helvetica Neue", 13))
        ys = ttk.Scrollbar(text_outer, orient="vertical", command=self.body_txt.yview)
        self.body_txt.configure(yscrollcommand=ys.set)
        self.body_txt.pack(side="left", fill="both", expand=True)
        ys.pack(side="right", fill="y")

        img_row = ttk.Frame(f)
        img_row.grid(row=8, column=0, sticky="ew", **pad)
        ttk.Button(img_row, text="Додати зображення…", command=self._pick_images).pack(side="left")
        self.img_list = tk.Listbox(f, height=4, activestyle="dotbox")
        self.img_list.grid(row=9, column=0, sticky="ew", **pad)

        ttk.Button(f, text="Відправити", command=self._submit).grid(row=10, column=0, sticky="ew", **pad)
        ttk.Label(f, textvariable=self.status_var, foreground="#555").grid(row=11, column=0, sticky="w", **pad)

        f.columnconfigure(0, weight=1)
        f.rowconfigure(7, weight=1)

    def _pick_images(self) -> None:
        files = filedialog.askopenfilenames(
            title="Оберіть зображення",
            filetypes=[
                ("Зображення", "*.jpeg *.jpg *.png *.webp *.gif *.JPEG *.JPG *.PNG"),
                ("Усі файли", "*.*"),
            ],
        )
        for p in files:
            path = Path(p)
            if path not in self.image_paths:
                self.image_paths.append(path)
        self._refresh_image_list()

    def _refresh_image_list(self) -> None:
        self.img_list.delete(0, END)
        for p in self.image_paths:
            self.img_list.insert(END, str(p))

    def _parse_date(self) -> str:
        d = int(self.day_var.get().strip())
        m = int(self.month_var.get().strip())
        y = int(self.year_var.get().strip())
        datetime(y, m, d)  # validate
        return f"{d:02d}.{m:02d}.{y}"

    def _submit(self) -> None:
        token = self.token_var.get().strip()
        if not token:
            messagebox.showerror("Помилка", "Потрібен токен GitHub.")
            return

        try:
            date_display = self._parse_date()
        except Exception:
            messagebox.showerror("Помилка", "Некоректна дата. Використайте цілі числа для дня, місяця і року.")
            return

        raw_text = self.body_txt.get("1.0", END).strip()
        if not raw_text:
            messagebox.showerror("Помилка", "Введіть текст новини.")
            return

        self.status_var.set("Відправка…")
        thread = threading.Thread(
            target=self._worker,
            args=(token, date_display, raw_text),
            daemon=True,
        )
        thread.start()

    def _worker(self, token: str, date_display: str, raw_text: str) -> None:
        try:
            self._do_publish(token, date_display, raw_text)
            self.after(0, lambda: self.status_var.set("Готово. Зміни відправлено на GitHub."))
            self.after(0, lambda: messagebox.showinfo("Успіх", "Новина опублікована у гілку main репозиторію bpbv."))
        except github_api.GitHubError as e:
            msg = str(e)
            self.after(0, lambda: self.status_var.set("Помилка GitHub."))
            self.after(0, lambda: messagebox.showerror("GitHub", msg))
        except Exception:
            tb = traceback.format_exc()
            self.after(0, lambda: self.status_var.set("Помилка."))
            self.after(0, lambda: messagebox.showerror("Помилка", tb))

    def _do_publish(self, token: str, date_display: str, raw_text: str) -> None:
        index_html, index_sha = github_api.get_file_text(token, OWNER, REPO, "index.html", BRANCH)
        translations_js, trans_sha = github_api.get_file_text(token, OWNER, REPO, "translations.js", BRANCH)

        card_id = next_card_index(translations_js)
        title, excerpt, detail_text = split_title_excerpt_detail(raw_text)
        if not title:
            raise ValueError("Не вдалося визначити заголовок (порожній текст).")

        stamp = datetime.now(timezone.utc).strftime("%Y%m%d") + "-" + uuid.uuid4().hex[:6]
        rel_paths: list[str] = []
        for i, src in enumerate(self.image_paths):
            fname = sanitize_image_filename(src, i, stamp)
            repo_path = f"{IMAGE_PREFIX}/{fname}"
            blob = src.read_bytes()
            github_api.put_file_bytes(
                token,
                OWNER,
                REPO,
                repo_path,
                BRANCH,
                blob,
                f"news: add image {fname}",
                None,
            )
            rel_paths.append(repo_path.replace("\\", "/"))

        hero = rel_paths[0] if rel_paths else None
        if len(rel_paths) <= 1:
            body_images: list[str] = []
        else:
            body_images = rel_paths[1:]
        body_html = build_body_html(detail_text, body_images)
        article_html = build_article_html(card_id, date_display, title, excerpt, body_html, hero)

        new_index = inject_article_into_index(index_html, article_html)
        block = translation_keys_block(card_id, date_display, title, excerpt, body_html)
        new_trans = inject_translation_block(translations_js, block)

        if new_index == index_html:
            raise ValueError("index.html не змінено — перевірте розмітку.")
        if new_trans == translations_js:
            raise ValueError("translations.js не змінено — перевірте файл.")

        github_api.put_file_text(
            token,
            OWNER,
            REPO,
            "index.html",
            BRANCH,
            new_index,
            f"news: add card {card_id} — {title[:60]}",
            index_sha,
        )
        github_api.put_file_text(
            token,
            OWNER,
            REPO,
            "translations.js",
            BRANCH,
            new_trans,
            f"news: i18n for card {card_id}",
            trans_sha,
        )


def tk_string(master, value: str = "") -> StringVar:
    return StringVar(master=master, value=value)


def main() -> None:
    App().mainloop()


if __name__ == "__main__":
    main()
