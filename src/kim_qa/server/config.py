"""Server configuration: results root, traces root, machine vendor."""
from dataclasses import dataclass
from pathlib import Path

VENDORS = ("Elekta", "Varian")


@dataclass
class ServerConfig:
    root: Path
    traces_root: Path | None = None
    vendor: str = "Elekta"

    def __post_init__(self):
        self.root = Path(self.root)
        self.traces_root = (
            Path(self.traces_root) if self.traces_root is not None
            else self.root / "Motion traces"
        )
        if self.vendor not in VENDORS:
            raise ValueError(f"vendor must be one of {VENDORS}, got {self.vendor!r}")
