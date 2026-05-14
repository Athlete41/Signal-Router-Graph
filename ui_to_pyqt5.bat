@echo off
setlocal enabledelayedexpansion

echo find .ui files...

for /r %%f in (*.ui) do (
    set "input=%%f"
    set "output=%%~dpnf_ui.py"
    echo compile: "!input!" -> "!output!"
    pyuic5 "!input!" -o "!output!"
    if errorlevel 1 (
        echo error: "!input!"
    ) else (
        echo success: "!output!"
    )
)

echo done.
pause