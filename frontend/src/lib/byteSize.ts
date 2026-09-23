/**
 * UTF-8 byte size of a string — the SINGLE source for every "how big is this
 * content" label (ISS-351 and its siblings ISS-587/588/589).
 *
 * `String.prototype.length` counts UTF-16 code units, not bytes. Any multi-byte
 * UTF-8 character (em dash `—`, arrow `→`, accented letters) makes a
 * `.length`-derived size SMALLER than the bytes a download actually delivers,
 * and — where a size CAP is gated on it — lets an over-cap payload through.
 */
const encoder = new TextEncoder();

export function utf8Bytes(text: string): number {
  return encoder.encode(text).length;
}
