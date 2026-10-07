# Installs the tool into this folder: a Python 3.12 environment in .venv, the packages, the two models in models\,
# and a desktop shortcut. install.bat runs this. Running it again is safe: it repairs or updates what is there and
# skips what is already done. Everything it adds stays in this folder (uv and its Python in .tools\, the models in
# models\), so deleting the folder and the shortcut removes the tool.
#
#   powershell -ExecutionPolicy Bypass -File tools\install.ps1 [-Torch auto|cuda|cpu] [-NoShortcut]
param(
    [ValidateSet('auto', 'cuda', 'cpu')][string]$Torch = 'auto',
    [switch]$NoShortcut
)

# Native programs (uv, curl, python) are checked by exit code: Windows PowerShell turns their stderr progress into
# error records when its own output is redirected, which 'Stop' would make fatal. Cmdlets that must succeed say so.
$ErrorActionPreference = 'Continue'
$ProgressPreference = 'SilentlyContinue'        # Invoke-WebRequest crawls with its progress bar on
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$Root = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $Root
$Tools = Join-Path $Root '.tools'
$Models = Join-Path $Root 'models'
$Py = Join-Path $Root '.venv\Scripts\python.exe'

$UvVersion = '0.12.23'
$UvUrl = "https://github.com/astral-sh/uv/releases/download/$UvVersion/uv-x86_64-pc-windows-msvc.zip"
$UvSha256 = '75D05DE6762778C31EE183398DE7DD15093FAD0ED90B1F236D8205EA5EC00C90'
$SamFile = 'sam_vit_b_01ec64.pth'
$SamUrl = "https://dl.fbaipublicfiles.com/segment_anything/$SamFile"
$SamSha256 = 'EC2DF62732614E57411CDCF32A23FFDF28910380D03139EE0F4FCBE91EB8C912'
$DepthRepo = 'depth-anything/Depth-Anything-V2-Small-hf'
$DepthRevision = '5426e4f0f36572d16453bbda7a8389317b1bef99'

# the app's own name, in the language the app opens in (it follows the Windows display language)
$AppName = if ([Globalization.CultureInfo]::CurrentUICulture.TwoLetterISOLanguageName -eq 'zh') { '丝袜纹理工具' } else { 'Stocking Texture Tool' }

# Hashing and unzipping go through .NET, not Get-FileHash / Expand-Archive: Windows PowerShell started from a
# PowerShell 7 window inherits 7's module path and cannot load those two.
function Get-Sha256($path) {
    $sha = [Security.Cryptography.SHA256]::Create()
    $fs = [IO.File]::OpenRead($path)
    try { [BitConverter]::ToString($sha.ComputeHash($fs)).Replace('-', '') } finally { $fs.Dispose(); $sha.Dispose() }
}

function Step($n, $text) { Write-Host ''; Write-Host "[$n/5] $text" -ForegroundColor Cyan }
function Note($text) { Write-Host "      $text" }
function Fail($text) {
    Write-Host ''
    Write-Host $text -ForegroundColor Red
    exit 1
}

# Downloads url to dest through dest.part, checks the SHA-256, then moves it into place. curl.exe (in Windows since
# 10 1803) shows progress and resumes; Invoke-WebRequest is the fallback.
function Get-File($url, $dest, $sha256) {
    $part = "$dest.part"
    $curl = Get-Command curl.exe -ErrorAction SilentlyContinue
    if ($curl) {
        & $curl.Source -L --fail --retry 3 --retry-delay 2 -C - -o $part $url
        if ($LASTEXITCODE -ne 0) {
            Remove-Item -LiteralPath $part -ErrorAction SilentlyContinue
            & $curl.Source -L --fail --retry 3 --retry-delay 2 -o $part $url
        }
        if ($LASTEXITCODE -ne 0) { throw "curl exit code $LASTEXITCODE" }
    } else {
        Invoke-WebRequest -Uri $url -OutFile $part -UseBasicParsing -ErrorAction Stop
    }
    $got = Get-Sha256 $part
    if ($got -ne $sha256) {
        Remove-Item -LiteralPath $part
        throw "the download does not match its checksum ($url)"
    }
    Move-Item -LiteralPath $part -Destination $dest -Force -ErrorAction Stop
}

