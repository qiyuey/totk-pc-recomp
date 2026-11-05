# Personal fork workflow

This repository switched from a single amended local FIX to ordinary focused commits on 2026-11-05. The historical FIX (`08885ec7db3fbb8ebfb9f02576e57ba2ff182dc1`) remains intact. Its commit-message maintenance instructions describe the former workflow and no longer apply.

- Personal fork: https://github.com/qiyuey/totk-pc-recomp
- `origin`: personal fork and default push destination.
- Development branch: `main`, tracking `origin/main`.
- `upstream`: https://github.com/valentderah/totk-pc-recomp, the original project.
- Pre-migration upstream baseline: `c38e0ca13d2bceb0590b195f69a010315913850d`.
- Local recovery refs: `refs/backup/fork-migration-20261105/main` and `refs/backup/fork-migration-20261105/upstream-base`. Retain these locally; do not publish them as extra branches.

Make new commits for subsequent changes. Do not automatically amend the historical FIX, squash the customization history, or force-push published branches. The local `singleFixUpstream` marker has been removed. Do not run the single-FIX workflow unless the user explicitly requests switching back.

Fork publication does not authorize updating the runtime to a newer upstream revision. When an upstream update is requested, fetch and review both repositories, preserve work in progress, and integrate with ordinary merge history. Resolve conflicts by behavior, retaining custom SDL3 frequency-band support, matched headers/library/DLL, and local tooling improvements. Never push directly to the original project.

Before publication, run `python tools/check_content.py --staged` and review the staged files. Keep game dumps, firmware, keys, saves, generated game code, extracted resources, logs and build artifacts outside version control. Record the platform, graphics backend and actual validation performed for runtime/UI changes; software checks do not establish physical controller behavior.

## Migration validation

At the user's request, the migration merged 113 upstream commits through `101132a` with ordinary merge history. The local HD-rumble submission path and custom SDL3 build selection remain present.

The Windows x86-64-v3 build for game 1.4.3 completed with the custom workspace SDL3. Installer bookkeeping (50), installer GUI (35 passed, 2 skipped), prompt overlays (10), and shader-cache packaging (5) checks passed. The rebuilt executable passed `--selftest` with the standard retail pool (`TOTK_APP_POOL=0xcd500000`), `--probe-loader`, and `--probe-kernel`. The earlier selftest with local settings failed its fixed-pool limit assertion; the standard-pool run passed without changing the user's settings.

Content checks passed. Full gameplay, the Vulkan overlay's appearance, the updated shader translator, and real-controller HD-rumble effects were not validated during this migration. Upstream patch-file whitespace was retained unchanged.
