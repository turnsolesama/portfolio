# 当前仓库职责：工具总入口

- 自 2026-09-12 起，每个工具在独立仓库开发与发布；映射见 docs/GITHUB_PROJECTS.md。用户已选择独立仓库方案，本段优先于下方旧的单仓库布局说明。
- 本仓库仅维护导航、历史说明与兼容下载。不要向这里继续发布应用新版本。
- 旧应用目录与 releases 文件保留以兼容已有链接；修改业务代码应进入相应独立仓库，不在存档目录继续开发。
- 旧提交与历史 Release 不删除，不强制改写历史。保持现有 main 原始下载地址可用。

---

以下为迁移前约定，仅供维护历史文件时参考。

# Software repository conventions

- Keep each application in its own folder: `frameweave/`, `yingxu/`, `ai-hub/`, `codex-switcher/`, `proxy-switch/`, and `video-catch/`. The repository README is a designed Chinese overview and directory; each application has its own detailed feature and usage page.
- Each application owns its source, usage instructions, and `releases/` packages. Preserve existing package paths and historical versions.
- Public ZIP download links must use `https://raw.githubusercontent.com/turnsolesama/portfolio/main/<package-path>` or a verified GitHub Release asset URL. Do not route ZIP links through `blob/` pages or relative `?raw=true` links.
- Before publishing download changes, fetch each current package, verify its byte size, SHA-256, ZIP integrity, and single-application root folder. Check that local Markdown destinations exist.
- Documentation-only changes require link/package verification, not application startup or changes to real user settings.
- Follow each application's nearest AGENTS.md for its build and test commands. Never publish local galleries, weights, credentials, databases, proxy rules, or personal configuration.
- User-facing project categories: Local AI Systems (FrameWeave in `frameweave/`, keeping a standalone project structure), Asset Management Systems (YingXu and AI Hub), Tools (Codex Switcher, FlowSwitch, and VideoCatch). Preserve physical paths and existing download URLs when changing category navigation.
