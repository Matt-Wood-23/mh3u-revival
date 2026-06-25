@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"
title MH3U Online - Host Server

rem ===========================================================================
rem  MH3U Online -- HOST launcher.  Starts the revival server and shows you the
rem  IP your friends type into THEIR launcher.  Auto-detects your Tailscale IP.
rem  Uses server.exe if present (self-contained, no installs); otherwise falls
rem  back to "python server.py" for a source checkout.
rem ===========================================================================

rem --- 1) work out the address friends will connect to -----------------------
set "IP="
for /f "tokens=*" %%a in ('tailscale ip -4 2^>nul') do if not defined IP set "IP=%%a"
if not defined IP if exist "%ProgramFiles%\Tailscale\tailscale.exe" for /f "tokens=*" %%a in ('"%ProgramFiles%\Tailscale\tailscale.exe" ip -4 2^>nul') do if not defined IP set "IP=%%a"

if defined IP goto haveip
echo(
echo  [MH3U Host] Couldn't auto-detect a Tailscale IP.
echo  If you use Tailscale, make sure it's running and signed in. Otherwise type
echo  the IP your friends should use, or just press Enter to host for this PC only.
set /p "IP=  Server IP [blank = 127.0.0.1]: "
if not defined IP set "IP=127.0.0.1"

:haveip
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
