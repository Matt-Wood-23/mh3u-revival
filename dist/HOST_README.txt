============================================================
 MH3U ONLINE - HOST ADD-ON
============================================================

This little add-on lets YOU host a game for your friends. It's just the
server (server.exe) plus a one-click launcher (HOST_MH3U.bat). No Python,
no installs - server.exe is fully self-contained.

You still play through the normal MH3U Online bundle; this only adds the
"be the host" part.

------------------------------------------------------------
 TO HOST A GAME
------------------------------------------------------------

1. Put HOST_MH3U.bat and server.exe together in one folder. Easiest spot:
   right inside your MH3U Online bundle folder (next to PLAY MH3U ONLINE.bat).

2. Make sure your overlay VPN is running and signed in - Tailscale or Radmin
   VPN (the recommended way for friends to reach you). LAN/public IP also
   works if you know what you're doing.

3. Double-click  HOST_MH3U.bat
   - It prints the IP your friends connect to (your Tailscale 100.x address;
     on Radmin VPN, enter your 26.x address at the prompt instead).
   - KEEP THIS WINDOW OPEN while you play. Closing it stops the server.

4. Now start the game yourself: run  PLAY MH3U ONLINE.bat  (from the bundle).
   When it asks for the host IP, type:  127.0.0.1
   (you're on the same PC as the server, so loopback is correct).

5. Tell your friends the IP from step 3. They run THEIR
   PLAY MH3U ONLINE.bat and paste that IP when asked.

------------------------------------------------------------
 NOTES
------------------------------------------------------------

* Windows / SmartScreen may flag server.exe as "unrecognized" - that's
  normal for a custom unsigned build (same as the Cemu build). It is the
  same server you can see the source for at:
  https://github.com/Matt-Wood-23/mh3u-revival

* First launch can take a second or two while it unpacks itself - that's
  expected for a single-file program.

* Friends having trouble connecting? 99% of the time it's the overlay VPN
  link, not the server. On Tailscale, have them run  tailscale ping <your
  100.x IP>  and confirm "pong"; on Radmin, have them  ping <your 26.x IP>.
  Everyone must be on the SAME overlay as the host.
