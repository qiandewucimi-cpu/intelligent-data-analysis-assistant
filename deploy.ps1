# 智能数据分析助手 · 一键部署脚本
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$here = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $here

function Say($m, $c = 'White') { Write-Host $m -ForegroundColor $c }
function Die($m) {
    Say ""
    Say "X 出错了: $m" 'Red'
    Say "把上面的红字截图发给我就行。" 'Yellow'
    Read-Host "按回车键退出"
    exit 1
}

function Python-Installer-Signature-OK($path) {
    try {
        $signature = Get-AuthenticodeSignature -FilePath $path
        return (
            $signature.Status -eq 'Valid' -and
            $null -ne $signature.SignerCertificate -and
            $signature.SignerCertificate.Subject -match 'Python Software Foundation'
        )
    } catch {
        return $false
    }
}

Say "============================================" 'Cyan'
Say "   智能数据分析助手 · 一键部署" 'Cyan'
Say "============================================" 'Cyan'
Say ""

# 1. 找 / 自动装 Python（必须 3.9 及以上，否则 pandas/numpy 装不上）
$minMajor = 3; $minMinor = 9
function PyVersionOK($cmd) {
    try {
        $v = & $cmd --version 2>&1
        if ($v -match 'Python (\d+)\.(\d+)') {
            $maj = [int]$Matches[1]; $min = [int]$Matches[2]
            if ($maj -gt $minMajor) { return $true }
            if ($maj -eq $minMajor -and $min -ge $minMinor) { return $true }
        }
    } catch {}
    return $false
}
$py = $null
$tooOld = $null
foreach ($cmd in @('py', 'python')) {
    $g = Get-Command $cmd -ErrorAction SilentlyContinue
    if ($g) {
        if (PyVersionOK $cmd) { $py = $cmd; break }
        else { try { $tooOld = (& $cmd --version 2>&1) } catch {} }
    }
}
if (-not $py) {
    $cand = @("$env:LocalAppData\Programs\Python\Python312\python.exe",
              "$env:LocalAppData\Programs\Python\Python311\python.exe",
              "$env:LocalAppData\Programs\Python\Python310\python.exe",
              "$env:LocalAppData\Programs\Python\Python39\python.exe",
              "$env:ProgramFiles\Python312\python.exe")
    foreach ($c in $cand) { if ((Test-Path $c) -and (PyVersionOK $c)) { $py = $c; break } }
}
if ((-not $py) -and $tooOld) {
    Say "[1/4] 检测到的 Python 版本过低（$tooOld），本工具需要 3.9 及以上，将自动安装新版本..." 'Yellow'
}
if (-not $py) {
    Say "[1/4] 没检测到 Python，开始自动下载安装（约 25MB，优先国内镜像，请保持联网）..." 'Yellow'
    $ver = '3.12.7'
    # 国内镜像优先（华为/阿里/npmmirror），最后才回退官方源，避免国内下载卡死
    $urls = @(
        "https://mirrors.huaweicloud.com/python/$ver/python-$ver-amd64.exe",
        "https://mirrors.aliyun.com/python-release/windows/python-$ver-amd64.exe",
        "https://registry.npmmirror.com/-/binary/python/$ver/python-$ver-amd64.exe",
        "https://www.python.org/ftp/python/$ver/python-$ver-amd64.exe"
    )
    $exe = "$env:TEMP\python-$ver-amd64.exe"
    $dlOK = $false
    foreach ($u in $urls) {
        try {
            Say "      正在尝试下载：$u" 'Gray'
            Invoke-WebRequest -Uri $u -OutFile $exe -UseBasicParsing -TimeoutSec 120
            if (
                (Test-Path $exe) -and
                ((Get-Item $exe).Length -gt 20MB) -and
                (Python-Installer-Signature-OK $exe)
            ) {
                $dlOK = $true
                Say "      下载成功，数字签名验证通过。" 'Green'
                break
            }
            Say "      安装包数字签名无效，已拒绝运行并切换下载源。" 'Yellow'
            Remove-Item -LiteralPath $exe -Force -ErrorAction SilentlyContinue
        } catch { Say "      这个源没下成功，换下一个..." 'Yellow' }
    }
    if (-not $dlOK) { Die "Python 安装包下载失败（国内外镜像都试过了），请检查网络后重新双击。" }
    Say "      正在静默安装 Python（自动加入 PATH）..." 'Yellow'
    Start-Process $exe -ArgumentList '/quiet InstallAllUsers=0 PrependPath=1 Include_pip=1 Include_test=0' -Wait
    $py = "$env:LocalAppData\Programs\Python\Python312\python.exe"
    if (-not (Test-Path $py)) { Die "Python 自动安装失败，请手动到 python.org 安装并勾选 Add to PATH。" }
    Say "      Python 安装完成。" 'Green'
} else {
    Say "[1/4] 已检测到 Python：$py" 'Green'
}

