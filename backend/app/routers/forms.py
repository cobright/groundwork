# -*- coding: utf-8 -*-
"""한글(HWPX) 양식 보관함 + 양식에 채워 내보내기.

양식은 사용자의 것이다. 우리가 만들지 않고, 올려둔 것을 그대로 보관했다가
최종본을 그 구조에 채워 돌려준다(services/hwpx_fill.py).
"""
import urllib.parse

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

from ..db import connect
from ..services import formstore
from ..services.formstore import MAX_FORM_BYTES, FormReject
from ..services.hwpx_fill import FormError, fill_form

router = APIRouter(prefix="/api", tags=["forms"])


def _row(r):
    d = dict(r)
    d.pop("data", None)                 # 목록에 원본 바이트를 실어 보내지 않는다
    return d


@router.get("/forms")
def list_forms():
    with connect() as c:
        rows = c.execute(
            "SELECT id,name,filename,size,note,supported,reason,created_at "
            "FROM hwpx_forms ORDER BY id DESC").fetchall()
    return [dict(r) for r in rows]


@router.post("/forms", status_code=201)
async def upload_form(request: Request, filename: str = "", name: str = "", note: str = ""):
    """양식 파일을 원시 바이트로 받는다(본문 = .hwpx 그대로).

    multipart 로 받으면 python-multipart 의존성이 늘고, 그러면 사용자가 1_SETUP 을
    다시 돌려야 한다(v0.10 때 실제로 그랬다). 프런트에서 File 을 그대로 body 에 실어 보낸다.
    """
    data = await request.body()
    # 검사와 저장은 services/formstore.py 한 곳에서 한다 — 가이드라인의 '서식'을 넘기는
    # 문(POST /guidelines/{gid}/to-form)도 같은 함수를 쓴다.
    try:
        with connect() as c:
            return formstore.register(c, data, filename, name, note)
    except FormReject as e:
        raise HTTPException(400, str(e))


@router.delete("/forms/{fid}")
def delete_form(fid: int):
    with connect() as c:
        if not c.execute("SELECT id FROM hwpx_forms WHERE id=?", (fid,)).fetchone():
            raise HTTPException(404, "양식을 찾을 수 없습니다.")
        c.execute("DELETE FROM hwpx_forms WHERE id=?", (fid,))
    return {"deleted": fid}


@router.get("/projects/{pid}/export.hwpx")
def export_hwpx(pid: int, form_id: int, org: str = "", page_break: bool = False):
    """업무의 최종본을 지정한 양식에 채워 .hwpx 로 돌려준다."""
    with connect() as c:
        if not c.execute("SELECT id FROM projects WHERE id=?", (pid,)).fetchone():
            raise HTTPException(404, "업무를 찾을 수 없습니다.")
        row = c.execute("SELECT data,name,supported,reason FROM hwpx_forms WHERE id=?",
                        (form_id,)).fetchone()
        if not row:
            raise HTTPException(404, "양식을 찾을 수 없습니다.")
        if not row["supported"]:
            raise HTTPException(400, f"‘{row['name']}’은(는) 아직 채울 수 없는 양식입니다. {row['reason']}")
        form_bytes = row["data"]

    try:
        data, filename = fill_form(pid, form_bytes, org=org.strip(), page_break=page_break)
    except FormError as e:
        raise HTTPException(400, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))

    quoted = urllib.parse.quote(filename)
    return Response(
        content=data,
        media_type="application/hwp+zip",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quoted}"},
    )
