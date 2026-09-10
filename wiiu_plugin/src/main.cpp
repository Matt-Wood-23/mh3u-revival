/*
 * MH3U Revival - Wii U (Aroma / WUPS) plugin
 * ------------------------------------------
 * Hardware counterpart to the patched Cemu fork. On a real Wii U the game's
 * NEX-token fetch is a genuine HTTPS request to Nintendo's (dead) account
 * server, with the server certificate pinned to Nintendo CA-G3 -- so DNS
 * redirection is impossible. Instead we replace the call itself.
 *
 * MH3U imports exactly one nex-token symbol (confirmed from the game ELF's
 * import table and from Cemu's export registration in nn_act.cpp:749):
 *
 *   AcquireNexServiceToken__Q2_2nn3actFP26ACTNexAuthenticationResultUi
 *   = nn::act::AcquireNexServiceToken(ACTNexAuthenticationResult *, u32 serverId)
 *
 * We fill the result struct ourselves and return success, so the call never
 * reaches IOSU: no TLS, no NNAS, no NNID handshake, and zero server changes.
 * This mirrors ACT_GetNexToken_WithCache() in the fork's napi_act.cpp:327-359.
 *
 * ---------------------------------------------------------------------------
 * v0.2.0 -- fixes the v0.1.0 field failure.
 *
 * WUPS_PLUGIN_NAME() expands to WUT_MALLOC / SOCKETS / NEWLIB / STDCPP /
 * THREAD but deliberately NOT WUT_DEVOPTAB (see wups/meta.h:45 and the
 * official example_plugin_cpp, which opts in explicitly). Without the
 * devoptab the "fs:" device is never registered, so every fopen() returns
 * NULL. In v0.1.0 that meant: no log file was ever created, the config was
 * never read, gHost silently stayed at its "127.0.0.1" default, and the game
 * was handed a loopback address it could never connect to. The plugin looked
 * dead from the outside while actually running.
 *
 * Two things changed:
 *   1. WUPS_USE_WUT_DEVOPTAB() -- the actual fix.
 *   2. Diagnostics that do NOT depend on the SD card, so "plugin never
 *      loaded" can never again be confused with "plugin ran but couldn't
 *      write": on-screen notifications, and a config-menu status page.
 *
 * ---------------------------------------------------------------------------
 * v0.3.0 -- drops the AcquireIndependentServiceToken hook and the
 * stub_independent_token flag.
 *
 * Static analysis flagged that symbol as the one open risk: MH3U imports it,
 * and on hardware it really does reach Nintendo. The v0.2.0 build hooked it
 * and logged BOTH branches (stubbed and passed-through) so one session would
 * settle it. Three sessions on a real EU console produced ZERO [indep] lines,
 * while [nex] REDIRECTED fired normally in the same runs -- so the hook was
 * installed and simply never invoked. MH3U does not call it on the online
 * path, and the flag was inert whatever it was set to.
 *
 * Removing it is a net safety win, not just tidying: WUPS_MUST_REPLACE is
 * MANDATORY, so every symbol listed here is one more way the whole plugin can
 * fail to load if a future Cafe OS/Aroma change moves it. Two read-only
 * logging hooks are kept (GetPrincipalId, HasNfsAccount) -- they change no
 * behaviour and each still answers something useful per run.
 *
 * ---------------------------------------------------------------------------
 * v0.4.0 -- the server address is editable ON-CONSOLE.
 *
 * Through v0.3.0 the only way to retarget the server was to power off, pull
 * the SD card, edit mh3u_server.txt on a PC and put it back. That is the
 * single most-repeated action in a test session and it dominated the
 * turnaround on every field test so far.
 *
 * The address now lives in WUPS storage and is edited with the GamePad from
 * the plugin config menu (L + DPAD-Down + Minus). mh3u_server.txt still works
 * and is still read; the two are reconciled by LAST EDIT WINS:
 *
 *   - the file's contents at the time we last adopted them are remembered
 *     (txt_host_seen / txt_port_seen)
 *   - if the file differs from that, the human edited the file -> adopt it
 *   - otherwise the stored value wins, because that is the only other place
 *     an edit can have come from
 *
 * So neither editor silently loses to the other, and no "which source?"
 * toggle is needed. A consequence worth knowing: mh3u_server.txt is now
 * OPTIONAL. Once an address has been set on-console the file can be deleted
 * and the plugin keeps working.
 *
 * Storage init ordering is NOT assumed. wups/hooks.h lists INIT_STORAGE after
 * INIT_PLUGIN in the hook enum, but that enum is a type list and not a
 * dispatch order (INIT_WUT_DEVOPTAB is listed early too, and demonstrably runs
 * before INITIALIZE_PLUGIN -- that is what the v0.2.0 fix relies on). Rather
 * than depend on either reading, every storage access goes through
 * storageReady(), which retries on the next entry point if the API reports
 * INTERNAL_NOT_INITIALIZED, and logs which attempt succeeded.
 */

