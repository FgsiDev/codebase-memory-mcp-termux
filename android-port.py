#!/usr/bin/env python3
"""Patch codebase-memory-mcp so it runs inside Android/Termux.

1. Android app processes cannot open '/' or /data/data, and /data/data is
   owned by uid 1000 (not root), so upstream's fd-based "walk every ancestor
   from /" directory logic fails. On __ANDROID__ we create directories with
   plain mkdir() and open the target directory directly. /tmp does not exist
   in Termux either, so the runtime dir defaults to $TMPDIR.
2. Android's SELinux policy forbids hard links for apps (linkat -> EACCES),
   and the upstream daemon's socket protocol is built on hard links. So on
   __ANDROID__ the daemon is bypassed: the MCP server (stdio) and one-shot
   `cli` commands run in-process, and hook clients are a fail-open no-op.
   `install` (agent auto-config) also relies on link() and is unsupported;
   register the MCP server manually.

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

# 4. main.c: bypass the daemon on Android (hard links are blocked by SELinux)
patch(
    "src/main.c",
    r'''static char *main_local_cli_daemon_execute(const char *tool_name, const char *args_json,
                                           bool quiet_requested) {
    cbm_daemon_ipc_endpoint_t *endpoint = main_daemon_endpoint_new();
''',
    r'''static char *main_local_cli_daemon_execute(const char *tool_name, const char *args_json,
                                           bool quiet_requested) {
#ifdef __ANDROID__
    /* No daemon on Android: run the tool in an in-process server. */
    (void)quiet_requested;
    {
        cbm_mcp_server_t *android_srv = cbm_mcp_server_new(NULL);
        if (!android_srv) {
            (void)fprintf(stderr, "error: failed to create local server\n");
            return NULL;
        }
        cbm_mcp_server_set_background_tasks(android_srv, false);
        char android_root[MAIN_PATH_CAP];
        char android_allowed[MAIN_PATH_CAP];
        const char *android_allowed_ptr = NULL;
        if (main_session_context(NULL, android_root, android_allowed, &android_allowed_ptr)) {
            (void)cbm_mcp_server_set_session_context(android_srv, android_root,
                                                     android_allowed_ptr);
        }
        char *android_result = cbm_mcp_handle_tool(android_srv, tool_name, args_json);
        cbm_mcp_server_free(android_srv);
        return android_result;
    }
#endif
    cbm_daemon_ipc_endpoint_t *endpoint = main_daemon_endpoint_new();
''',
)
patch(
    "src/main.c",
    r'''    if (role == CBM_DAEMON_PROCESS_LOCAL_CLI) {
        bool feedback_enabled = main_local_cli_feedback_enabled(argc, argv);
''',
    r'''#ifdef __ANDROID__
    if (role == CBM_DAEMON_PROCESS_LOCAL_CLI) {
        /* No daemon / coordination locks on Android (they need hard links). */
        int android_cli_result = handle_subcommand(argc, argv, NULL, NULL);
        return android_cli_result >= 0 ? android_cli_result : EXIT_FAILURE;
    }
#endif
    if (role == CBM_DAEMON_PROCESS_LOCAL_CLI) {
        bool feedback_enabled = main_local_cli_feedback_enabled(argc, argv);
''',
)
patch(
    "src/main.c",
    r'''    const char *hook_event = NULL;
    const char *hook_dialect = NULL;
    if (role == CBM_DAEMON_PROCESS_HOOK_CLIENT &&
''',
    r'''#ifdef __ANDROID__
    if (role == CBM_DAEMON_PROCESS_HOOK_CLIENT) {
        return EXIT_SUCCESS; /* hooks are fail-open; augmentation needs the daemon */
    }
    if (role == CBM_DAEMON_PROCESS_MCP_CLIENT) {
        /* Stdio MCP server fully in-process: the daemon protocol needs hard
         * links, which Android's SELinux policy denies to apps. */
        cbm_mcp_server_t *android_mcp = cbm_mcp_server_new(NULL);
        if (!android_mcp) {
            (void)fprintf(stderr, "codebase-memory-mcp: failed to create MCP server\n");
            return EXIT_FAILURE;
        }
        cbm_mcp_server_set_tool_profile(android_mcp, tool_profile);
        char android_root[MAIN_PATH_CAP];
        char android_allowed[MAIN_PATH_CAP];
        const char *android_allowed_ptr = NULL;
        if (main_session_context(NULL, android_root, android_allowed, &android_allowed_ptr)) {
            (void)cbm_mcp_server_set_session_context(android_mcp, android_root,
                                                     android_allowed_ptr);
        }
        setup_signal_handlers();
        int android_rc = cbm_mcp_server_run(android_mcp, stdin, stdout);
        cbm_mcp_server_free(android_mcp);
        return android_rc < 0 ? EXIT_FAILURE : EXIT_SUCCESS;
    }
#endif
    const char *hook_event = NULL;
    const char *hook_dialect = NULL;
    if (role == CBM_DAEMON_PROCESS_HOOK_CLIENT &&
''',
)

# 5. compat.h: temp dir. Termux has no /tmp; use $TMPDIR ($PREFIX/tmp).
patch(
    "src/foundation/compat.h",
    r'''#else
    return "/tmp";
#endif
}
''',
    r'''#elif defined(__ANDROID__)
    const char *android_tmp = getenv("TMPDIR");
    return (android_tmp && android_tmp[0]) ? android_tmp : "/data/data/com.termux/files/usr/tmp";
#else
    return "/tmp";
#endif
}
''',
)

print("android-port: all patches applied")
