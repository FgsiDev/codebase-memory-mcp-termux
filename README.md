# codebase-memory-mcp (Termux build)

Build **tidak resmi** dari [DeusData/codebase-memory-mcp](https://github.com/DeusData/codebase-memory-mcp) untuk **Termux (Android, bionic libc)**, dibuild otomatis lewat GitHub Actions memakai Android NDK.

Biner resmi upstream (`linux-*-portable`) gagal dijalankan di Termux, jadi repo ini menyediakan build native Android.

> Semua kredit untuk project upstream (MIT). Repo ini hanya workflow build + install script. Bukan afiliasi dengan DeusData.

## Arsitektur

| Termux (`uname -m`)  | Asset                                    | Status       |
| -------------------- | ---------------------------------------- | ------------ |
| `aarch64`            | `codebase-memory-mcp-termux-arm64`       | utama        |
| `x86_64`             | `codebase-memory-mcp-termux-x86_64`      | utama        |
| `armv7l` / `armv8l`  | `codebase-memory-mcp-termux-arm`         | eksperimental (32-bit) |
| `i686`               | `codebase-memory-mcp-termux-x86`         | eksperimental (32-bit) |

Persyaratan: **Android 9+ (API 28)**. Build 32-bit bisa saja tidak tersedia di release tertentu kalau build-nya gagal.

## Install

Satu baris (auto-detect arsitektur, verifikasi SHA-256):

```bash
curl -fsSL https://raw.githubusercontent.com/FgsiDev/codebase-memory-mcp-termux/main/install-termux.sh | bash
```

Terpasang di `~/.local/bin/codebase-memory-mcp`. Pastikan ada di `PATH`:

```bash
export PATH="$HOME/.local/bin:$PATH"
codebase-memory-mcp --version
```

Opsi (environment variable):

| Variable   | Default                                  | Fungsi                         |
| ---------- | ---------------------------------------- | ------------------------------ |
| `CBM_TAG`  | release terbaru                          | Pasang versi tertentu, mis. `termux-0.12.1-281-gxxxxxxx` |
| `CBM_DIR`  | `~/.local/bin`                           | Folder tujuan                  |
| `CBM_REPO` | `FgsiDev/codebase-memory-mcp-termux`     | Repo sumber release            |

### Manual

1. Unduh asset sesuai arsitektur dari [Releases](../../releases/latest).
2. Cek checksum, ekstrak, pindahkan:

```bash
sha256sum -c codebase-memory-mcp-termux-arm64.tar.gz.sha256
tar xzf codebase-memory-mcp-termux-arm64.tar.gz
mkdir -p ~/.local/bin && mv codebase-memory-mcp ~/.local/bin/
```

## Daftarkan sebagai MCP server

Tambahkan ke konfigurasi MCP client kamu (mis. `~/.claude.json` atau `.mcp.json`). Pakai **path absolut**:

```json
{
  "mcpServers": {
    "codebase-memory-mcp": {
      "command": "/data/data/com.termux/files/home/.local/bin/codebase-memory-mcp",
      "args": []
    }
  }
}
```

Lalu restart client dan minta: *"Index this project"*. Dokumentasi tool lengkap ada di [README upstream](https://github.com/DeusData/codebase-memory-mcp#readme).

## Build sendiri (GitHub Actions)

1. Fork repo ini.
2. Buka **Actions → Build codebase-memory-mcp (Termux all arch) → Run workflow**.
   - `ref`: tag/branch/sha upstream (default `main`).
   - `release`: centang untuk publish ke Releases.
3. Pastikan **Settings → Actions → General → Workflow permissions** = *Read and write*.

Workflow meng-checkout upstream, cross-compile dengan NDK r27c (API 28) per arsitektur, lalu membuat release `termux-<versi>`. Push ke `main` (selain perubahan `.md` / `install-termux.sh`) juga memicu build.

### Build manual di Termux

```bash
pkg install clang make zlib git
git clone https://github.com/DeusData/codebase-memory-mcp.git
cd codebase-memory-mcp
scripts/build.sh
# hasil: build/c/codebase-memory-mcp
```

## Catatan teknis

- Dilink dengan libc++ statis, jadi tidak butuh `libc++_shared.so`.
- mimalloc global override dimatikan (bionic).
- `-Werror` upstream dimatikan karena beberapa warning khusus bionic.

## Troubleshooting

| Masalah | Solusi |
| ------- | ------ |
| `cannot execute binary` / `not found` | Cek arsitektur: `uname -m`, pasang asset yang cocok |
| `codebase-memory-mcp: command not found` | Tambahkan `~/.local/bin` ke `PATH` |
| Gagal di Android < 9 | Build butuh API 28; gunakan build native di Termux (lihat di atas) |
| Asset 32-bit tidak ada di release | Build eksperimental gagal; cek log Actions |

## Lisensi

Mengikuti upstream: [MIT](https://github.com/DeusData/codebase-memory-mcp/blob/main/LICENSE).
