@echo off
REM ==========================================
REM LINE朝刊レポート自動配信 タスクスケジューラ登録
REM ==========================================

REM 管理者権限チェック
NET SESSION >nul 2>&1
IF %ERRORLEVEL% NEQ 0 (
    echo Administrator privileges are required to create a scheduled task.
    echo Right-click on this file and select "Run as administrator".
    echo 管理者権限が必要です。このファイルを右クリックして「管理者として実行」を選択してください。
    pause
    exit /b
)

set TASK_NAME=SectorRotationAutoReporter
set SCRIPT_PATH=G:\マイドライブ\Antigravity\Sector Analysis\sector-rotation-deep\scripts\auto_reporter.py
set WORKING_DIR=G:\マイドライブ\Antigravity\Sector Analysis\sector-rotation-deep
set PYTHON_EXE=python

REM 既存のタスクがあれば削除
schtasks /delete /tn "%TASK_NAME%" /f >nul 2>&1

REM タスクの作成
REM US EST (東部標準時・冬時間 UTC-5) の朝5時は、日本時間 (JST UTC+9) では14時間の時差で 19:00 となります。
schtasks /create /tn "%TASK_NAME%" /tr "%PYTHON_EXE% \"%SCRIPT_PATH%\"" /sc daily /st 19:00 /rl highest /f

IF %ERRORLEVEL% EQU 0 (
    echo.
    echo ==========================================
    echo タスクスケジューラへの登録が完了しました。
    echo 毎日 20:00 (JST) に自動実行されます。
    echo ==========================================
) ELSE (
    echo.
    echo タスクの登録に失敗しました。
)

pause
