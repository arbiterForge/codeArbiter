/** A native fragment navigation may revalidate the unchanged document icon.
 * Classify only that exact browser image read, never a fetch/XHR or payload.
 * This is a test observation boundary, not a runtime network permission rule.
 */
export interface ChapterRequest {
  url: string;
  method: string;
  resourceType: string;
  body: string | null;
  headers: Record<string, string>;
}

export function isNativeIconRead(request: ChapterRequest, iconUrl: string): boolean {
  return request.url === iconUrl && request.method === 'GET' && request.body === null
    && request.resourceType === 'other'
    && request.headers['sec-fetch-dest'] === 'image'
    && request.headers['sec-fetch-mode'] === 'no-cors'
    && request.headers['sec-fetch-site'] === 'same-origin';
}
