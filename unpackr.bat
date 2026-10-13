@echo off
REM Unpackr launcher - runs from a source checkout
set "PYTHONPATH=%~dp0src;%PYTHONPATH%"
python -m unpackr %*
