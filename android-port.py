#!/usr/bin/env python3
"""Patch codebase-memory-mcp so it runs inside Android/Termux.

Android app processes cannot open '/' or /data/data, and /data/data is owned
by uid 1000 (not root), so upstream's fd-based "walk every ancestor from /"
directory logic fails. On __ANDROID__ we create directories with plain mkdir()
and open the target directory directly. Also, /tmp does not exist in Termux,
so the daemon runtime dir defaults to $TMPDIR.

Usage: android-port.py <upstream-checkout-dir>
Exits non-zero if any anchor is missing, so upstream drift fails loudly.
"""
import pathlib
import sys

root = pathlib.Path(sys.argv[1])


def patch(rel, old, new):
    p = root / rel
    s = p.read_text()
    n = s.count(old)
    if n != 1:
        sys.exit(f"android-port: anchor mismatch in {rel}: found {n}, expected 1\n--- anchor ---\n{old}")
    p.write_text(s.replace(old, new))
    print(f"patched {rel}")


# 1. compat_fs.c: cbm_mkdir_p_ex -> plain mkdir loop on Android
patch(
    "src/foundation/compat_fs.c",
    r'''bool cbm_mkdir_p_ex(const char *path, int mode, unsigned int policy) {
    if (!path || path[0] == '\0') {
        return false;
    }
''',
    r'''#ifdef __ANDROID__
/* Android app processes cannot open '/' or /data/data, so the fd-based
 * ancestor walk below cannot even start. Use plain mkdir() per component. */
static bool cbm_android_mkdir_p(const char *path, int mode) {
    char *tmp = strdup(path);
    if (!tmp) {
        return false;
    }
    bool ok = true;
    for (char *p = tmp + 1; ok; p++) {
        char saved = *p;
        if (saved == '/' || saved == '\0') {
            *p = '\0';
            if (tmp[0] != '\0' && mkdir(tmp, (mode_t)mode) != 0 && errno != EEXIST) {
                struct stat st;
                if (stat(tmp, &st) != 0 || !S_ISDIR(st.st_mode)) {
                    ok = false;
                }
            }
            *p = saved;
        }
        if (saved == '\0') {
            break;
        }
    }
    free(tmp);
    return ok;
}
#endif

bool cbm_mkdir_p_ex(const char *path, int mode, unsigned int policy) {
    if (!path || path[0] == '\0') {
        return false;
    }
#ifdef __ANDROID__
    (void)policy;
    return cbm_android_mkdir_p(path, mode);
#endif
''',
)

# 2. activation_transaction.c: open the target directly, skip the ancestor walk
patch(
    "src/cli/activation_transaction.c",
    r'''    int descriptor = open(absolute ? "/" : ".", flags);
''',
    r'''#ifdef __ANDROID__
    int descriptor = open(absolute ? walk_path : ".", flags);
#else
    int descriptor = open(absolute ? "/" : ".", flags);
#endif
''',
)
patch(
    "src/cli/activation_transaction.c",
    r'''    char *cursor = walk_path;
    while (*cursor == '/') {
        cursor++;
    }
    if (ok && *cursor) {
''',
    r'''    char *cursor = walk_path;
    while (*cursor == '/') {
        cursor++;
    }
#ifdef __ANDROID__
    if (absolute) {
        cursor += strlen(cursor); /* target already opened; skip ancestor walk */
    }
#endif
    if (ok && *cursor) {
''',
)

# 3. ipc.c: runtime dir parent + private directory open
patch(
    "src/daemon/ipc.c",
    r'''#else
    const char *default_parent = "/tmp";
#endif
''',
    r'''#elif defined(__ANDROID__)
    /* Termux has no /tmp; its writable temp dir is $TMPDIR ($PREFIX/tmp). */
    const char *default_parent =
        (getenv("TMPDIR") && getenv("TMPDIR")[0]) ? getenv("TMPDIR")
                                                   : "/data/data/com.termux/files/usr/tmp";
#else
    const char *default_parent = "/tmp";
#endif
''',
)
patch(
    "src/daemon/ipc.c",
    r'''    int current_fd = open(absolute ? "/" : ".", O_RDONLY | O_DIRECTORY | O_CLOEXEC | O_NOFOLLOW);
''',
    r'''#ifdef __ANDROID__
    int current_fd = -1;
    if (absolute && cbm_mkdir_p(path, 0700)) {
        current_fd = open(path, O_RDONLY | O_DIRECTORY | O_CLOEXEC | O_NOFOLLOW);
    } else if (!absolute) {
        current_fd = open(".", O_RDONLY | O_DIRECTORY | O_CLOEXEC | O_NOFOLLOW);
    }
#else
    int current_fd = open(absolute ? "/" : ".", O_RDONLY | O_DIRECTORY | O_CLOEXEC | O_NOFOLLOW);
#endif
''',
)
patch(
    "src/daemon/ipc.c",
    r'''    bool visited = false;
    while (ok && *cursor) {
        char *component = cursor;
''',
    r'''    bool visited = false;
#ifdef __ANDROID__
    if (ok && absolute) {
        cursor += strlen(cursor); /* target already opened; skip ancestor walk */
        visited = true;
    }
#endif
    while (ok && *cursor) {
        char *component = cursor;
''',
)
print("android-port: all patches applied")
