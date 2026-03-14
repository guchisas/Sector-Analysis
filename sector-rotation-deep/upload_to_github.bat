@echo off
REM ==========================================
REM GitHub Actions 隠しフォルダ (.github) 自動アップロードツール
REM ==========================================

echo [1/3] ファイルの変更を検出しています...
git add .
IF %ERRORLEVEL% NEQ 0 (
    echo.
    echo ⚠️ Gitコマンドが見つかりませんでした。
    echo GitHub Desktop 等をご利用の場合は、GitHub Desktopの画面を開くと
    echo 「.github」フォルダの変更が検知されているはずですので、
    echo そちらから通常通り「Commit」して「Push」をお願いします！
    pause
    exit /b
)

echo [2/3] 変更を確定 (Commit) しています...
git commit -m "Add GitHub Actions Auto Reporter"

echo [3/3] GitHubへアップロード (Push) しています...
git push

IF %ERRORLEVEL% EQU 0 (
    echo.
    echo ==========================================
    echo ✅ アップロードが成功しました！
    echo GitHubの「Actions」タブをリロードして確認してください。
    echo ==========================================
) ELSE (
    echo.
    echo ⚠️ アップロードに失敗しました。
)

pause