Write-Host 'Stocking Texture Tool: install' -ForegroundColor White
Write-Host "Folder: $Root"
# the deepest file the install writes is about 150 characters below this folder, and Windows stops at 260
if ($Root.Length -gt 100) {
    Write-Host 'Note: this folder path is long, and some files may exceed the Windows path limit. If the install fails, move the folder somewhere shorter.' -ForegroundColor Yellow
}

# ---------------------------------------------------------------- 1. uv (installs Python and the packages)
Step 1 'Getting the installer tool, uv'
$Uv = Join-Path $Tools 'uv.exe'
$have = $null
if (Test-Path -LiteralPath $Uv) { $have = (& $Uv --version) }
if ($have -notlike "uv $UvVersion*") {
    New-Item -ItemType Directory -Force -Path $Tools -ErrorAction Stop | Out-Null
    $zip = Join-Path $Tools 'uv.zip'
    try { Get-File $UvUrl $zip $UvSha256 }
    catch { Fail "Could not download uv: $($_.Exception.Message)`nCheck the internet connection and run install.bat again." }
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $z = [IO.Compression.ZipFile]::OpenRead($zip)
    try {
        foreach ($e in $z.Entries) {
            if ($e.Name -like '*.exe') { [IO.Compression.ZipFileExtensions]::ExtractToFile($e, (Join-Path $Tools $e.Name), $true) }
        }
    } finally { $z.Dispose() }
    Remove-Item -LiteralPath $zip
}
Note "uv $UvVersion"
# uv keeps its Python and its download cache in this folder too, so the cache can hard-link into .venv
$env:UV_CACHE_DIR = Join-Path $Tools 'uv-cache'
$env:UV_PYTHON_INSTALL_DIR = Join-Path $Tools 'python'
Remove-Item Env:VIRTUAL_ENV -ErrorAction SilentlyContinue

# ---------------------------------------------------------------- 2. Python 3.12 in .venv
Step 2 'Setting up Python 3.12 (.venv)'
$ok = $false
if (Test-Path -LiteralPath $Py) {
    $v = (& $Py -c "import sys; print('%d.%d' % sys.version_info[:2])")
    $ok = ($LASTEXITCODE -eq 0 -and $v -eq '3.12')
    if (-not $ok) { Note 'The existing .venv is unusable; making a new one' }
}
if (-not $ok) {
    if (Test-Path -LiteralPath (Join-Path $Root '.venv')) { Remove-Item -LiteralPath (Join-Path $Root '.venv') -Recurse -Force -ErrorAction Stop }
    # uv's own Python 3.12 (downloaded into .tools\python), whatever Python the machine has or lacks
    & $Uv venv (Join-Path $Root '.venv') --python 3.12 --managed-python --seed
    if ($LASTEXITCODE -ne 0) { Fail 'Could not set up Python; see the error above.' }
}
Note (& $Py --version)

# ---------------------------------------------------------------- 3. which torch: NVIDIA card or CPU
Step 3 'Checking the graphics card'
$variant = $Torch
if ($variant -eq 'auto') {
    $variant = 'cpu'
    $smi = Get-Command nvidia-smi.exe -ErrorAction SilentlyContinue
    if (-not $smi -and (Test-Path "$env:SystemRoot\System32\nvidia-smi.exe")) { $smi = Get-Item "$env:SystemRoot\System32\nvidia-smi.exe" }
    if ($smi) {
        $smiPath = if ($smi.Source) { $smi.Source } else { $smi.FullName }
        $rows = & $smiPath --query-gpu=name,driver_version,compute_cap --format=csv,noheader
        foreach ($row in @($rows)) {
            $f = $row -split ',\s*'
            if ($f.Count -lt 3) { continue }
            $driver = [double](($f[1] -split '\.')[0])
            $cap = [double]$f[2]
            Note "$($f[0]) (driver $($f[1]), compute capability $($f[2]))"
            if ($cap -lt 7.5) {
                Note 'This card is too old for the GPU build of torch; using the CPU'
            } elseif ($driver -lt 570) {
                Note 'The driver is older than 570, which the GPU build of torch needs. Installing the CPU build; update the driver and run install.bat again to switch.'
            } else {
                $variant = 'cuda'
            }
        }
    } else {
        Note 'No NVIDIA card: using the CPU (everything works; Pick and depth are slower)'
    }
}
if ($variant -eq 'cuda') { Note 'Installing the GPU build of torch (about 3 GB)' }
else { Note 'Installing the CPU build of torch (about 110 MB)' }