#include <wups.h>

#include <wups/config/WUPSConfigItemIPAddress.h>
#include <wups/config/WUPSConfigItemIntegerRange.h>
#include <wups/config/WUPSConfigItemStub.h>
#include <wups/config_api.h>
#include <wups/storage.h>

#include <coreinit/debug.h>
#include <coreinit/title.h>

#include <notifications/notifications.h>

#include <cstdarg>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>

#define PLUGIN_VERSION "v0.4.0"

WUPS_PLUGIN_NAME("MH3U Revival");
WUPS_PLUGIN_DESCRIPTION("Redirects Monster Hunter 3 Ultimate's NEX token to a self-hosted revival server.");
WUPS_PLUGIN_VERSION(PLUGIN_VERSION);
WUPS_PLUGIN_AUTHOR("Matt Wood");
WUPS_PLUGIN_LICENSE("MIT");

// THE v0.1.0 BUG. Not implied by WUPS_PLUGIN_NAME -- without this, no fopen()
// in this plugin can ever succeed.
WUPS_USE_WUT_DEVOPTAB();

// Backing store for the on-console address editor. The id names the file under
// sd:/wiiu/plugins/config/, so it must not change between versions or every
// tester silently reverts to their SD txt on upgrade.
#define STORAGE_ID "mh3u_revival"
WUPS_USE_STORAGE(STORAGE_ID);

#define KEY_HOST     "server_host"    // string  - the address we will hand the game
#define KEY_PORT     "server_port"    // u32     - ...and its port
#define KEY_TXT_HOST "txt_host_seen"  // string  - mh3u_server.txt as of our last adopt
#define KEY_TXT_PORT "txt_port_seen"  // u32

// MH3U's NEX game-server-id, identical across US/EU/JP -- gating on this is
// region-agnostic (the titleId list below is belt-and-suspenders only).
#define MH3U_GAME_SERVER_ID 0x10104d00u

#define SD_ROOT      "fs:/vol/external01"
#define CFG_PATH     SD_ROOT "/wiiu/mh3u_server.txt"
#define LOG_PATH     SD_ROOT "/wiiu/mh3u_plugin.log"
// Fallback without the "fs:" device prefix, in case the devoptab is named
// differently on the tester's WUPS build. Cheap insurance.
#define CFG_PATH_ALT "/vol/external01/wiiu/mh3u_server.txt"
#define LOG_PATH_ALT "/vol/external01/wiiu/mh3u_plugin.log"

#define DEFAULT_HOST "127.0.0.1"
#define DEFAULT_PORT 1223

// nn::Result: 0 == success, high bit set == error (Cemu iosu_act.cpp:588-602).
#define NN_RESULT_SUCCESS 0u
#define NN_RESULT_FAILURE 0x80000000u

