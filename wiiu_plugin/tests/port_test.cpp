// Host-side test for the port editor in src/main.cpp.
//
// The code under test is NOT copied here. tests/run_port_test.sh pulls the
// block between the "port-editor-core" markers out of main.cpp into
// build/port_core.inc, so this always tests the code that ships. The only
// stand-ins are the few WUPS names that block uses.
//
// Run (inside the plugin's Docker image, or anywhere with g++):
//   sh tests/run_port_test.sh

#include <cstdint>
#include <cstdio>
#include <cstring>

#define DEFAULT_PORT 1223

enum {
    WUPS_CONFIG_BUTTON_LEFT  = (1 << 0),
    WUPS_CONFIG_BUTTON_RIGHT = (1 << 1),
    WUPS_CONFIG_BUTTON_UP    = (1 << 2),
    WUPS_CONFIG_BUTTON_DOWN  = (1 << 3),
    WUPS_CONFIG_BUTTON_A     = (1 << 4),
    WUPS_CONFIG_BUTTON_B     = (1 << 5),
};
typedef struct {
    uint32_t buttons_h;
    uint32_t buttons_d;
    uint32_t buttons_r;
} WUPSConfigSimplePadData;

#include "port_core.inc"

static int failures = 0;

#define CHECK(cond, ...)                                     \
    do {                                                     \
        if (!(cond)) {                                       \
            failures++;                                      \
            printf("FAIL %s:%d: ", __FILE__, __LINE__);      \
            printf(__VA_ARGS__);                             \
            printf("\n");                                    \
        }                                                    \
    } while (0)

static PortItem makeItem(uint32_t v) {
    PortItem it;
    it.value           = v;
    it.valueAtCreation = v;
    it.valueBeforeEdit = v;
    it.cursor          = -1;
    it.frameTimer      = 0;
    return it;
}

// One menu frame. `held` = buttons down this frame, `prevHeld` = last frame,
// so buttons_d (newly pressed) is derived the same way the menu derives it.
static void frame(PortItem *it, uint32_t held, uint32_t prevHeld) {
    WUPSConfigSimplePadData in;
    in.buttons_h = held;
    in.buttons_d = held & ~prevHeld;
    in.buttons_r = prevHeld & ~held;
    portOnInput(it, in);
}

static void press(PortItem *it, uint32_t button) {
    frame(it, button, 0);
    frame(it, 0, button);
}

static void hold(PortItem *it, uint32_t button, int frames) {
    uint32_t prev = 0;
    for (int i = 0; i < frames; i++) {
        frame(it, button, prev);
        prev = button;
    }
    frame(it, 0, prev);
}

static void render(const PortItem *it, bool selected, char *out) {
    if (selected) {
        portGetSelectedDisplay((void *) it, out, 64);
    } else {
        portGetDisplay((void *) it, out, 64);
    }
}

