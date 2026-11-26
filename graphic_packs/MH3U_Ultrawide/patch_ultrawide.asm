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

; GUI draw (TV layouts only): after the viewport / canvas scale, move the 16:9 layout to the centre. With the HUD
; preset on Edges, the layouts in the side table (by class: r28 = the uGUI being drawn, its vptr at 0) go to the
; left or right screen edge instead (offset 0 / twice the centring offset). cr0, r0 and r12 are free here.
_uwHudOffC:
.float ($gameWidth / 2) * (1 - ($gameWidth * $height) / ($gameHeight * $width))
_uwHudOffL:
.float ($gameWidth / 2) * (1 - ($gameWidth * $height) / ($gameHeight * $width)) * (1 - $hudEdges)
_uwHudOffR:
.float ($gameWidth / 2) * (1 - ($gameWidth * $height) / ($gameHeight * $width)) * (1 + $hudEdges)
; Region shifts: the HUD hook copies the drawn layout's block (x min, y min, y max, shift) into _uwRgnCur (r9-r11 are
; written before use on both paths after the hook); the piece hook adds the shift to the x of a piece whose centre
; is in the area (the 5th word of _uwRgnCur stays 0). Shift D = the centring offset in layout units (/ the
; squeeze), 0 with the HUD centred.
_uwRgnCur:
.float 0.0
.float 0.0
.float 0.0
.float 0.0
.float 0.0
_uwRgnNone:
.float 0.0
.float 0.0
.float 0.0
.float 0.0
_uwRgnMap:
.float 1480.0
.float -100000.0
.float 540.0
.float 1 * ($gameWidth / 2) * (1 - ($gameWidth * $height) / ($gameHeight * $width)) / (($gameWidth * $height) / ($gameHeight * $width)) * $hudEdges
_uwRgnHint:
.float 1200.0
.float 860.0
.float 100000.0
.float 1 * ($gameWidth / 2) * (1 - ($gameWidth * $height) / ($gameHeight * $width)) / (($gameWidth * $height) / ($gameHeight * $width)) * $hudEdges
_uwRgnWide:
.float 1000.0
.float -100000.0
.float 100000.0
.float 2 * ($gameWidth / 2) * (1 - ($gameWidth * $height) / ($gameHeight * $width)) / (($gameWidth * $height) / ($gameHeight * $width)) * $hudEdges

_uwHud:
fmuls f29, f29, f12
lwz r0, 0(r28)
lis r12, 0x1005
ori r12, r12, 0x2d20
cmpw r0, r12
beq _uwHudR ; uIDCockpitItem
lis r12, 0x1005
ori r12, r12, 0x0284
cmpw r0, r12
beq _uwHudR ; uIDCockpit
lis r12, 0x1005
ori r12, r12, 0x4f54
cmpw r0, r12
beq _uwHudR ; 0x10054f54
lis r12, 0x1005
ori r12, r12, 0xd1bc
cmpw r0, r12
beq _uwHudL ; uIDLobbyDest
lis r12, 0x1005
ori r12, r12, 0x35f4
cmpw r0, r12
beq _uwHudL ; uIDCockpitMess
lis r12, 0x1005
ori r12, r12, 0x5ce4
cmpw r0, r12
beq _uwHudL ; uIDCommonChat
lis r12, 0x1006
ori r12, r12, 0x00b4
cmpw r0, r12
beq _uwHudR ; uIDLobbyPlayerList
lis r12, _uwHudOffC@ha
lfs f0, _uwHudOffC@l(r12)
b _uwHudAdd
_uwHudL:
lis r12, _uwHudOffL@ha
lfs f0, _uwHudOffL@l(r12)
b _uwHudAdd
_uwHudR:
lis r12, _uwHudOffR@ha
lfs f0, _uwHudOffR@l(r12)
_uwHudAdd:
fadds f31, f31, f0
lwz r0, 0(r28)
lis r12, 0x1005
ori r12, r12, 0x4be8
cmpw r0, r12
beq _uwHudRgnMap ; uIDCockpitSign
lis r12, 0x1005
ori r12, r12, 0x3f6c
cmpw r0, r12
beq _uwHudRgnMap ; uIDCockpitMap
lis r12, 0x1005
ori r12, r12, 0x5824
cmpw r0, r12
beq _uwHudRgnHint ; uIDCommonBG
lis r12, 0x1005
ori r12, r12, 0x5ce4
cmpw r0, r12
beq _uwHudRgnWide ; uIDCommonChat
lis r12, _uwRgnNone@ha
addi r12, r12, _uwRgnNone@l
b _uwHudRgnSet
_uwHudRgnMap:
lis r12, _uwRgnMap@ha
addi r12, r12, _uwRgnMap@l
b _uwHudRgnSet
_uwHudRgnHint:
lis r12, _uwRgnHint@ha
addi r12, r12, _uwRgnHint@l
b _uwHudRgnSet
_uwHudRgnWide:
lis r12, _uwRgnWide@ha
addi r12, r12, _uwRgnWide@l
b _uwHudRgnSet
_uwHudRgnSet:
lis r11, _uwRgnCur@ha
addi r11, r11, _uwRgnCur@l
lwz r0, 0(r12)
stw r0, 0(r11)
lwz r0, 4(r12)
stw r0, 4(r11)
lwz r0, 8(r12)
stw r0, 8(r11)
lwz r0, 12(r12)
stw r0, 12(r11)

b 0x02a72210

0x02a7220c = b _uwHud