// ---------------------------------------------------------------------------
// ACTNexAuthenticationResult -- 0x25C bytes, layout from Cemu nn_act.cpp:612
// ---------------------------------------------------------------------------
struct ACTNexAuthenticationResult {
    /* +0x000 */ char     token[0x201];      // /nex_token/token
    /* +0x201 */ uint8_t  _pad201[3];
    /* +0x204 */ char     nexPassword[0x41]; // /nex_token/nex_password
    /* +0x245 */ uint8_t  _pad245[3];
    /* +0x248 */ char     host[0x10];        // /nex_token/host (15 chars + NUL)
    /* +0x258 */ uint16_t port;              // /nex_token/port
    /* +0x25A */ uint16_t _pad25A;
};
static_assert(sizeof(ACTNexAuthenticationResult) == 0x25C,
              "ACTNexAuthenticationResult must be 0x25C bytes");

// The game's host field is char[0x10]. Every buffer here is sized to match so a
// value that fits in storage or the txt cannot overflow it later.
#define HOST_MAX 16

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------
enum CfgSource {
    SRC_DEFAULT = 0, // nothing configured anywhere
    SRC_TXT,         // mh3u_server.txt
    SRC_MENU,        // WUPS storage, i.e. edited on-console
};

static char     gHost[HOST_MAX] = DEFAULT_HOST;
static uint16_t gPort           = DEFAULT_PORT;
static bool     gIsMH3U         = false;

// Diagnostics surfaced in the config menu and in notifications.
static bool      gNotifyReady    = false;
static bool      gCfgFound       = false; // mh3u_server.txt opened
static bool      gCfgParsed      = false; // ...and yielded a usable endpoint
static bool      gLogWritable    = false; // the SD log actually accepted a write
static bool      gStorageOk      = false; // WUPS storage answered us
static bool      gHaveEndpoint   = false; // gHost/gPort came from somewhere real
static CfgSource gSource         = SRC_DEFAULT;
static uint32_t  gRedirectCount  = 0;
static char      gStatusLine[96] = "not run yet";

static const char *sourceName(CfgSource s) {
    switch (s) {
        case SRC_MENU: return "console config menu";
        case SRC_TXT:  return "sd:/wiiu/mh3u_server.txt";
        default:       return "built-in default";
    }
}

// ---------------------------------------------------------------------------
// Logging. Always OSReport (visible over a UDP/serial log catcher even with no
// SD write access), then best-effort append to the SD. Opened and closed per
// line so the log survives a hang or a crash.
// ---------------------------------------------------------------------------
static void plog(const char *fmt, ...) __attribute__((format(printf, 1, 2)));

static void plog(const char *fmt, ...) {
    char    buf[512];
    va_list ap;
    va_start(ap, fmt);
    vsnprintf(buf, sizeof(buf), fmt, ap);
    va_end(ap);

    OSReport("[MH3U-Revival] %s\n", buf);

    FILE *f = fopen(LOG_PATH, "a");
    if (!f) {
        f = fopen(LOG_PATH_ALT, "a");
    }
    if (!f) {
        return;
    }
    fputs(buf, f);
    fputc('\n', f);
    fclose(f);
    gLogWritable = true;
}

// ---------------------------------------------------------------------------
// On-screen notifications -- the proof-of-life channel that does not touch the
// SD card at all. If these appear, the plugin is loaded and running, whatever
// the filesystem is doing.
// ---------------------------------------------------------------------------
static void notify(bool isError, const char *fmt, ...) __attribute__((format(printf, 2, 3)));

static void notify(bool isError, const char *fmt, ...) {
    if (!gNotifyReady) {
        return;
    }
    char    buf[256];
    va_list ap;
    va_start(ap, fmt);
    vsnprintf(buf, sizeof(buf), fmt, ap);
    va_end(ap);

    const NMColor white = {255, 255, 255, 255};
    if (isError) {
        const NMColor red = {160, 32, 32, 255};
        NotificationModule_AddErrorNotificationEx(buf, 12.0f, 2.0f, white, red, nullptr, nullptr, true);
    } else {
        const NMColor navy = {24, 48, 96, 255};
        NotificationModule_AddInfoNotificationEx(buf, 8.0f, white, navy, nullptr, nullptr, true);
    }
}

