"""Stub ``netifaces`` for the MH3U Revival server.

The real `netifaces` is a C extension and publishes **no wheels for Python 3.10+**, so
`pip install` falls back to building it from source — which needs the MSVC C++ build
tools that a host shouldn't have to install. `anynet` imports `netifaces` at the top of
`anynet/util.py`, but the MH3U server never calls the functions that use it (they only
enumerate local network interfaces to guess a default IP — the server binds 0.0.0.0 and
uses MH3U_ADVERTISE instead).

So this stub exists purely to satisfy `import netifaces`. The data functions raise a clear
error if anything ever actually calls them, rather than returning bogus interface data.
"""

# Address-family constants anynet references as dict keys. Values mirror the real lib's
# Windows values; they're only used as lookup keys, never for real syscalls here.
AF_INET = 2
AF_INET6 = 23
AF_LINK = -1000


def _stubbed(name):
    def _raise(*_args, **_kwargs):
        raise RuntimeError(
            f"netifaces.{name}() was called, but this is the MH3U Revival pure-Python "
            "stub (the real netifaces needs a C compiler we deliberately avoid). The "
            "server doesn't enumerate network interfaces; if you hit this, a code path "
            "tried to and we'd need to revisit the dependency."
        )
    _raise.__name__ = name
    return _raise


interfaces = _stubbed("interfaces")
ifaddresses = _stubbed("ifaddresses")
gateways = _stubbed("gateways")
