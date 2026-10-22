// randombytes for the standalone keytool: the operating system's CSPRNG. (The node tree provides its own
// randombytes() from its RNG, so a tool built against the node's sources uses that one instead.)
//   macOS: arc4random_buf, which cannot fail.  Windows: BCryptGenRandom with the system RNG.
//   Linux: getrandom(2), which blocks only until the kernel pool is first initialised.
#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>
#include "randombytes.h"

#if defined(__APPLE__)
int randombytes(uint8_t *output, size_t n) { arc4random_buf(output, n); return 0; }

#elif defined(_WIN32)
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <bcrypt.h>
int randombytes(uint8_t *output, size_t n) {
    while (n > 0) {
        ULONG chunk = n > 0x40000000u ? 0x40000000u : (ULONG)n;
        if (!BCRYPT_SUCCESS(BCryptGenRandom(NULL, output, chunk, BCRYPT_USE_SYSTEM_PREFERRED_RNG))) return -1;
        output += chunk; n -= chunk;
    }
    return 0;
}

#else
#include <errno.h>
#include <sys/random.h>
int randombytes(uint8_t *output, size_t n) {
    while (n > 0) {
        ssize_t got = getrandom(output, n, 0);
        if (got < 0) { if (errno == EINTR) continue; return -1; }
        output += got; n -= (size_t)got;
    }
    return 0;
}
#endif