// ---------------------------------------------------------------------------
// IPv4 <-> uint32. WUPSConfigItemIPAddress speaks uint32 only, but the token
// field the game reads is a string, and mh3u_server.txt may legitimately hold
// a short hostname -- so the string stays authoritative and these convert only
// for the benefit of the editor widget.
// ---------------------------------------------------------------------------
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
    if (*s != '\0' || parts != 4) {
        return false;
    }
    *out = acc;
    return true;
}

static void ipToString(uint32_t ip, char *out, size_t n) {
    snprintf(out, n, "%u.%u.%u.%u",
             (unsigned) ((ip >> 24) & 0xFF), (unsigned) ((ip >> 16) & 0xFF),
             (unsigned) ((ip >> 8) & 0xFF), (unsigned) (ip & 0xFF));
}

// ---------------------------------------------------------------------------
// Storage. Every call funnels through storageReady() so a late-initialising
// storage API degrades to "SD txt only" instead of to a crash, and recovers by
// itself on the next entry point.
// ---------------------------------------------------------------------------
static bool storageReady() {
    if (gStorageOk) {
        return true;
    }
    // Any cheap read tells us whether the API is live. NOT_FOUND is a perfectly
    // good answer -- it means storage works and the key simply is not set yet.
    uint32_t         probe = 0;
    WUPSStorageError e     = WUPSStorageAPI_GetU32(nullptr, KEY_PORT, &probe);
    if (e == WUPS_STORAGE_ERROR_SUCCESS || e == WUPS_STORAGE_ERROR_NOT_FOUND) {
        gStorageOk = true;
        return true;
    }
    plog("[store] not available yet (err=%d) -- will retry", (int) e);
    return false;
}

static bool storeGetHost(const char *key, char *out, size_t n) {
    if (!storageReady()) {
        return false;
    }
    out[0] = '\0';
    if (WUPSStorageAPI_GetString(nullptr, key, out, (uint32_t) n, nullptr) != WUPS_STORAGE_ERROR_SUCCESS) {
        return false;
    }
    return out[0] != '\0';
}

static bool storeGetPort(const char *key, uint16_t *out) {
    if (!storageReady()) {
        return false;
    }
    uint32_t v = 0;
    if (WUPSStorageAPI_GetU32(nullptr, key, &v) != WUPS_STORAGE_ERROR_SUCCESS) {
        return false;
    }
    if (v == 0 || v > 65535) {
        return false;
    }
    *out = (uint16_t) v;
    return true;
}

static void storePut(const char *hostKey, const char *host, const char *portKey, uint16_t port) {
    if (!storageReady()) {
        return;
    }
    WUPSStorageError a = WUPSStorageAPI_StoreString(nullptr, hostKey, host);
    WUPSStorageError b = WUPSStorageAPI_StoreU32(nullptr, portKey, (uint32_t) port);
    WUPSStorageError c = WUPSStorageAPI_SaveStorage(false);
    if (a != WUPS_STORAGE_ERROR_SUCCESS || b != WUPS_STORAGE_ERROR_SUCCESS ||
        c != WUPS_STORAGE_ERROR_SUCCESS) {
        plog("[store] write %s/%s failed (host=%d port=%d save=%d)",
             hostKey, portKey, (int) a, (int) b, (int) c);
    }
}

// ---------------------------------------------------------------------------
// mh3u_server.txt: "<host>" or "<host>:<port>" on the first non-comment line,
// plus optional "key=value" flag lines. Mirrors the Cemu fork's file so a
// tester can retarget the server without a rebuild.
// ---------------------------------------------------------------------------
static void trim(char *s) {
    char *a = s;
    while (*a == ' ' || *a == '\t' || *a == '\r' || *a == '\n') {
        a++;
    }
    if (a != s) {
        memmove(s, a, strlen(a) + 1);
    }
    size_t n = strlen(s);
    while (n > 0) {
        char c = s[n - 1];
        if (c != ' ' && c != '\t' && c != '\r' && c != '\n') {
            break;
        }
        s[--n] = '\0';
    }
}

