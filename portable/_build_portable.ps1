# 그라운드워크 · 포터블 꾸러미 만들기
# 인터넷 되는 윈도우 PC에서 한 번만 실행하세요.
$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$repo = Split-Path -Parent $PSScriptRoot
$out  = Join-Path $repo "그라운드워크_포터블"
$tmp  = Join-Path $repo "_build_tmp"
$pyver  = "3.11.9"
$pyurl  = "https://www.python.org/ftp/python/$pyver/python-$pyver-embed-amd64.zip"
$pipurl = "https://bootstrap.pypa.io/get-pip.py"

Write-Host ""
Write-Host "[1/8] 사전 점검 · 화면(frontend) 빌드..." -ForegroundColor Cyan
# 저장소(GitLab)에는 빌드 결과 frontend\dist 를 올리지 않는다(.gitignore).
# 그래서 Node 가 있으면 여기서 늘 새로 빌드한다 — 있던 dist 가 소스보다 낡았을 수 있다.
# Node 가 없으면 배포용 압축에 든 dist 를 그대로 쓰고, 그마저 없으면 방법을 알려 멈춘다.
$fe = Join-Path $repo "frontend"
$npm = Get-Command npm.cmd -ErrorAction SilentlyContinue
if ($npm) {
    Push-Location $fe
    try {
        if (-not (Test-Path (Join-Path $fe "node_modules"))) {
            & $npm.Source ci
            if ($LASTEXITCODE -ne 0) { throw "npm ci 가 실패했습니다. 위 메시지를 확인하세요." }
        }
        & $npm.Source run build
        if ($LASTEXITCODE -ne 0) { throw "화면 빌드(npm run build)가 실패했습니다. 위 메시지를 확인하세요." }
    } finally { Pop-Location }
} elseif (Test-Path (Join-Path $fe "dist\index.html")) {
    Write-Host "  Node.js 가 없어 이미 들어 있는 frontend\dist 를 그대로 씁니다." -ForegroundColor Yellow
} else {
    throw ("frontend\dist 가 없고 Node.js 도 없습니다. 둘 중 하나가 필요합니다.`n" +
           "  - Node.js 18 이상을 설치한 뒤 다시 실행하거나(화면을 여기서 빌드합니다)`n" +
           "  - frontend\dist 가 들어 있는 배포용 압축을 푼 폴더에서 실행하세요.")
}
if (-not (Test-Path (Join-Path $repo "backend\requirements.txt"))) {
    throw "backend\requirements.txt 를 찾을 수 없습니다."
}

Write-Host "[2/8] 이전 결과 정리..." -ForegroundColor Cyan
Remove-Item $out, $tmp -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path $out  | Out-Null
New-Item -ItemType Directory -Path $tmp  | Out-Null

Write-Host "[3/8] 파이썬(임베디드) 내려받기..." -ForegroundColor Cyan
$pyzip = Join-Path $tmp "py-embed.zip"
Invoke-WebRequest -Uri $pyurl -OutFile $pyzip
Expand-Archive -Path $pyzip -DestinationPath (Join-Path $out "python")

Write-Host "[4/8] pip 활성화 및 설치..." -ForegroundColor Cyan
$pth = Get-ChildItem (Join-Path $out "python") -Filter "python*._pth" | Select-Object -First 1
(Get-Content $pth.FullName) -replace '^\s*#\s*import site', 'import site' | Set-Content $pth.FullName
$py = Join-Path $out "python\python.exe"
$getpip = Join-Path $tmp "get-pip.py"
Invoke-WebRequest -Uri $pipurl -OutFile $getpip
& $py $getpip --no-warn-script-location

Write-Host "[5/8] 필요한 패키지 설치(인터넷)..." -ForegroundColor Cyan
& $py -m pip install --no-warn-script-location -r (Join-Path $repo "backend\requirements.txt")
if ($LASTEXITCODE -ne 0) { throw "패키지 설치가 실패했습니다. 위 메시지를 확인하세요." }
# 설치가 끝났다고 다 된 것이 아니다 — 실제로 불러와지는지 확인한다(1_SETUP.bat 의 목록과 같게).
& $py -c "import fastapi, uvicorn, pydantic, httpx, dotenv, docx, openpyxl, pypdf, defusedxml"
if ($LASTEXITCODE -ne 0) { throw "설치한 패키지를 불러오지 못했습니다. 위 메시지를 확인하세요." }

Write-Host "[6/8] 앱 파일 복사..." -ForegroundColor Cyan
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

Write-Host "[7/8] 실행 런처/설명서 배치..." -ForegroundColor Cyan
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

Write-Host "[8/8] 압축 파일 만들기..." -ForegroundColor Cyan
# 폴더를 하나의 파일로 묶어 둔다. 메신저·GitLab 처럼 '파일 하나'만 받는 통로로 넘길 때 쓴다.
# 풀면 '그라운드워크_포터블' 폴더가 그대로 나온다. (.gitignore 가 *.zip 을 막아 저장소엔 안 들어간다)
$zip = "$out.zip"
Remove-Item $zip -Force -ErrorAction SilentlyContinue
Compress-Archive -Path $out -DestinationPath $zip -CompressionLevel Optimal

Write-Host ""
Write-Host "완성되었습니다." -ForegroundColor Green
Write-Host ("포터블 폴더: " + $out)
Write-Host ("압축 파일  : " + $zip)
Write-Host "이 폴더를 통째로 행정망 PC로 옮긴 뒤, 안의 '실행.bat' 을 더블클릭하세요."
Write-Host "(파일 하나로 넘겨야 하면 압축 파일을 보내고, 받은 쪽에서 풀어 같은 방법으로 실행합니다.)"
