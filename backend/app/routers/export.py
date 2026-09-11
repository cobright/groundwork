# -*- coding: utf-8 -*-
import urllib.parse
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from ..db import connect
from ..services.export_docx import final_check, build_docx
from ..services.numbering import sections_with_body

router = APIRouter(prefix="/api/projects", tags=["export"])


def _require(c, pid):
    if not c.execute("SELECT id FROM projects WHERE id=?", (pid,)).fetchone():
        raise HTTPException(404, "업무를 찾을 수 없습니다.")


@router.get("/{pid}/final-check")
def get_final_check(pid: int):
    with connect() as c:
        _require(c, pid)
    try:
        return final_check(pid)
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.get("/{pid}/preview")
def get_preview(pid: int):
    """미리보기용: 조립된 본문(목차+반영 본문)을 구조화해 돌려준다."""
    with connect() as c:
        _require(c, pid)
        proj = c.execute("SELECT name,doc_type FROM projects WHERE id=?", (pid,)).fetchone()
        sections = sections_with_body(c, pid)
    return {"name": proj["name"], "doc_type": proj["doc_type"], "sections": sections}


@router.get("/{pid}/export.docx")
def export_docx(pid: int, include_evidence: bool = True):
    with connect() as c:
        _require(c, pid)
    try:
        data, filename = build_docx(pid, include_evidence=include_evidence)
    except ModuleNotFoundError:
        raise HTTPException(500, "python-docx 가 설치되지 않았습니다. 1_SETUP.bat 을 다시 실행해 주세요.")
    except ValueError as e:
        raise HTTPException(404, str(e))
    quoted = urllib.parse.quote(filename)
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quoted}"},
    )
