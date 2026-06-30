# Launch the regular n-gon construction app on Windows: start the local server
# (using the bundled venv interpreter) and open it in the default browser.
# Usage:  .\run_Windows.ps1 [PORT]      (default port 8000; press Ctrl-C to stop)
[CmdletBinding()]
param(
    [int]$Port = 8000
)

$ErrorActionPreference = 'Stop'

$Dir = $PSScriptRoot
$Py  = Join-Path $Dir 'venv_Windows\Scripts\python.exe'
$Url = "http://127.0.0.1:$Port/"

if (-not (Test-Path $Py)) {
    Write-Error @"
找不到虚拟环境解释器：$Py
请先创建：
    py -3 -m venv --copies "$Dir\venv_Windows"
    & "$Dir\venv_Windows\Scripts\python.exe" -m pip install -r "$Dir\requirements.txt"
"@
    exit 1
}

Write-Host "启动服务器：$Url  （按 Ctrl-C 停止）"
$srv = Start-Process -FilePath $Py -ArgumentList @("$Dir\server.py", '--port', "$Port") -PassThru -NoNewWindow

# 进程退出时（含 Ctrl-C）确保关闭服务器
try {
    # 等待端口就绪后再打开浏览器（用 venv 的 python 探测，无需 curl）
    $ready = $false
    foreach ($i in 1..50) {
        $code = & $Py -c "import socket,sys; s=socket.socket(); s.settimeout(0.2); sys.exit(0 if s.connect_ex(('127.0.0.1',$Port))==0 else 1)"
        if ($LASTEXITCODE -eq 0) { $ready = $true; break }
        Start-Sleep -Milliseconds 100
    }
    if ($ready) {
        Start-Process $Url | Out-Null
    } else {
        Write-Host "请在浏览器打开：$Url"
    }

    # 阻塞直到服务器退出（或 Ctrl-C）
    Wait-Process -Id $srv.Id
}
finally {
    if (-not $srv.HasExited) {
        Stop-Process -Id $srv.Id -Force -ErrorAction SilentlyContinue
    }
}
