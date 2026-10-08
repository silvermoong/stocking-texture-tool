# Installs the tool into this folder: a Python 3.12 environment in .venv, the packages, the two models in models\,
# and a desktop shortcut. install.bat runs this. Running it again is safe: it repairs or updates what is there and
# downloads only what is missing. Everything it adds stays in this folder (uv and its Python in .tools\, the models
# in models\), so deleting the folder and the shortcut removes the tool.
#
#   powershell -ExecutionPolicy Bypass -File tools\install.ps1 [-Torch auto|cuda|cpu] [-Source auto|official|github]
#                                                               [-NoShortcut]
#
# Everything the install needs is listed in tools\deps.json (made by tools\make_deps.py): uv, Python, every package
# wheel and both models, each pinned by size and SHA-256. They come, in order, from:
#   1. the install package the user downloaded (the files of the deps release on GitHub), in deps\, next to
#      install.bat, or in the folder above it: then nothing is downloaded at all;
#   2. -Source github: the install package from this project's GitHub release (whoever got this code can reach it,
#      and it needs nothing else: Hugging Face and Meta, which the models come from, are blocked in mainland China);
#      official: each file from where it is published (PyPI, PyTorch, Python's builds, Meta, Hugging Face);
#      auto (default): GitHub, and the original sources for whatever GitHub fails to deliver.
# Then the install itself runs with no network: Python from the gathered archive, the packages with --no-index.
param(
    [ValidateSet('auto', 'cuda', 'cpu')][string]$Torch = 'auto',
    [ValidateSet('auto', 'official', 'github')][string]$Source = 'auto',
    [switch]$NoShortcut
)

# Native programs (uv, curl, python) are checked by exit code: Windows PowerShell turns their stderr progress into
# error records when its own output is redirected, which 'Stop' would make fatal. Cmdlets that must succeed say so.
$ErrorActionPreference = 'Continue'
$ProgressPreference = 'SilentlyContinue'        # Invoke-WebRequest crawls with its progress bar on
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
Add-Type -AssemblyName System.IO.Compression.FileSystem

$Root = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $Root
$Tools = Join-Path $Root '.tools'
$Work = Join-Path $Tools 'deps'                 # downloads land here; removed after a successful install
$Staging = Join-Path $Work 'files'              # the install files, laid out as in the release zips
$Py = Join-Path $Root '.venv\Scripts\python.exe'
$Uv = Join-Path $Tools 'uv.exe'
$Deps = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'deps.json') -Raw -Encoding UTF8 | ConvertFrom-Json

# the app's own name, in the language the app opens in (it follows the Windows display language)
$AppName = if ([Globalization.CultureInfo]::CurrentUICulture.TwoLetterISOLanguageName -eq 'zh') { '丝袜纹理工具' } else { 'Stocking Texture Tool' }

function Step($n, $text) { Write-Host ''; Write-Host "[$n/5] $text" -ForegroundColor Cyan }
function Note($text) { Write-Host "      $text" }
function Fail($text) {
    Write-Host ''
    Write-Host $text -ForegroundColor Red
    exit 1
}

# Hashing and unzipping go through .NET, not Get-FileHash / Expand-Archive: Windows PowerShell started from a
# PowerShell 7 window inherits 7's module path and cannot load those two.
function Get-Sha256($path) {
    $sha = [Security.Cryptography.SHA256]::Create()
    $fs = [IO.File]::OpenRead($path)
    try { [BitConverter]::ToString($sha.ComputeHash($fs)).Replace('-', '') } finally { $fs.Dispose(); $sha.Dispose() }
}

# A file is good when it has the expected size and SHA-256 (sizes first: a wrong size needs no hashing).
function Test-Good($path, $size, $sha256) {
    if (-not (Test-Path -LiteralPath $path)) { return $false }
    if ((Get-Item -LiteralPath $path).Length -ne $size) { return $false }
    return (Get-Sha256 $path) -eq $sha256
}

