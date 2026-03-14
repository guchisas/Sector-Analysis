@echo off
REM ==========================================
REM LINE朝刊レポート スリープ解除設定の追加
REM ==========================================

REM 管理者権限チェック
NET SESSION >nul 2>&1
IF %ERRORLEVEL% NEQ 0 (
    echo Administrator privileges are required to modify the scheduled task.
    echo Right-click on this file and select "Run as administrator".
    echo 管理者権限が必要です。このファイルを右クリックして「管理者として実行」を選択してください。
    pause
    exit /b
)

set TASK_NAME=SectorRotationAutoReporter
set XML_FILE="%TEMP%\UpdateTask.xml"

echo 現在の設定を読み込んでいます...
schtasks /query /tn "%TASK_NAME%" /xml > %XML_FILE% 2>nul
IF %ERRORLEVEL% NEQ 0 (
    echo タスク "%TASK_NAME%" が見つかりませんでした。
    echo 先に setup_task.bat でタスクを作成してください。
    pause
    exit /b
)

echo スリープ解除設定を追加しています...
REM PowerShell を使って XML 内の <WakeToRun>false</WakeToRun> を true に書き換える
powershell -Command "(Get-Content '%TEMP%\UpdateTask.xml') -replace '<WakeToRun>false</WakeToRun>', '<WakeToRun>true</WakeToRun>' | Set-Content '%TEMP%\UpdateTask.xml'"

echo タスクの設定を更新しています...
schtasks /create /tn "%TASK_NAME%" /xml %XML_FILE% /f

IF %ERRORLEVEL% EQU 0 (
    echo.
    echo ==========================================
    echo スリープ解除の設定が完了しました！
    echo 19:00になると自動でスリープから復帰してLINEが送信されます。
    echo ==========================================
) ELSE (
    echo.
    echo タスクの更新に失敗しました。
)

del %XML_FILE%
pause
