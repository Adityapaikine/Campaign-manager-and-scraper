Option Explicit
Dim files, shell, folder, python, entry
Set files = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")
folder = files.GetParentFolderName(WScript.ScriptFullName)
python = files.BuildPath(folder, "runtime\python\pythonw.exe")
If Not files.FileExists(python) Then python = files.BuildPath(folder, ".venv\Scripts\pythonw.exe")
entry = files.BuildPath(folder, "run.pyw")
If Not files.FileExists(python) Then
    MsgBox "The Python runtime is missing. Copy the entire portable folder, or run Setup_Combined.bat for a source-only copy.", 48, "Lead Workspace setup"
    WScript.Quit 1
End If
shell.CurrentDirectory = folder
shell.Run Chr(34) & python & Chr(34) & " " & Chr(34) & entry & Chr(34), 0, False
