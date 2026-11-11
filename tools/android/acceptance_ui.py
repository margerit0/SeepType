"""Small native Windows control panel; all product UI remains in the Android APK."""
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import ctypes
import os
import queue
import threading
import time
import traceback
import tkinter as tk
from tkinter import font, messagebox, ttk

from tools.android.acceptance import Acceptance, InstanceLock, SCENARIOS, WORK
from tools.android.common import write


class Panel:
    def __init__(self, root, serial):
        self.root = root
        self.messages = queue.Queue()
        self.backend = Acceptance(lambda text: self.messages.put(("status", text)), serial)
        self.busy = False
        self.ready = False
        self.closing = False
        self.controls = []
        self.status = tk.StringVar(value="正在准备验收环境…")
        self.version = tk.StringVar(value="真实 Android APK · 本机运行")
        self.scenario = tk.StringVar(value=SCENARIOS["text"][0])
        self.display = tk.StringVar(value="标准竖屏")
        self.record_text = tk.StringVar(value="开始录像")
        self.last_saved = tk.StringVar(value="截图和录像保存在本机开发缓存。")
        self.display_options = {"标准竖屏": "portrait", "窄屏 · 320 dp": "narrow", "横屏": "landscape",
                                "系统字号 · 100%": "font100", "系统字号 · 130%": "font130",
                                "系统浅色": "light", "系统深色": "dark"}
        self.layout()
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.after(100, self.drain)
        root.after(250, self.start)

    def layout(self):
        root = self.root
        root.title("拾词 · Windows 验收面板")
        root.configure(bg="#f5f7f4")
        width = min(590, max(500, root.winfo_screenwidth() // 3))
        height = min(850, root.winfo_screenheight() - 120)
        root.geometry(f"{width}x{height}+40+40")
        root.minsize(480, 520)
        for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont"):
            font.nametofont(name).configure(family="Microsoft YaHei UI", size=10)
        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure("TFrame", background="#f5f7f4")
        style.configure("TLabel", background="#f5f7f4", foreground="#263b30", font=("Microsoft YaHei UI", 10))
        style.configure("Sub.TLabel", foreground="#66766b", font=("Microsoft YaHei UI", 9))
        style.configure("Title.TLabel", font=("Microsoft YaHei UI", 25, "bold"), foreground="#285d45")
        style.configure("Heading.TLabel", font=("Microsoft YaHei UI", 11, "bold"))
        style.configure("TButton", font=("Microsoft YaHei UI", 10), padding=(12, 9),
                        background="#ffffff", foreground="#294835", bordercolor="#d5dfd5", relief="flat")
        style.map("TButton", background=[("active", "#e5eee5"), ("disabled", "#edf0eb")],
                  foreground=[("disabled", "#8a978d")])
        style.configure("Accent.TButton", background="#2d6b53", foreground="white", bordercolor="#2d6b53")
        style.map("Accent.TButton", background=[("active", "#24573f"), ("disabled", "#a7b9aa")], foreground=[("disabled", "white")])
        style.configure("TCombobox", padding=8, foreground="#263b30", fieldbackground="white")
        outer = ttk.Frame(root, padding=(24, 20))
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="拾词", style="Title.TLabel").pack(anchor="w")
        ttk.Label(outer, text="Windows 交互验收", style="Heading.TLabel").pack(anchor="w", pady=(4, 3))
        ttk.Label(outer, textvariable=self.version, style="Sub.TLabel").pack(anchor="w", pady=(0, 14))
        status = tk.Label(outer, textvariable=self.status, bg="#e5eee4", fg="#2d5b40", justify="left",
                          anchor="w", padx=14, pady=12, font=("Microsoft YaHei UI", 10), wraplength=width - 100)
        status.pack(fill="x")
        scroll_area = ttk.Frame(outer)
        scroll_area.pack(fill="both", expand=True, pady=(12, 0))
        canvas = tk.Canvas(scroll_area, bg="#f5f7f4", highlightthickness=0, borderwidth=0)
        scrollbar = ttk.Scrollbar(scroll_area, orient="vertical", command=canvas.yview)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        canvas.configure(yscrollcommand=scrollbar.set)
        content = ttk.Frame(canvas)
        item = canvas.create_window((0, 0), window=content, anchor="nw")
        content.bind("<Configure>", lambda _: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda event: canvas.itemconfigure(item, width=event.width))
        # Bind only this panel's widgets, never a global desktop mouse hook.
        root.bind("<MouseWheel>", lambda event: canvas.yview_scroll(-int(event.delta / 120), "units"))

        row = self.row(content)
        self.button(row, "手机窗口", lambda: self.submit(self.reopen), 0, accent=True)
        self.button(row, "键盘设置", lambda: self.submit(lambda: self.backend.open_app("settings")), 1)
        self.button(row, "应用首页", lambda: self.submit(lambda: self.backend.open_app("home")), 2)
        self.section(content, "输入场景")
        ttk.Label(content, text="切换场景会开始一份新的测试输入。", style="Sub.TLabel").pack(anchor="w", pady=(0, 8))
        row = self.row(content)
        combo = ttk.Combobox(row, textvariable=self.scenario, state="readonly", values=[item[0] for item in SCENARIOS.values()])
        combo.grid(row=0, column=0, columnspan=2, sticky="ew", padx=(0, 8))
        self.controls.append((combo, "readonly"))
        self.button(row, "打开场景", lambda: self.submit(self.open_scene), 2, accent=True)
        row = self.row(content)
        self.button(row, "自由输入", lambda: self.pick_scene("text"), 0)
        self.button(row, "多行文本", lambda: self.pick_scene("multiline"), 1)
        self.button(row, "密码", lambda: self.pick_scene("password"), 2)
        self.section(content, "显示与布局")
        row = self.row(content)
        combo = ttk.Combobox(row, textvariable=self.display, state="readonly", values=list(self.display_options))
        combo.grid(row=0, column=0, columnspan=2, sticky="ew", padx=(0, 8))
        self.controls.append((combo, "readonly"))
        self.button(row, "应用", lambda: self.submit(self.change_display), 2)
        ttk.Label(content, text="系统浅深色在键盘选择“跟随系统”时生效。\n拼音方案、英文开关和键盘高度请在“键盘设置”中调整。",
                  style="Sub.TLabel", wraplength=width - 100).pack(anchor="w", pady=(4, 0))
        self.section(content, "记录问题")
        row = self.row(content)
        self.button(row, "保存截图", lambda: self.submit(self.capture), 0)
        record = self.button(row, "", lambda: self.submit(self.record), 1)
        record.configure(textvariable=self.record_text)
        self.button(row, "打开记录", self.open_captures, 2, needs_device=False)
        ttk.Label(content, textvariable=self.last_saved, style="Sub.TLabel", wraplength=width - 100).pack(anchor="w", pady=(5, 10))
        self.section(content, "操作提示")
        ttk.Label(content, text="体验拼音与候选，请点手机画面上的键盘。\n按住候选查看释义，按住并拖动可滑动页面。\n右键返回 · Alt+F 全屏 · 每段录像最多 2 分钟。",
                  style="Sub.TLabel", wraplength=width - 100, justify="left").pack(anchor="w", pady=(0, 12))
        row = self.row(content)
        self.button(row, "重新开始输入", lambda: self.submit(self.open_scene), 0)
        self.button(row, "重新连接", self.start, 1, needs_device=False)
        self.button(row, "使用说明", self.open_docs, 2, needs_device=False)
        ttk.Label(content, text="关闭面板会恢复模拟器显示设置。", style="Sub.TLabel").pack(anchor="w", pady=(8, 12))
        self.set_busy(False)

    @staticmethod
    def row(parent):
        frame = ttk.Frame(parent)
        frame.pack(fill="x", pady=4)
        for column in range(3):
            frame.columnconfigure(column, weight=1, uniform="button")
        return frame

    @staticmethod
    def section(parent, title):
        ttk.Separator(parent).pack(fill="x", pady=(14, 12))
        ttk.Label(parent, text=title, style="Heading.TLabel").pack(anchor="w", pady=(0, 7))

    def button(self, parent, title, command, column, accent=False, needs_device=True):
        widget = ttk.Button(parent, text=title, command=command, style="Accent.TButton" if accent else "TButton")
        widget.grid(row=0, column=column, sticky="ew", padx=(0 if column == 0 else 4, 0 if column == 2 else 4))
        self.controls.append((widget, "normal" if needs_device else "offline"))
        return widget

    def set_busy(self, busy):
        self.busy = busy
        for widget, enabled in self.controls:
            widget.configure(state="disabled" if busy or (not self.ready and enabled != "offline")
                             else "normal" if enabled == "offline" else enabled)

    def submit(self, action):
        if self.busy:
            return
        self.selected_scenario = next(key for key, value in SCENARIOS.items() if value[0] == self.scenario.get())
        self.selected_display = self.display_options[self.display.get()]
        self.set_busy(True)

        def worker():
            try:
                action()
            except Exception as error:
                with (self.backend.session / "launcher-errors.log").open("a", encoding="utf-8") as output:
                    traceback.print_exc(file=output)
                self.messages.put(("error", str(error)))
            finally:
                self.messages.put(("done", None))

        threading.Thread(target=worker, name="StudyIME-acceptance", daemon=False).start()

    def geometry(self):
        self.root.update_idletasks()
        height = max(420, min(850, self.root.winfo_screenheight() - 150))
        x = self.root.winfo_rootx() + self.root.winfo_width() + 28
        x = min(x, max(0, self.root.winfo_screenwidth() - int(height * 1080 / 2340) - 40))
        return x, 50, height

    def start(self):
        if self.busy:
            return
        geometry = self.geometry()
        self.ready = False
        self.version.set("正在准备真实 Android APK…")

        def prepare():
            if self.backend.baseline:
                self.backend.close()
            self.backend.prepare(geometry)
            self.messages.put(("ready", None))

        self.submit(prepare)

    def reopen(self):
        self.backend.open_mirror()
        self.messages.put(("status", "手机窗口已打开。"))

    def pick_scene(self, kind):
        self.scenario.set(SCENARIOS[kind][0])
        self.submit(lambda: self.backend.open_scenario(kind))

    def open_scene(self):
        # tkinter variables must be read on the UI thread; drain stores selections.
        self.backend.open_scenario(self.selected_scenario)

    def change_display(self):
        self.backend.display(self.selected_display)
        self.messages.put(("status", "显示设置已更新。"))

    def capture(self):
        result = self.backend.screenshot()
        self.messages.put(("saved", result.name))
        self.messages.put(("status", "已保存原生截图和 APK 版本记录。"))

    def record(self):
        if self.backend.recording:
            result = self.backend.stop_recording()
            self.messages.put(("saved", result.name))
            self.messages.put(("status", "录像已保存。"))
        else:
            self.backend.start_recording()
            self.messages.put(("status", "正在录像；继续在手机窗口操作，完成后点“结束录像”。"))

    def open_captures(self):
        path = WORK / "captures"
        path.mkdir(parents=True, exist_ok=True)
        os.startfile(path.resolve())

    @staticmethod
    def open_docs():
        from tools.android.common import ROOT
        os.startfile(ROOT / "docs/android-acceptance.md")

    def close(self):
        if self.closing:
            return
        self.closing = True
        self.status.set("正在结束验收并恢复显示设置…")
        if not self.busy:
            self.finish_close()

    def finish_close(self):
        def cleanup():
            try:
                self.backend.close()
            finally:
                self.messages.put(("destroy", None))
        self.submit(cleanup)

    def drain(self):
        destroy = False
        while True:
            try:
                kind, value = self.messages.get_nowait()
            except queue.Empty:
                break
            if kind == "status":
                self.status.set(value)
            elif kind == "error":
                self.status.set("操作未完成，可查看日志后重试。")
                messagebox.showerror("拾词 · 操作未完成", value + "\n\n日志：" + str(self.backend.session.resolve()), parent=self.root)
            elif kind == "ready":
                self.ready = True
                self.version.set(f"Release {self.backend.version} · APK {self.backend.installed[0]['sha256'][:10]}")
            elif kind == "saved":
                self.last_saved.set("已保存：" + value)
            elif kind == "done":
                self.set_busy(False)
            elif kind == "destroy":
                destroy = True
        if destroy:
            self.root.destroy()
            return
        if self.backend.recording:
            seconds = int(time.monotonic() - self.backend.recording["started"])
            self.record_text.set(f"结束录像 {seconds // 60}:{seconds % 60:02d}")
            if seconds >= 121 and not self.busy:
                self.submit(self.record)
        else:
            self.record_text.set("开始录像")
        if self.closing and not self.busy:
            self.finish_close()
        self.root.after(100, self.drain)


def run(serial=None):
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (AttributeError, OSError):
        pass
    root = tk.Tk()
    root.withdraw()
    try:
        with InstanceLock():
            Panel(root, serial)
            root.deiconify()
            root.mainloop()
    except Exception as error:
        write(WORK / "startup-error.log", traceback.format_exc())
        messagebox.showerror("拾词 · 无法打开验收面板", str(error), parent=root)
        root.destroy()
