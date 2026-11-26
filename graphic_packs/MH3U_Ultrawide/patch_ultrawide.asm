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
