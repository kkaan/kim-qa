"""Native file dialog for picking a centroid file.

The server always binds 127.0.0.1 and opens the browser itself, so the machine
running this process is the machine looking at the page — a native dialog lands
on the right desktop. This is the same tkinter route `__main__._ask_root()`
already uses to choose the results root, so PyInstaller already bundles it.

Tk requires every call for a given interpreter to happen on one thread, but not
specifically the main one, so running the whole dialog inside the request's
threadpool thread is safe (verified on Windows). Callers must treat this as
fallible: a headless host has no display and tkinter may be absent entirely.
"""
from pathlib import Path
from typing import Optional

FILETYPES = [
    ("Centroid / text files", "*.txt"),
    ("All files", "*.*"),
]


def ask_centroid_file(initialdir: Optional[str] = None) -> Optional[str]:
    """Open a modal open-file dialog and return the chosen absolute path.

    Returns None when the user cancels. Raises RuntimeError when no dialog can
    be shown at all (no tkinter, no display), which the caller reports as 503
    rather than a crash.
    """
    try:
        import tkinter as tk
        from tkinter import filedialog
    except ImportError as e:                       # tkinter not bundled/installed
        raise RuntimeError(f"file dialog unavailable: {e}") from e

    root = None
    try:
        root = tk.Tk()
        root.withdraw()
        # Without this the dialog opens behind the browser window that asked
        # for it, looking like the button did nothing.
        root.attributes("-topmost", True)
        chosen = filedialog.askopenfilename(
            parent=root,
            title="Select centroid file",
            initialdir=initialdir or None,
            filetypes=FILETYPES,
        )
    except Exception as e:                         # noqa: BLE001 - no display, Tcl errors
        raise RuntimeError(f"file dialog unavailable: {e}") from e
    finally:
        if root is not None:
            try:
                root.destroy()
            except Exception:                      # noqa: BLE001 - already gone
                pass
    # askopenfilename returns "" on cancel, and on some Tk builds an empty tuple.
    return str(Path(chosen)) if chosen else None
