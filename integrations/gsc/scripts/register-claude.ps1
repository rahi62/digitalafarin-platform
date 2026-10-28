$ErrorActionPreference = 'Stop'
$script = Join-Path $PSScriptRoot 'register-claude.mjs'
& node $script
if ($LASTEXITCODE -ne 0) { throw "Claude Desktop registration failed; existing configuration preserved." }