; ID sprites (the in-quest status block: bars, clock, party plates; also lines, bars and frames of many menus) map
; 1920x1080 pixels to the screen as x/960 - 1. On the TV (owner +0x1bc screen index 0) squeeze that about the
; centre like the layouts above. In-world markers (NPC speech bubbles, quest icons) don't come through here.
; This routine (US 0x025e19a0) has one caller, uDrawIDSprite's draw (US 0x025e46d8), which hands it each sprite
; of the unit with r27 = the screen's draw context (+0x1bc screen index; +0x1b8 low 27 bits = the unit's mPriority,
; written by the caller just before) and the unit's summed mOffset (+0x70/+0x80/+0x90) at its own frame + 0x10
; (our frame's back chain, 0(r1)). The loop transforms the 4 corners in place, so corner 0 (r9 = 0) decides for the
; quad from the raw x of all four and corners 1..3 reuse its factor and shift (x' = x * factor + shift):
;  - as wide as the 16:9 screen (width >= 1900, centre within 64 of 960: the dark layer behind network-mode
;    dialogs) -> factor 1, shift 0 (full screen);
;  - else factor = the squeeze; with the HUD preset on Edges, the in-quest status block goes to the left edge:
;    uIDCockpitMain's units have priority 5 or 7 (menus 0x15, others 0 / 0xf). Priority 5 with a negative offset
;    x (-70 / -86: clock, bars, sharpness, gauges, bottom-left list) -> left; priority 5 with offset 0 is the
;    centred aim overlay (stays). Priority 7 holds the digits by the clock (left) and a gauge at the bottom centre,
;    so there only pieces whose right end is left of x 760 go left.
; Free here: r0, r12, f0, f7-f10, f12, f13 (all reloaded before use; f12 / f13 = the max / min x); cr0 is live, so
; the tests use cr1.
_uwSpriteK:
.float 1920.0
.float 128.0
.float 1900.0
.float ($gameWidth * $height) / ($gameHeight * $width)
.float 1.0
.float 1.0
.float 0.0
.float 0.0
.float 760.0
.float $hudEdges * (1 - ($gameWidth * $height) / ($gameHeight * $width))

_uwSprite:
fsubs f6, f9, f31
lwz r12, 0x1bc(r27)
rlwinm r12, r12, 6, 27, 31
cmpwi cr1, r12, 0
.uint 0x408600fc ; bne cr1, _uwSpriteOut
cmpwi cr1, r9, 0
.uint 0x408600dc ; bne cr1, _uwSpriteApply
lfs f0, 0(r31)
lfs f7, 64(r31)
lfs f8, 128(r31)
lfs f9, 192(r31)
fsubs f10, f0, f7
.uint 0xfd8a382e ; fsel f12, f10, f0, f7
.uint 0xfdaa01ee ; fsel f13, f10, f7, f0
fsubs f10, f8, f9
.uint 0xfc0a4a2e ; fsel f0, f10, f8, f9
.uint 0xfcea426e ; fsel f7, f10, f9, f8
fsubs f10, f12, f0
.uint 0xfd8a032e ; fsel f12, f10, f12, f0
fsubs f10, f13, f7
.uint 0xfdaa69ee ; fsel f13, f10, f7, f13
fsubs f0, f12, f13
fadds f7, f12, f13
lis r12, _uwSpriteK@ha
addi r12, r12, _uwSpriteK@l
lfs f10, 28(r12)
lfs f8, 32(r12)
fsubs f8, f8, f12
lfs f9, 36(r12)
fneg f9, f9
lwz r0, 0x1b8(r27)
clrlwi r0, r0, 5
cmpwi cr1, r0, 7
.uint 0x4086000c ; bne cr1, _uwSpriteP5
.uint 0xfd48526e ; fsel f10, f8, f9, f10
b _uwSpriteSide
_uwSpriteP5:
cmpwi cr1, r0, 5
.uint 0x40860018 ; bne cr1, _uwSpriteSide
lwz r12, 0(r1)
lwz r0, 0x10(r12)
cmpwi cr1, r0, 0
.uint 0x40840008 ; bge cr1, _uwSpriteSide
fmr f10, f9
_uwSpriteSide:
lis r12, _uwSpriteK@ha
addi r12, r12, _uwSpriteK@l
lfs f8, 0(r12)
fsubs f7, f7, f8
fabs f7, f7
lfs f8, 4(r12)
fsubs f7, f8, f7
lfs f8, 8(r12)
fsubs f0, f0, f8
lfs f8, 28(r12)
.uint 0xfd07522e ; fsel f8, f7, f8, f10
.uint 0xfd40522e ; fsel f10, f0, f8, f10
stfs f10, 24(r12)
lfs f9, 12(r12)
lfs f8, 16(r12)
.uint 0xfd074a2e ; fsel f8, f7, f8, f9
.uint 0xfd004a2e ; fsel f8, f0, f8, f9
stfs f8, 20(r12)

_uwSpriteApply:
lis r12, _uwSpriteK@ha
addi r12, r12, _uwSpriteK@l
lfs f8, 20(r12)
lfs f9, 24(r12)
fmadds f6, f6, f8, f9
b 0x025e2454
_uwSpriteOut:
b 0x025e2454

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
; These tags are drawn in uIDCockpitMess's layout, which goes to the left edge with Edges (it also holds the names on
; the party plates). The value here is x/w + 1, later * 0.5 * the TV width (0x02617ce0 with screen 0), so the tag
; gets the centring offset back as a fraction of 960 (0 with the HUD centred; tested: half of it left the tags
; ~160 px short at 2560x1080). f0 is reloaded after both.
_uwTagShift:
.float (1 - ($gameWidth * $height) / ($gameHeight * $width)) / (($gameWidth * $height) / ($gameHeight * $width)) * $hudEdges

_uwSignA:
lis r12, _uwFactor@ha
lfs f0, _uwFactor@l(r12)
fmuls f0, f6, f0
fmadds f7, f0, f3, f12
lis r12, _uwTagShift@ha
lfs f0, _uwTagShift@l(r12)
fadds f7, f7, f0
b 0x026181d0

0x026181cc = b _uwSignA

_uwSignB:
lis r12, _uwFactor@ha
lfs f7, _uwFactor@l(r12)
fmuls f0, f0, f7
fmadds f11, f0, f6, f12
lis r12, _uwTagShift@ha
lfs f0, _uwTagShift@l(r12)
fadds f11, f11, f0
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
.uint 0xfd24426e ; fsel f9, f4, f9, f8
.uint 0xfd25426e ; fsel f9, f5, f9, f8
fmuls f4, f1, f0
fmadds f4, f2, f4, f3
lfs f5, 0x34(r4)
lis r11, _uwRgnCur@ha
addi r11, r11, _uwRgnCur@l
lfs f7, 0(r11)
fsubs f4, f4, f7
lfs f7, 4(r11)
fsubs f1, f5, f7
lfs f7, 8(r11)
fsubs f5, f7, f5
lfs f7, 12(r11)
lfs f8, 16(r11)
.uint 0xfce541ee ; fsel f7, f5, f7, f8
.uint 0xfce141ee ; fsel f7, f1, f7, f8
.uint 0xfce441ee ; fsel f7, f4, f7, f8
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
fadds f0, f0, f7
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

; Text (cGUIObjMessage draw, US 0x02b00c44 `addi r4, r30, 0x10`, the same upload as the pieces): only the region
; shift, no stretch (a message's +0xa0 / +0xc0 aren't a piece's anchor and size). Same registers as the piece hooks
; (cr0 is live for the beq after the site; r3 holds the call's first argument).
_uwMsg:
lfs f4, 0x30(r4)
lfs f5, 0x34(r4)
lis r11, _uwRgnCur@ha
addi r11, r11, _uwRgnCur@l
lfs f7, 0(r11)
fsubs f4, f4, f7
lfs f7, 4(r11)
fsubs f1, f5, f7
lfs f7, 8(r11)
fsubs f5, f7, f5
lfs f7, 12(r11)
lfs f8, 16(r11)
.uint 0xfce541ee ; fsel f7, f5, f7, f8
.uint 0xfce141ee ; fsel f7, f1, f7, f8
.uint 0xfce441ee ; fsel f7, f4, f7, f8
lis r12, _uwFullBuf@ha
addi r12, r12, _uwFullBuf@l
lfs f0, 0(r4)
stfs f0, 0(r12)
lfs f0, 4(r4)
stfs f0, 4(r12)
lfs f0, 8(r4)
stfs f0, 8(r12)
lfs f0, 12(r4)
stfs f0, 12(r12)
lfs f0, 16(r4)
stfs f0, 16(r12)
lfs f0, 20(r4)
stfs f0, 20(r12)
lfs f0, 24(r4)
stfs f0, 24(r12)
lfs f0, 28(r4)
stfs f0, 28(r12)
lfs f0, 32(r4)
stfs f0, 32(r12)
lfs f0, 36(r4)
stfs f0, 36(r12)
lfs f0, 40(r4)
stfs f0, 40(r12)
lfs f0, 44(r4)
stfs f0, 44(r12)
lfs f0, 48(r4)
fadds f0, f0, f7
stfs f0, 48(r12)
lfs f0, 52(r4)
stfs f0, 52(r12)
lfs f0, 56(r4)
stfs f0, 56(r12)
lfs f0, 60(r4)
stfs f0, 60(r12)
mr r4, r12
blr
_uwFullMsg:
addi r4, r30, 0x10
b _uwMsg

0x02b00c44 = bl _uwFullMsg

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

; GUI draw (TV layouts only): after the viewport / canvas scale, move the 16:9 layout to the centre. With the HUD
; preset on Edges, the layouts in the side table (by class: r28 = the uGUI being drawn, its vptr at 0) go to the
; left or right screen edge instead (offset 0 / twice the centring offset). cr0, r0 and r12 are free here.
_uwHudOffC:
.float ($gameWidth / 2) * (1 - ($gameWidth * $height) / ($gameHeight * $width))
_uwHudOffL:
.float ($gameWidth / 2) * (1 - ($gameWidth * $height) / ($gameHeight * $width)) * (1 - $hudEdges)
_uwHudOffR:
.float ($gameWidth / 2) * (1 - ($gameWidth * $height) / ($gameHeight * $width)) * (1 + $hudEdges)
; Region shifts: the HUD hook copies the drawn layout's block (x min, y min, y max, shift) into _uwRgnCur (r9-r11 are
; written before use on both paths after the hook); the piece hook adds the shift to the x of a piece whose centre
; is in the area (the 5th word of _uwRgnCur stays 0). Shift D = the centring offset in layout units (/ the
; squeeze), 0 with the HUD centred.
_uwRgnCur:
.float 0.0
.float 0.0
.float 0.0
.float 0.0
.float 0.0
_uwRgnNone:
.float 0.0
.float 0.0
.float 0.0
.float 0.0
_uwRgnMap:
.float 1480.0
.float -100000.0
.float 540.0
.float 1 * ($gameWidth / 2) * (1 - ($gameWidth * $height) / ($gameHeight * $width)) / (($gameWidth * $height) / ($gameHeight * $width)) * $hudEdges
_uwRgnHint:
.float 1200.0
.float 860.0
.float 100000.0
.float 1 * ($gameWidth / 2) * (1 - ($gameWidth * $height) / ($gameHeight * $width)) / (($gameWidth * $height) / ($gameHeight * $width)) * $hudEdges
_uwRgnWide:
.float 1000.0
.float -100000.0
.float 100000.0
.float 2 * ($gameWidth / 2) * (1 - ($gameWidth * $height) / ($gameHeight * $width)) / (($gameWidth * $height) / ($gameHeight * $width)) * $hudEdges

_uwHud:
fmuls f29, f29, f12
lwz r0, 0(r28)
lis r12, 0x1005
ori r12, r12, 0x2d20
cmpw r0, r12
beq _uwHudR ; uIDCockpitItem
lis r12, 0x1005
ori r12, r12, 0x0284
cmpw r0, r12
beq _uwHudR ; uIDCockpit
lis r12, 0x1005
ori r12, r12, 0x4f54
cmpw r0, r12
beq _uwHudR ; 0x10054f54
lis r12, 0x1005
ori r12, r12, 0xd1bc
cmpw r0, r12
beq _uwHudL ; uIDLobbyDest
lis r12, 0x1005
ori r12, r12, 0x35f4
cmpw r0, r12
beq _uwHudL ; uIDCockpitMess
lis r12, 0x1005
ori r12, r12, 0x5ce4
cmpw r0, r12
beq _uwHudL ; uIDCommonChat
lis r12, 0x1006
ori r12, r12, 0x00b4
cmpw r0, r12
beq _uwHudR ; uIDLobbyPlayerList
lis r12, _uwHudOffC@ha
lfs f0, _uwHudOffC@l(r12)
b _uwHudAdd
_uwHudL:
lis r12, _uwHudOffL@ha
lfs f0, _uwHudOffL@l(r12)
b _uwHudAdd
_uwHudR:
lis r12, _uwHudOffR@ha
lfs f0, _uwHudOffR@l(r12)
_uwHudAdd:
fadds f31, f31, f0
lwz r0, 0(r28)
lis r12, 0x1005
ori r12, r12, 0x4be8
cmpw r0, r12
beq _uwHudRgnMap ; uIDCockpitSign
lis r12, 0x1005
ori r12, r12, 0x3f6c
cmpw r0, r12
beq _uwHudRgnMap ; uIDCockpitMap
lis r12, 0x1005
ori r12, r12, 0x5824
cmpw r0, r12
beq _uwHudRgnHint ; uIDCommonBG
lis r12, 0x1005
ori r12, r12, 0x5ce4
cmpw r0, r12
beq _uwHudRgnWide ; uIDCommonChat
lis r12, _uwRgnNone@ha
addi r12, r12, _uwRgnNone@l
b _uwHudRgnSet
_uwHudRgnMap:
lis r12, _uwRgnMap@ha
addi r12, r12, _uwRgnMap@l
b _uwHudRgnSet
_uwHudRgnHint:
lis r12, _uwRgnHint@ha
addi r12, r12, _uwRgnHint@l
b _uwHudRgnSet
_uwHudRgnWide:
lis r12, _uwRgnWide@ha
addi r12, r12, _uwRgnWide@l
b _uwHudRgnSet
_uwHudRgnSet:
lis r11, _uwRgnCur@ha
addi r11, r11, _uwRgnCur@l
lwz r0, 0(r12)
stw r0, 0(r11)
lwz r0, 4(r12)
stw r0, 4(r11)
lwz r0, 8(r12)
stw r0, 8(r11)
lwz r0, 12(r12)
stw r0, 12(r11)

b 0x02a72188

0x02a72184 = b _uwHud

; ID sprites (the in-quest status block: bars, clock, party plates; also lines, bars and frames of many menus) map
; 1920x1080 pixels to the screen as x/960 - 1. On the TV (owner +0x1bc screen index 0) squeeze that about the
; centre like the layouts above. In-world markers (NPC speech bubbles, quest icons) don't come through here.
; This routine (US 0x025e19a0) has one caller, uDrawIDSprite's draw (US 0x025e46d8), which hands it each sprite
; of the unit with r27 = the screen's draw context (+0x1bc screen index; +0x1b8 low 27 bits = the unit's mPriority,
; written by the caller just before) and the unit's summed mOffset (+0x70/+0x80/+0x90) at its own frame + 0x10
; (our frame's back chain, 0(r1)). The loop transforms the 4 corners in place, so corner 0 (r9 = 0) decides for the
; quad from the raw x of all four and corners 1..3 reuse its factor and shift (x' = x * factor + shift):
;  - as wide as the 16:9 screen (width >= 1900, centre within 64 of 960: the dark layer behind network-mode
;    dialogs) -> factor 1, shift 0 (full screen);
;  - else factor = the squeeze; with the HUD preset on Edges, the in-quest status block goes to the left edge:
;    uIDCockpitMain's units have priority 5 or 7 (menus 0x15, others 0 / 0xf). Priority 5 with a negative offset
;    x (-70 / -86: clock, bars, sharpness, gauges, bottom-left list) -> left; priority 5 with offset 0 is the
;    centred aim overlay (stays). Priority 7 holds the digits by the clock (left) and a gauge at the bottom centre,
;    so there only pieces whose right end is left of x 760 go left.
; Free here: r0, r12, f0, f7-f10, f12, f13 (all reloaded before use; f12 / f13 = the max / min x); cr0 is live, so
; the tests use cr1.
_uwSpriteK:
.float 1920.0
.float 128.0
.float 1900.0
.float ($gameWidth * $height) / ($gameHeight * $width)
.float 1.0
.float 1.0
.float 0.0
.float 0.0
.float 760.0
.float $hudEdges * (1 - ($gameWidth * $height) / ($gameHeight * $width))

_uwSprite:
fsubs f6, f9, f31
lwz r12, 0x1bc(r27)
rlwinm r12, r12, 6, 27, 31
cmpwi cr1, r12, 0
.uint 0x408600fc ; bne cr1, _uwSpriteOut
cmpwi cr1, r9, 0
.uint 0x408600dc ; bne cr1, _uwSpriteApply
lfs f0, 0(r31)
lfs f7, 64(r31)
lfs f8, 128(r31)
lfs f9, 192(r31)
fsubs f10, f0, f7
.uint 0xfd8a382e ; fsel f12, f10, f0, f7
.uint 0xfdaa01ee ; fsel f13, f10, f7, f0
fsubs f10, f8, f9
.uint 0xfc0a4a2e ; fsel f0, f10, f8, f9
.uint 0xfcea426e ; fsel f7, f10, f9, f8
fsubs f10, f12, f0
.uint 0xfd8a032e ; fsel f12, f10, f12, f0
fsubs f10, f13, f7
.uint 0xfdaa69ee ; fsel f13, f10, f7, f13
fsubs f0, f12, f13
fadds f7, f12, f13
lis r12, _uwSpriteK@ha
addi r12, r12, _uwSpriteK@l
lfs f10, 28(r12)
lfs f8, 32(r12)
fsubs f8, f8, f12
lfs f9, 36(r12)
fneg f9, f9
lwz r0, 0x1b8(r27)
clrlwi r0, r0, 5
cmpwi cr1, r0, 7
.uint 0x4086000c ; bne cr1, _uwSpriteP5
.uint 0xfd48526e ; fsel f10, f8, f9, f10
b _uwSpriteSide
_uwSpriteP5:
cmpwi cr1, r0, 5
.uint 0x40860018 ; bne cr1, _uwSpriteSide
lwz r12, 0(r1)
lwz r0, 0x10(r12)
cmpwi cr1, r0, 0
.uint 0x40840008 ; bge cr1, _uwSpriteSide
fmr f10, f9
_uwSpriteSide:
lis r12, _uwSpriteK@ha
addi r12, r12, _uwSpriteK@l
lfs f8, 0(r12)
fsubs f7, f7, f8
fabs f7, f7
lfs f8, 4(r12)
fsubs f7, f8, f7
lfs f8, 8(r12)
fsubs f0, f0, f8
lfs f8, 28(r12)
.uint 0xfd07522e ; fsel f8, f7, f8, f10
.uint 0xfd40522e ; fsel f10, f0, f8, f10
stfs f10, 24(r12)
lfs f9, 12(r12)
lfs f8, 16(r12)
.uint 0xfd074a2e ; fsel f8, f7, f8, f9
.uint 0xfd004a2e ; fsel f8, f0, f8, f9
stfs f8, 20(r12)

_uwSpriteApply:
lis r12, _uwSpriteK@ha
addi r12, r12, _uwSpriteK@l
lfs f8, 20(r12)
lfs f9, 24(r12)
fmadds f6, f6, f8, f9
b 0x025e23cc
_uwSpriteOut:
b 0x025e23cc

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
; These tags are drawn in uIDCockpitMess's layout, which goes to the left edge with Edges (it also holds the names on
; the party plates). The value here is x/w + 1, later * 0.5 * the TV width (0x02617ce0 with screen 0), so the tag
; gets the centring offset back as a fraction of 960 (0 with the HUD centred; tested: half of it left the tags
; ~160 px short at 2560x1080). f0 is reloaded after both.
_uwTagShift:
.float (1 - ($gameWidth * $height) / ($gameHeight * $width)) / (($gameWidth * $height) / ($gameHeight * $width)) * $hudEdges

_uwSignA:
lis r12, _uwFactor@ha
lfs f0, _uwFactor@l(r12)
fmuls f0, f6, f0
fmadds f7, f0, f3, f12
lis r12, _uwTagShift@ha
lfs f0, _uwTagShift@l(r12)
fadds f7, f7, f0
b 0x02618148

0x02618144 = b _uwSignA

_uwSignB:
lis r12, _uwFactor@ha
lfs f7, _uwFactor@l(r12)
fmuls f0, f0, f7
fmadds f11, f0, f6, f12
lis r12, _uwTagShift@ha
lfs f0, _uwTagShift@l(r12)
fadds f11, f11, f0
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
.uint 0xfd24426e ; fsel f9, f4, f9, f8
.uint 0xfd25426e ; fsel f9, f5, f9, f8
fmuls f4, f1, f0
fmadds f4, f2, f4, f3
lfs f5, 0x34(r4)
lis r11, _uwRgnCur@ha
addi r11, r11, _uwRgnCur@l
lfs f7, 0(r11)
fsubs f4, f4, f7
lfs f7, 4(r11)
fsubs f1, f5, f7
lfs f7, 8(r11)
fsubs f5, f7, f5
lfs f7, 12(r11)
lfs f8, 16(r11)
.uint 0xfce541ee ; fsel f7, f5, f7, f8
.uint 0xfce141ee ; fsel f7, f1, f7, f8
.uint 0xfce441ee ; fsel f7, f4, f7, f8
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
fadds f0, f0, f7
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

; Text (cGUIObjMessage draw, US 0x02b00c44 `addi r4, r30, 0x10`, the same upload as the pieces): only the region
; shift, no stretch (a message's +0xa0 / +0xc0 aren't a piece's anchor and size). Same registers as the piece hooks
; (cr0 is live for the beq after the site; r3 holds the call's first argument).
_uwMsg:
lfs f4, 0x30(r4)
lfs f5, 0x34(r4)
lis r11, _uwRgnCur@ha
addi r11, r11, _uwRgnCur@l
lfs f7, 0(r11)
fsubs f4, f4, f7
lfs f7, 4(r11)
fsubs f1, f5, f7
lfs f7, 8(r11)
fsubs f5, f7, f5
lfs f7, 12(r11)
lfs f8, 16(r11)
.uint 0xfce541ee ; fsel f7, f5, f7, f8
.uint 0xfce141ee ; fsel f7, f1, f7, f8
.uint 0xfce441ee ; fsel f7, f4, f7, f8
lis r12, _uwFullBuf@ha
addi r12, r12, _uwFullBuf@l
lfs f0, 0(r4)
stfs f0, 0(r12)
lfs f0, 4(r4)
stfs f0, 4(r12)
lfs f0, 8(r4)
stfs f0, 8(r12)
lfs f0, 12(r4)
stfs f0, 12(r12)
lfs f0, 16(r4)
stfs f0, 16(r12)
lfs f0, 20(r4)
stfs f0, 20(r12)
lfs f0, 24(r4)
stfs f0, 24(r12)
lfs f0, 28(r4)
stfs f0, 28(r12)
lfs f0, 32(r4)
stfs f0, 32(r12)
lfs f0, 36(r4)
stfs f0, 36(r12)
lfs f0, 40(r4)
stfs f0, 40(r12)
lfs f0, 44(r4)
stfs f0, 44(r12)
lfs f0, 48(r4)
fadds f0, f0, f7
stfs f0, 48(r12)
lfs f0, 52(r4)
stfs f0, 52(r12)
lfs f0, 56(r4)
stfs f0, 56(r12)
lfs f0, 60(r4)
stfs f0, 60(r12)
mr r4, r12
blr
_uwFullMsg:
addi r4, r30, 0x10
b _uwMsg

0x02b00bbc = bl _uwFullMsg

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

; GUI draw (TV layouts only): after the viewport / canvas scale, move the 16:9 layout to the centre. With the HUD
; preset on Edges, the layouts in the side table (by class: r28 = the uGUI being drawn, its vptr at 0) go to the
; left or right screen edge instead (offset 0 / twice the centring offset). cr0, r0 and r12 are free here.
_uwHudOffC:
.float ($gameWidth / 2) * (1 - ($gameWidth * $height) / ($gameHeight * $width))
_uwHudOffL:
.float ($gameWidth / 2) * (1 - ($gameWidth * $height) / ($gameHeight * $width)) * (1 - $hudEdges)
_uwHudOffR:
.float ($gameWidth / 2) * (1 - ($gameWidth * $height) / ($gameHeight * $width)) * (1 + $hudEdges)
; Region shifts: the HUD hook copies the drawn layout's block (x min, y min, y max, shift) into _uwRgnCur (r9-r11 are
; written before use on both paths after the hook); the piece hook adds the shift to the x of a piece whose centre
; is in the area (the 5th word of _uwRgnCur stays 0). Shift D = the centring offset in layout units (/ the
; squeeze), 0 with the HUD centred.
_uwRgnCur:
.float 0.0
.float 0.0
.float 0.0
.float 0.0
.float 0.0
_uwRgnNone:
.float 0.0
.float 0.0
.float 0.0
.float 0.0
_uwRgnMap:
.float 1480.0
.float -100000.0
.float 540.0
.float 1 * ($gameWidth / 2) * (1 - ($gameWidth * $height) / ($gameHeight * $width)) / (($gameWidth * $height) / ($gameHeight * $width)) * $hudEdges
_uwRgnHint:
.float 1200.0
.float 860.0
.float 100000.0
.float 1 * ($gameWidth / 2) * (1 - ($gameWidth * $height) / ($gameHeight * $width)) / (($gameWidth * $height) / ($gameHeight * $width)) * $hudEdges
_uwRgnWide:
.float 1000.0
.float -100000.0
.float 100000.0
.float 2 * ($gameWidth / 2) * (1 - ($gameWidth * $height) / ($gameHeight * $width)) / (($gameWidth * $height) / ($gameHeight * $width)) * $hudEdges

_uwHud:
fmuls f29, f29, f12
lwz r0, 0(r28)
lis r12, 0x1005
ori r12, r12, 0x2bc8
cmpw r0, r12
beq _uwHudR ; uIDCockpitItem
lis r12, 0x1005
ori r12, r12, 0x012c
cmpw r0, r12
beq _uwHudR ; uIDCockpit
lis r12, 0x1005
ori r12, r12, 0x4dfc
cmpw r0, r12
beq _uwHudR ; 0x10054f54
lis r12, 0x1005
ori r12, r12, 0xd05c
cmpw r0, r12
beq _uwHudL ; uIDLobbyDest
lis r12, 0x1005
ori r12, r12, 0x349c
cmpw r0, r12
beq _uwHudL ; uIDCockpitMess
lis r12, 0x1005
ori r12, r12, 0x5b8c
cmpw r0, r12
beq _uwHudL ; uIDCommonChat
lis r12, 0x1005
ori r12, r12, 0xff5c
cmpw r0, r12
beq _uwHudR ; uIDLobbyPlayerList
lis r12, _uwHudOffC@ha
lfs f0, _uwHudOffC@l(r12)
b _uwHudAdd
_uwHudL:
lis r12, _uwHudOffL@ha
lfs f0, _uwHudOffL@l(r12)
b _uwHudAdd
_uwHudR:
lis r12, _uwHudOffR@ha
lfs f0, _uwHudOffR@l(r12)
_uwHudAdd:
fadds f31, f31, f0
lwz r0, 0(r28)
lis r12, 0x1005
ori r12, r12, 0x4a90
cmpw r0, r12
beq _uwHudRgnMap ; uIDCockpitSign
lis r12, 0x1005
ori r12, r12, 0x3e14
cmpw r0, r12
beq _uwHudRgnMap ; uIDCockpitMap
lis r12, 0x1005
ori r12, r12, 0x56cc
cmpw r0, r12
beq _uwHudRgnHint ; uIDCommonBG
lis r12, 0x1005
ori r12, r12, 0x5b8c
cmpw r0, r12
beq _uwHudRgnWide ; uIDCommonChat
lis r12, _uwRgnNone@ha
addi r12, r12, _uwRgnNone@l
b _uwHudRgnSet
_uwHudRgnMap:
lis r12, _uwRgnMap@ha
addi r12, r12, _uwRgnMap@l
b _uwHudRgnSet
_uwHudRgnHint:
lis r12, _uwRgnHint@ha
addi r12, r12, _uwRgnHint@l
b _uwHudRgnSet
_uwHudRgnWide:
lis r12, _uwRgnWide@ha
addi r12, r12, _uwRgnWide@l
b _uwHudRgnSet
_uwHudRgnSet:
lis r11, _uwRgnCur@ha
addi r11, r11, _uwRgnCur@l
lwz r0, 0(r12)
stw r0, 0(r11)
lwz r0, 4(r12)
stw r0, 4(r11)
lwz r0, 8(r12)
stw r0, 8(r11)
lwz r0, 12(r12)
stw r0, 12(r11)

b 0x02a71b48

0x02a71b44 = b _uwHud

; ID sprites (the in-quest status block: bars, clock, party plates; also lines, bars and frames of many menus) map
; 1920x1080 pixels to the screen as x/960 - 1. On the TV (owner +0x1bc screen index 0) squeeze that about the
; centre like the layouts above. In-world markers (NPC speech bubbles, quest icons) don't come through here.
; This routine (US 0x025e19a0) has one caller, uDrawIDSprite's draw (US 0x025e46d8), which hands it each sprite
; of the unit with r27 = the screen's draw context (+0x1bc screen index; +0x1b8 low 27 bits = the unit's mPriority,
; written by the caller just before) and the unit's summed mOffset (+0x70/+0x80/+0x90) at its own frame + 0x10
; (our frame's back chain, 0(r1)). The loop transforms the 4 corners in place, so corner 0 (r9 = 0) decides for the
; quad from the raw x of all four and corners 1..3 reuse its factor and shift (x' = x * factor + shift):
;  - as wide as the 16:9 screen (width >= 1900, centre within 64 of 960: the dark layer behind network-mode
;    dialogs) -> factor 1, shift 0 (full screen);
;  - else factor = the squeeze; with the HUD preset on Edges, the in-quest status block goes to the left edge:
;    uIDCockpitMain's units have priority 5 or 7 (menus 0x15, others 0 / 0xf). Priority 5 with a negative offset
;    x (-70 / -86: clock, bars, sharpness, gauges, bottom-left list) -> left; priority 5 with offset 0 is the
;    centred aim overlay (stays). Priority 7 holds the digits by the clock (left) and a gauge at the bottom centre,
;    so there only pieces whose right end is left of x 760 go left.
; Free here: r0, r12, f0, f7-f10, f12, f13 (all reloaded before use; f12 / f13 = the max / min x); cr0 is live, so
; the tests use cr1.
_uwSpriteK:
.float 1920.0
.float 128.0
.float 1900.0
.float ($gameWidth * $height) / ($gameHeight * $width)
.float 1.0
.float 1.0
.float 0.0
.float 0.0
.float 760.0
.float $hudEdges * (1 - ($gameWidth * $height) / ($gameHeight * $width))

_uwSprite:
fsubs f6, f9, f31
lwz r12, 0x1bc(r27)
rlwinm r12, r12, 6, 27, 31
cmpwi cr1, r12, 0
.uint 0x408600fc ; bne cr1, _uwSpriteOut
cmpwi cr1, r9, 0
.uint 0x408600dc ; bne cr1, _uwSpriteApply
lfs f0, 0(r31)
lfs f7, 64(r31)
lfs f8, 128(r31)
lfs f9, 192(r31)
fsubs f10, f0, f7
.uint 0xfd8a382e ; fsel f12, f10, f0, f7
.uint 0xfdaa01ee ; fsel f13, f10, f7, f0
fsubs f10, f8, f9
.uint 0xfc0a4a2e ; fsel f0, f10, f8, f9
.uint 0xfcea426e ; fsel f7, f10, f9, f8
fsubs f10, f12, f0
.uint 0xfd8a032e ; fsel f12, f10, f12, f0
fsubs f10, f13, f7
.uint 0xfdaa69ee ; fsel f13, f10, f7, f13
fsubs f0, f12, f13
fadds f7, f12, f13
lis r12, _uwSpriteK@ha
addi r12, r12, _uwSpriteK@l
lfs f10, 28(r12)
lfs f8, 32(r12)
fsubs f8, f8, f12
lfs f9, 36(r12)
fneg f9, f9
lwz r0, 0x1b8(r27)
clrlwi r0, r0, 5
cmpwi cr1, r0, 7
.uint 0x4086000c ; bne cr1, _uwSpriteP5
.uint 0xfd48526e ; fsel f10, f8, f9, f10
b _uwSpriteSide
_uwSpriteP5:
cmpwi cr1, r0, 5
.uint 0x40860018 ; bne cr1, _uwSpriteSide
lwz r12, 0(r1)
lwz r0, 0x10(r12)
cmpwi cr1, r0, 0
.uint 0x40840008 ; bge cr1, _uwSpriteSide
fmr f10, f9
_uwSpriteSide:
lis r12, _uwSpriteK@ha
addi r12, r12, _uwSpriteK@l
lfs f8, 0(r12)
fsubs f7, f7, f8
fabs f7, f7
lfs f8, 4(r12)
fsubs f7, f8, f7
lfs f8, 8(r12)
fsubs f0, f0, f8
lfs f8, 28(r12)
.uint 0xfd07522e ; fsel f8, f7, f8, f10
.uint 0xfd40522e ; fsel f10, f0, f8, f10
stfs f10, 24(r12)
lfs f9, 12(r12)
lfs f8, 16(r12)
.uint 0xfd074a2e ; fsel f8, f7, f8, f9
.uint 0xfd004a2e ; fsel f8, f0, f8, f9
stfs f8, 20(r12)

_uwSpriteApply:
lis r12, _uwSpriteK@ha
addi r12, r12, _uwSpriteK@l
lfs f8, 20(r12)
lfs f9, 24(r12)
fmadds f6, f6, f8, f9
b 0x025e27d4
_uwSpriteOut:
b 0x025e27d4

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
; These tags are drawn in uIDCockpitMess's layout, which goes to the left edge with Edges (it also holds the names on
; the party plates). The value here is x/w + 1, later * 0.5 * the TV width (0x02617ce0 with screen 0), so the tag
; gets the centring offset back as a fraction of 960 (0 with the HUD centred; tested: half of it left the tags
; ~160 px short at 2560x1080). f0 is reloaded after both.
_uwTagShift:
.float (1 - ($gameWidth * $height) / ($gameHeight * $width)) / (($gameWidth * $height) / ($gameHeight * $width)) * $hudEdges

_uwSignA:
lis r12, _uwFactor@ha
lfs f0, _uwFactor@l(r12)
fmuls f0, f6, f0
fmadds f7, f0, f3, f12
lis r12, _uwTagShift@ha
lfs f0, _uwTagShift@l(r12)
fadds f7, f7, f0
b 0x02618550

0x0261854c = b _uwSignA

_uwSignB:
lis r12, _uwFactor@ha
lfs f7, _uwFactor@l(r12)
fmuls f0, f0, f7
fmadds f11, f0, f6, f12
lis r12, _uwTagShift@ha
lfs f0, _uwTagShift@l(r12)
fadds f11, f11, f0
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
.uint 0xfd24426e ; fsel f9, f4, f9, f8
.uint 0xfd25426e ; fsel f9, f5, f9, f8
fmuls f4, f1, f0
fmadds f4, f2, f4, f3
lfs f5, 0x34(r4)
lis r11, _uwRgnCur@ha
addi r11, r11, _uwRgnCur@l
lfs f7, 0(r11)
fsubs f4, f4, f7
lfs f7, 4(r11)
fsubs f1, f5, f7
lfs f7, 8(r11)
fsubs f5, f7, f5
lfs f7, 12(r11)
lfs f8, 16(r11)
.uint 0xfce541ee ; fsel f7, f5, f7, f8
.uint 0xfce141ee ; fsel f7, f1, f7, f8
.uint 0xfce441ee ; fsel f7, f4, f7, f8
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
fadds f0, f0, f7
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

; Text (cGUIObjMessage draw, US 0x02b00c44 `addi r4, r30, 0x10`, the same upload as the pieces): only the region
; shift, no stretch (a message's +0xa0 / +0xc0 aren't a piece's anchor and size). Same registers as the piece hooks
; (cr0 is live for the beq after the site; r3 holds the call's first argument).
_uwMsg:
lfs f4, 0x30(r4)
lfs f5, 0x34(r4)
lis r11, _uwRgnCur@ha
addi r11, r11, _uwRgnCur@l
lfs f7, 0(r11)
fsubs f4, f4, f7
lfs f7, 4(r11)
fsubs f1, f5, f7
lfs f7, 8(r11)
fsubs f5, f7, f5
lfs f7, 12(r11)
lfs f8, 16(r11)
.uint 0xfce541ee ; fsel f7, f5, f7, f8
.uint 0xfce141ee ; fsel f7, f1, f7, f8
.uint 0xfce441ee ; fsel f7, f4, f7, f8
lis r12, _uwFullBuf@ha
addi r12, r12, _uwFullBuf@l
lfs f0, 0(r4)
stfs f0, 0(r12)
lfs f0, 4(r4)
stfs f0, 4(r12)
lfs f0, 8(r4)
stfs f0, 8(r12)
lfs f0, 12(r4)
stfs f0, 12(r12)
lfs f0, 16(r4)
stfs f0, 16(r12)
lfs f0, 20(r4)
stfs f0, 20(r12)
lfs f0, 24(r4)
stfs f0, 24(r12)
lfs f0, 28(r4)
stfs f0, 28(r12)
lfs f0, 32(r4)
stfs f0, 32(r12)
lfs f0, 36(r4)
stfs f0, 36(r12)
lfs f0, 40(r4)
stfs f0, 40(r12)
lfs f0, 44(r4)
stfs f0, 44(r12)
lfs f0, 48(r4)
fadds f0, f0, f7
stfs f0, 48(r12)
lfs f0, 52(r4)
stfs f0, 52(r12)
lfs f0, 56(r4)
stfs f0, 56(r12)
lfs f0, 60(r4)
stfs f0, 60(r12)
mr r4, r12
blr
_uwFullMsg:
addi r4, r30, 0x10
b _uwMsg

0x02b0057c = bl _uwFullMsg
