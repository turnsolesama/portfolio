# VideoCatch

- Keep source, browser extension, documentation, and release packages in this folder.
- Run `.build/venv/Scripts/python.exe -m unittest discover -s tests -v` for backend and download integration changes.
- Run `node --test tests/extension.test.cjs` for extension changes if Node is available.
- Build the portable Windows app with `.build/venv/Scripts/python.exe build.py`.
- Never bundle captured URLs, cookies, pairing tokens, downloaded videos, or local settings.
- Test with generated local video fixtures; do not change a user's browser profile, proxy, or certificate store.
