# -*- coding: utf-8 -*-
"""마크다운 초안 → 한글(.hwpx). 표준 라이브러리만 쓴다(행정망 PC 에서도 돈다).

사용:
  python tools/md2hwpx.py <뼈대.hwpx> <입력.md> <출력.hwpx>
  예) python tools/md2hwpx.py "모의데이터/01_공고_2027년 스마트 경로당 조성 지원사업.hwpx"           docs/submission/구동안내서_초안.md docs/submission/구동안내서_초안.hwpx

뼈대: 한글로 저장한 hwpx 하나. 거기서 **스타일(header.xml)·구역 설정·문서 설정만** 가져오고
본문은 새로 쓴다. 아래 STY 의 번호는 그 header.xml 안의 문단·글자 모양 번호라서, 뼈대를 다른
문서로 바꾸면 번호도 다시 골라야 한다(모의데이터 hwpx 는 같은 header 를 쓰므로 그대로 된다).

다루는 마크다운: # 제목, ## 소제목, 표(|), 목록(- , 1. ), > 인용(※ 로), ```코드```(본문 줄로), **굵게**.
줄만 바꿔 이어 쓴 문장은 한 문단으로 붙인다.

XML 은 문자열로 짓는다. 이스케이프는 html.escape 로 한다 — 표준 xml 모듈은 공공GitLab 보안 스캔이
막는다(CLAUDE.md 6장). 읽지는 않으므로 defusedxml 도 필요 없다.
"""
import os, re, sys, zipfile, random, datetime
from html import escape as _esc

SK, SRC, OUT = sys.argv[1:4]
sys.stdout.reconfigure(encoding="utf-8")
random.seed(11)


def escape(t):
    return _esc(t, quote=False)


_z = zipfile.ZipFile(SK)
NAMES = set(_z.namelist())


def rd(name):
    return _z.read(name)


sec = rd("Contents/section0.xml").decode("utf-8")
SEC_OPEN = sec[:sec.find("<hp:p ")]
_first = sec[sec.find("<hp:p "):]
_first = _first[:_first.find("</hp:p>")]
# 첫 문단의 run 중 구역 설정(secPr)·단·쪽번호처럼 **글자가 없는 run** 만 살린다.
SEC_RUNS = "".join(r for r in re.findall(r"<hp:run [^>]*>.*?</hp:run>", _first, re.S)
                   if "<hp:t>" not in r and "<hp:t/>" not in r)

# (paraPrIDRef, styleIDRef, 보통 글자, 굵은 글자)
STY = {
    "title": ("87", "0", "93", "93"),
    "head": ("84", "0", "94", "94"),
    "body": ("82", "171", "87", "86"),
    "sub": ("193", "171", "87", "86"),
    "note": ("79", "171", "127", "127"),
}


def clean(t):
    t = t.replace("`", "")
    t = re.sub(r"(?<!\*)\*(?!\*)([^*]+)(?<!\*)\*(?!\*)", r"\1", t)   # *기울임* → 글자만
    t = re.sub(r"\[([^\]]+)\]\((?!http)[^)]+\)", r"\1", t)           # 내부 링크 → 글자만
    return t


def runs(text, normal, bold):
    """**굵게** 를 글자 모양 둘로 나눠 run 으로."""
    out = []
    for i, part in enumerate(re.split(r"\*\*", clean(text))):
        if part:
            cp = bold if i % 2 else normal
            out.append(f'<hp:run charPrIDRef="{cp}"><hp:t>{escape(part)}</hp:t></hp:run>')
    return "".join(out) or f'<hp:run charPrIDRef="{normal}"/>'


def para(text, kind="body"):
    pp, st, cp, cb = STY[kind]
    return (f'<hp:p id="0" paraPrIDRef="{pp}" styleIDRef="{st}" pageBreak="0" columnBreak="0" merged="0">'
            f'{runs(text, cp, cb)}</hp:p>')


