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

; Full-screen pieces (backdrops, dark overlays, loading covers, letterbox bars): a polygon or texture that spans the
; whole 16:9 layout (world width >= 1900, centred on x 960) is drawn with its x scaled about the centre by the canvas
; factor, so it covers the whole screen instead of stopping at the 16:9 edges. The piece itself is left alone: the
; draw gets a stretched copy of its matrix. No compares (fsel), so the game's condition flags are untouched.
_uwFullK:
.float 0.5
.float 0.0
.float -0.5
.float 100000000.0
.float 960.0
.float 64.0
.float 1900.0
.float 1.0
_uwFullBuf:
.float 0.0
.float 0.0
.float 0.0
.float 0.0
.float 0.0
.float 0.0
.float 0.0
.float 0.0
.float 0.0
.float 0.0
.float 0.0
.float 0.0
.float 0.0
.float 0.0
.float 0.0
.float 0.0

_uwFull:
lwz r11, 0x90(r4)
rlwinm r11, r11, 6, 28, 29
lis r12, _uwFullK@ha
addi r12, r12, _uwFullK@l
lfsx f0, r12, r11
lfs f1, 0xb0(r4)
lfs f2, 0(r4)
lfs f3, 0x30(r4)
fmuls f4, f1, f0
fmadds f4, f2, f4, f3
fmuls f5, f2, f1
fabs f5, f5
lfs f6, 16(r12)
fsubs f4, f4, f6
fabs f4, f4
lfs f7, 20(r12)
fsubs f4, f7, f4
lfs f7, 24(r12)
fsubs f5, f5, f7
lfs f8, 28(r12)
lis r11, _uwFactor@ha
lfs f9, _uwFactor@l(r11)
.uint 0xfd24426e
.uint 0xfd25426e
addi r12, r12, 32
lfs f0, 0(r4)
fmuls f0, f0, f9
stfs f0, 0(r12)
lfs f0, 4(r4)
stfs f0, 4(r12)
lfs f0, 8(r4)
stfs f0, 8(r12)
lfs f0, 12(r4)
stfs f0, 12(r12)
lfs f0, 16(r4)
fmuls f0, f0, f9
stfs f0, 16(r12)
lfs f0, 20(r4)
stfs f0, 20(r12)
lfs f0, 24(r4)
stfs f0, 24(r12)
lfs f0, 28(r4)
stfs f0, 28(r12)
lfs f0, 32(r4)
fmuls f0, f0, f9
stfs f0, 32(r12)
lfs f0, 36(r4)
stfs f0, 36(r12)
lfs f0, 40(r4)
stfs f0, 40(r12)
lfs f0, 44(r4)
stfs f0, 44(r12)
lfs f0, 48(r4)
fsubs f0, f0, f6
fmadds f0, f0, f9, f6
stfs f0, 48(r12)
lfs f0, 52(r4)
stfs f0, 52(r12)
lfs f0, 56(r4)
stfs f0, 56(r12)
lfs f0, 60(r4)
stfs f0, 60(r12)
mr r4, r12
blr

_uwFullPoly:
addi r4, r30, 0x10
b _uwFull

_uwFullTex:
addi r4, r27, 0x10
b _uwFull

_uwFullTset:
addi r4, r29, 0x10
b _uwFull

0x02afb53c = bl _uwFullPoly
0x02afc748 = bl _uwFullTex
0x02afdc60 = bl _uwFullTset

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

; Full-screen pieces (backdrops, dark overlays, loading covers, letterbox bars): a polygon or texture that spans the
; whole 16:9 layout (world width >= 1900, centred on x 960) is drawn with its x scaled about the centre by the canvas
; factor, so it covers the whole screen instead of stopping at the 16:9 edges. The piece itself is left alone: the
; draw gets a stretched copy of its matrix. No compares (fsel), so the game's condition flags are untouched.
_uwFullK:
.float 0.5
.float 0.0
.float -0.5
.float 100000000.0
.float 960.0
.float 64.0
.float 1900.0
.float 1.0
_uwFullBuf:
.float 0.0
.float 0.0
.float 0.0
.float 0.0
.float 0.0
.float 0.0
.float 0.0
.float 0.0
.float 0.0
.float 0.0
.float 0.0
.float 0.0
.float 0.0
.float 0.0
.float 0.0
.float 0.0

