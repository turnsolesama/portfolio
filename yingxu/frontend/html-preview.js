/* Content is structurally sanitized by the backend; the frame also has no capabilities. */
(() => {
  'use strict';
  const policy = "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'";
  const style = 'body{margin:24px;color:#263d2e;background:#fff;font:15px/1.7 system-ui,sans-serif;overflow-wrap:anywhere}table{border-collapse:collapse;display:block;max-width:100%;overflow:auto}td,th{border:1px solid #d5dfd6;padding:6px 10px}pre{white-space:pre-wrap}img{max-width:100%}h1,h2,h3{line-height:1.3}';
  window.YingXuHtmlPreview = {document: safe => '<!doctype html><html><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="' + policy + '"><style>' + style + '</style></head><body>' + safe + '</body></html>'};
})();
