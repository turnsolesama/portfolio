"""Build the small Windows GUI launcher using the installed .NET compiler."""
from pathlib import Path
import os
import subprocess
root=Path(__file__).resolve().parent
compiler=Path(os.environ.get('WINDIR','C:/Windows'))/'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
subprocess.run([str(compiler),'/nologo','/target:winexe','/platform:x64',
                '/reference:System.Windows.Forms.dll','/out:'+str(root/'Codex Switcher.exe'),
                '/win32icon:'+str(root/'switcher.ico'),str(root/'Launcher.cs')],check=True)
print('Built Codex Switcher.exe (Windows GUI, x64)')
