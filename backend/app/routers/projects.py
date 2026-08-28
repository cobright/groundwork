# -*- coding: utf-8 -*-
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from ..db import connect, now

router = APIRouter(prefix="/api/projects", tags=["projects"])


class ProjectIn(BaseModel):
    name: str | None = None
    doc_type: str | None = None
    purpose: str | None = None
    audience: str | None = None
    due_date: str | None = None


@router.get("")
def list_projects():
    with connect() as c:
        rows = c.execute("SELECT * FROM projects ORDER BY updated_at DESC, id DESC").fetchall()
    return [dict(r) for r in rows]


@router.post("", status_code=201)
def create_project(p: ProjectIn):
    ts = now()
    with connect() as c:
        cur = c.execute(
            "INSERT INTO projects(name,doc_type,purpose,audience,due_date,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
            ((p.name or "").strip(), (p.doc_type or "").strip(), (p.purpose or "").strip(),
             (p.audience or "").strip(), (p.due_date or "").strip(), ts, ts),
        )
        row = c.execute("SELECT * FROM projects WHERE id=?", (cur.lastrowid,)).fetchone()
    return dict(row)


@router.put("/{pid}")
def update_project(pid: int, p: ProjectIn):
    """전달된 필드만 갱신(부분 수정). 보내지 않은 필드는 건드리지 않는다."""
    with connect() as c:
        cur = c.execute("SELECT * FROM projects WHERE id=?", (pid,)).fetchone()
        if not cur:
            raise HTTPException(404, "업무를 찾을 수 없습니다.")
        vals = {
            "name": p.name.strip() if p.name is not None else cur["name"],
            "doc_type": p.doc_type.strip() if p.doc_type is not None else cur["doc_type"],
            "purpose": p.purpose.strip() if p.purpose is not None else cur["purpose"],
            "audience": p.audience.strip() if p.audience is not None else cur["audience"],
            "due_date": p.due_date.strip() if p.due_date is not None else cur["due_date"],
        }
        c.execute("UPDATE projects SET name=?, doc_type=?, purpose=?, audience=?, due_date=?, updated_at=? WHERE id=?",
                  (vals["name"], vals["doc_type"], vals["purpose"], vals["audience"], vals["due_date"], now(), pid))
        row = c.execute("SELECT * FROM projects WHERE id=?", (pid,)).fetchone()
    return dict(row)


@router.get("/{pid}")
def get_project(pid: int):
    with connect() as c:
        row = c.execute("SELECT * FROM projects WHERE id=?", (pid,)).fetchone()
    if not row:
        raise HTTPException(404, "업무를 찾을 수 없습니다.")
    return dict(row)