// Fills outHost/outPort from the SD file. Returns true only for a usable
// endpoint. Sets gCfgFound as a side effect so the menu can distinguish
// "no file" from "file present but unparseable".
static bool readTxtConfig(char *outHost, uint16_t *outPort) {
    gCfgFound = false;

    FILE *f = fopen(CFG_PATH, "r");
    if (!f) {
        f = fopen(CFG_PATH_ALT, "r");
    }
    if (!f) {
        return false;
    }
    gCfgFound = true;

    bool got = false;
    char line[256];
    while (fgets(line, sizeof(line), f)) {
        trim(line);
        if (line[0] == '\0' || line[0] == '#') {
            continue;
        }

        char *eq = strchr(line, '=');
        if (eq) { // flag line
            *eq       = '\0';
            char *key = line;
            char *val = eq + 1;
            trim(key);
            trim(val);
            plog("[cfg] unknown flag ignored: %s=%s", key, val);
            continue;
        }

        if (got) {
            continue; // first valid endpoint line wins
        }

        // host[:port] -- split on the LAST colon so odd input degrades sanely
        char *colon = strrchr(line, ':');
        long  port  = DEFAULT_PORT;
        if (colon && colon[1] != '\0') {
            bool numeric = true;
            for (char *p = colon + 1; *p; p++) {
                if (*p < '0' || *p > '9') {
                    numeric = false;
                    break;
                }
            }
            if (numeric) {
                *colon = '\0';
                port   = strtol(colon + 1, nullptr, 10);
            }
        }
        trim(line);

        // The nexToken host field is char[0x10]: 15 chars max. An IPv4 literal
        // always fits; a long hostname does not, so reject rather than truncate.
        size_t hlen = strlen(line);
        if (hlen == 0 || hlen > 15) {
            plog("[cfg] host invalid (empty or >15 chars), ignoring: %s", line);
        } else if (port <= 0 || port > 65535) {
            plog("[cfg] port out of range (%ld), ignoring line", port);
        } else {
            strcpy(outHost, line);
            *outPort = (uint16_t) port;
            got      = true;
        }
    }
    fclose(f);
    return got;
}

// ---------------------------------------------------------------------------
// Reconcile the two editors. See the v0.4.0 header note: LAST EDIT WINS, with
// the file's previously-adopted contents as the tiebreaker.
// ---------------------------------------------------------------------------
static void applyEndpoint(const char *host, uint16_t port, CfgSource src) {
    // Callers that only change the port pass gHost straight back in; copying a
    // buffer onto itself is undefined (and -Werror=restrict catches it).
    if (host != gHost) {
        snprintf(gHost, sizeof(gHost), "%s", host);
    }
    gPort         = port;
    gSource       = src;
    gHaveEndpoint = (src != SRC_DEFAULT);
}

