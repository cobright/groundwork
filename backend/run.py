# -*- coding: utf-8 -*-
"""포터블 실행 진입점: 이 파일이 있는 backend 폴더를 경로에 넣고 서버를 띄운다.
어느 위치에서 실행하든(더블클릭 포함) 동작하도록 __file__ 기준으로 처리한다."""
import os
import sys
import threading
import webbrowser

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

HOST = "127.0.0.1"
PORT = 8000


def _open_browser():
    webbrowser.open(f"http://{HOST}:{PORT}/")


if __name__ == "__main__":
    import uvicorn
    # 서버가 뜬 뒤 브라우저 자동 열기(1.2초 지연)
    threading.Timer(1.2, _open_browser).start()
    print("행정기획 워크벤치를 시작합니다...")
    print(f"브라우저에서 http://{HOST}:{PORT}/ 이 열립니다. (이 창은 닫지 마세요)")
    uvicorn.run("app.main:app", host=HOST, port=PORT, log_level="warning")
