import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

export function middleware(request: NextRequest) {
  if (request.nextUrl.pathname === "/workflow/create") {
    const mode = request.nextUrl.searchParams.get("mode");

    if (mode) {
      // Construct a fresh URL with only the pathname, no query params
      return NextResponse.redirect(new URL(`/create/${mode}`, request.url));
    }
    // If mode is missing, pass the request through unchanged
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/workflow/create"],
};