function Native($rel) { Join-Path $Staging ($rel -replace '/', '\') }

# Downloads the first of urls that works into dest, through dest.part (resumed when run again), and keeps it only if
# size and SHA-256 match. curl.exe is in Windows since 10 1803; a download slower than 10 KB/s for a minute is given
# up on, so a blocked or crawling host moves on to the next source.
function Get-Url($urls, $dest, $size, $sha256) {
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $dest) -ErrorAction Stop | Out-Null
    $part = "$dest.part"
    foreach ($url in $urls) {
        & curl.exe -L --fail --retry 3 --retry-delay 2 --connect-timeout 15 --speed-limit 10240 --speed-time 60 `
            -# -C - -o $part $url
        if ($LASTEXITCODE -ne 0) {
            Remove-Item -LiteralPath $part -ErrorAction SilentlyContinue
            continue
        }
        if (Test-Good $part $size $sha256) {
            Move-Item -LiteralPath $part -Destination $dest -Force -ErrorAction Stop
            return $true
        }
        Remove-Item -LiteralPath $part -ErrorAction SilentlyContinue
        Note "The file from $url does not match its checksum; trying the next source"
    }
    return $false
}

function Expand-Wanted($zip, $wanted) {
    $z = [IO.Compression.ZipFile]::OpenRead($zip)
    try {
        foreach ($e in $z.Entries) {
            $f = $wanted[$e.FullName]
            if ($null -eq $f) { continue }
            $dest = Native $f.path
            New-Item -ItemType Directory -Force -Path (Split-Path -Parent $dest) -ErrorAction Stop | Out-Null
            [IO.Compression.ZipFileExtensions]::ExtractToFile($e, $dest, $true)
            if (-not (Test-Good $dest $f.size $f.sha256)) { throw "$($f.path) in $zip does not match its checksum" }
        }
    } finally { $z.Dispose() }
}

# One group of the release (base, cpu or cuda): its assets found in the folders given, or (with $download) fetched from
# the GitHub release into $Work; joined when in parts; the wanted files extracted to $Staging. False when not all of
# its assets are at hand (or a download failed).
function Get-Group($group, $wanted, $folders, $download) {
    $g = $Deps.groups.$group
    $paths = @()
    foreach ($a in $g.assets) {
        $found = $null
        foreach ($d in $folders) {
            $p = Join-Path $d $a.name
            if ((Test-Path -LiteralPath $p) -and (Get-Item -LiteralPath $p).Length -eq $a.size) { $found = $p; break }
        }
        if ($null -eq $found -and $download) {
            $found = Join-Path $Work $a.name
            Note "$($a.name) ($([math]::Round($a.size / 1MB)) MB)"
            if (-not (Get-Url @($Deps.release + $a.name) $found $a.size $a.sha256)) { return $false }
        }
        if ($null -eq $found) { return $false }
        $paths += $found
    }
    $zip = $paths[0]
    if ($paths.Count -gt 1) {
        $zip = Join-Path $Work $g.zip.name
        $out = [IO.File]::Create($zip)
        try { foreach ($p in $paths) { $in = [IO.File]::OpenRead($p); try { $in.CopyTo($out, 4MB) } finally { $in.Dispose() } } }
        finally { $out.Dispose() }
    }
    if (-not (Test-Good $zip $g.zip.size $g.zip.sha256)) { Note "$($g.zip.name) does not match its checksum"; return $false }
    Expand-Wanted $zip $wanted
    foreach ($p in @($paths) + @($zip)) {           # what this run downloaded or joined; the user's own files stay
        if ($p.StartsWith($Work) -and (Test-Path -LiteralPath $p)) { Remove-Item -LiteralPath $p }
    }
    return $true
}

# Where the user may have put the install package: deps\, next to install.bat, or the folder above (a download folder
# holding the code zip, extracted where it lies, and the package).
$Local = @((Join-Path $Root 'deps'), $Root, (Split-Path -Parent $Root)) | Where-Object { $_ -and (Test-Path -LiteralPath $_) }

function Test-LocalGroup($group) {
    foreach ($a in $Deps.groups.$group.assets) {
        $here = $false
        foreach ($d in $Local) {
            $p = Join-Path $d $a.name
            if ((Test-Path -LiteralPath $p) -and (Get-Item -LiteralPath $p).Length -eq $a.size) { $here = $true; break }
        }
        if (-not $here) { return $false }
    }
    return $true
}

# Gets the files listed (entries of deps.json) into $Staging: those already there from an unfinished run, then the
# install package the user put here (in deps\, next to install.bat, or in the folder above: a download folder holding
# the code zip, extracted where it lies, and the package), then downloads, per -Source.
function Get-Files($files) {
    $todo = @($files | Where-Object { -not (Test-Good (Native $_.path) $_.size $_.sha256) })
    if ($todo.Count -eq 0) { return }
    $mb = [math]::Round((($todo | Measure-Object size -Sum).Sum) / 1MB)
    Note "$($todo.Count) files to get ($mb MB)"
    New-Item -ItemType Directory -Force -Path $Staging -ErrorAction Stop | Out-Null
    $wanted = @{}
    foreach ($f in $todo) {
        if (-not $wanted.ContainsKey($f.group)) { $wanted[$f.group] = @{} }
        $wanted[$f.group][$f.path] = $f
    }
    $left = @()
    foreach ($g in @($wanted.Keys | Sort-Object)) {
        if (Get-Group $g $wanted[$g] $Local $false) { Note "Used the $g install files found in this folder" } else { $left += $g }
    }
    if ($left.Count -eq 0) { return }
    $order = if ($Source -eq 'auto') { @('github', 'official') } else { @($Source) }
    foreach ($src in $order) {
        if ($left.Count -eq 0) { break }
        $still = @()
        if ($src -eq 'github') {
            Note 'Downloading from GitHub'
            foreach ($g in $left) { if (-not (Get-Group $g $wanted[$g] @() $true)) { $still += $g } }
        } else {
            Note 'Downloading from where each file is published'
            foreach ($g in $left) {
                foreach ($f in $wanted[$g].Values) {
                    if (Test-Good (Native $f.path) $f.size $f.sha256) { continue }
                    Note "$(Split-Path -Leaf $f.path) ($([math]::Round($f.size / 1MB, 1)) MB)"
                    if (-not (Get-Url @($f.url) (Native $f.path) $f.size $f.sha256)) {
                        $still += $g            # the whole group comes from the next source: stop here
                        break
                    }
                }
            }
        }
        $left = $still
        if ($left.Count -gt 0 -and $src -ne $order[-1]) {
            if ($src -eq 'github') { Note 'Some files did not download from GitHub; getting them from where each is published' }
            else { Note 'Some files did not download; getting them from the install package on GitHub' }
        }
    }
    if ($left.Count -gt 0) {
        Fail ("Some install files could not be downloaded; see the messages above. Check the connection and run`n" +
              "install.bat again: what has downloaded is kept. Or download the $($Deps.name) release files from this`n" +
              "project's GitHub page (Releases), put them in a folder named deps next to install.bat, and run it again.")
    }
}

