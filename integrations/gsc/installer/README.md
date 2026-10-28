# Windows installer (personal preview)

Build on **Windows x64** with Node.js 20+ and Inno Setup 6 installed:

```powershell
cd integrations/gsc
powershell -NoProfile -ExecutionPolicy Bypass -File installer/build-windows.ps1
```

Expected output: `installer/output/DigitalAfarin-GSC-Setup.exe`.

The build runs `npm ci`, TypeScript validation, build, and tests before staging the app. The installer includes the current Windows Node runtime and production dependencies, so the user does not need to run npm afterward.

Installer behavior:
- Per-user install (no administrator elevation), Start Menu shortcut opens browser-based settings.
- Optional **unchecked** task registers/updates the `digitalafarin-gsc` MCP entry in Claude Desktop. The registration script creates a backup and preserves other entries. If the Claude profile is ambiguous, use its documented `CLAUDE_CONFIG_PATH` setting manually.
- Existing OAuth tokens remain at `%LOCALAPPDATA%\DigitalAfarin\GSC\accounts.json` and are DPAPI protected.
- Uninstall intentionally preserves accounts and does not remove Claude config to avoid deleting unrelated entries.
- Stop Claude Desktop and the settings process before upgrading. Installer validation and smoke testing must be done on a Windows machine.

Important: This is a build recipe, **not yet a compiled or Windows-tested executable**. Never commit OAuth credentials or `installer/stage`, `installer/output` folders.
