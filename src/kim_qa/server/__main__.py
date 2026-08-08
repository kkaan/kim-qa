"""Entry point: python -m kim_qa.server --root <results root>."""
import argparse
import socket
import threading
import webbrowser

import uvicorn

from kim_qa.version import __version__

from .app import create_app
from .config import ServerConfig
from .state import load_vendor


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        prog="kim_qa.server",
        description="KIM QA Analysis: browser-based overlay GUI")
    p.add_argument("--version", action="version",
                   version=f"KIM-QA-Server {__version__}")
    p.add_argument("--root", default=None,
                   help="Results root (folder of session folders). "
                        "Omit to pick via folder dialog.")
    p.add_argument("--traces-root", default=None,
                   help="Hexamotion traces root (default: <root>/Motion traces)")
    p.add_argument("--baselines-root", default=None,
                   help="Baseline KIM-log folders root "
                        "(default: <root>/Baselines)")
    p.add_argument("--vendor", choices=["Elekta", "Varian"], default=None,
                   help="Machine vendor (default: last one saved for this "
                        "root, else Elekta)")
    p.add_argument("--port", type=int, default=0,
                   help="Port (default: pick a free one)")
    p.add_argument("--no-browser", action="store_true")
    return p.parse_args(argv)


def _ask_root() -> str | None:
    import tkinter as tk
    from tkinter import filedialog
    tk_root = tk.Tk()
    tk_root.withdraw()
    chosen = filedialog.askdirectory(title="Select KIM results root")
    tk_root.destroy()
    return chosen or None


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main(argv=None) -> int:
    args = parse_args(argv)
    root = args.root or _ask_root()
    if not root:
        print("No results root selected; exiting.")
        return 1
    # Vendor resolution: explicit flag > persisted per-root choice > Elekta.
    vendor = args.vendor or load_vendor(root) or "Elekta"
    config = ServerConfig(root=root, traces_root=args.traces_root,
                          baselines_root=args.baselines_root, vendor=vendor)
    app = create_app(config)
    port = args.port or _free_port()
    url = f"http://127.0.0.1:{port}/"
    print(f"KIM QA Analysis serving {config.root}")
    print(f"  {url}")
    if not args.no_browser:
        threading.Timer(1.0, webbrowser.open, args=[url]).start()
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
