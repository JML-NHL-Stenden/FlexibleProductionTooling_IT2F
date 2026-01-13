@echo off
pushd "%~dp0"
py -3 arkite_agent.py >> arkite_agent.log 2>&1
popd
