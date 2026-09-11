@echo off
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -STA -ExecutionPolicy Bypass -WindowStyle Hidden -File "%~dp0ProxySwitch.ps1"
if errorlevel 1 (
  echo Unable to open ProxySwitch. Keep all files in the same folder.
  pause
)