_uwFull:
lwz r11, 0x90(r4)
rlwinm r11, r11, 6, 28, 29
lis r12, _uwFullK@ha
addi r12, r12, _uwFullK@l
lfsx f0, r12, r11
lfs f1, 0xb0(r4)
lfs f2, 0(r4)
lfs f3, 0x30(r4)
fmuls f4, f1, f0
fmadds f4, f2, f4, f3
fmuls f5, f2, f1
fabs f5, f5
lfs f6, 16(r12)
fsubs f4, f4, f6
fabs f4, f4
lfs f7, 20(r12)
fsubs f4, f7, f4
lfs f7, 24(r12)
fsubs f5, f5, f7
lfs f8, 28(r12)
lis r11, _uwFactor@ha
lfs f9, _uwFactor@l(r11)
.uint 0xfd24426e
.uint 0xfd25426e
addi r12, r12, 32
lfs f0, 0(r4)
fmuls f0, f0, f9
stfs f0, 0(r12)
lfs f0, 4(r4)
stfs f0, 4(r12)
lfs f0, 8(r4)
stfs f0, 8(r12)
lfs f0, 12(r4)
stfs f0, 12(r12)
lfs f0, 16(r4)
fmuls f0, f0, f9
stfs f0, 16(r12)
lfs f0, 20(r4)
stfs f0, 20(r12)
lfs f0, 24(r4)
stfs f0, 24(r12)
lfs f0, 28(r4)
stfs f0, 28(r12)
lfs f0, 32(r4)
fmuls f0, f0, f9
stfs f0, 32(r12)
lfs f0, 36(r4)
stfs f0, 36(r12)
lfs f0, 40(r4)
stfs f0, 40(r12)
lfs f0, 44(r4)
stfs f0, 44(r12)
lfs f0, 48(r4)
fsubs f0, f0, f6
fmadds f0, f0, f9, f6
stfs f0, 48(r12)
lfs f0, 52(r4)
stfs f0, 52(r12)
lfs f0, 56(r4)
stfs f0, 56(r12)
lfs f0, 60(r4)
stfs f0, 60(r12)
mr r4, r12
blr

_uwFullPoly:
addi r4, r30, 0x10
b _uwFull

_uwFullTex:
addi r4, r27, 0x10
b _uwFull

_uwFullTset:
addi r4, r29, 0x10
b _uwFull

0x02afb4b4 = bl _uwFullPoly
0x02afc6c0 = bl _uwFullTex
0x02afdbd8 = bl _uwFullTset

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

; Full-screen pieces (backdrops, dark overlays, loading covers, letterbox bars): a polygon or texture that spans the
; whole 16:9 layout (world width >= 1900, centred on x 960) is drawn with its x scaled about the centre by the canvas
; factor, so it covers the whole screen instead of stopping at the 16:9 edges. The piece itself is left alone: the
; draw gets a stretched copy of its matrix. No compares (fsel), so the game's condition flags are untouched.
_uwFullK:
.float 0.5
.float 0.0
.float -0.5
.float 100000000.0
.float 960.0
.float 64.0
.float 1900.0
.float 1.0
_uwFullBuf:
.float 0.0
.float 0.0
.float 0.0
.float 0.0
.float 0.0
.float 0.0
.float 0.0
.float 0.0
.float 0.0
.float 0.0
.float 0.0
.float 0.0
.float 0.0
.float 0.0
.float 0.0
.float 0.0

_uwFull:
lwz r11, 0x90(r4)
rlwinm r11, r11, 6, 28, 29
lis r12, _uwFullK@ha
addi r12, r12, _uwFullK@l
lfsx f0, r12, r11
lfs f1, 0xb0(r4)
lfs f2, 0(r4)
lfs f3, 0x30(r4)
fmuls f4, f1, f0
fmadds f4, f2, f4, f3
fmuls f5, f2, f1
fabs f5, f5
lfs f6, 16(r12)
fsubs f4, f4, f6
fabs f4, f4
lfs f7, 20(r12)
fsubs f4, f7, f4
lfs f7, 24(r12)
fsubs f5, f5, f7
lfs f8, 28(r12)
lis r11, _uwFactor@ha
lfs f9, _uwFactor@l(r11)
.uint 0xfd24426e
.uint 0xfd25426e
addi r12, r12, 32
lfs f0, 0(r4)
fmuls f0, f0, f9
stfs f0, 0(r12)
lfs f0, 4(r4)
stfs f0, 4(r12)
lfs f0, 8(r4)
stfs f0, 8(r12)
lfs f0, 12(r4)
stfs f0, 12(r12)
lfs f0, 16(r4)
fmuls f0, f0, f9
stfs f0, 16(r12)
lfs f0, 20(r4)
stfs f0, 20(r12)
lfs f0, 24(r4)
stfs f0, 24(r12)
lfs f0, 28(r4)
stfs f0, 28(r12)
lfs f0, 32(r4)
fmuls f0, f0, f9
stfs f0, 32(r12)
lfs f0, 36(r4)
stfs f0, 36(r12)
lfs f0, 40(r4)
stfs f0, 40(r12)
lfs f0, 44(r4)
stfs f0, 44(r12)
lfs f0, 48(r4)
fsubs f0, f0, f6
fmadds f0, f0, f9, f6
stfs f0, 48(r12)
lfs f0, 52(r4)
stfs f0, 52(r12)
lfs f0, 56(r4)
stfs f0, 56(r12)
lfs f0, 60(r4)
stfs f0, 60(r12)
mr r4, r12
blr

_uwFullPoly:
addi r4, r30, 0x10
b _uwFull

_uwFullTex:
addi r4, r27, 0x10
b _uwFull

_uwFullTset:
addi r4, r29, 0x10
b _uwFull

0x02afae74 = bl _uwFullPoly
0x02afc080 = bl _uwFullTex
0x02afd598 = bl _uwFullTset
