@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"
title MH3U Online

rem ===========================================================================
rem  MH3U Online launcher.  First run: mints a UNIQUE random NEX identity and
rem  asks for the host's IP, then starts Cemu.  Later runs: just start Cemu
rem  (the identity persists, so launching Cemu directly works too -- this .bat
rem  is only required the FIRST time).  No Python, no admin, no extra installs.
rem ===========================================================================

rem --- 0) friendly check: is a game dump present? (first-run guidance) --------
set "GAMEDIR=portable\mlc01\usr\title\00050000\10118300"
if not exist "%GAMEDIR%\code" (
    echo(
    echo  [MH3U Online] No MH3U game found in this bundle yet.
    echo  Cemu will still open, but its game list will be empty until you add YOUR
    echo  own legal MH3U dump. Two ways:
    echo    1^) copy your dump into:
    echo         %~dp0%GAMEDIR%
    echo       ^(so the "code", "content" and "meta" folders sit inside 10118300^)
    echo    2^) or in Cemu:  Options ^> General Settings ^> Game Paths ^> add its folder
    echo(
    echo  Press any key to continue...
    pause >nul
)

set "ACTDIR=portable\mlc01\usr\save\system\act\80000001"
set "ACCT=%ACTDIR%\account.dat"
set "SRVFILE=portable\mh3u_server.txt"
set "PLACEHOLDER=PASTE_HOST_IP_HERE"
set "MIID=010001100000d73e030034330100010001000100010001000100640065006600610075006c0074000000000000000100010001000100010001000106010001000100010001000100010001000100010001000100010001000100010001000100"
set "MIIN=00640065006600610075006c00740000000000000000"

rem --- 1) one-time: create OR repair a unique local online identity ----------
rem  Re-mint when account.dat is missing OR is a blank default Cemu account (no
rem  cached online identity). The blank one appears if Cemu was ever launched
rem  before this .bat -- Cemu auto-creates an offline account, and a plain
rem  "if not exist" guard would then leave you stuck Offline forever. We detect a
rem  valid account by its "IsPasswordCacheEnabled=1" line and self-heal otherwise.
set "MAKEACCT="
if not exist "%ACCT%" set "MAKEACCT=new"
rem  /c: (substring) not /x (whole-line): /x misses LF-only files (e.g. make_account.py
rem  output), which would spuriously re-mint a valid account every launch.
if exist "%ACCT%" findstr /c:"IsPasswordCacheEnabled=1" "%ACCT%" >nul 2>nul || set "MAKEACCT=repair"
if "!MAKEACCT!"=="repair" move /y "%ACCT%" "%ACCT%.offline.bak" >nul 2>nul
if defined MAKEACCT (
    echo(
    if "!MAKEACCT!"=="repair" echo  [MH3U Online] Your Cemu account has no online identity yet -- setting one up...
    if "!MAKEACCT!"=="new" echo  [MH3U Online] First run -- creating your unique online identity...
    if not exist "%ACTDIR%" mkdir "%ACTDIR%"
    call :randpid PID
    call :randhex 16 TIB
    call :randhex 32 UUID
    call :randhex 64 APC
    >  "%ACCT%" echo AccountInstance_20120705
    >> "%ACCT%" echo PersistentId=80000001
    >> "%ACCT%" echo TransferableIdBase=!TIB!
    >> "%ACCT%" echo Uuid=!UUID!
    >> "%ACCT%" echo MiiData=!MIID!
    >> "%ACCT%" echo MiiName=!MIIN!
    >> "%ACCT%" echo AccountId=CemuMH3U!PID:~-4!
    >> "%ACCT%" echo BirthYear=0
    >> "%ACCT%" echo BirthMonth=0
    >> "%ACCT%" echo BirthDay=0
    >> "%ACCT%" echo Gender=0
    >> "%ACCT%" echo EmailAddress=
    >> "%ACCT%" echo Country=0
    >> "%ACCT%" echo SimpleAddressId=0
    >> "%ACCT%" echo PrincipalId=!PID!
    >> "%ACCT%" echo IsPasswordCacheEnabled=1
    >> "%ACCT%" echo AccountPasswordCache=!APC!
    echo  [MH3U Online] Identity ready ^(NEX PID !PID!^).
)

rem --- 2) one-time: ask for the host's IP if it's still the placeholder ------
set "SRV="
if exist "%SRVFILE%" set /p SRV=<"%SRVFILE%"
if "!SRV!"=="" set "SRV=%PLACEHOLDER%"
if "!SRV!"=="%PLACEHOLDER%" (
    echo(
    echo  [MH3U Online] Enter the HOST'S IP address.
    echo  Ask the host -- it's their Tailscale 100.x address ^(or their LAN/public IP
    echo  if you're not using Tailscale^).
    set /p SRV=  Host IP:
    > "%SRVFILE%" echo !SRV!
    echo  [MH3U Online] Saved host = !SRV!
)

rem --- 3) launch Cemu (skip with MH3U_NOLAUNCH=1 for setup-only/testing) -----
echo(
echo  [MH3U Online] Host = !SRV!  --  launching Cemu...
if not defined MH3U_NOLAUNCH start "" "Cemu_release.exe"
exit /b 0

rem ===========================================================================
:randpid
rem  8-hex PID starting 4/5/6 -> range 0x40000000-0x6fffffff (~1.07-1.88e9):
rem  huge space, clear of every reserved low PID, fits u32.  Collision within a
rem  4-player room is ~negligible; the server also rejects any duplicate.
setlocal enabledelayedexpansion
set "hi=456"
set /a "h=!random! %% 3"
set "out=!hi:~%h%,1!"
set "hx=0123456789abcdef"
for /l %%i in (1,1,7) do ( set /a "r=!random! %% 16" & for %%r in (!r!) do set "out=!out!!hx:~%%r,1!" )
endlocal & set "%~1=%out%"
exit /b

:randhex
rem  %~1 random lowercase hex chars -> caller var %~2
setlocal enabledelayedexpansion
set "hx=0123456789abcdef"
set "out="
for /l %%i in (1,1,%~1) do ( set /a "r=!random! %% 16" & for %%r in (!r!) do set "out=!out!!hx:~%%r,1!" )
endlocal & set "%~2=%out%"
exit /b
