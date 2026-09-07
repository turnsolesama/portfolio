@echo off
chcp 65001 >nul
title AI Hub - AI 资产管理终端
cd /d "%~dp0"

where py >nul 2>nul && (set PY=py -3) || (set PY=python)

echo ============================================
echo   AI Hub · AI 资产管理终端
echo   数据目录: %~dp0data
echo ============================================
%PY% server.py serve --open
pause
