/* Build-time adaptation of the pinned upstream font fallback, never runtime CDN access. */
export function localFontFallback(source) {
  const marker=/`https:\/\/esm\.sh\/[\s\S]*?\/dist\/prod\/`/g;
  let replacements=0;
  const contents=source.replace(marker,()=>{replacements++;return 'new URL("/canvas/",window.location.origin).href';});
  return {contents,replacements};
}
