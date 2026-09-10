#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include <stdbool.h>

static bool ipFromString(const char *s, uint32_t *out) {
    uint32_t acc   = 0;
    int      parts = 0;

    for (;;) {
        if (*s < '0' || *s > '9') {
            return false; // every octet must start with a digit
        }
        // A leading zero makes an octet ambiguous -- "010" is 8 to any resolver
        // that follows the historical octal rule, and 10 to one that does not.
        // Rejecting means such a string is left untouched and handed to the game
        // exactly as written, instead of being silently normalised by the editor
        // widget into a DIFFERENT address.
        const bool leadingZero = (s[0] == '0' && s[1] >= '0' && s[1] <= '9');
        uint32_t   v           = 0;
        int        digits      = 0;
        while (*s >= '0' && *s <= '9') {
            v = v * 10 + (uint32_t) (*s - '0');
            s++;
            if (++digits > 3 || v > 255) {
                return false;
            }
        }
        if (leadingZero) {
            return false;
        }
        acc = (acc << 8) | v;
        parts++;
        if (*s == '.') {
            s++;
            if (parts == 4) {
                return false; // "1.2.3.4." / five octets
            }
            continue;
        }
        break;
    }
    if (*s != '' || parts != 4) {
        return false;
    }
    *out = acc;
    return true;
}

static void ipToString(uint32_t ip, char *out, size_t n) {
    snprintf(out, n, "%u.%u.%u.%u",
             (unsigned)((ip >> 24) & 0xFF), (unsigned)((ip >> 16) & 0xFF),
             (unsigned)((ip >> 8) & 0xFF), (unsigned)(ip & 0xFF));
}

static int fails = 0;
static void ok(const char *s, uint32_t want) {
    uint32_t got = 0;
    if (!ipFromString(s, &got)) { printf("FAIL accept %-20s -> rejected\n", s); fails++; return; }
    if (got != want) { printf("FAIL value  %-20s -> 0x%08x want 0x%08x\n", s, got, want); fails++; return; }
    char back[16]; ipToString(got, back, sizeof back);
    if (strcmp(back, s) != 0) { printf("FAIL round  %-20s -> %s\n", s, back); fails++; return; }
    printf("ok   %-20s = 0x%08x\n", s, got);
}
static void no(const char *s) {
    uint32_t got = 0;
    if (ipFromString(s, &got)) { printf("FAIL reject %-20s -> accepted as 0x%08x\n", s, got); fails++; return; }
    printf("ok   reject %-15s\n", s);
}

int main(void) {
    /* the addresses that actually matter in this project */
    ok("127.0.0.1",       0x7F000001);
    ok("192.168.1.100",   0xC0A80164);
    ok("10.0.0.1",        0x0A000001);
    ok("0.0.0.0",         0x00000000);
    ok("255.255.255.255", 0xFFFFFFFF);
    ok("8.8.4.4",         0x08080404);
    ok("100.64.0.1",      0x64400001);   /* tailscale CGNAT range */
    ok("26.1.2.3",        0x1A010203);   /* radmin range */

    /* malformed input must never silently become a valid-looking address */
    no("");            no("1.2.3");        no("1.2.3.4.5");
    no("1.2.3.4.");    no("256.1.1.1");    no("1.2.3.999");
    no("1.2.3.-1");    no("a.b.c.d");      no(" 1.2.3.4");
    no("1.2.3.4 ");    no("1..3.4");       no("1.2.3.");
    no("01.02.03.004");                     /* leading zeros are ambiguous */
    no("010.1.1.1");    no("192.168.01.1");  no("00.0.0.0");
    no("mh3u.example.com");                 /* hostname stays a hostname */
    no("1.2.3.4:1223");                     /* port must be split off first */

    printf("\n%s (%d failure%s)\n", fails ? "FAILED" : "ALL PASS", fails, fails == 1 ? "" : "s");
    return fails != 0;
}