def cell(r, c, text, width, head, left, ncols):
    if head:
        bf = "18" if c == 0 else ("17" if c == ncols - 1 else "35")
        pp, cp, cb = "119", "104", "104"
    else:
        bf = "16" if c == 0 else ("30" if c == ncols - 1 else "14")
        pp, cp, cb = ("127" if left else "126"), "159", "161"
    ps = "".join(f'<hp:p id="0" paraPrIDRef="{pp}" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0">'
                 f'{runs(line, cp, cb)}</hp:p>' for line in (text.split("<br>") if text else [""]))
    return (f'<hp:tc name="" header="{1 if head else 0}" hasMargin="0" protect="0" editable="0" dirty="0" '
            f'borderFillIDRef="{bf}"><hp:subList id="" textDirection="HORIZONTAL" lineWrap="BREAK" '
            f'vertAlign="CENTER" linkListIDRef="0" linkListNextIDRef="0" textWidth="0" textHeight="0" '
            f'hasTextRef="0" hasNumRef="0">{ps}</hp:subList>'
            f'<hp:cellAddr colAddr="{c}" rowAddr="{r}"/><hp:cellSpan colSpan="1" rowSpan="1"/>'
            f'<hp:cellSz width="{width}" height="2331"/>'
            f'<hp:cellMargin left="510" right="510" top="141" bottom="141"/></hp:tc>')


def table(rows):
    nc = max(len(r) for r in rows)
    rows = [r + [""] * (nc - len(r)) for r in rows]
    # 칸 폭: 글자 수에 비례하되 너무 좁거나 넓지 않게
    lens = [max(len(clean(r[c]).replace("**", "")) for r in rows) for c in range(nc)]
    w = [min(max(L, 4), 60) for L in lens]
    total = 48190
    ws = [int(total * x / sum(w)) for x in w]
    ws[-1] = total - sum(ws[:-1])
    left = {c for c in range(nc) if lens[c] > 12}
    trs = "".join("<hp:tr>" + "".join(cell(r, c, rows[r][c], ws[c], r == 0, c in left, nc)
                                       for c in range(nc)) + "</hp:tr>" for r in range(len(rows)))
    tid = random.randint(10 ** 9, 2 * 10 ** 9)
    return (f'<hp:p id="0" paraPrIDRef="114" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0">'
            f'<hp:run charPrIDRef="156"><hp:tbl id="{tid}" zOrder="0" numberingType="TABLE" '
            f'textWrap="TOP_AND_BOTTOM" textFlow="BOTH_SIDES" lock="0" dropcapstyle="None" pageBreak="CELL" '
            f'repeatHeader="1" rowCnt="{len(rows)}" colCnt="{nc}" cellSpacing="0" borderFillIDRef="34" noAdjust="0">'
            f'<hp:sz width="{total}" widthRelTo="ABSOLUTE" height="{2331 * len(rows)}" heightRelTo="ABSOLUTE" protect="0"/>'
            f'<hp:pos treatAsChar="1" affectLSpacing="0" flowWithText="1" allowOverlap="0" holdAnchorAndSO="0" '
            f'vertRelTo="PARA" horzRelTo="PARA" vertAlign="TOP" horzAlign="LEFT" vertOffset="0" horzOffset="0"/>'
            f'<hp:outMargin left="0" right="0" top="0" bottom="0"/>'
            f'<hp:inMargin left="510" right="510" top="141" bottom="141"/>{trs}</hp:tbl><hp:t/></hp:run></hp:p>')


BLOCK = re.compile(r"^\s*(#|\||-\s|\d+\.\s|>|```|【|---)")


def join_wrapped(md):
    """마크다운에서 줄만 바꿔 이어 쓴 문장을 한 문단으로 붙인다(빈 줄·표·목록 머리는 끊는다)."""
    out, in_code = [], False
    for ln in md.split("\n"):
        s = ln.strip()
        if s.startswith("```"):
            in_code = not in_code
            out.append(ln)
            continue
        prev = out[-1] if out else ""
        ps = prev.strip()
        if (not in_code and s and ps and not BLOCK.match(ln) and not s.startswith("**")
                and not ps.startswith(("#", "|", "```", "【", "---", ">")) and not ps.endswith("**")):
            out[-1] = prev.rstrip() + ("" if ps.endswith(("·", "(", "/")) else " ") + s
        else:
            out.append(ln)
    return "\n".join(out)


