# 小凡智能体 · 工作台一键启动
# 作用：先确保后端 server.py(8765) 在跑，再确保前端 vite(5276) 在跑，最后打开浏览器。
# 说明：前端 /api、/v1 由 vite 代理到 127.0.0.1:8765（见 vite.config.ts）。
#       后端不在时，旧聊天页会降级成「独立模式」直连模型，智谱/GLM 会被跨域拦掉。
# 日志：workbench\.dev-logs\backend.log / frontend.log

param([switch]$SkipBrowser)

$root = Split-Path -Parent $PSScriptRoot   # workbench/
$repo = Split-Path -Parent $root           # 仓库根目录（server.py 在这里）
$logs = Join-Path $root '.dev-logs'
if (-not (Test-Path $logs)) { New-Item -ItemType Directory -Path $logs -Force | Out-Null }

$py = "C:\Users\18146\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
if (-not (Test-Path $py)) { $py = "python" }

function Test-Backend {
    try {
        $r = Invoke-WebRequest -Uri 'http://127.0.0.1:8765/api/health' -TimeoutSec 2 -UseBasicParsing
        return ($r.StatusCode -eq 200)
    } catch { return $false }
}

function Test-Port([int]$port) {
    try {
        $c = New-Object Net.Sockets.TcpClient
        $c.Connect('127.0.0.1', $port)
        $c.Close()
        return $true
    } catch { return $false }
}

Write-Host "[1/3] 检查后端 8765 ..."
if (Test-Backend) {
    Write-Host "      后端已在运行，跳过。"
} else {
    Write-Host "      后端没在跑，启动 server.py ..."
    # 重定向到日志：既方便排查，也避免子进程继承本窗口的输出句柄（否则窗口关不掉）
    Start-Process -FilePath $py `
        -ArgumentList (Join-Path $repo 'server.py') `
        -WorkingDirectory $repo `
        -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $logs 'backend.log') `
        -RedirectStandardError (Join-Path $logs 'backend.err.log')
}

Write-Host "[2/3] 等待后端就绪（最多 30 秒）..."
$ok = $false
for ($i = 0; $i -lt 30; $i++) {
    if (Test-Backend) { $ok = $true; break }
    Start-Sleep -Seconds 1
}
if ($ok) {
    Write-Host "      后端 OK: http://127.0.0.1:8765"
} else {
    Write-Host "      [!] 后端 30 秒没起来，看 $logs\backend.err.log"
}

Write-Host "[3/3] 检查前端 5276 ..."
if (Test-Port 5276) {
    Write-Host "      5276 已被占用（多半是上次的 vite 还没退），直接复用。"
} else {
    Write-Host "      启动 vite（npm run dev，日志见 $logs\frontend.log）..."
    Start-Process -FilePath "npm.cmd" `
        -ArgumentList "run", "dev" `
        -WorkingDirectory $root `
        -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $logs 'frontend.log') `
        -RedirectStandardError (Join-Path $logs 'frontend.err.log')
    for ($i = 0; $i -lt 25; $i++) {
        if (Test-Port 5276) { break }
        Start-Sleep -Seconds 1
    }
    if (-not (Test-Port 5276)) {
        Write-Host "      [!] vite 没起来，看 $logs\frontend.err.log"
    }
}

if (-not $SkipBrowser) { Start-Process "http://127.0.0.1:5276" }
Write-Host ""
Write-Host "工作台: http://127.0.0.1:5276"
Write-Host "（本窗口可以直接关闭，服务在后台继续跑）"
