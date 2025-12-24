@echo off
REM Unpackr launcher - runs from source directory
REM This allows 'unpackr' command to work from the project directory

python "%~dp0unpackr.py" %*
