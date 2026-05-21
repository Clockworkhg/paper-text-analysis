# app/settings_store.py
from __future__ import annotations
from pathlib import Path
import json
from typing import Any

from app.constants import SETTINGS_FILE, RECENT_RUNS_MAX
import sys

class SettingsStore:
    def __init__(self, path: Path = SETTINGS_FILE):
        self.path = path

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"[settings] failed to load '{self.path}': {e}", file=sys.stderr)
            return {}

    def save(self, data: dict[str, Any]) -> None:
        self.path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

def add_recent_run(settings: dict[str, Any], run_item: dict[str, Any]) -> dict[str, Any]:
    """把一次运行记录塞进 settings['recent_runs']，去重、截断。"""
    recent = settings.get("recent_runs", [])
    # 去重：按 (docx_paths, out_dir) 或你原逻辑的唯一键
    recent = [x for x in recent if x != run_item]
    recent.insert(0, run_item)
    settings["recent_runs"] = recent[:RECENT_RUNS_MAX]
    return settings
