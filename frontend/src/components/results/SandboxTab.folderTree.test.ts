import { describe, expect, it } from "vitest";
import { folderLevel } from "./SandboxTab";

const f = (path: string) => ({ path, size: 1 }) as never;

describe("folderLevel — nested sub-folders in All files", () => {
  it("splits direct files from sub-folders, one level at a time", () => {
    const files = [
      f("file-synthesis/1-crimson/gaps.json"),
      f("file-synthesis/1-crimson/shards/s01/status.json"),
      f("file-synthesis/2-amber/gaps.json"),
      f("file-synthesis/index.md"),
    ];
    const top = folderLevel(files, "file-synthesis/");
    expect(top.here.map((x: { path: string }) => x.path)).toEqual(["file-synthesis/index.md"]);
    expect(top.dirs.map(([name, list]) => [name, list.length])).toEqual([
      ["1-crimson", 2],
      ["2-amber", 1],
    ]);
    const crimson = folderLevel(top.dirs[0][1], "file-synthesis/1-crimson/");
    expect(crimson.here.map((x: { path: string }) => x.path)).toEqual([
      "file-synthesis/1-crimson/gaps.json",
    ]);
    expect(crimson.dirs.map(([name]) => name)).toEqual(["shards"]);
  });
});
