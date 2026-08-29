import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

export function proxy(request: NextRequest) {
  if (request.nextUrl.pathname === "/workflow/create") {
    // ISS-250: `.get("mode")` is `null` when the key is absent and `""` when it
    // is present but empty — both are falsy, and the old passthrough branch
    // gave them no destination at all, so `/workflow/create` stayed live and
    // uncanonicalized. Default to the same family `page.tsx` already renders
    // for an unresolved mode, so EVERY request to this route canonicalizes
    // through the one mechanism instead of two divergent ones.
    const mode = request.nextUrl.searchParams.get("mode") || "prototype";

    // Construct a fresh URL with only the pathname, no query params.
    // ISS-227: `mode` is untrusted query input, so it is encoded as ONE path
    // segment before interpolation — same as `createRouteForType` and
    // `routes.workflowCanvas` already do. Raw, a `../` (or `%2e%2e%2f`)
    // segment is resolved by `new URL()` and escapes /create/* entirely,
    // landing on unrelated real routes such as /admin.
    return NextResponse.redirect(
      new URL(`/create/${encodeURIComponent(mode)}`, request.url),
    );
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/workflow/create"],
};
