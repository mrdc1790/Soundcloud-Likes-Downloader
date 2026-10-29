"""Presentation primitives for the desktop app; no downloader or settings logic."""
import math
import sys
import tkinter as tk
from tkinter import ttk

BG = "#111318"
CARD = "#1b1e25"
SURFACE = "#232730"
LINE = "#303540"
TEXT = "#f3f4f7"
MUTED = "#a1a8b7"
ACCENT = "#ff7448"
GREEN = "#7cd4b0"
FONT = "Segoe UI" if sys.platform == "win32" else "DejaVu Sans"


def rounded_image(root, color, matte=CARD):
    """Small nine-slice button background, retaining a real ttk keyboard control."""
    size, radius = 32, 9
    image = tk.PhotoImage(master=root, width=size, height=size)
    foreground = tuple(int(color[i:i+2], 16) for i in (1, 3, 5))
    background = tuple(int(matte[i:i+2], 16) for i in (1, 3, 5))
    rows = []
    for y in range(size):
        row = []
        for x in range(size):
            dx = max(radius - x - 0.5, x + 0.5 - (size - radius), 0)
            dy = max(radius - y - 0.5, y + 0.5 - (size - radius), 0)
            alpha = min(1, max(0, radius - math.hypot(dx, dy) + 0.5))
            row.append("#%02x%02x%02x" % tuple(round(b + (f-b)*alpha) for f, b in zip(foreground, background)))
        rows.append("{" + " ".join(row) + "}")
    image.put(" ".join(rows))
    return image


def configure_theme(root):
    style = ttk.Style(root)
    try:
        import sv_ttk
    except ImportError:
        style.theme_use("clam")
    else:
        sv_ttk.set_theme("dark", root=root)
    style.configure(".", background=CARD, foreground=TEXT, font=(FONT, 10))
    style.configure("TFrame", background=CARD)
    style.configure("Shell.TFrame", background=BG)
    style.configure("TLabel", background=CARD, foreground=TEXT)
    style.configure("Muted.TLabel", foreground=MUTED)
    style.configure("Shell.TLabel", background=BG, foreground=MUTED, font=(FONT, 9))
    style.configure("TButton", padding=(10, 4), font=(FONT, 10))
    style.configure("TEntry", padding=(8, 4), fieldbackground=SURFACE, foreground=TEXT)
    style.configure("TCombobox", padding=(8, 4), fieldbackground=SURFACE, foreground=TEXT)
    style.map("TCombobox", foreground=[("disabled", "#6f7889"), ("readonly", TEXT)],
              fieldbackground=[("readonly", SURFACE)])
    root.option_add("*TCombobox*Listbox.background", SURFACE)
    root.option_add("*TCombobox*Listbox.foreground", TEXT)
    root.option_add("*TCombobox*Listbox.selectBackground", LINE)
    root.option_add("*TCombobox*Listbox.selectForeground", TEXT)
    style.configure("TCheckbutton", background=CARD, padding=(0, 5))
    style.configure("TNotebook", background=CARD, borderwidth=0, tabmargins=(0, 0, 0, 12))
    style.configure("TNotebook.Tab", padding=(12, 8), font=(FONT, 10))
    style.map("TNotebook.Tab", foreground=[("selected", TEXT), ("!selected", MUTED)])
    style.configure("Treeview", background=CARD, fieldbackground=CARD, foreground=TEXT,
                    rowheight=42, borderwidth=0, font=(FONT, 10))
    style.configure("Treeview.Heading", background=CARD, foreground=MUTED,
                    font=(FONT, 9, "bold"), padding=(10, 10), relief="flat")
    style.layout("Treeview.Heading", [("Treeheading.padding", {"sticky": "nswe", "children": [
        ("Treeheading.text", {"sticky": "we"})]})])
    style.map("Treeview", background=[("selected", "#34303a")], foreground=[("selected", TEXT)])
    style.layout("Treeview", [("Treeview.treearea", {"sticky": "nswe"})])

    # A custom image element gives the primary action an orange, rounded face;
    # focus, pointer, disabled and keyboard behavior still belong to ttk.Button.
    root._studio_images = [rounded_image(root, color) for color in
                           (ACCENT, "#ff8965", "#e4633b", "#38313a", "#ff9d7e")]
    style.element_create("Studio.Primary", "image", root._studio_images[0],
                         ("disabled", root._studio_images[3]), ("pressed", root._studio_images[2]),
                         ("active", root._studio_images[1]), ("focus", root._studio_images[4]),
                         border=10, padding=0, sticky="nsew")
    style.layout("Studio.TButton", [("Studio.Primary", {"sticky": "nsew", "children": [
        ("Button.padding", {"sticky": "nsew", "children": [("Button.label", {"sticky": "nsew"})]})]})])
    style.configure("Studio.TButton", foreground="#20150f", font=(FONT, 11, "bold"), padding=(16, 12))
    style.map("Studio.TButton", foreground=[("disabled", "#a79a9a"), ("!disabled", "#20150f")])
    tab_images = [rounded_image(root, color) for color in (CARD, SURFACE, "#292e38")]
    root._studio_images.extend(tab_images)
    style.element_create("Studio.Tab", "image", tab_images[0], ("selected", tab_images[1]),
                         ("active", tab_images[2]), border=10, padding=0, sticky="nsew")
    style.layout("TNotebook.Tab", [("Studio.Tab", {"sticky": "nswe", "children": [
        ("Notebook.padding", {"sticky": "nswe", "children": [("Notebook.label", {"sticky": "nswe"})]})]})])
    for part, color in (("trough", LINE), ("pbar", ACCENT)):
        image = tk.PhotoImage(master=root, width=1, height=4)
        image.put(color, to=(0, 0, 1, 4))
        root._studio_images.append(image)
        style.element_create(f"Studio.Horizontal.Progressbar.{part}", "image", image, sticky="nswe")
    style.layout("Studio.Horizontal.TProgressbar", [("Studio.Horizontal.Progressbar.trough", {
        "sticky": "nswe", "children": [("Studio.Horizontal.Progressbar.pbar", {"side": "left", "sticky": "ns"})]})])
    style.configure("Studio.Horizontal.TProgressbar", troughcolor=LINE, background=ACCENT,
                    lightcolor=ACCENT, darkcolor=ACCENT, bordercolor=LINE, borderwidth=0, thickness=4)


