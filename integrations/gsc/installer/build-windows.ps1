# Run on Windows with Node.js >=20 and Inno Setup 6 installed.
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$stage = Join-Path $PSScriptRoot 'stage'
$node = (Get-Command node.exe -ErrorAction Stop).Source
$nodeVersion = (& $node -p "process.versions.node").Trim()
if ([int]($nodeVersion.Split('.')[0]) -lt 20) { throw 'Node.js 20+ required' }
Push-Location $root
try {
  if (Test-Path (Join-Path $root 'package-lock.json')) {
    & npm.cmd ci
  } else {
    & npm.cmd install --no-audit --no-fund
  }
  if ($LASTEXITCODE -ne 0) { throw 'npm dependency installation failed' }
  & npm.cmd run check
  if ($LASTEXITCODE -ne 0) { throw 'TypeScript check failed' }
  & npm.cmd run build
  if ($LASTEXITCODE -ne 0) { throw 'TypeScript build failed' }
  & npm.cmd test
  if ($LASTEXITCODE -ne 0) { throw 'Tests failed' }
  if (Test-Path $stage) { Remove-Item $stage -Recurse -Force }
  New-Item -ItemType Directory -Force -Path (Join-Path $stage 'runtime'),(Join-Path $stage 'dist'),(Join-Path $stage 'scripts') | Out-Null
  Copy-Item $node (Join-Path $stage 'runtime/node.exe')
  Copy-Item (Join-Path $root 'dist/*') (Join-Path $stage 'dist') -Recurse
  Copy-Item (Join-Path $root 'scripts/register-claude.mjs') (Join-Path $stage 'scripts')
  Copy-Item (Join-Path $root 'package.json') $stage
  if (Test-Path (Join-Path $root 'package-lock.json')) {
    Copy-Item (Join-Path $root 'package-lock.json') $stage
    & npm.cmd ci --omit=dev --ignore-scripts --prefix $stage
  } else {
    & npm.cmd install --omit=dev --ignore-scripts --no-audit --no-fund --prefix $stage
  }
  if ($LASTEXITCODE -ne 0) { throw 'Production dependencies install failed' }
  $isccCandidates = @()
  if ($env:INNO_ISCC_PATH) { $isccCandidates += $env:INNO_ISCC_PATH }
  $onPath = Get-Command ISCC.exe -ErrorAction SilentlyContinue
  if ($onPath) { $isccCandidates += $onPath.Source }
  foreach ($base in @($env:ProgramFiles, ${env:ProgramFiles(x86)}, $env:LOCALAPPDATA)) {
    if ($base) {
      $isccCandidates += (Join-Path $base 'Inno Setup 6\ISCC.exe')
      $isccCandidates += (Join-Path $base 'Programs\Inno Setup 6\ISCC.exe')
    }
  }
  foreach ($regPath in @('HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 6_is1', 'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 6_is1', 'HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 6_is1')) {
    $install = Get-ItemProperty -Path $regPath -ErrorAction SilentlyContinue
    if ($install -and $install.InstallLocation) { $isccCandidates += (Join-Path $install.InstallLocation 'ISCC.exe') }
  }
  $iscc = $isccCandidates | Where-Object { $_ -and (Test-Path -LiteralPath $_ -PathType Leaf) } | Select-Object -First 1
  if (-not $iscc) { throw 'ISCC.exe not found. Set INNO_ISCC_PATH to the full ISCC.exe path and rerun, or compile installer/gsc.iss manually.' }
  Write-Host "Inno Setup compiler: $iscc"
  & $iscc (Join-Path $PSScriptRoot 'gsc.iss')
  if ($LASTEXITCODE -ne 0) { throw 'Installer compilation failed' }
} finally { Pop-Location }
