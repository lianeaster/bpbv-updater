#!/usr/bin/env python3
"""Desktop UI to publish a news item to lianeaster/bpbv via the GitHub API."""

from __future__ import annotations

import sys
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
    inject_translation_blocks,
    next_card_index,
    sanitize_image_filename,
    split_title_excerpt_detail,
    translation_keys_block,
)
from translator import translate

OWNER = "lianeaster"
REPO = "bpbv"
BRANCH = "main"
IMAGE_PREFIX = "images/news"

_BURGUNDY = "#5b1a3a"
_BG_WINDOW = "#f8f6f8"


def _font_tuple_platform() -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    """(body, small, title) font tuples for tk."""
    if sys.platform == "darwin":
        return ("Helvetica Neue", 12), ("Helvetica Neue", 10), ("Helvetica Neue", 18, "bold")
    if sys.platform == "win32":
        return ("Segoe UI", 10), ("Segoe UI", 9), ("Segoe UI", 16, "bold")
    return ("DejaVu Sans", 10), ("DejaVu Sans", 9), ("DejaVu Sans", 14, "bold")


def _load_token() -> str:
    """Load GitHub token from bundled or local config.py. Returns '' if unavailable."""
    try:
        from config import DEFAULT_TOKEN  # type: ignore[import-not-found]
        return DEFAULT_TOKEN.strip() if DEFAULT_TOKEN else ""
    except Exception:
        return ""


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("BPBV — оновлення новин")
        self.minsize(560, 700)
        self.geometry("640x760")
        self._font_body, self._font_small, self._font_title = _font_tuple_platform()

        self._token = _load_token()
        self.section_var = tk_string(self, value="news")
        self.day_var = tk_string(self, value=str(datetime.now().day))
        self.month_var = tk_string(self, value=str(datetime.now().month))
        self.year_var = tk_string(self, value=str(datetime.now().year))
        self.image_paths: list[Path] = []
        self.status_var = tk_string(self, value="Готово.")

        self._apply_style()
        self._build()
        self._bind_clipboard()
        self._bind_context_menu()

    def _apply_style(self) -> None:
        style = ttk.Style(self)
        if sys.platform == "win32":
            for t in ("vista", "xpnative", "clam", "default"):
                try:
                    style.theme_use(t)
                    break
                except tk.TclError:
                    continue
        else:
            try:
                style.theme_use("default")
            except tk.TclError:
                pass
        style.configure("TLabel", font=self._font_body)
        style.configure("TLabelframe", padding=10)
        style.configure("TLabelframe.Label", foreground=_BURGUNDY, font=self._font_body)
        style.configure("TButton", font=self._font_body, padding=(12, 6))
        style.configure(
            "Accent.TButton",
            font=self._font_body,
            padding=(16, 10),
            foreground="#ffffff",
            background=_BURGUNDY,
        )
        style.map(
            "Accent.TButton",
            background=[("active", "#721947"), ("disabled", "#a08090")],
            foreground=[("disabled", "#e8e0e4")],
        )

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
        gap = {"padx": 0, "pady": (0, 14)}

        outer = ttk.Frame(self, padding=18)
        outer.pack(fill="both", expand=True)

        # -------- Header --------
        head = ttk.Frame(outer)
        head.grid(row=0, column=0, sticky="ew", **gap)
        ttk.Label(
            head,
            text="Публікація новини на сайт кафедри БПБВ",
            font=self._font_title,
            foreground=_BURGUNDY,
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            head,
            text="Зміни відправляються у репозиторій lianeaster/bpbv (гілка main).",
            font=self._font_small,
            foreground="#5c4a52",
        ).grid(row=1, column=0, sticky="w", pady=(4, 0))

        row = 1

        # -------- Section & date --------
        lf_meta = ttk.Labelframe(outer, text="Секція та дата", padding=10)
        lf_meta.grid(row=row, column=0, sticky="ew", **gap)
        row += 1
        ttk.Label(lf_meta, text="Секція для оновлення").grid(row=0, column=0, sticky="w", pady=(0, 4))
        section = ttk.Combobox(
            lf_meta,
            textvariable=self.section_var,
            values=["Новини"],
            state="readonly",
            width=54,
        )
        section.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        section.current(0)

        ttk.Label(lf_meta, text="Дата публікації (день · місяць · рік)").grid(row=2, column=0, sticky="w", pady=(0, 4))
        date_row = ttk.Frame(lf_meta)
        date_row.grid(row=3, column=0, sticky="w")
        for i, (lbl, var, w) in enumerate(
            [
                ("День", self.day_var, 6),
                ("Місяць", self.month_var, 6),
                ("Рік", self.year_var, 8),
            ]
        ):
            ttk.Label(date_row, text=lbl).grid(row=0, column=i * 2, padx=(0, 4))
            ttk.Entry(date_row, textvariable=var, width=w).grid(row=0, column=i * 2 + 1, padx=(0, 16))
        lf_meta.columnconfigure(0, weight=1)

        # -------- Text --------
        lf_text = ttk.Labelframe(outer, text="Текст новини", padding=10)
        lf_text.grid(row=row, column=0, sticky="nsew", **gap)
        row += 1
        ttk.Label(
            lf_text,
            text="Перший рядок — заголовок на картці. Далі 3 перші рядки — видимий анонс; решта — лише під «Детальніше» на сайті.",
            font=self._font_small,
            wraplength=580,
        ).grid(row=0, column=0, sticky="w", pady=(0, 8))
        text_outer = tk.Frame(lf_text)
        text_outer.grid(row=1, column=0, sticky="nsew")
        self.body_txt = tk.Text(text_outer, height=14, wrap="word")
        ys = ttk.Scrollbar(text_outer, orient="vertical", command=self.body_txt.yview)
        self.body_txt.configure(yscrollcommand=ys.set)
        self.body_txt.pack(side="left", fill="both", expand=True)
        ys.pack(side="right", fill="y")
        self.body_txt.configure(
            font=self._font_body,
            bg="#ffffff",
            fg="#261a22",
            insertbackground=_BURGUNDY,
            relief="flat",
            highlightthickness=1,
            highlightbackground="#d9ced4",
            padx=8,
            pady=8,
        )
        lf_text.columnconfigure(0, weight=1)
        lf_text.rowconfigure(1, weight=1)

        # -------- Images --------
        lf_img = ttk.Labelframe(outer, text="Зображення (JPEG, PNG, WebP…)", padding=10)
        lf_img.grid(row=row, column=0, sticky="ew", **gap)
        row += 1
        img_row = ttk.Frame(lf_img)
        img_row.grid(row=0, column=0, sticky="w", pady=(0, 8))
        ttk.Button(img_row, text="Додати файли…", command=self._pick_images).pack(side="left")
        self.img_list = tk.Listbox(
            lf_img,
            height=4,
            activestyle="dotbox",
            font=self._font_small,
            bg="#ffffff",
            fg="#261a22",
            selectbackground=_BURGUNDY,
            selectforeground="#ffffff",
            relief="flat",
            highlightthickness=1,
            highlightbackground="#d9ced4",
        )
        self.img_list.grid(row=1, column=0, sticky="ew")
        lf_img.columnconfigure(0, weight=1)

        # -------- Actions --------
        act = ttk.Frame(outer)
        act.grid(row=row, column=0, sticky="ew", pady=(4, 0))
        ttk.Button(act, text="Відправити на GitHub", command=self._submit, style="Accent.TButton").pack(
            fill="x", pady=(0, 8)
        )
        ttk.Label(act, textvariable=self.status_var, foreground="#5c4a52", font=self._font_small).pack(anchor="w")

        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(2, weight=1)

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
        token = self._token
        if not token:
            messagebox.showerror(
                "Помилка",
                "Токен GitHub не знайдено.\n\n"
                "Цю збірку програми створено без вбудованого токена.\n"
                "Зверніться до адміністратора або завантажте актуальну версію.",
            )
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
        # Pre-read translations.js to determine next card index
        translations_js_pre, _ = github_api.get_file_text(token, OWNER, REPO, "translations.js", BRANCH)
        card_id = next_card_index(translations_js_pre)

        title, excerpt, detail_text = split_title_excerpt_detail(raw_text)
        if not title:
            raise ValueError("Не вдалося визначити заголовок (порожній текст).")

        # 1. Upload images (each creates a commit)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d") + "-" + uuid.uuid4().hex[:6]
        rel_paths: list[str] = []
        for i, src in enumerate(self.image_paths):
            fname = sanitize_image_filename(src, i, stamp)
            repo_path = f"{IMAGE_PREFIX}/{fname}"
            blob = src.read_bytes()
            github_api.put_file_bytes(
                token, OWNER, REPO, repo_path, BRANCH,
                blob, f"news: add image {fname}", None,
            )
            rel_paths.append(repo_path.replace("\\", "/"))

        hero = rel_paths[0] if rel_paths else None
        if len(rel_paths) <= 1:
            body_images: list[str] = []
        else:
            body_images = rel_paths[1:]
        body_html = build_body_html(detail_text, body_images)
        article_html = build_article_html(card_id, date_display, title, excerpt, body_html, hero)

        # Build Ukrainian translation block
        blocks: dict[str, str] = {
            "uk": translation_keys_block(card_id, date_display, title, excerpt, body_html),
        }

        # Translate to EN / DE / FR
        lang_labels = [("en", "англійську"), ("de", "німецьку"), ("fr", "французьку")]
        for lang, label in lang_labels:
            self.after(0, lambda l=label: self.status_var.set(f"Переклад на {l}…"))
            t_title = translate(title, lang)
            t_excerpt = translate(excerpt, lang) if excerpt else ""
            t_detail = translate(detail_text, lang) if detail_text else ""
            t_body_html = build_body_html(t_detail, body_images)
            blocks[lang] = translation_keys_block(card_id, date_display, t_title, t_excerpt, t_body_html)

        self.after(0, lambda: self.status_var.set("Оновлення index.html…"))

        # 2. Read index.html with fresh SHA, modify, write immediately
        index_html, index_sha = github_api.get_file_text(token, OWNER, REPO, "index.html", BRANCH)
        new_index = inject_article_into_index(index_html, article_html)
        if new_index == index_html:
            raise ValueError("index.html не змінено — перевірте розмітку.")
        github_api.put_file_text(
            token, OWNER, REPO, "index.html", BRANCH,
            new_index, f"news: add card {card_id} — {title[:60]}", index_sha,
        )

        self.after(0, lambda: self.status_var.set("Оновлення translations.js…"))

        # 3. Read translations.js with fresh SHA, modify, write immediately
        translations_js, trans_sha = github_api.get_file_text(token, OWNER, REPO, "translations.js", BRANCH)
        new_trans = inject_translation_blocks(translations_js, blocks)
        if new_trans == translations_js:
            raise ValueError("translations.js не змінено — перевірте файл.")
        github_api.put_file_text(
            token, OWNER, REPO, "translations.js", BRANCH,
            new_trans, f"news: i18n for card {card_id}", trans_sha,
        )


def tk_string(master, value: str = "") -> StringVar:
    return StringVar(master=master, value=value)


def main() -> None:
    App().mainloop()


if __name__ == "__main__":
    main()
