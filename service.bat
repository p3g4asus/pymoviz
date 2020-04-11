call %~dp0venv\Scripts\activate.bat
set PATH=C:\Program Files\Java\jre1.8.0_231\bin\server;%PATH%
set KCFG_KIVY_LOG_LEVEL=debug
set KCFG_KIVY_LOG_ENABLE=1
set KCFG_KIVY_LOG_DIR=%~dp0logs
pushd %~dp0src
python -m service --db_fname "%~dp0maindb.db" --ab_portlisten 10002 --ab_hostlisten 192.168.25.57 --ab_portconnect 10001 --ab_hostconnect 192.168.25.24 --verbose DEBUG
pause
