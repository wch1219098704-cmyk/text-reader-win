' 静默启动 text-reader（不弹黑框）
' 需要 pythonw.exe 在 PATH 中；若不在，把下面的 "pythonw.exe" 换成完整路径。
Set fso = CreateObject("Scripting.FileSystemObject")
Set sh = CreateObject("WScript.Shell")
sh.CurrentDirectory = fso.GetParentFolderName(WScript.ScriptFullName)
sh.Run "pythonw.exe text_reader.pyw", 0, False
