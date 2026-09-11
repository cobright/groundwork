# -*- coding: utf-8 -*-
"""목차 틀 제공. 프런트는 여기서 받아 쓴다(틀의 출처는 백엔드 한 곳)."""
from fastapi import APIRouter
from ..services.templates import DOC_TEMPLATES, BLOCKS

router = APIRouter(prefix="/api/templates", tags=["templates"])


@router.get("")
def list_templates():
    return {
        "templates": [
            {"name": name, "family": t["family"], "nodes": t["nodes"]}
            for name, t in DOC_TEMPLATES.items()
        ],
        "blocks": BLOCKS,
    }
