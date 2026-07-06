@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"
title MH3U Online - Host Server

rem ===========================================================================
rem  MH3U Online -- HOST launcher.  Starts the revival server and shows you the
rem  IP your friends type into THEIR launcher.  Detects Radmin VPN (26.x) and
rem  Tailscale (100.x) addresses but ALWAYS asks -- it never silently picks one
rem  (a PC can have both installed while friends are on the other overlay).
rem  Uses server.exe if present (self-contained, no installs); otherwise falls
rem  back to "python server.py" for a source checkout.
rem ===========================================================================

rem --- 1) work out the address friends will connect to -----------------------
set "IP="
set "TSIP="
set "RVIP="
for /f "tokens=*" %%a in ('tailscale ip -4 2^>nul') do if not defined TSIP set "TSIP=%%a"
if not defined TSIP if exist "%ProgramFiles%\Tailscale\tailscale.exe" for /f "tokens=*" %%a in ('"%ProgramFiles%\Tailscale\tailscale.exe" ip -4 2^>nul') do if not defined TSIP set "TSIP=%%a"
for /f "usebackq tokens=*" %%a in (`powershell -NoProfile -Command "(Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue | Where-Object {$_.IPAddress -like '26.*'} | Select-Object -First 1).IPAddress" 2^>nul`) do if not defined RVIP set "RVIP=%%a"

rem  Enter-default: Radmin if present, else Tailscale, else host-only loopback.
set "DEFIP=127.0.0.1"
set "DEFSRC=this PC only"
if defined TSIP set "DEFIP=%TSIP%"
if defined TSIP set "DEFSRC=Tailscale"
if defined RVIP set "DEFIP=%RVIP%"
if defined RVIP set "DEFSRC=Radmin VPN"

echo(
echo  [MH3U Host] Which IP will your friends connect to?
if defined RVIP echo    Radmin VPN detected:  %RVIP%
if defined TSIP echo    Tailscale detected:   %TSIP%
if not defined RVIP if not defined TSIP echo    No overlay VPN detected on this PC.
echo    You can also type any other IP - public / port-forward / LAN.
echo(
set /p "IP=  Server IP  [Enter = %DEFIP% - %DEFSRC%]: "
if not defined IP set "IP=%DEFIP%"
echo(
echo  ===========================================================================
echo     MH3U ONLINE SERVER
echo(
echo     Friends connect to:   !IP!
echo     they paste this into PLAY MH3U ONLINE.bat when it asks for the host IP
echo  ===========================================================================
echo(
echo  Keep this window OPEN while you play. Closing it stops the server.
echo(

set "MH3U_ADVERTISE=!IP!"

rem --- 2) start the server (frozen exe preferred, python source fallback) -----
rem  goto-based (no parenthesised blocks) so stray punctuation can't break parsing.
if exist "server.exe" goto runexe
if exist "server.py" goto runpy
echo  [MH3U Host] ERROR: neither server.exe nor server.py was found next to this file.
echo  Put HOST_MH3U.bat in the same folder as server.exe.
goto done

:runexe
"server.exe"
goto done

:runpy
where py >nul 2>nul && py server.py || python server.py
goto done

:done
echo(
echo  [MH3U Host] Server stopped. Press any key to close.
pause >nul