# 2. 建虚拟环境（若已有但版本过低，自动删除重建，避免沿用旧 Python）
$vpy = Join-Path $here '.venv\Scripts\python.exe'
if ((Test-Path $vpy) -and (-not (PyVersionOK $vpy))) {
    Say "[2/4] 检测到旧的运行环境版本过低，正在重建..." 'Yellow'
    Remove-Item (Join-Path $here '.venv') -Recurse -Force -ErrorAction SilentlyContinue
}
if (-not (Test-Path $vpy)) {
    Say "[2/4] 首次运行，正在创建运行环境..." 'Yellow'
    & $py -m venv .venv
    if (-not (Test-Path $vpy)) { Die "创建运行环境失败。" }
} else {
    Say "[2/4] 运行环境已就绪。" 'Green'
}

# 3. 装依赖（清华镜像）
$flag = Join-Path $here '.venv\.deps_ok'
if (-not (Test-Path $flag)) {
    Say "[3/4] 正在安装依赖（国内镜像，第一次约几分钟，别关窗口）..." 'Yellow'
    $mirror = 'https://pypi.tuna.tsinghua.edu.cn/simple'
    & $vpy -m pip install --upgrade pip -i $mirror
    & $vpy -m pip install -r requirements.txt -i $mirror
    if ($LASTEXITCODE -ne 0) { Die "依赖安装失败。常见原因：1) 网络不通——重连网络后再双击一次即可；2) Python 版本过低（需 3.9+）——请卸载旧版 Python 或删除本文件夹里的 .venv 后重新双击，脚本会自动装新版。" }
    New-Item $flag -ItemType File -Force | Out-Null
    Say "      依赖安装完成。" 'Green'
} else {
    Say "[3/4] 依赖已安装。" 'Green'
}

# 4. 自动找可用端口并启动
function Port-Free($p) {
    try { $c = Get-NetTCPConnection -State Listen -LocalPort $p -ErrorAction SilentlyContinue; return ($null -eq $c) }
    catch { $n = netstat -ano | Select-String ":$p\s.*LISTENING"; return ($null -eq $n) }
}
$port = 0
foreach ($p in 8501..8599) { if (Port-Free $p) { $port = $p; break } }
if ($port -eq 0) { Die "8501-8599 端口全被占用，请重启电脑后再试。" }
if ($port -ne 8501) { Say "[4/4] 8501 端口被占用，已自动改用端口 $port" 'Yellow' }
else { Say "[4/4] 使用端口 8501" 'Green' }

$openUrl = "http://localhost:$port"

# 在桌面创建/更新一键启动快捷方式，方便以后直接从桌面打开（失败不影响启动）
try {
    $desktop = [Environment]::GetFolderPath('Desktop')
    $lnkPath = Join-Path $desktop '启动-智能数据分析助手.lnk'
    $ws = New-Object -ComObject WScript.Shell
    $shortcut = $ws.CreateShortcut($lnkPath)
    $shortcut.TargetPath = (Join-Path $here '一键部署.bat')
    $shortcut.WorkingDirectory = $here
    $shortcut.WindowStyle = 1
    $shortcut.Description = '智能数据分析助手 · 一键启动'
    $shortcut.Save()
    Say "已在桌面创建快捷方式：启动-智能数据分析助手（以后直接双击它就行）" 'Green'
} catch {
    Say "（桌面快捷方式没创建成功，没关系：以后从本文件夹双击『一键部署.bat』也能启动）" 'Yellow'
}

Say ""
Say "★ 启动中... 浏览器将自动打开：$openUrl" 'Cyan'
Say "★ 用完直接关掉本窗口即可停止。" 'Cyan'
Say ""
Start-Job -ArgumentList $openUrl { param($u) Start-Sleep 6; Start-Process $u } | Out-Null
& $vpy -m streamlit run app.py --server.port $port --server.headless true
Read-Host "（程序已停止，按回车退出）"
