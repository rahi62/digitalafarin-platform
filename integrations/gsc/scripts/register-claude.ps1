param()
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$entry = Join-Path $root 'dist\index.js'
if (!(Test-Path $entry)) { throw 'Build missing. Run npm run build in integrations/gsc first.' }
$configDir = Join-Path $env:APPDATA 'Claude'
if (!(Test-Path $configDir)) { New-Item -ItemType Directory -Path $configDir -Force | Out-Null }
$configFile = Join-Path $configDir 'claude_desktop_config.json'
$nodePath = (Get-Command node -ErrorAction Stop).Source
if (Test-Path $configFile) {
  $raw = Get-Content -Raw -Encoding UTF8 $configFile
  try { $config = ConvertFrom-Json -InputObject $raw -AsHashtable } catch {
    throw 'Claude config is not valid JSON. No changes made.'
  }
  $backup = "$configFile.bak-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
  Copy-Item $configFile $backup
  Write-Host "Backup: $backup"
} else {
  $config = @{}
}
if (-not $config.ContainsKey('mcpServers') -or $null -eq $config.mcpServers) { $config.mcpServers = @{} }
if ($config.mcpServers -isnot [System.Collections.IDictionary]) { throw 'mcpServers must be an object; no changes made.' }
# Do not replace existing connectors; only set the dedicated new GSC entry.
$config.mcpServers['digitalafarin-gsc'] = @{ command = $nodePath; args = @($entry) }
$json = ConvertTo-Json -InputObject $config -Depth 64
$temp = "$configFile.tmp"
[System.IO.File]::WriteAllText($temp, $json, [System.Text.UTF8Encoding]::new($false))
Move-Item -LiteralPath $temp -Destination $configFile -Force
Write-Host 'DigitalAfarin GSC added. Existing Claude MCP entries preserved. Restart Claude Desktop.'