# ---------------------------------------------------------------- 4. packages
Step 4 'Installing the packages (the first time downloads a few GB)'
& $Uv pip install --python $Py --index-strategy unsafe-best-match -r requirements.txt -r "requirements-torch-$variant.txt"
if ($LASTEXITCODE -ne 0) { Fail 'Installing the packages failed; see the error above. Check the connection and run install.bat again; nothing is downloaded twice.' }

# ---------------------------------------------------------------- 5. models, then the shortcut
Step 5 'Downloading the models'
New-Item -ItemType Directory -Force -Path $Models -ErrorAction Stop | Out-Null
$sam = Join-Path $Models $SamFile
if (-not (Test-Path -LiteralPath $sam)) {
    $local = Join-Path ([Environment]::GetFolderPath('UserProfile')) "Downloads\$SamFile"
    if ((Test-Path -LiteralPath $local) -and (Get-Sha256 $local) -eq $SamSha256) {
        Copy-Item -LiteralPath $local -Destination $sam -ErrorAction Stop
    } else {
        Note 'Pick model, SAM ViT-B (375 MB)'
        try { Get-File $SamUrl $sam $SamSha256 }
        catch { Fail "Could not download the SAM model: $($_.Exception.Message)`nCheck the internet connection and run install.bat again." }
    }
}
Note "SAM ViT-B: models\$SamFile"
$depthDir = Join-Path $Models ($DepthRepo -split '/')[-1]
Remove-Item Env:HF_HUB_OFFLINE -ErrorAction SilentlyContinue
$env:PYTHONIOENCODING = 'utf-8'
$env:STOCKING_DEPTH_DIR = $depthDir
& $Py -c "import os; from huggingface_hub import snapshot_download as s; s('$DepthRepo', revision='$DepthRevision', local_dir=os.environ['STOCKING_DEPTH_DIR'], allow_patterns=['*.json', '*.safetensors'])"
if ($LASTEXITCODE -ne 0) { Fail 'Could not download the depth model; see the error above. Check the internet connection and run install.bat again.' }
Note "Depth Anything V2 Small: models\$(Split-Path -Leaf $depthDir)"

$device = & $Py -c "import torch; from stocking.sam import pick_device; print(pick_device(torch)[1])"
if ($LASTEXITCODE -ne 0) { Fail 'The installed environment does not start; see the error above.' }

if (-not $NoShortcut) {
    try {
        $lnk = Join-Path ([Environment]::GetFolderPath('Desktop')) "$AppName.lnk"
        $shell = New-Object -ComObject WScript.Shell
        $s = $shell.CreateShortcut($lnk)
        $s.TargetPath = Join-Path $Root '.venv\Scripts\pythonw.exe'
        $s.Arguments = '-m stocking'
        $s.WorkingDirectory = $Root
        $s.Description = $AppName
        $icon = Join-Path $Root 'stocking\static\icon.ico'
        if (Test-Path -LiteralPath $icon) { $s.IconLocation = "$icon,0" }
        $s.Save()
    } catch {
        Write-Host "Could not make the desktop shortcut ($($_.Exception.Message)); start.bat opens the tool too." -ForegroundColor Yellow
        $NoShortcut = $true
    }
}

Write-Host ''
Write-Host "Done. Computing on: $device" -ForegroundColor Green
if ($NoShortcut) {
    Write-Host 'Double-click start.bat to open the tool.'
} else {
    Write-Host "Double-click `"$AppName`" on the desktop to open the tool, or drop a picture or PSD on it."
}
