# 행정기획 워크벤치 · 포터블 꾸러미 만들기
# 인터넷 되는 윈도우 PC에서 한 번만 실행하세요.
$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$repo = Split-Path -Parent $PSScriptRoot
$out  = Join-Path $repo "행정기획워크벤치_포터블"
$tmp  = Join-Path $repo "_build_tmp"
$pyver  = "3.11.9"
$pyurl  = "https://www.python.org/ftp/python/$pyver/python-$pyver-embed-amd64.zip"
$pipurl = "https://bootstrap.pypa.io/get-pip.py"

Write-Host ""
Write-Host "[1/7] 사전 점검..." -ForegroundColor Cyan
if (-not (Test-Path (Join-Path $repo "frontend\dist\index.html"))) {
    throw "frontend\dist 가 없습니다. 배포용 압축을 그대로 푼 폴더에서 실행하세요."
}
if (-not (Test-Path (Join-Path $repo "backend\requirements.txt"))) {
    throw "backend\requirements.txt 를 찾을 수 없습니다."
}

Write-Host "[2/7] 이전 결과 정리..." -ForegroundColor Cyan
Remove-Item $out, $tmp -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path $out  | Out-Null
New-Item -ItemType Directory -Path $tmp  | Out-Null

Write-Host "[3/7] 파이썬(임베디드) 내려받기..." -ForegroundColor Cyan
$pyzip = Join-Path $tmp "py-embed.zip"
Invoke-WebRequest -Uri $pyurl -OutFile $pyzip
Expand-Archive -Path $pyzip -DestinationPath (Join-Path $out "python")

Write-Host "[4/7] pip 활성화 및 설치..." -ForegroundColor Cyan
$pth = Get-ChildItem (Join-Path $out "python") -Filter "python*._pth" | Select-Object -First 1
(Get-Content $pth.FullName) -replace '^\s*#\s*import site', 'import site' | Set-Content $pth.FullName
$py = Join-Path $out "python\python.exe"
$getpip = Join-Path $tmp "get-pip.py"
Invoke-WebRequest -Uri $pipurl -OutFile $getpip
& $py $getpip --no-warn-script-location

Write-Host "[5/7] 필요한 패키지 설치(인터넷)..." -ForegroundColor Cyan
& $py -m pip install --no-warn-script-location -r (Join-Path $repo "backend\requirements.txt")

Write-Host "[6/7] 앱 파일 복사..." -ForegroundColor Cyan
Copy-Item (Join-Path $repo "backend") (Join-Path $out "backend") -Recurse
# 개발 흔적 제거. 키가 들어 있는 두 곳을 반드시 뺀다:
#   .env       — 예전부터 쓰던 자리
#   data\      — v0.22 부터 화면에서 넣은 AI 키가 workbench.db 에 들어간다.
#                 자동 백업(data/backups)에도 같은 것이 들어 있으므로 폴더째 뺀다.
Remove-Item (Join-Path $out "backend\.venv"), (Join-Path $out "backend\data"), (Join-Path $out "backend\__pycache__"), (Join-Path $out "backend\.env") -Recurse -Force -ErrorAction SilentlyContinue
Get-ChildItem (Join-Path $out "backend") -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path (Join-Path $out "frontend") | Out-Null
Copy-Item (Join-Path $repo "frontend\dist") (Join-Path $out "frontend\dist") -Recurse
if (Test-Path (Join-Path $repo "backend\.env.example")) {
    if (-not (Test-Path (Join-Path $out "backend\.env"))) {
        Copy-Item (Join-Path $repo "backend\.env.example") (Join-Path $out "backend\.env")
    }
}

Write-Host "[7/7] 실행 런처/설명서 배치..." -ForegroundColor Cyan
Copy-Item (Join-Path $PSScriptRoot "실행.bat") (Join-Path $out "실행.bat")
if (Test-Path (Join-Path $PSScriptRoot "사용설명.txt")) {
    Copy-Item (Join-Path $PSScriptRoot "사용설명.txt") (Join-Path $out "사용설명.txt")
}
# 담당자용 사용설명서. 원본은 frontend/public 에 있고 빌드 때 dist 로 복사되므로
# 프로그램 화면의 '사용설명서' 버튼으로 열린다. 여기서는 폴더에서 바로 두 번 눌러
# 열 수 있도록 꾸러미 맨 위에 사본을 하나 더 둔다.
# (위 '사용설명.txt' 는 꾸러미를 만들고 반입하는 관리자용이라 대상이 다르다.)
$manual = Join-Path $repo "frontend\dist\사용설명서.html"
if (Test-Path $manual) {
    Copy-Item $manual (Join-Path $out "사용설명서.html")
} else {
    Write-Host "  경고: 사용설명서.html 이 frontend\dist 에 없습니다. 'npm run build' 를 먼저 하세요." -ForegroundColor Yellow
}
# 버전 안내도 함께 넣어, 지금 쓰는 것이 무엇인지 폴더에서 바로 볼 수 있게 한다.
if (Test-Path (Join-Path $repo "VERSION.txt")) {
    Copy-Item (Join-Path $repo "VERSION.txt") (Join-Path $out "업데이트_내역.txt")
}
Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "완성되었습니다." -ForegroundColor Green
Write-Host ("포터블 폴더: " + $out)
Write-Host "이 폴더를 통째로 행정망 PC로 옮긴 뒤, 안의 '실행.bat' 을 더블클릭하세요."