int main() {
    // 1. Exhaustive: every valid port, every digit, both directions.
    for (uint32_t v = 1; v <= 65535; v++) {
        for (int pos = 0; pos < PORT_DIGITS; pos++) {
            for (int delta = -1; delta <= 1; delta += 2) {
                const uint32_t r = portStepDigit(v, pos, delta);
                CHECK(r >= 1 && r <= 65535, "step(%u,%d,%d)=%u out of range", v, pos, delta, r);
                for (int o = 0; o < PORT_DIGITS; o++) {
                    if (o != pos) {
                        CHECK(portDigit(r, o) == portDigit(v, o),
                              "step(%u,%d,%d)=%u changed digit %d", v, pos, delta, r, o);
                    }
                }
                CHECK(portStepDigit(r, pos, -delta) == v,
                      "step(%u,%d,%d)=%u does not step back", v, pos, delta, r);
            }
        }
        if (failures > 20) {
            break;
        }
    }

    // 2. Spot checks for the wrap and skip rules.
    CHECK(portStepDigit(1223, 0, +1) == 11223, "1223 top digit up");
    CHECK(portStepDigit(1223, 0, -1) == 61223, "1223 top digit down skips 9,8,7");
    CHECK(portStepDigit(65535, 0, +1) == 5535, "65535 top digit up wraps past 7,8,9");
    CHECK(portStepDigit(65535, 4, +1) == 65530, "65535 last digit up wraps to 0");
    CHECK(portStepDigit(1, 4, -1) == 9, "1 down skips port 0");
    CHECK(portStepDigit(9, 4, +1) == 1, "9 up skips port 0");
    CHECK(portStepDigit(9999, 0, -1) == 59999, "09999 top digit down lands on 5");

    // 3. Display.
    char     buf[64];
    PortItem it = makeItem(1223);
    render(&it, false, buf);
    CHECK(strcmp(buf, "1223") == 0, "idle display: %s", buf);
    render(&it, true, buf);
    CHECK(strcmp(buf, "(Press A to edit) 1223") == 0, "selected display: %s", buf);

    // 4. Editing flow: A edits, cursor starts left, LEFT wraps to the right end.
    press(&it, WUPS_CONFIG_BUTTON_A);
    CHECK(it.cursor == 0, "A enters edit at cursor 0 (got %d)", it.cursor);
    CHECK(!portIsMovementAllowed(&it), "row movement blocked while editing");
    render(&it, true, buf);
    CHECK(strcmp(buf, "[0]1223") == 0, "edit display: %s", buf);
    press(&it, WUPS_CONFIG_BUTTON_LEFT);
    render(&it, true, buf);
    CHECK(strcmp(buf, "0122[3]") == 0, "LEFT wraps to last digit: %s", buf);
    press(&it, WUPS_CONFIG_BUTTON_RIGHT);
    CHECK(it.cursor == 0, "RIGHT wraps back to 0");

    // One tap = exactly one step.
    press(&it, WUPS_CONFIG_BUTTON_UP);
    CHECK(it.value == 11223, "one tap UP: %u", it.value);
    press(&it, WUPS_CONFIG_BUTTON_DOWN);
    CHECK(it.value == 1223, "one tap DOWN: %u", it.value);

    // Holding repeats. Steps land on frames 1, 1+DELAY+1, then every EVERY+1.
    const int frames   = 60;
    int       expected = 1;
    if (frames > PORT_REPEAT_DELAY + 1) {
        expected += 1 + (frames - (PORT_REPEAT_DELAY + 2)) / (PORT_REPEAT_EVERY + 1);
    }
    uint32_t want = 1223;
    for (int i = 0; i < expected; i++) {
        want = portStepDigit(want, 0, +1);
    }
    hold(&it, WUPS_CONFIG_BUTTON_UP, frames);
    CHECK(expected > 2, "holding should repeat (expected %d steps)", expected);
    CHECK(it.value == want, "hold UP %d frames: got %u want %u (%d steps)",
          frames, it.value, want, expected);

    // B cancels back to the value before editing.
    press(&it, WUPS_CONFIG_BUTTON_B);
    CHECK(it.cursor == -1, "B leaves edit mode");
    CHECK(it.value == 1223, "B restores: %u", it.value);

    // A accepts.
    press(&it, WUPS_CONFIG_BUTTON_A);
    press(&it, WUPS_CONFIG_BUTTON_RIGHT); // thousands
    press(&it, WUPS_CONFIG_BUTTON_UP);    // 02223
    press(&it, WUPS_CONFIG_BUTTON_A);
    CHECK(it.cursor == -1 && it.value == 2223, "A accepts: cursor %d value %u", it.cursor, it.value);

    if (failures == 0) {
        printf("port_test: all checks passed (%d repeat steps in %d frames)\n", expected, frames);
        return 0;
    }
    printf("port_test: %d failure(s)\n", failures);
    return 1;
}