static void loadConfig() {
    char       txtHost[HOST_MAX] = {0};
    uint16_t   txtPort           = DEFAULT_PORT;
    const bool haveTxt           = readTxtConfig(txtHost, &txtPort);
    gCfgParsed                   = haveTxt;

    char       stHost[HOST_MAX] = {0};
    uint16_t   stPort           = DEFAULT_PORT;
    const bool haveStored       = storeGetHost(KEY_HOST, stHost, sizeof(stHost)) &&
                            storeGetPort(KEY_PORT, &stPort);

    char       seenHost[HOST_MAX] = {0};
    uint16_t   seenPort           = 0;
    const bool haveSeen           = storeGetHost(KEY_TXT_HOST, seenHost, sizeof(seenHost)) &&
                          storeGetPort(KEY_TXT_PORT, &seenPort);

    // Did a human edit the SD file since we last took a copy of it? A missing
    // record counts as "changed" so the very first boot adopts the file.
    const bool txtChanged = haveTxt && (!haveSeen ||
                                        strcmp(txtHost, seenHost) != 0 ||
                                        txtPort != seenPort);

    if (txtChanged) {
        applyEndpoint(txtHost, txtPort, SRC_TXT);
        storePut(KEY_HOST, txtHost, KEY_PORT, txtPort);
        storePut(KEY_TXT_HOST, txtHost, KEY_TXT_PORT, txtPort);
        plog("[cfg] adopted %s:%u from the SD file (it changed since last boot)",
             gHost, (unsigned) gPort);
    } else if (haveStored) {
        applyEndpoint(stHost, stPort, SRC_MENU);
    } else if (haveTxt) {
        applyEndpoint(txtHost, txtPort, SRC_TXT);
    } else {
        applyEndpoint(DEFAULT_HOST, DEFAULT_PORT, SRC_DEFAULT);
    }

    if (gHaveEndpoint) {
        snprintf(gStatusLine, sizeof(gStatusLine), "%s:%u", gHost, (unsigned) gPort);
    } else {
        snprintf(gStatusLine, sizeof(gStatusLine), "NOT SET - open this menu to set it");
    }
    plog("[cfg] endpoint = %s:%u (source=%s, txt=%d, stored=%d, storage=%d)",
         gHost, (unsigned) gPort, sourceName(gSource),
         (int) haveTxt, (int) haveStored, (int) gStorageOk);
}

// ---------------------------------------------------------------------------
// THE PATCH: hand the game our own NEX endpoint directly.
// ---------------------------------------------------------------------------
DECL_FUNCTION(uint32_t, AcquireNexServiceToken, ACTNexAuthenticationResult *token, uint32_t serverId) {
    if (serverId != MH3U_GAME_SERVER_ID) {
        uint32_t r = real_AcquireNexServiceToken(token, serverId);
        if (gIsMH3U) {
            plog("[nex] passthrough serverId=0x%08x -> result=0x%08x", serverId, r);
        }
        return r;
    }

    if (!token) {
        plog("[nex] serverId matched but token pointer is NULL");
        return NN_RESULT_FAILURE;
    }

    memset(token, 0, sizeof(*token));
    snprintf(token->token, sizeof(token->token), "%s", "mh3u_revival_token");
    snprintf(token->nexPassword, sizeof(token->nexPassword), "%s", "mh3u_revival_pw");
    snprintf(token->host, sizeof(token->host), "%s", gHost);
    token->port = gPort;

    gRedirectCount++;
    plog("[nex] REDIRECTED #%u serverId=0x%08x -> %s:%u (source=%s)",
         gRedirectCount, serverId, gHost, (unsigned) gPort, sourceName(gSource));

    // Notify on the first couple only -- the game may retry and we do not want
    // to bury the screen in overlays mid-connect.
    if (gRedirectCount <= 2) {
        if (gHaveEndpoint) {
            notify(false, "MH3U: NEX token redirected -> %s:%u", gHost, (unsigned) gPort);
        } else {
            notify(true, "MH3U: no server address set! Using %s:%u - set one in the plugin config menu",
                   gHost, (unsigned) gPort);
        }
    }
    return NN_RESULT_SUCCESS;
}
WUPS_MUST_REPLACE(AcquireNexServiceToken,
                  WUPS_LOADER_LIBRARY_NN_ACT,
                  AcquireNexServiceToken__Q2_2nn3actFP26ACTNexAuthenticationResultUi);

// ---------------------------------------------------------------------------
// DIAGNOSTICS: read-only pass-through hooks. These change no behaviour; they
// exist so a single log explains a failed session.
// ---------------------------------------------------------------------------

