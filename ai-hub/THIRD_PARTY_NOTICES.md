# Third-party notices

AI Hub's Windows desktop executable embeds the following Microsoft WebView2 SDK redistributables:

- Microsoft.Web.WebView2.Core.dll
- Microsoft.Web.WebView2.WinForms.dll
- WebView2Loader.dll

SDK version: 1.0.4191.47. Package SHA-256: `f492bbf547d0da329553b6727435b677579b1e9f91cc9e4a1ad029366d5f23d0`.

The complete Microsoft license is provided in [desktop/WebView2-LICENSE.txt](desktop/WebView2-LICENSE.txt) and embedded in the desktop executable. The WebView2 Runtime is separately installed and is not bundled with AI Hub.

Python and Node.js are not redistributed in this package. Optional Pillow support uses a separately installed library. Model weights and generated images are not distributed with AI Hub.
