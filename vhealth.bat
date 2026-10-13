@echo off
REM Video health checker launcher for a source checkout
set "PYTHONPATH=%~dp0src;%PYTHONPATH%"
python -m unpackr.vhealth %*
