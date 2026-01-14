@echo off
pushd "%~dp0"
py -3 arkite_trigger.py >> arkite_trigger.log 2>&1
popd