// Logged so the tester's console PID can be matched against the server log.
DECL_FUNCTION(uint32_t, GetPrincipalId, void) {
    uint32_t pid = real_GetPrincipalId();
    if (gIsMH3U) {
        plog("[act] GetPrincipalId -> %u (0x%08x)", pid, pid);
    }
    return pid;
}
WUPS_MUST_REPLACE(GetPrincipalId,
                  WUPS_LOADER_LIBRARY_NN_ACT,
                  GetPrincipalId__Q2_2nn3actFv);

// Cemu hardcodes this to true; log the real console's answer in case the game
// gates Network Mode on it.
DECL_FUNCTION(bool, HasNfsAccount, void) {
    bool r = real_HasNfsAccount();
    if (gIsMH3U) {
        plog("[act] HasNfsAccount -> %d", (int) r);
    }
    return r;
}
WUPS_MUST_REPLACE(HasNfsAccount,
                  WUPS_LOADER_LIBRARY_NN_ACT,
                  HasNfsAccount__Q2_2nn3actFv);

// ---------------------------------------------------------------------------
// Config menu -- now the primary way to set the server address, and still the
// proof-of-life page. Openable from anywhere (including the Wii U menu) with
// L + DPAD-Down + Minus, so the address can be changed without ejecting the SD
// card and without launching the game first.
// ---------------------------------------------------------------------------
static void onServerIpChanged(ConfigItemIPAddress *, uint32_t ip) {
    char buf[HOST_MAX];
    ipToString(ip, buf, sizeof(buf));

    applyEndpoint(buf, gPort, SRC_MENU);
    storePut(KEY_HOST, gHost, KEY_PORT, gPort);
    snprintf(gStatusLine, sizeof(gStatusLine), "%s:%u", gHost, (unsigned) gPort);
    plog("[cfg] server address set to %s from the console config menu", gHost);
}

static void onServerPortChanged(ConfigItemIntegerRange *, int32_t port) {
    if (port < 1 || port > 65535) {
        return;
    }
    applyEndpoint(gHost, (uint16_t) port, SRC_MENU);
    storePut(KEY_HOST, gHost, KEY_PORT, gPort);
    snprintf(gStatusLine, sizeof(gStatusLine), "%s:%u", gHost, (unsigned) gPort);
    plog("[cfg] server port set to %u from the console config menu", (unsigned) gPort);
}

static WUPSConfigAPICallbackStatus ConfigMenuOpened(WUPSConfigCategoryHandle root) {
    char buf[128];

    // Re-read on OPEN as well as on close: the tester may have swapped the SD
    // file since boot, and the editable item below has to show the live value.
    loadConfig();

    // --- the editable pair, first so it is what the D-pad lands on ---
    uint32_t   ipValue    = 0;
    const bool hostIsIPv4 = ipFromString(gHost, &ipValue);

    WUPSConfigItemIPAddress_AddToCategory(root, "server_ip", "Server IP address",
                                          0 /* default 0.0.0.0 */, ipValue,
                                          &onServerIpChanged);

    WUPSConfigItemIntegerRange_AddToCategory(root, "server_port", "Server port",
                                             DEFAULT_PORT, (int32_t) gPort,
                                             1, 65535, &onServerPortChanged);

    // --- read-only status below ---
    snprintf(buf, sizeof(buf), "In use: %s:%u", gHost, (unsigned) gPort);
    WUPSConfigItemStub_AddToCategory(root, buf);

    snprintf(buf, sizeof(buf), "Set from: %s", sourceName(gSource));
    WUPSConfigItemStub_AddToCategory(root, buf);

    if (!hostIsIPv4) {
        // The widget above cannot represent a name, so say so rather than let
        // it sit at 0.0.0.0 looking like the address failed to load.
        snprintf(buf, sizeof(buf), "(hostname %s - editing above replaces it)", gHost);
        WUPSConfigItemStub_AddToCategory(root, buf);
    }

    snprintf(buf, sizeof(buf), "sd:/wiiu/mh3u_server.txt: %s",
             gCfgFound ? (gCfgParsed ? "read OK (optional now)" : "found, but no valid address")
                       : "not present (optional now)");
    WUPSConfigItemStub_AddToCategory(root, buf);

    snprintf(buf, sizeof(buf), "Settings saved on console: %s",
             gStorageOk ? "yes" : "NO - storage unavailable");
    WUPSConfigItemStub_AddToCategory(root, buf);

    snprintf(buf, sizeof(buf), "sd:/wiiu/mh3u_plugin.log: %s",
             gLogWritable ? "writing OK" : "not written yet");
    WUPSConfigItemStub_AddToCategory(root, buf);

    snprintf(buf, sizeof(buf), "NEX redirects so far: %u", gRedirectCount);
    WUPSConfigItemStub_AddToCategory(root, buf);

    snprintf(buf, sizeof(buf), "Plugin: MH3U Revival %s (loaded)", PLUGIN_VERSION);
    WUPSConfigItemStub_AddToCategory(root, buf);

    return WUPSCONFIG_API_CALLBACK_RESULT_SUCCESS;
}

