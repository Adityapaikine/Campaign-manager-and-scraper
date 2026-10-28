Option Explicit
Dim files, shell, folder, python, entry
Set files = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")
folder = files.GetParentFolderName(WScript.ScriptFullName)
python = files.BuildPath(folder, "runtime\python\pythonw.exe")
If Not files.FileExists(python) Then python = files.BuildPath(folder, ".venv\Scripts\pythonw.exe")
entry = files.BuildPath(folder, "run.pyw")
shell.CurrentDirectory = folder
shell.Run Chr(34) & python & Chr(34) & " " & Chr(34) & entry & Chr(34), 0, False
