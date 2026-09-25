import capture from '../../data/context-examples.json';

/** Serve the exact checked capture, not a second manually maintained evidence copy. */
export function GET() {
  return new Response(JSON.stringify(capture, null, 2) + '\n', {
    headers: { 'Content-Type': 'application/json; charset=utf-8' },
  });
}
