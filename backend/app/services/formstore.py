# -*- coding: utf-8 -*-
"""양식 보관함에 넣기 — 검사와 저장을 한 곳에.

왜 함수로 빼는가:
  양식이 들어오는 문이 둘이 되었다. ① 최종본 탭에서 직접 올리기,
  ② 공모 가이드라인으로 이미 올린 파일 중 '서식'을 넘기기(같은 파일을 두 번 올리게 하지 않는다).
  두 문이 각자 검사하면 한쪽만 고쳐져 '어떤 양식은 되고 어떤 양식은 안 되는' 상태가 된다.

거절할 때는 **왜 못 쓰는지와 어떻게 하면 되는지**를 담는다. 양식은 사용자의 것이고,
우리가 못 다루는 것은 우리 사정이므로 그 사정을 정직하게 말해야 한다.
"""
from __future__ import annotations

import io
import zipfile

from ..db import now
from .hwpx_fill import inspect_form

MAX_FORM_BYTES = 20 * 1024 * 1024      # 양식 하나가 20MB를 넘을 일은 없다


class FormReject(Exception):
    """양식으로 쓸 수 없는 파일. 사람이 읽는 말을 담는다(그대로 화면에 나간다)."""


def validate(data: bytes) -> None:
    if not data:
        raise FormReject("빈 파일입니다.")
    if len(data) > MAX_FORM_BYTES:
        raise FormReject("양식 파일이 너무 큽니다(20MB 이하).")
    if not data.startswith(b"PK"):
        raise FormReject("HWPX 파일이 아닙니다. 한글에서 ‘한글 문서(*.hwpx)’로 저장한 파일을 올려주세요.")
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            names = z.namelist()
    except zipfile.BadZipFile:
        raise FormReject("파일이 손상되었거나 HWPX 형식이 아닙니다.")
    if "Contents/section0.xml" not in names:
        raise FormReject("HWPX 파일이 아닙니다(Contents/section0.xml 이 없습니다). "
                         ".hwp 나 PDF 라면 한글에서 .hwpx 로 다시 저장해 주세요.")


def register(c, data: bytes, filename: str, name: str = "", note: str = "") -> dict:
    """검사하고 보관함에 넣는다. 채울 수 있는 구조인지도 **지금** 살펴 함께 저장한다
    (내보낼 때가 되어서야 못 채운다고 알면 늦다)."""
    validate(data)
    info = inspect_form(data)
    fname = (filename or "").strip() or "양식.hwpx"
    label = (name or "").strip() or fname.rsplit(".", 1)[0]
    cur = c.execute(
        "INSERT INTO hwpx_forms(name,filename,data,size,note,supported,reason,created_at) "
        "VALUES(?,?,?,?,?,?,?,?)",
        (label, fname, data, len(data), (note or "").strip(),
         1 if info["supported"] else 0, info["reason"], now()))
    row = c.execute(
        "SELECT id,name,filename,size,note,supported,reason,created_at FROM hwpx_forms WHERE id=?",
        (cur.lastrowid,)).fetchone()
    out = dict(row)
    out["chapters"] = info.get("chapters", 0)
    return out
