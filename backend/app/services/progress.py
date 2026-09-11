# -*- coding: utf-8 -*-
"""진행상황을 사람이 읽는 말로 — 진행상황 보고와 보고전 뽑기가 함께 쓴다.

세는 것은 `routers/dashboard.compute_metrics` 한 곳에서만 한다. 여기서는 그 결과를
**문장으로 옮기기만** 한다(세는 곳이 둘이 되면 반드시 어긋난다 — 이 저장소의 반복 교훈).

두 가지 모양이 필요하다:
  fact_lines()      진행상황 보고 팝업에 그대로 보여줄 요약 줄
  progress_claims() 보고전의 근거로 쓸 주장 문장 — '주어와 서술어가 있는 한 문장'이어야
                    근거표·초고 프롬프트에서 그대로 쓸 수 있다.
"""
from __future__ import annotations


def fact_lines(m: dict) -> list[str]:
    """사람이 읽는 요약 줄들(보고 파일을 직접 열어도 보이도록)."""
    due = m["due_date"] or "미정"
    dday = "" if m["d_day"] is None else (f"(마감 {abs(m['d_day'])}일 지남)" if m["d_day"] < 0 else f"(D-{m['d_day']})")
    lines = [
        f"단계: {m['stage_label']}  ·  진행률: 본문 {m['bodies_filled']}/{m['outline_total']}",
        f"마감: {due} {dday}".rstrip(),
    ]
    issues = []
    if m["severe"]:
        issues.append(f"중대·중요 미해결 검토의견 {m['severe']}건")
    if m["unresolved"] - m["severe"] > 0:
        issues.append(f"기타 미해결 의견 {m['unresolved'] - m['severe']}건")
    if m["need_flags"]:
        issues.append(f"확인 필요 표시 {m['need_flags']}건")
    if m["ev_unconfirmed"]:
        issues.append(f"미확정 근거 {m['ev_unconfirmed']}건")
    if m["ev_changed"]:
        issues.append(f"변경된 근거 {m['ev_changed']}건")
    if m["req_open"]:
        issues.append(f"자료 회신 대기 {m['req_open']}건")
    if m["req_overdue"]:
        issues.append(f"요청 마감 초과 {m['req_overdue']}건")
    lines.append("미해결: " + (", ".join(issues) if issues else "없음"))
    return lines


def progress_claims(m: dict, name: str) -> list[str]:
    """보고전의 근거로 삼을 주장 문장들.

    지어내는 것이 하나도 없다 — 전부 DB 를 센 결과다. 그래서 이것을 근거로 삼는 것은
    원칙 2를 어기지 않는다. 다만 **문서로 확인된 자료는 아니므로** 담당자 진술과 같은
    자리에 두고 `[진술]` 표시를 끝까지 달고 간다(services/evidence.evidence_mark).
    """
    out = []
    if m["outline_total"]:
        out.append(f"‘{name}’은(는) 현재 ‘{m['stage_label']}’ 단계이며, "
                   f"목차 {m['outline_total']}개 중 {m['bodies_filled']}개 항목의 본문이 작성되었다.")
    if m["due_date"]:
        if m["d_day"] is None:
            out.append(f"‘{name}’의 마감일은 {m['due_date']}이다.")
        elif m["d_day"] < 0:
            out.append(f"‘{name}’의 마감일({m['due_date']})이 {abs(m['d_day'])}일 지났다.")
        else:
            out.append(f"‘{name}’의 마감일은 {m['due_date']}로 {m['d_day']}일 남았다.")
    if m["unresolved"]:
        tail = f"(이 중 중대·중요 {m['severe']}건)" if m["severe"] else ""
        out.append(f"처리되지 않은 검토의견이 {m['unresolved']}건 남아 있다{tail}.")
    if m["req_open"]:
        tail = f", 그중 {m['req_overdue']}건은 회신 기한이 지났다" if m["req_overdue"] else ""
        out.append(f"부서에 요청한 자료 {m['req_open']}건이 회신 대기 중이다{tail}.")
    if m["need_flags"]:
        out.append(f"본문에 확인이 필요한 표시가 {m['need_flags']}건 남아 있다.")
    if m["ev_changed"]:
        out.append(f"근거로 쓴 자료가 바뀌어 확인이 필요한 항목이 {m['ev_changed']}건 있다.")
    return out