def convert(md):
    lines = join_wrapped(md).split("\n")
    parts, title, i = [], None, 0
    while i < len(lines):
        ln = lines[i].rstrip()
        s = ln.strip()
        if not s or s == "---":
            i += 1
            continue
        if s.startswith("|"):                                   # 표
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if not all(re.fullmatch(r":?-{2,}:?", c) for c in cells):
                    rows.append(cells)
                i += 1
            parts.append(table(rows))
            continue
        if s.startswith("```"):                                 # 코드 → 본문 줄
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                if lines[i].strip():
                    parts.append(para("   " + lines[i].strip(), "sub"))
                i += 1
            i += 1
            continue
        if s.startswith("# ") and title is None:
            title = clean(s[2:]).replace("**", "")
        elif s.startswith("## "):
            parts.append(para(s[3:].replace("**", ""), "head"))
        elif s.startswith(">"):
            parts.append(para("※ " + s.lstrip("> ").strip(), "note"))
        elif re.match(r"^\s*- ", ln):
            depth = (len(ln) - len(ln.lstrip())) // 2
            parts.append(para(("   " * depth) + " ◦ " + s[2:], "sub" if depth else "body"))
        elif re.match(r"^\s*\d+\. ", ln):
            depth = (len(ln) - len(ln.lstrip())) // 3
            parts.append(para(("   " * depth) + " " + s, "sub" if depth else "body"))
        else:
            parts.append(para(s, "body"))
        i += 1
    return title or "구동 안내서", parts


def write_hwpx(path, title, parts):
    pp, st, cp, _ = STY["title"]
    first = (f'<hp:p id="0" paraPrIDRef="{pp}" styleIDRef="{st}" pageBreak="0" columnBreak="0" merged="0">'
             f'{SEC_RUNS}<hp:run charPrIDRef="{cp}"><hp:t>{escape(title)}</hp:t></hp:run></hp:p>')
    body = SEC_OPEN + first + "".join(parts) + "</hs:sec>"
    hpf = rd("Contents/content.hpf").decode("utf-8")
    a, b = hpf.find("<opf:metadata>"), hpf.find("</opf:metadata>")
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    meta = ("<opf:metadata>"
            f"<opf:title>{escape(title)}</opf:title><opf:language>ko</opf:language>"
            '<opf:meta name="creator" content="text">workbench</opf:meta>'
            '<opf:meta name="subject" content="text"/><opf:meta name="description" content="text"/>'
            '<opf:meta name="lastsaveby" content="text">workbench</opf:meta>'
            f'<opf:meta name="CreatedDate" content="text">{now}</opf:meta>'
            f'<opf:meta name="ModifiedDate" content="text">{now}</opf:meta>'
            '<opf:meta name="date" content="text"/><opf:meta name="keyword" content="text"/>')
    hpf = hpf[:a] + meta + hpf[b:]
    with zipfile.ZipFile(path, "w") as z:
        z.writestr(zipfile.ZipInfo("mimetype"), rd("mimetype"), compress_type=zipfile.ZIP_STORED)
        z.writestr(zipfile.ZipInfo("version.xml"), rd("version.xml"), compress_type=zipfile.ZIP_STORED)
        for name, data in [("Contents/header.xml", rd("Contents/header.xml")),
                           ("Contents/section0.xml", body.encode("utf-8")),
                           ("Preview/PrvText.txt", title.encode("utf-8")),
                           ("settings.xml", rd("settings.xml")),
                           ("META-INF/container.rdf", rd("META-INF/container.rdf")),
                           ("Contents/content.hpf", hpf.encode("utf-8")),
                           ("META-INF/container.xml", rd("META-INF/container.xml")),
                           ("META-INF/manifest.xml", rd("META-INF/manifest.xml"))]:
            z.writestr(name, data, compress_type=zipfile.ZIP_DEFLATED)


title, parts = convert(open(SRC, encoding="utf-8").read())
write_hwpx(OUT, title, parts)
print("ok", title, len(parts), "parts")
