# -*- coding: utf-8 -*-
import json
import os
import sys
import subprocess
from pathlib import Path
from datetime import date
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from ..db import connect

router = APIRouter(prefix="/api/inbox", tags=["inbox"])


# OS 폴더 선택창을 '별도 프로세스'로 띄운다(서버 스레드와 분리 → 멈춤/충돌 방지).
_PICK_SCRIPT = r'''
import sys
try:
    import tkinter as tk
    from tkinter import filedialog
except Exception:
    print("__NO_TK__"); sys.exit(0)
try:
    root = tk.Tk(); root.withdraw()
    try: root.attributes("-topmost", True)
    except Exception: pass
    path = filedialog.askdirectory(title="보고 폴더 선택")
    root.destroy()
    print(path or "")
except Exception as e:
    print("__ERR__" + str(e))
'''

# tkinter 가 없는 환경(예: 윈도우 임베디드 파이썬)에서 쓰는 폴백 — PowerShell 폴더 대화상자.
_PS_PICK = (
    "[Console]::OutputEncoding=[System.Text.Encoding]::UTF8;"
    "Add-Type -AssemblyName System.Windows.Forms;"
    "$f=New-Object System.Windows.Forms.FolderBrowserDialog;"
    "$f.Description='보고 폴더 선택';$f.ShowNewFolderButton=$false;"
    "if($f.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK){[Console]::Out.Write($f.SelectedPath)}"
)


def _pick_via_tk():
    """tkinter 로 폴더 선택. 사용 가능하면 경로(취소 시 ''), 불가하면 None."""
    try:
        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        out = subprocess.run([sys.executable, "-c", _PICK_SCRIPT],
                             capture_output=True, timeout=300, env=env)
    except Exception:
        return None
    text = (out.stdout or b"").decode("utf-8", "replace").strip()
    val = text.splitlines()[-1] if text else ""
    if val == "__NO_TK__" or val.startswith("__ERR__"):
        return None
    return val


def _pick_via_powershell():
    """윈도우 PowerShell 폴더 대화상자. 경로(취소 시 ''), 실패 시 None."""
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-STA", "-Command", _PS_PICK],
            capture_output=True, timeout=300)
    except Exception:
        return None
    if out.returncode != 0:
        return None
    return (out.stdout or b"").decode("utf-8", "replace").strip()


@router.post("/pick-folder")
def pick_folder():
    """로컬 PC에 OS 폴더 선택창을 띄우고 고른 경로를 돌려준다.
    tkinter 를 먼저 쓰고, 없으면(임베디드 파이썬 등) 윈도우에서는 PowerShell 로 폴백한다."""
    result = _pick_via_tk()
    if result is not None:
        return {"available": True, "folder": result}
    if os.name == "nt":
        ps = _pick_via_powershell()
        if ps is not None:
            return {"available": True, "folder": ps}
    return {"available": False, "folder": ""}


def _get_setting(c, key, default=""):
    r = c.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return r["value"] if r else default


def _d_day(due: str):
    if not due:
        return None
    try:
        return (date.fromisoformat(due) - date.today()).days
    except Exception:
        return None


class InboxSettingsIn(BaseModel):
    folder: str | None = None


@router.get("/settings")
def get_inbox_settings():
    with connect() as c:
        return {"folder": _get_setting(c, "inbox_folder", "")}


@router.put("/settings")
def put_inbox_settings(s: InboxSettingsIn):
    with connect() as c:
        if s.folder is not None:
            c.execute(
                "INSERT INTO settings(key,value) VALUES('inbox_folder',?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (s.folder.strip(),))
        return {"folder": _get_setting(c, "inbox_folder", "")}


def _flatten(rep, filename):
    p = rep.get("project", {}) or {}
    due = p.get("due_date", "")
    dd = _d_day(due)
    return {
        "author": rep.get("author", "") or "(이름 미상)",
        "project_name": p.get("name", "") or "(무제)",
        "doc_type": p.get("doc_type", ""),
        "generated_at": rep.get("generated_at", ""),
        "status_label": rep.get("status_label", ""),
        "message": rep.get("message", ""),
        "stage_label": p.get("stage_label", ""),
        "stage_index": p.get("stage_index", 0),
        "progress": p.get("progress", 0),
        "bodies_filled": p.get("bodies_filled", 0),
        "outline_total": p.get("outline_total", 0),
        "due_date": due, "d_day": dd, "overdue": (dd is not None and dd < 0),
        "severe": p.get("severe", 0), "unresolved": p.get("unresolved", 0),
        "need_flags": p.get("need_flags", 0),
        "ev_unconfirmed": p.get("ev_unconfirmed", 0), "ev_changed": p.get("ev_changed", 0),
        "req_open": p.get("req_open", 0), "req_overdue": p.get("req_overdue", 0),
        "blockers": p.get("blockers", 0),
        "file": filename,
    }


@router.get("")
def read_inbox(folder: str | None = None):
    """지정한 폴더의 진행보고 파일을 읽어, (보고자·업무)별 최신 보고만 모아 돌려준다.
    파일을 읽기만 하며, 우리 형식이 아닌 파일은 조용히 건너뛴다."""
    with connect() as c:
        folder = (folder or "").strip() or _get_setting(c, "inbox_folder", "")
    if not folder:
        return {"folder": "", "reports": [], "scanned": 0, "skipped": 0, "errors": [],
                "hint": "메신저 다운로드 폴더 경로를 지정하세요."}

    path = Path(folder).expanduser()
    if not path.exists() or not path.is_dir():
        raise HTTPException(400, f"폴더를 찾을 수 없습니다: {folder}")

    reports = {}
    scanned = skipped = 0
    errors = []
    try:
        files = sorted(path.glob("*.json"))
    except PermissionError:
        raise HTTPException(400, f"폴더를 읽을 권한이 없습니다: {folder}")

    for f in files:
        scanned += 1
        try:
            rep = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            skipped += 1
            continue
        if not isinstance(rep, dict) or rep.get("type") != "workbench-progress-report":
            skipped += 1
            continue
        item = _flatten(rep, f.name)
        key = (item["author"], item["project_name"])
        # 같은 보고자·업무의 더 최신(generated_at 큰) 것만 유지
        prev = reports.get(key)
        if prev is None or (item["generated_at"] or "") >= (prev["generated_at"] or ""):
            reports[key] = item

    items = list(reports.values())
    # 정렬: 마감 초과 → 임박 → 미해결 많은 순
    def keyf(x):
        dd = x["d_day"]
        return (0 if x["overdue"] else 1, dd if dd is not None else 9999, -x["blockers"], -x["unresolved"])
    items.sort(key=keyf)
    return {"folder": folder, "reports": items, "scanned": scanned,
            "skipped": skipped, "errors": errors,
            "authors": sorted({i["author"] for i in items}),
            "projects": sorted({i["project_name"] for i in items})}
