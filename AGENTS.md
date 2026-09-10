# Software repository conventions

- Keep each application in its own folder: `frameweave/`, `yingxu/`, `ai-hub/`, `codex-switcher/`, and `proxy-switch/`. The repository README is a designed Chinese overview and directory; each application has its own detailed feature and usage page.
- Each application owns its source, usage instructions, and `releases/` packages. Preserve existing package paths and historical versions.
- Public ZIP download links must use `https://raw.githubusercontent.com/turnsolesama/portfolio/main/<package-path>` or a verified GitHub Release asset URL. Do not route ZIP links through `blob/` pages or relative `?raw=true` links.
- Before publishing download changes, fetch each current package, verify its byte size, SHA-256, ZIP integrity, and single-application root folder. Check that local Markdown destinations exist.
- Documentation-only changes require link/package verification, not application startup or changes to real user settings.
- Follow each application's nearest AGENTS.md for its build and test commands. Never publish local galleries, weights, credentials, databases, proxy rules, or personal configuration.
- User-facing project categories: Local AI Systems (FrameWeave in `frameweave/`, keeping a standalone project structure), Asset Management Systems (YingXu and AI Hub), Tools (Codex Switcher and FlowSwitch). Preserve physical paths and existing download URLs when changing category navigation.
