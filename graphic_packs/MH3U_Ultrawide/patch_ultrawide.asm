[MH3U_Ultrawide_US_v32]
moduleMatches = 0x9D2F15E5

.origin = codecave

; Camera aspect: the viewport's width / height, scaled to the output shape.
_uwFactor:
.float ($width * $gameHeight) / ($height * $gameWidth)

_uwAspect:
lis r12, _uwFactor@ha
lfs f13, _uwFactor@l(r12)
fmuls f11, f11, f13
stfs f11, 0x38(r23)
b 0x02ba047c

0x02ba0478 = b _uwAspect

; HUD canvas for TV layouts: 1920 wide in the game, now as wide as the output shape.
0x0228caf4 = li r0, ($gameHeight * $width / $height)

; GUI draw: after the viewport / canvas scale, move the 16:9 layout to the centre.
_uwHudOffset:
.float ($gameWidth / 2) * (1 - ($gameWidth * $height) / ($gameHeight * $width))

_uwHud:
fmuls f29, f29, f12
lis r12, _uwHudOffset@ha
lfs f0, _uwHudOffset@l(r12)
fadds f31, f31, f0
b 0x02a72210

0x02a7220c = b _uwHud

; ID sprites (in-quest cockpit: bars, clock, name plate) map 1920x1080 pixels to the screen as x/960 - 1.
; On the TV (draw context +0x1bc screen index 0) squeeze that about the centre like the layouts above.
; In-world markers (NPC speech bubbles, quest icons) don't come through here and stay put.
_uwSprite:
fsubs f6, f9, f31
lwz r12, 0x1bc(r27)
rlwinm r12, r12, 6, 27, 31
cmpwi cr1, r12, 0
.uint 0x40860014
lis r12, _uwSpriteScale@ha
lfs f8, _uwSpriteScale@l(r12)
fmuls f6, f6, f8
b 0x025e2454
b 0x025e2454

_uwSpriteScale:
.float ($gameWidth * $height) / ($gameHeight * $width)

0x025e2450 = b _uwSprite

; In-quest markers above a hunter's head (uIDCockpitAbovehead): the head is projected to a fixed 1920-wide canvas
; as (x/w + 1) * 960 and drawn through the squeezed HUD, which pulled the marker toward the centre.
; Widen the projected x by the camera factor so it lands over the hunter again.
_uwTag:
lis r12, _uwFactor@ha
lfs f9, _uwFactor@l(r12)
fmuls f9, f10, f9
fmadds f7, f9, f12, f0
b 0x025f2f34

0x025f2f30 = b _uwTag

; Hall name tags and NPC speech bubbles (uIDLobbyNpcMsg): one leaf maps each projected point to 1920 x 1080 as
; (x + 1) * 0.5 * 1920, and the squeezed HUD pulled it toward the centre. Same fix: x * factor + 1.
_uwNpc:
lis r12, _uwFactor@ha
lfs f10, _uwFactor@l(r12)
fmadds f9, f7, f10, f12
b 0x026a8f34

0x026a8f30 = b _uwNpc

; In-quest name tags over teammates and their Felyne / Cha-Cha (uIDCockpitSign): two routines project each head and
; map it as (x/w + 1) * 0.5 * 1920. Same fix at both: multiply the projected x by the camera factor first.
_uwSignA:
lis r12, _uwFactor@ha
lfs f0, _uwFactor@l(r12)
fmuls f0, f6, f0
fmadds f7, f0, f3, f12
b 0x026181d0

0x026181cc = b _uwSignA

_uwSignB:
lis r12, _uwFactor@ha
lfs f7, _uwFactor@l(r12)
fmuls f0, f0, f7
fmadds f11, f0, f6, f12
b 0x02618998

0x02618994 = b _uwSignB

[MH3U_Ultrawide_EU_v32]
moduleMatches = 0xADA406E7, 0xA386FAF4, 0x9F1D81A4, 0x913F7DB7

.origin = codecave

; Camera aspect: the viewport's width / height, scaled to the output shape.
_uwFactor:
.float ($width * $gameHeight) / ($height * $gameWidth)

_uwAspect:
lis r12, _uwFactor@ha
lfs f13, _uwFactor@l(r12)
fmuls f11, f11, f13
stfs f11, 0x38(r23)
b 0x02ba03f4

0x02ba03f0 = b _uwAspect

; HUD canvas for TV layouts: 1920 wide in the game, now as wide as the output shape.
0x0228ca6c = li r0, ($gameHeight * $width / $height)

; GUI draw: after the viewport / canvas scale, move the 16:9 layout to the centre.
_uwHudOffset:
.float ($gameWidth / 2) * (1 - ($gameWidth * $height) / ($gameHeight * $width))

_uwHud:
fmuls f29, f29, f12
lis r12, _uwHudOffset@ha
lfs f0, _uwHudOffset@l(r12)
fadds f31, f31, f0
b 0x02a72188

0x02a72184 = b _uwHud

; ID sprites (in-quest cockpit: bars, clock, name plate) map 1920x1080 pixels to the screen as x/960 - 1.
; On the TV (draw context +0x1bc screen index 0) squeeze that about the centre like the layouts above.
; In-world markers (NPC speech bubbles, quest icons) don't come through here and stay put.
_uwSprite:
fsubs f6, f9, f31
lwz r12, 0x1bc(r27)
rlwinm r12, r12, 6, 27, 31
cmpwi cr1, r12, 0
.uint 0x40860014
lis r12, _uwSpriteScale@ha
lfs f8, _uwSpriteScale@l(r12)
fmuls f6, f6, f8
b 0x025e23cc
b 0x025e23cc