Write-Host 'Stocking Texture Tool: install' -ForegroundColor White
Write-Host "Folder: $Root"
# the deepest file the install writes is about 150 characters below this folder, and Windows stops at 260
if ($Root.Length -gt 100) {
    Write-Host 'Note: this folder path is long, and some files may exceed the Windows path limit. If the install fails, move the folder somewhere shorter.' -ForegroundColor Yellow
}

# ---------------------------------------------------------------- 1. which torch: NVIDIA card or CPU
Step 1 'Checking the graphics card'
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
if ($Torch -eq 'auto') {
    # the install package put here holds one build of torch: the user chose it
    if ($variant -eq 'cuda' -and -not (Test-LocalGroup 'cuda') -and (Test-LocalGroup 'cpu')) {
        $variant = 'cpu'; Note 'The install package here holds the CPU build of torch, so that is the one installed'
    } elseif ($variant -eq 'cpu' -and -not (Test-LocalGroup 'cpu') -and (Test-LocalGroup 'cuda')) {
        $variant = 'cuda'; Note 'The install package here holds the GPU build of torch, so that is the one installed'
    }
}
if ($variant -eq 'cuda') { Note 'Using the GPU build of torch' } else { Note 'Using the CPU build of torch' }

# ---------------------------------------------------------------- 2. the install files that are missing here
Step 2 'Getting the install files'
$uvOk = (Test-Path -LiteralPath $Uv) -and ((& $Uv --version) -like "uv $($Deps.uv)*")
$pyOk = $false
if (Test-Path -LiteralPath $Py) {
    $v = (& $Py -c "import sys; print('%d.%d' % sys.version_info[:2])")
    $pyOk = ($LASTEXITCODE -eq 0 -and $v -eq '3.12')
    if (-not $pyOk) { Note 'The existing .venv is unusable; making a new one' }
}
# The packages: when this .venv already satisfies the requirements (uv's dry run, with no network), none are needed;
# else those not installed at the release's versions (a cpu -> cuda switch: just PyTorch), and step 4 fetches the
# rest should uv still want more.
$wheelsOk = $false
$installed = @{}
if ($uvOk -and $pyOk) {
    $env:UV_CACHE_DIR = Join-Path $Tools 'uv-cache'
    & $Uv pip install --python $Py --offline --no-index --dry-run -q -r requirements.txt -r "requirements-torch-$variant.txt" 2>$null
    $wheelsOk = ($LASTEXITCODE -eq 0)
    if (-not $wheelsOk) {
        $list = & $Uv pip list --python $Py --format json 2>$null
        if ($LASTEXITCODE -eq 0) {
            foreach ($p in ($list | ConvertFrom-Json)) { $installed[(($p.name -replace '[-_.]+', '-').ToLower()) + '==' + $p.version] = $true }
        }
    }
}
$need = @()
foreach ($f in $Deps.files) {
    if ($f.group -ne 'base' -and $f.group -ne $variant) { continue }
    $missing = switch (($f.path -split '/')[0]) {
        'uv' { -not $uvOk }
        'python' { -not $pyOk }
        'wheels' {
            $parts = (Split-Path -Leaf $f.path) -split '-'
            (-not $wheelsOk) -and -not $installed[(($parts[0] -replace '[-_.]+', '-').ToLower()) + '==' + $parts[1]]
        }
        'models' {
            $p = Join-Path $Root ($f.path -replace '/', '\')
            -not ((Test-Path -LiteralPath $p) -and (Get-Item -LiteralPath $p).Length -eq $f.size)
        }
    }
    if ($missing) { $need += $f }
}
if ($need.Count -eq 0) { Note 'Everything is here already' } else { Get-Files $need }

# ---------------------------------------------------------------- 3. uv and Python 3.12 in .venv
Step 3 'Setting up Python 3.12 (.venv)'
if (-not $uvOk) {
    New-Item -ItemType Directory -Force -Path $Tools -ErrorAction Stop | Out-Null
    $whl = Native ($Deps.files | Where-Object { $_.path -like 'uv/*' } | Select-Object -First 1).path
    $z = [IO.Compression.ZipFile]::OpenRead($whl)
    try {
        $e = $z.Entries | Where-Object { $_.FullName -like '*/scripts/uv.exe' } | Select-Object -First 1
        [IO.Compression.ZipFileExtensions]::ExtractToFile($e, $Uv, $true)
    } finally { $z.Dispose() }
}
Note "uv $($Deps.uv)"
# uv keeps its Python and its cache in this folder too, so the cache can hard-link into .venv
$env:UV_CACHE_DIR = Join-Path $Tools 'uv-cache'
$env:UV_PYTHON_INSTALL_DIR = Join-Path $Tools 'python'
Remove-Item Env:VIRTUAL_ENV -ErrorAction SilentlyContinue
if (-not $pyOk) {
    if (Test-Path -LiteralPath (Join-Path $Root '.venv')) { Remove-Item -LiteralPath (Join-Path $Root '.venv') -Recurse -Force -ErrorAction Stop }
    # uv's own Python (from the gathered archive, laid out as uv's download mirror), whatever the machine has
    $env:UV_PYTHON_INSTALL_MIRROR = ([Uri](Join-Path $Staging 'python')).AbsoluteUri
    & $Uv venv (Join-Path $Root '.venv') --python $Deps.python --managed-python
    if ($LASTEXITCODE -ne 0) { Fail 'Could not set up Python; see the error above.' }
}
Note (& $Py --version)

# ---------------------------------------------------------------- 4. packages, with no network
Step 4 'Installing the packages'
$wheelDir = Join-Path $Staging 'wheels'
$args4 = @('pip', 'install', '--python', $Py, '--offline', '--no-index', '--find-links', $wheelDir,
           '-r', 'requirements.txt', '-r', "requirements-torch-$variant.txt")
New-Item -ItemType Directory -Force -Path $wheelDir -ErrorAction Stop | Out-Null
$out4 = & $Uv @args4 2>&1
if ($LASTEXITCODE -eq 0) {
    $out4 | ForEach-Object { "$_" }
} else {
    # uv wants a package version this .venv lacks: fetch every package of the release and install again
    Get-Files @($Deps.files | Where-Object { $_.path -like 'wheels/*' -and ($_.group -eq 'base' -or $_.group -eq $variant) })
    & $Uv @args4
    if ($LASTEXITCODE -ne 0) { Fail 'Installing the packages failed; see the error above. Run install.bat again.' }
}

# ---------------------------------------------------------------- 5. models, then the shortcut
Step 5 'Setting up the models'
foreach ($f in $Deps.files) {
    if (-not $f.path.StartsWith('models/')) { continue }
    $dest = Join-Path $Root ($f.path -replace '/', '\')
    $src = Native $f.path
    if (Test-Path -LiteralPath $src) {
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $dest) -ErrorAction Stop | Out-Null
        Move-Item -LiteralPath $src -Destination $dest -Force -ErrorAction Stop
    }
    if (-not ((Test-Path -LiteralPath $dest) -and (Get-Item -LiteralPath $dest).Length -eq $f.size)) {
        Fail "The model file $($f.path) is missing. Run install.bat again."
    }
}
Note 'SAM ViT-B and Depth Anything V2 Small in models\'

$device = & $Py -c "import torch; from stocking.sam import pick_device; print(pick_device(torch)[1])"
if ($LASTEXITCODE -ne 0) { Fail 'The installed environment does not start; see the error above.' }
if (Test-Path -LiteralPath $Work) { Remove-Item -LiteralPath $Work -Recurse -Force -ErrorAction SilentlyContinue }

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