class Panel(tk.Canvas):
    """Resizable rounded surface with a normal ttk content frame."""
    def __init__(self, parent, *, padding=20, **kwargs):
        super().__init__(parent, bg=BG, highlightthickness=0, width=1, height=1, **kwargs)
        self.padding = padding
        self.outline = self.create_polygon(0, 0, 1, 0, 1, 1, fill=CARD, outline=LINE, smooth=True, splinesteps=24)
        self.content = ttk.Frame(self)
        self.slot = self.create_window(padding, padding, window=self.content, anchor="nw")
        self.bind("<Configure>", self._resize)

    def _resize(self, event):
        w, h, r = event.width-1, event.height-1, 18
        self.coords(self.outline, r, 1, w-r, 1, w, 1, w, r, w, h-r, w, h,
                    w-r, h, r, h, 1, h, 1, h-r, 1, r, 1, 1)
        self.itemconfigure(self.slot, width=max(1, w-self.padding*2), height=max(1, h-self.padding*2))


def wave_mark(parent, *, size=44, color=ACCENT, background=BG):
    canvas = tk.Canvas(parent, width=size, height=size, bg=background, highlightthickness=0, takefocus=False)
    unit = size / 44
    for i, height in enumerate((9, 19, 29, 21, 35, 25, 13)):
        x = (5 + i*5) * unit
        y = (44-height)/2 * unit
        canvas.create_line(x, y, x, y+height*unit, fill=color, width=3*unit, capstyle="round")
    return canvas


def bind_form_scrolling(canvas, content):
    """Keep wheel events local and keyboard-focused fields inside the viewport."""
    def wheel(event):
        if content.winfo_height() <= canvas.winfo_height():
            return
        delta = -1 if getattr(event, "num", None) == 4 else 1 if getattr(event, "num", None) == 5 else (-1 if event.delta > 0 else 1)
        canvas.yview_scroll(delta * 3, "units")
        return "break"

    def reveal(event):
        widget = event.widget
        top = widget.winfo_rooty() - content.winfo_rooty()
        low, high = canvas.canvasy(0), canvas.canvasy(canvas.winfo_height())
        if top < low:
            canvas.yview_moveto(max(0, top-8) / max(1, content.winfo_height()))
        elif top + widget.winfo_height() > high:
            canvas.yview_moveto((top + widget.winfo_height() + 8 - canvas.winfo_height()) / max(1, content.winfo_height()))

    def attach(widget):
        # Comboboxes retain their native mouse-wheel selection behavior.
        if not isinstance(widget, ttk.Combobox):
            widget.bind("<MouseWheel>", wheel, add=True)
            widget.bind("<Button-4>", wheel, add=True)
            widget.bind("<Button-5>", wheel, add=True)
        widget.bind("<FocusIn>", reveal, add=True)
        for child in widget.winfo_children():
            attach(child)
    attach(content)
    canvas.bind("<MouseWheel>", wheel)
    canvas.bind("<Button-4>", wheel)
    canvas.bind("<Button-5>", wheel)


def style_titlebar(root):
    """Opt into the OS dark caption for our own window; retain native controls."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        from ctypes import wintypes
        root.update_idletasks()
        ctypes.windll.user32.GetParent.argtypes = [wintypes.HWND]
        ctypes.windll.user32.GetParent.restype = wintypes.HWND
        handle = ctypes.windll.user32.GetParent(root.winfo_id())
        ctypes.windll.dwmapi.DwmSetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
        dark = ctypes.c_int(1)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(handle, 20, ctypes.byref(dark), ctypes.sizeof(dark))
    except (AttributeError, OSError):
        pass  # Older Windows builds keep their normal native caption.
