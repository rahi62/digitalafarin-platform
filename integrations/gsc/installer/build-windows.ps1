# Run on Windows with Node.js >=20 and Inno Setup 6 installed.
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$stage = Join-Path $PSScriptRoot 'stage'
$node = (Get-Command node.exe -ErrorAction Stop).Source
$nodeVersion = (& $node -p "process.versions.node").Trim()
if ([int]($nodeVersion.Split('.')[0]) -lt 20) { throw 'Node.js 20+ required' }
Push-Location $root
try {
  & npm.cmd ci
  if ($LASTEXITCODE -ne 0) { throw 'npm ci failed' }
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
  & npm.cmd ci --omit=dev --ignore-scripts --prefix $stage
  if ($LASTEXITCODE -ne 0) { throw 'Production dependencies install failed' }
  $iscc = (Get-Command ISCC.exe -ErrorAction SilentlyContinue).Source
  if (-not $iscc) {
    $iscc = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
  }
  if (-not (Test-Path $iscc)) { throw 'Inno Setup 6 ISCC.exe not found (stage prepared, installer not built)' }
  & $iscc (Join-Path $PSScriptRoot 'gsc.iss')
  if ($LASTEXITCODE -ne 0) { throw 'Installer compilation failed' }
} finally { Pop-Location }
