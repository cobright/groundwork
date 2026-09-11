# -*- coding: utf-8 -*-
"""구형 한글(.hwp 5.x) 본문 추출 — **검증된 시제품(아직 화면에 연결되지 않음)**

왜 남겨 두는가:
  다음 과제 1번(한글 파일에서 자료 본문 읽기)의 핵심 난제를 미리 풀어 둔 것이다.
  2026-08-29에 실제 파일(청와대 비서실 보고서 작성법.hwp)로 본문 추출을 확인했다.
  **파이썬 표준 라이브러리만 쓴다** — 원칙 4(추가 설치 곤란)를 지킨다.

무엇을 하는가:
  .hwp 5.x = OLE 복합문서(CFB). olefile 없이 헤더/DIFAT/FAT/디렉터리를 직접 읽고,
  BodyText/Section0 스트림을 zlib.decompress(data, -15) 로 푼 뒤
  레코드(태그 67 = HWPTAG_PARA_TEXT)에서 UTF-16LE 텍스트를 뽑는다.

반드시 지킬 것 — 제어문자의 '폭'이 다르다:
  확장(EXT: 1,2,3,11,12,14~18,21~23)과 인라인(INL: 4~8, **9=탭**, 19,20)은 8워드를 차지하고,
  그 밖의 32 미만 문자는 1워드다. 탭(9)을 1워드로 세면 본문에 깨진 글자가 섞인다
  (처음 구현에서 실제로 겪었다). 이 파일은 그 교정이 반영된 상태다.

남는 잡티(정상):
  한컴 기호 글꼴로 그린 글머리표 등은 사용자 영역(U+E000~U+F8FF) 문자로 나온다.
  파서 오류가 아니다. 자료 본문으로 쓸 때는 걸러 내거나 '·' 로 바꾸면 된다.

화면에 붙일 때 할 일:
  - 표 안 글자(태그 71 이하 리스트)는 아직 안 뽑는다. 본문만으로도 충분히 쓸모 있다.
  - .hwpx 는 services/hwpx_fill.py 가 이미 읽고 있으니 그쪽 파서를 쓴다.
  - 실패하면 조용히 넘어가지 말고 "이 파일은 못 읽습니다"라고 말하고 붙여넣기로 유도한다.

지금은 어디서도 import 하지 않는다. 붙일 때 이 파일을 정리해 쓰면 된다.
"""
import struct, zlib, sys, io

