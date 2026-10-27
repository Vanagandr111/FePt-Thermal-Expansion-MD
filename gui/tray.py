#!/usr/bin/env python
"""
tray.py — Windows system tray icon for the FePt GUI.

Menu: open the GUI in the browser (default double-click), restart the
program, or quit it fully (the quit path shares the shutdown function
used by the API, so no stray processes remain).

pystray + Pillow are optional: when they are not bundled (dev runs, an
old exe) the tray silently stays off and everything else keeps working.
"""

import os
import threading
import webbrowser

try:
    import pystray
    from PIL import Image, ImageDraw
    HAVE_TRAY = True
    TRAY_ERR = ''
except Exception as exc:            # pragma: no cover - optional deps
    HAVE_TRAY = False
    TRAY_ERR = str(exc)

_icon = None


def _make_image():
    """A small dark rounded tile with an 'F' mark (matches the GUI theme)."""
    img = Image.new('RGBA', (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([2, 2, 61, 61], radius=14,
                        fill=(26, 31, 43, 255),
                        outline=(90, 98, 112, 255), width=3)
    fg = (159, 176, 200, 255)
    d.rectangle([20, 15, 26, 49], fill=fg)     # stem
    d.rectangle([20, 15, 44, 21], fill=fg)     # top bar
    d.rectangle([20, 30, 39, 36], fill=fg)     # middle bar
    d.ellipse([44, 42, 54, 52], fill=(120, 140, 170, 255))  # accent dot
    return img


def start(gui_url, on_restart=None, on_quit=None):
    """Show the tray icon in a daemon thread. Returns True when enabled."""
    global _icon
    if not HAVE_TRAY:
        return False

    def _open(icon=None, item=None):
        webbrowser.open(gui_url)

    def _restart(icon=None, item=None):
        if on_restart:
            threading.Thread(target=on_restart, daemon=True).start()

    def _quit(icon=None, item=None):
        if on_quit:
            threading.Thread(target=on_quit, daemon=True).start()

    menu = pystray.Menu(
        pystray.MenuItem('Открыть GUI в браузере', _open, default=True),
        pystray.MenuItem('Перезагрузить программу', _restart),
        pystray.MenuItem('Выключить программу', _quit),
    )
    _icon = pystray.Icon('fept-gui', _make_image(),
                         'FePt Thermal Expansion GUI', menu)
    threading.Thread(target=_icon.run, daemon=True).start()
    return True


def stop():
    """Remove the tray icon (used on shutdown paths)."""
    global _icon
    if _icon is not None:
        try:
            _icon.stop()
        except Exception:
            pass
        _icon = None
