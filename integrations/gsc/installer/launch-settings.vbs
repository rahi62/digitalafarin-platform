Option Explicit
Dim shell, fso, root, cmd
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
root = fso.GetParentFolderName(WScript.ScriptFullName)
cmd = Chr(34) & root & "\runtime\node.exe" & Chr(34) & " " & Chr(34) & root & "\dist\index.js" & Chr(34) & " settings"
shell.Run cmd, 0, False
WScript.Sleep 1500
shell.Run "http://127.0.0.1:47861/", 1, False
