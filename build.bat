@echo off
if exist .\dist\Last.presence.exe (
    del .\dist\Last.presence.exe
)

@echo on
python -m venv venv
call .\venv\Scripts\activate.bat
pip install -r requirements.txt
pyinstaller main.pyw --onefile --name Last.presence --copy-metadata pylast -i "assets/icon.ico" --add-data "assets/icon.ico;."


@echo off
echo.
echo.
if exist .\dist\Last.presence.exe (
    echo Last.presence was sucessfully built on ./dist/Last.presence.exe
) else (
    echo Something went wrong, look through the errors above.
)

pause