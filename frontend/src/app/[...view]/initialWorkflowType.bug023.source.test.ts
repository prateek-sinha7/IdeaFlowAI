import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import ts from "typescript";
import { parseViewPath, routes } from "@/lib/routes";

// BUG-023 / ISS-916 — a cold /create/app must seed workflowType "app_builder".
// initialWorkflowTypeFor is module-private in a Next page with no mount harness,
// so slice it out of page.tsx and transpile it (source-test technique).

const page = readFileSync(resolve(__dirname, "page.tsx"), "utf8");
const start = page.indexOf("function initialWorkflowTypeFor(");
const fnSrc = page.slice(start, page.indexOf("\n}\n", start) + 3);
const js = ts.transpileModule(fnSrc, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText;
const initialWorkflowTypeFor = new Function(`${js}; return initialWorkflowTypeFor;`)() as (
  p: ReturnType<typeof parseViewPath>,
) => string | undefined;
const typeFor = (url: string) => initialWorkflowTypeFor(parseViewPath(url.split("/").filter(Boolean)));

describe("BUG-023 initialWorkflowTypeFor maps the named create screens", () => {
  it("/create/app seeds app_builder", () => {
    expect(typeFor("/create/app")).toBe("app_builder");
  });
  it("/create/user-stories seeds user_stories", () => {
    expect(typeFor("/create/user-stories")).toBe("user_stories");
  });
  it("generic /create/<type> keeps passing the type through", () => {
    expect(typeFor("/create/ex_A2_branch")).toBe("ex_A2_branch");
  });
  it("non-launch screens seed nothing", () => {
    expect(typeFor("/create")).toBeUndefined();
    expect(typeFor("/create/ppt")).toBeUndefined();
    expect(typeFor("/dashboard")).toBeUndefined();
  });
});

describe("ISS-916 the in-app push target survives the page remount", () => {
  // Home tile / "Edit brief & run again" do router.push(routes.createApp()); the remounted
  // page can only recover the type from that URL.
  it("the URL the app_builder tile pushes seeds app_builder on remount", () => {
    expect(typeFor(routes.createApp())).toBe("app_builder");
  });
});
