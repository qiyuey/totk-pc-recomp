# Personal fork workflow

This repository switched from a single amended local FIX to ordinary focused commits on 2026-11-05. The historical FIX (`08885ec7db3fbb8ebfb9f02576e57ba2ff182dc1`) remains intact. Its commit-message maintenance instructions describe the former workflow and no longer apply.

- Personal fork: https://github.com/qiyuey/totk-pc-recomp
- `origin`: personal fork and default push destination.
- `upstream`: https://github.com/valentderah/totk-pc-recomp, the original project.
- Pre-migration upstream baseline: `c38e0ca13d2bceb0590b195f69a010315913850d`.
- Local recovery refs: `refs/backup/fork-migration-20261105/main` and `refs/backup/fork-migration-20261105/upstream-base`. Retain these locally; do not publish them as extra branches.

Make new commits for subsequent changes. Do not automatically amend the historical FIX, squash the customization history, or force-push published branches. The local `singleFixUpstream` marker has been removed. Do not run the single-FIX workflow unless the user explicitly requests switching back.

Fork publication does not authorize updating the runtime to a newer upstream revision. When an upstream update is requested, fetch and review both repositories, preserve work in progress, and integrate with ordinary merge history. Resolve conflicts by behavior, retaining custom SDL3 frequency-band support, matched headers/library/DLL, and local tooling improvements. Never push directly to the original project.

Before publication, run `python tools/check_content.py --staged` and review the staged files. Keep game dumps, firmware, keys, saves, generated game code, extracted resources, logs and build artifacts outside version control. Record the platform, graphics backend and actual validation performed for runtime/UI changes; software checks do not establish physical controller behavior.
