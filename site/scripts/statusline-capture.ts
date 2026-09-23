/** Decode only the renderer's bounded SGR color/style sequences. Never emit HTML from a capture. */
import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
export interface TerminalToken { text: string; foreground: string; background: string; bold: boolean }
export function terminalTokens(value: string): TerminalToken[] {
  if (value.length > 100_000) throw new Error('Statusline capture exceeds the reviewed bound');
  const tokens: TerminalToken[] = [];
  let foreground = 'inherit', background = 'transparent', bold = false, offset = 0;
  const expression = /\u001b\[([0-9;]*)m/g;
  function text(end: number) {
    const plain = value.slice(offset, end);
    if (/[\u0000-\u0008\u000b-\u001f\u007f]/.test(plain)) throw new Error('Unsupported terminal control');
    if (plain) tokens.push({ text: plain, foreground, background, bold });
  }
  for (const match of value.matchAll(expression)) {
    text(match.index!);
    const codes = (match[1] || '0').split(';').map(Number);
    for (let i = 0; i < codes.length; i++) {
      const code = codes[i];
      if (code === 0) { foreground = 'inherit'; background = 'transparent'; bold = false; }
      else if (code === 1) bold = true;
      else if (code === 22) bold = false;
      else if (code === 39) foreground = 'inherit';
      else if (code === 49) background = 'transparent';
      else if (code === 2 || code === 3 || code === 23) { /* Dim/italic do not change the captured text. */ }
      else if ((code === 38 || code === 48) && codes[i + 1] === 2 && codes.slice(i + 2, i + 5).length === 3) {
        const rgb = codes.slice(i + 2, i + 5);
        if (!rgb.every((channel) => Number.isInteger(channel) && channel >= 0 && channel <= 255)) throw new Error('Invalid RGB');
        const color = `rgb(${rgb.join(' ')})`;
        if (code === 38) foreground = color; else background = color;
        i += 4;
      } else throw new Error(`Unsupported SGR ${code}`);
    }
    offset = match.index! + match[0].length;
  }
  text(value.length);
  return tokens;
}
export function loadThemeCaptures() {
  const file = JSON.parse(readFileSync(resolve(process.cwd(), 'public/examples/statusline-themes.json'), 'utf8')) as {
    boundary: string; source_commit: string; renderer: string; renderer_sha256: string;
    captures: Array<{ theme: string; ansi: string; sha256: string }>;
  };
  if (file.captures.map((capture) => capture.theme).join(',') !== 'violet,blue,green,amber,mono') throw new Error('Theme inventory mismatch');
  return { ...file, captures: file.captures.map((capture) => {
    if (createHash('sha256').update(capture.ansi).digest('hex') !== capture.sha256) throw new Error('Theme capture digest mismatch');
    return { ...capture, tokens: terminalTokens(capture.ansi) };
  }) };
}
