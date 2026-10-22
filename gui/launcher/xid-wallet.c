/* XID Wallet.exe: the Windows app people double-click, at the top of the XID Wallet folder.

   It runs the wallet inside this process with the bundled Python (runtime\python312.dll, which reads
   runtime\python312._pth for its paths), so Windows sees one app named XID Wallet with the xCoin icon:
   in the folder, on the taskbar, when pinned, and in Task Manager. GUI subsystem: no console window,
   exactly like runtime\pythonw.exe. Arguments go to the app (app\gui\app.py).

   Built by gui/build-portable.sh with zig (x86_64-windows-gnu), with xid-wallet.rc for the icon,
   version and manifest. */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <shellapi.h>

#define LONG_PATH 32768

typedef int (*py_main_fn)(int, wchar_t **);

static int say(const wchar_t *text) {
    MessageBoxW(NULL, text, L"XID Wallet", MB_OK | MB_ICONERROR);
    return 1;
}

int WINAPI WinMain(HINSTANCE inst, HINSTANCE prev, LPSTR cmdline, int show) {
    static wchar_t root[LONG_PATH], dll[LONG_PATH], app[LONG_PATH];
    (void)inst; (void)prev; (void)cmdline; (void)show;

    DWORD n = GetModuleFileNameW(NULL, root, LONG_PATH);
    wchar_t *slash = (n > 0 && n < LONG_PATH) ? wcsrchr(root, L'\\') : NULL;
    if (!slash) return say(L"XID Wallet could not find its own folder.");
    *slash = 0;
    if (lstrlenW(root) + 40 >= LONG_PATH) return say(L"The XID Wallet folder path is too long. Move the folder somewhere shorter.");
    lstrcpyW(dll, root); lstrcatW(dll, L"\\runtime\\python312.dll");
    lstrcpyW(app, root); lstrcatW(app, L"\\app\\gui\\app.py");

    if (GetFileAttributesW(dll) == INVALID_FILE_ATTRIBUTES || GetFileAttributesW(app) == INVALID_FILE_ATTRIBUTES)
        return say(L"XID Wallet cannot start: its runtime or app folder is missing.\n\n"
                   L"If you opened it from inside the zip, extract the zip first: right-click it, choose Extract All, "
                   L"then open XID Wallet.exe in the extracted folder.\n\n"
                   L"Otherwise keep everything in the XID Wallet folder together.");

    /* altered search path: python312.dll's own dependencies (vcruntime140.dll) load from runtime\ */
    HMODULE py = LoadLibraryExW(dll, NULL, LOAD_WITH_ALTERED_SEARCH_PATH);
    if (!py) return say(L"XID Wallet cannot start: runtime\\python312.dll did not load. Get a fresh copy of XID Wallet.");
    py_main_fn py_main = (py_main_fn)(void (*)(void))GetProcAddress(py, "Py_Main");
    if (!py_main) return say(L"XID Wallet cannot start: runtime\\python312.dll is not the expected Python.");

    int argc = 0;
    wchar_t **argv = CommandLineToArgvW(GetCommandLineW(), &argc);
    if (!argv || argc < 1) return say(L"XID Wallet could not read its command line.");
    wchar_t **args = (wchar_t **)HeapAlloc(GetProcessHeap(), 0, sizeof(wchar_t *) * (argc + 2));
    if (!args) return say(L"XID Wallet is out of memory.");
    args[0] = argv[0];                                   /* [this exe, app.py, the arguments it was given] */
    args[1] = app;
    for (int i = 1; i < argc; i++) args[i + 1] = argv[i];
    args[argc + 1] = NULL;

    int rc = py_main(argc + 1, args);
    if (rc != 0)
        say(L"XID Wallet stopped with an error.\n\n"
            L"To see the error, open the app folder inside the XID Wallet folder and double-click "
            L"\"XID Wallet (debug).cmd\". Your wallet file and seed are not affected.");
    return rc;
}
