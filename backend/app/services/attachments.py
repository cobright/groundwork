# -*- coding: utf-8 -*-
"""올린 파일을 자료에 붙인다 — 읽어서 본문으로, 원본은 그대로 보관.

왜 함수 하나로 모으는가:
  파일이 들어오는 입구는 둘이다. ① 자료·근거 화면의 '파일로 등록',
  ② 자료요청 화면의 '회신 파일 등록'. 두 곳이 각자 읽고 각자 저장하면
  한쪽만 고쳐져 '어떤 자료는 원본이 남고 어떤 자료는 안 남는' 상태가 된다.

원본을 보관하는 이유(원칙 2):
  근거는 언제든 원문으로 되돌아갈 수 있어야 한다. 특히 엑셀 수치는
  '이 숫자가 어느 칸이었나'를 확인해야 하는 순간이 반드시 온다.
  읽은 글자는 사람이 고칠 수 있지만(resources.text), 원본은 고쳐지지 않는다.
"""
from __future__ import annotations

from ..db import now
from .doc_read import read_document, to_text

MAX_BYTES = 40 * 1024 * 1024


def read_upload(data: bytes, filename: str = "") -> dict:
    """파일을 읽어 {text, file_kind, pages, blocks, read_note} 로 돌려준다.

    읽지 못하면 ReadError 를 그대로 올린다 — 왜 못 읽었는지가 사람이 읽는 말로
    담겨 있고, 그 말이 그대로 화면에 나가야 담당자가 다음 수를 안다
    (한글에서 .hwpx 로 다시 저장, 엑셀에서 열었다 저장 등).
    """
    doc = read_document(data, filename)
    return {
        "text": to_text(doc),
        "file_kind": doc.get("kind", ""),
        "pages": int(doc.get("pages") or 0),
        "blocks": len(doc.get("blocks") or []),
        "read_note": doc.get("note", "") or "",
    }


def store_file(c, resource_id: int, data: bytes, filename: str, info: dict) -> None:
    """읽은 결과와 원본을 자료에 매단다(자료 1건에 파일 1개, 다시 올리면 교체)."""
    c.execute(
        """INSERT INTO resource_files(resource_id,filename,file_kind,size,pages,blocks,read_note,data,created_at)
           VALUES(?,?,?,?,?,?,?,?,?)
           ON CONFLICT(resource_id) DO UPDATE SET
             filename=excluded.filename, file_kind=excluded.file_kind, size=excluded.size,
             pages=excluded.pages, blocks=excluded.blocks, read_note=excluded.read_note,
             data=excluded.data, created_at=excluded.created_at""",
        (resource_id, filename or "첨부파일", info["file_kind"], len(data),
         info["pages"], info["blocks"], info["read_note"], data, now()),
    )


def file_meta(c, resource_ids) -> dict:
    """자료 목록에 붙일 파일 정보(원본 BLOB 은 빼고). 목록을 부를 때마다
    수십 MB 가 딸려 나오지 않도록 여기서 컬럼을 못박는다."""
    ids = [int(i) for i in resource_ids]
    if not ids:
        return {}
    q = ",".join("?" * len(ids))
    rows = c.execute(
        f"SELECT resource_id,filename,file_kind,size,pages,blocks,read_note FROM resource_files "
        f"WHERE resource_id IN ({q})", ids).fetchall()
    return {r["resource_id"]: dict(r) for r in rows}
