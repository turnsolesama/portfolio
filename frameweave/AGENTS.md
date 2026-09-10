# FrameWeave development

- Reply in Chinese for this project. This is an independently written lightweight AI canvas client.
- Never copy YUH Studio implementation, branding, advertisements, user history, configuration, or weights into this repository.
- Use Python 3.11+ standard library for the local HTTP service, plain ES modules/CSS for the canvas. No runtime npm dependencies.
- Keep all runtime user data outside the source tree; tests use temporary directories.
- Validation: `python -m unittest discover -s tests -v`; `node --test tests/*.test.mjs`; `python -m compileall -q frameweave`; `node --check web/app.js`.
- Bind only to loopback. Validate Host, Origin and CSRF token on writes. Backend connections are loopback-only in v0.1.
- Publish only source, documentation, a clean release archive and manifests. Never publish local model paths, user media, tokens, cache, or private inspection evidence.
- Do not claim generation quality/speed from protocol or mock tests. Report real GPU generation separately.
- Keep docs/DEVELOPMENT_LOG.md current with each change's scope, decisions, issues, validation evidence and outstanding limits. Record private paths, prompts and temporary runtime details only outside the public project tree.
- Workflow packages are data-only JSON with explicit scalar/image bindings; importing must never submit a job. Preserve stable package identity and old canvas compatibility, and validate live node schemas before generation.
