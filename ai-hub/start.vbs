Option Explicit
Dim shell, fso, folder, launcher, command, result, runtime, argument
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
folder = fso.GetParentFolderName(WScript.ScriptFullName)
launcher = fso.BuildPath(folder, "launcher.pyw")
shell.CurrentDirectory = folder
runtime = ""
If RuntimeWorks("py -3") Then
    runtime = "py -3"
ElseIf RuntimeWorks("python") Then
    runtime = "python"
End If
If runtime = "" Then
    MsgBox "Python 3.9 or later could not be found. Please use debug.bat to inspect the environment.", 16, "AI Hub"
    WScript.Quit 1
End If
If WScript.Arguments.Count > 0 Then
    If WScript.Arguments(0) = "--check" Then
        WScript.Echo runtime
        WScript.Quit 0
    End If
End If
command = runtime & " " & Chr(34) & launcher & Chr(34)
For Each argument In WScript.Arguments
    If argument = "--no-browser" Or argument = "--no-dialog" Then
        command = command & " " & argument
    End If
Next
result = shell.Run(command, 0, True)
WScript.Quit result

Function RuntimeWorks(prefix)
    Dim exitCode
    On Error Resume Next
    Err.Clear
    exitCode = shell.Run(prefix & " -c " & Chr(34) & "import sys; sys.exit(sys.version_info < (3, 9))" & Chr(34), 0, True)
    RuntimeWorks = (Err.Number = 0 And exitCode = 0)
    On Error GoTo 0
End Function