static void ConfigMenuClosed() {
    // The item callbacks have already applied and stored any edit; this just
    // re-derives the status line and picks up an SD file swapped while open.
    loadConfig();
    if (gHaveEndpoint) {
        notify(false, "MH3U Revival: server set to %s:%u", gHost, (unsigned) gPort);
    }
}

// ---------------------------------------------------------------------------
// Lifecycle
// ---------------------------------------------------------------------------
INITIALIZE_PLUGIN() {
    gNotifyReady = (NotificationModule_InitLibrary() == NOTIFICATION_MODULE_RESULT_SUCCESS);

    WUPSConfigAPIOptionsV1 opts = {.name = "MH3U Revival"};
    WUPSConfigAPI_Init(opts, ConfigMenuOpened, ConfigMenuClosed);

    // Runs after the devoptab hook, so the SD is readable here. Storage may or
    // may not be up yet -- storageReady() handles both and retries later.
    loadConfig();
}

DEINITIALIZE_PLUGIN() {
    if (gNotifyReady) {
        NotificationModule_DeInitLibrary();
        gNotifyReady = false;
    }
}

ON_APPLICATION_START() {
    uint64_t titleId = OSGetTitleID();

    gIsMH3U = (titleId == 0x0005000010118300ull    // US
               || titleId == 0x0005000010117200ull // EU
               || titleId == 0x0005000010116300ull // EU alt SKU
               || titleId == 0x0005000010104D00ull // JP (MH3G HD Ver.)
    );

    const bool isWiiUMenu = (titleId == 0x0005001010040000ull    // JP
                             || titleId == 0x0005001010040100ull // US
                             || titleId == 0x0005001010040200ull // EU
    );

    if (!gIsMH3U && !isWiiUMenu) {
        return; // stay silent for every other title
    }

    // Second chance for storage if it was not up during INITIALIZE_PLUGIN.
    loadConfig();

    if (isWiiUMenu) {
        // One-line proof of life at the system menu: if the tester sees this,
        // the plugin is installed and loaded, full stop.
        if (gHaveEndpoint) {
            notify(false, "MH3U Revival %s active - server %s:%u",
                   PLUGIN_VERSION, gHost, (unsigned) gPort);
        } else {
            notify(true, "MH3U Revival %s loaded - no server address set yet (L + DPAD-Down + Minus)",
                   PLUGIN_VERSION);
        }
        return;
    }

    plog(" ");
    plog("=== MH3U Revival plugin %s -- titleId=0x%016llx ===",
         PLUGIN_VERSION, (unsigned long long) titleId);

    if (gHaveEndpoint) {
        notify(false, "MH3U Revival %s - will redirect NEX to %s:%u",
               PLUGIN_VERSION, gHost, (unsigned) gPort);
    } else {
        notify(true, "MH3U Revival %s - NO SERVER ADDRESS. Set one with L + DPAD-Down + Minus",
               PLUGIN_VERSION);
    }
}