_uwSpriteScale:
.float ($gameWidth * $height) / ($gameHeight * $width)

0x025e23c8 = b _uwSprite

; In-quest markers above a hunter's head (uIDCockpitAbovehead): the head is projected to a fixed 1920-wide canvas
; as (x/w + 1) * 960 and drawn through the squeezed HUD, which pulled the marker toward the centre.
; Widen the projected x by the camera factor so it lands over the hunter again.
_uwTag:
lis r12, _uwFactor@ha
lfs f9, _uwFactor@l(r12)
fmuls f9, f10, f9
fmadds f7, f9, f12, f0
b 0x025f2eac

0x025f2ea8 = b _uwTag

; Hall name tags and NPC speech bubbles (uIDLobbyNpcMsg): one leaf maps each projected point to 1920 x 1080 as
; (x + 1) * 0.5 * 1920, and the squeezed HUD pulled it toward the centre. Same fix: x * factor + 1.
_uwNpc:
lis r12, _uwFactor@ha
lfs f10, _uwFactor@l(r12)
fmadds f9, f7, f10, f12
b 0x026a8eac

0x026a8ea8 = b _uwNpc

; In-quest name tags over teammates and their Felyne / Cha-Cha (uIDCockpitSign): two routines project each head and
; map it as (x/w + 1) * 0.5 * 1920. Same fix at both: multiply the projected x by the camera factor first.
_uwSignA:
lis r12, _uwFactor@ha
lfs f0, _uwFactor@l(r12)
fmuls f0, f6, f0
fmadds f7, f0, f3, f12
b 0x02618148

0x02618144 = b _uwSignA

_uwSignB:
lis r12, _uwFactor@ha
lfs f7, _uwFactor@l(r12)
fmuls f0, f0, f7
fmadds f11, f0, f6, f12
b 0x02618910

0x0261890c = b _uwSignB

[MH3U_Ultrawide_JP_v96]
moduleMatches = 0x348600A0

.origin = codecave

; Camera aspect: the viewport's width / height, scaled to the output shape.
_uwFactor:
.float ($width * $gameHeight) / ($height * $gameWidth)

_uwAspect:
lis r12, _uwFactor@ha
lfs f13, _uwFactor@l(r12)
fmuls f11, f11, f13
stfs f11, 0x38(r23)
b 0x02b9fdb4

0x02b9fdb0 = b _uwAspect

; HUD canvas for TV layouts: 1920 wide in the game, now as wide as the output shape.
0x0228cacc = li r0, ($gameHeight * $width / $height)

; GUI draw: after the viewport / canvas scale, move the 16:9 layout to the centre.
_uwHudOffset:
.float ($gameWidth / 2) * (1 - ($gameWidth * $height) / ($gameHeight * $width))

_uwHud:
fmuls f29, f29, f12
lis r12, _uwHudOffset@ha
lfs f0, _uwHudOffset@l(r12)
fadds f31, f31, f0
b 0x02a71b48

0x02a71b44 = b _uwHud

; ID sprites (in-quest cockpit: bars, clock, name plate) map 1920x1080 pixels to the screen as x/960 - 1.
; On the TV (draw context +0x1bc screen index 0) squeeze that about the centre like the layouts above.
; In-world markers (NPC speech bubbles, quest icons) don't come through here and stay put.
_uwSprite:
fsubs f6, f9, f31
lwz r12, 0x1bc(r27)
rlwinm r12, r12, 6, 27, 31
cmpwi cr1, r12, 0
.uint 0x40860014
lis r12, _uwSpriteScale@ha
lfs f8, _uwSpriteScale@l(r12)
fmuls f6, f6, f8
b 0x025e27d4
b 0x025e27d4

_uwSpriteScale:
.float ($gameWidth * $height) / ($gameHeight * $width)

0x025e27d0 = b _uwSprite

; In-quest markers above a hunter's head (uIDCockpitAbovehead): the head is projected to a fixed 1920-wide canvas
; as (x/w + 1) * 960 and drawn through the squeezed HUD, which pulled the marker toward the centre.
; Widen the projected x by the camera factor so it lands over the hunter again.
_uwTag:
lis r12, _uwFactor@ha
lfs f9, _uwFactor@l(r12)
fmuls f9, f10, f9
fmadds f7, f9, f12, f0
b 0x025f32b4

0x025f32b0 = b _uwTag

; Hall name tags and NPC speech bubbles (uIDLobbyNpcMsg): one leaf maps each projected point to 1920 x 1080 as
; (x + 1) * 0.5 * 1920, and the squeezed HUD pulled it toward the centre. Same fix: x * factor + 1.
_uwNpc:
lis r12, _uwFactor@ha
lfs f10, _uwFactor@l(r12)
fmadds f9, f7, f10, f12
b 0x026a9238

0x026a9234 = b _uwNpc

; In-quest name tags over teammates and their Felyne / Cha-Cha (uIDCockpitSign): two routines project each head and
; map it as (x/w + 1) * 0.5 * 1920. Same fix at both: multiply the projected x by the camera factor first.
_uwSignA:
lis r12, _uwFactor@ha
lfs f0, _uwFactor@l(r12)
fmuls f0, f6, f0
fmadds f7, f0, f3, f12
b 0x02618550

0x0261854c = b _uwSignA

_uwSignB:
lis r12, _uwFactor@ha
lfs f7, _uwFactor@l(r12)
fmuls f0, f0, f7
fmadds f11, f0, f6, f12
b 0x02618d18

0x02618d14 = b _uwSignB
