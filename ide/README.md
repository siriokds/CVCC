# Web IDE

The IDE owns the browser interface, local HTTP service and user workspace storage.
It imports the project/ROM tools and invokes the compiler through their CLI.
The compiler and toolchain do not import this component.
Commands below are run from the repository root.

## Local Web Workbench

A browser editor is available with syntax coloring, persistent local drafts,
compiler diagnostics with line navigation, Z80 assembly output, ROM download,
and a separate GearSC3000 Web player. It uses no external JavaScript packages.

After building the native frontend, point the server at an existing Web player
build (the directory must contain `core.js` and `core.wasm`):

```sh
./ide/run.sh --player-dist /path/to/GearSF7000/platforms/web/dist
```

Open `http://127.0.0.1:8844`. The square example compiles and starts automatically.
Use **Compila e avvia** or Command/Ctrl+Enter after editing. Source drafts are
stored in the browser, not written over repository examples. The last successful
ROM remains available after an error and is labeled accordingly.

### Open, save and GitHub

**Apri…** opens an existing project folder on this machine or a GitHub project.
**Salva copia…** creates a new folder from the current sources and binary assets;
existing folders are never overwritten. On macOS **Sfoglia…** opens the native
folder chooser; on other systems enter the absolute path. A project has a
`main.cvc` at its root. The Recent list remembers locations, not credentials.

For local folders, **Salva** / Command/Ctrl+S writes the whole project to disk.
The server checks the original content revision before replacing changed files;
external modifications stop the save. Each file is replaced atomically, but a
hardware/I/O failure can still interrupt a multi-file save. Unrelated files are
preserved. Examples remain browser drafts until saved as a personal copy.

For GitHub, install GitHub CLI and sign in using `gh auth login` on the machine
running the local server. Choose an accessible recent repository or enter
`owner/repository`, select a branch (blank uses the default), then use
**Trova progetti CVCC** to choose a folder containing `main.cvc`. This reads the
remote repository directly, without cloning or modifying a local checkout.
Credentials stay in GitHub CLI and are never returned to the browser.

**Salva bozza** / Command/Ctrl+S only stores GitHub edits in this browser.
**Modifiche** shows saved text alongside the draft; **Commit e invia** submits
changed project files as one commit to the displayed branch, attributed to the
authenticated GitHub user. There is no AI coauthor. Unrelated repository files
are preserved. A changed remote branch, missing write permissions or branch
protection stops the operation; force push is never used. Review and commit are
explicit actions, separate from compilation. Browser drafts are recovery copies,
not cloud backups. The storage strip always distinguishes disk, browser and
GitHub states. Reopening a project with a stale draft requires resolving it or
saving a separate copy before writing. After a server restart, reopen from Recent.

Dropbox/Google Drive currently work through their **locally synchronized folders**.
The UI explicitly labels this and does not claim that a disk save has reached the
cloud. Direct browser OAuth integrations are not implemented yet; they require
registering CVCC with each provider. GitHub currently uses the local CLI rather
than hosted OAuth. This workbench remains local, not a hosted service.

Storage tests: `python3 tests/test_workspaces.py` covers disk conflicts, binary
preservation, path restrictions and GitHub commit/race behavior against a fake API.
`python3 tests/test_web.py` exercises real HTTP persistence against the running
workbench. Live remote writes are not required by these tests.

The download menu offers the original image and 8, 16, 32 or 48 KiB files.
Only sizes that fit `ROM_END` (all generated code and ROM data) are enabled.
Exporting never changes the ROM currently running in the player. The original
is byte-for-byte unchanged. Native images have no Sega footer and use verified
0xFF padding to 8, 16, 32 or 48 KiB, within the selected cartridge's ROM window.
Banked ROMs retain their exact size and cannot be resized by the download menu.
The legacy format is recognized separately, including its optional identification footer.
Unknown layouts disable resizing rather than risk dropping meaningful bytes.
`python3 tests/test_rom_exports.py` checks size boundaries and preservation.

The browser sends source to a loopback-only Python service, which invokes the
native compiler pipeline. The returned ROM runs in the separate WebAssembly
player. **The compiler itself is not yet running in WebAssembly.** The editor,
compilation API and player adapter are separate components for a future desktop
or VS Code-style interface. This is a local development server, not a hosted
multi-user compilation service.

Only the two specified player artifacts are served from the external directory;
no emulator code, private game library or WebAssembly binary is copied into this
repository. The player adapter uses its published `_web_*` ABI (project-selected mapper and RAM,
NTSC, RGB565 video, 48 kHz audio). At ROM load, the adapter requests
60 Hz through `_web_set_target_fps` and uses the effective rate returned by the
core. Older player builds without that API retain native timing. Native emulator
validation continues to use the original NTSC/PAL timing. The browser UI does not expose emulator
MCP/debugger controls.

With the workbench running, `python3 tests/test_web.py` verifies compilation,
errors, request origin checks and the static file allowlist. Set
`CVCC_WEB_TEST_PORT` when using a nondefault server port.

## Source layout

- `run.sh`: launch the local service from any working directory.
- `serve.py`: HTTP endpoints, static files, compilation requests and player delivery.
- `workspace_store.py`: local/GitHub persistence and conflict handling.
- `web/`: browser editor, file explorer, persistence UI and external player adapter.

There is no separate frontend build: HTML, CSS and JavaScript are served directly.
Use `PYTHON=/path/to/python3 ./ide/run.sh …` to select Python.