class CFB:
    def __init__(self, data):
        self.d = data
        assert data[:8] == b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1', 'not CFB'
        self.ssz = 1 << struct.unpack_from('<H', data, 0x1E)[0]
        self.mssz = 1 << struct.unpack_from('<H', data, 0x20)[0]
        nfat = struct.unpack_from('<I', data, 0x2C)[0]
        self.dir_start = struct.unpack_from('<I', data, 0x30)[0]
        self.cutoff = struct.unpack_from('<I', data, 0x38)[0]
        mini_start = struct.unpack_from('<I', data, 0x3C)[0]
        difat_start = struct.unpack_from('<I', data, 0x44)[0]
        ndifat = struct.unpack_from('<I', data, 0x48)[0]
        # DIFAT
        difat = list(struct.unpack_from('<109I', data, 0x4C))
        sec = difat_start
        for _ in range(ndifat):
            if sec >= 0xFFFFFFFA: break
            off = self._off(sec)
            n = self.ssz // 4 - 1
            difat += list(struct.unpack_from('<%dI' % n, data, off))
            sec = struct.unpack_from('<I', data, off + self.ssz - 4)[0]
        # FAT
        self.fat = []
        for s in difat[:nfat]:
            if s >= 0xFFFFFFFA: continue
            self.fat += list(struct.unpack_from('<%dI' % (self.ssz//4), data, self._off(s)))
        # MiniFAT
        self.minifat = []
        s = mini_start
        while s < 0xFFFFFFFA:
            self.minifat += list(struct.unpack_from('<%dI' % (self.ssz//4), data, self._off(s)))
            s = self.fat[s]
        # Directory
        self.dirs = []
        raw = self._chain(self.dir_start)
        for i in range(0, len(raw), 128):
            e = raw[i:i+128]
            if len(e) < 128: break
            nlen = struct.unpack_from('<H', e, 64)[0]
            name = e[:max(0, nlen-2)].decode('utf-16-le', 'replace')
            typ = e[66]
            start = struct.unpack_from('<I', e, 116)[0]
            size = struct.unpack_from('<Q', e, 120)[0]
            self.dirs.append({'name': name, 'type': typ, 'start': start, 'size': size,
                              'left': struct.unpack_from('<i', e, 68)[0],
                              'right': struct.unpack_from('<i', e, 72)[0],
                              'child': struct.unpack_from('<i', e, 76)[0]})
        # mini stream (root entry)
        self.mini = self._chain(self.dirs[0]['start'])[:self.dirs[0]['size']] if self.dirs else b''

    def _off(self, sec): return 512 + sec * self.ssz

    def _chain(self, sec):
        out = bytearray()
        seen = set()
        while sec < 0xFFFFFFFA:
            if sec in seen: break
            seen.add(sec)
            out += self.d[self._off(sec):self._off(sec)+self.ssz]
            sec = self.fat[sec]
        return bytes(out)

    def _minichain(self, sec, size):
        out = bytearray()
        while sec < 0xFFFFFFFA and len(out) < size:
            o = sec * self.mssz
            out += self.mini[o:o+self.mssz]
            sec = self.minifat[sec]
        return bytes(out[:size])

    def read(self, name):
        for e in self.dirs:
            if e['name'] == name and e['type'] == 2:
                if e['size'] < self.cutoff:
                    return self._minichain(e['start'], e['size'])
                return self._chain(e['start'])[:e['size']]
        return None

    def names(self):
        return [(e['name'], e['type'], e['size']) for e in self.dirs]


# 제어문자의 '폭'. 이걸 틀리면 뒤따르는 데이터가 글자로 새어 나온다.
EXT = {1, 2, 3, 11, 12, 14, 15, 16, 17, 18, 21, 22, 23}   # 확장: 8워드
INL = {4, 5, 6, 7, 8, 9, 19, 20}                          # 인라인: 8워드 (9 = 탭!)
# 그 밖의 32 미만은 1워드 (10·13 = 줄바꿈/문단끝 등)

def para_text(b):
    out = []
    i = 0
    n = len(b)//2
    while i < n:
        c = struct.unpack_from('<H', b, i*2)[0]
        if c in EXT:
            out.append(chr(10)+'[CTRL]'+chr(10)); i += 8
        elif c in INL:
            out.append('\t' if c == 9 else '')
            i += 8
        elif c < 32:
            if c in (10, 13):
                out.append('\n')
            i += 1
        else:
            out.append(chr(c)); i += 1
    return ''.join(out)

def records(data):
    i = 0
    while i + 4 <= len(data):
        h = struct.unpack_from('<I', data, i)[0]; i += 4
        tag = h & 0x3FF; lvl = (h >> 10) & 0x3FF; sz = (h >> 20) & 0xFFF
        if sz == 0xFFF:
            sz = struct.unpack_from('<I', data, i)[0]; i += 4
        yield tag, lvl, data[i:i+sz]
        i += sz

def main(path):
    cfb = CFB(open(path, 'rb').read())
    fh = cfb.read('FileHeader') or b''
    sig = fh[:32].split(b'\x00')[0].decode('ascii', 'replace')
    ver = struct.unpack_from('<4B', fh, 32)
    flags = struct.unpack_from('<I', fh, 36)[0] if len(fh) >= 40 else 0
    comp = bool(flags & 1)
    print('# sig=%r ver=%s compressed=%s' % (sig, '.'.join(map(str, ver[::-1])), comp), file=sys.stderr)
    print('# streams: %s' % [n for n,t,s in cfb.names() if t==2][:40], file=sys.stderr)

    idx = 0
    while True:
        raw = cfb.read('Section%d' % idx)
        if raw is None: break
        if comp: raw = zlib.decompress(raw, -15)
        cur = []
        for tag, lvl, body in records(raw):
            if tag == 66:  # PARA_HEADER
                if cur: print(''.join(cur))
                cur = []
            elif tag == 67:  # PARA_TEXT
                cur.append(para_text(body))
        if cur: print(''.join(cur))
        idx += 1

main(sys.argv[1])
