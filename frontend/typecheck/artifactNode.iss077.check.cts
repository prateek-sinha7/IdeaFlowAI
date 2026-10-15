/**
 * ISS-077 red/green check (cannot be xfail'd: it is a compile check).
 * A node literal in the real wire shape, assigned to ArtifactNode.
 * Run: ./node_modules/.bin/tsc -p typecheck/tsconfig.iss077.json
 * RED today (errors on task_id, derived_from, children, retention); GREEN once the
 * type is corrected. Gate: no error from this file.
 */
import type { ArtifactNode } from "../src/lib/api";

const child: ArtifactNode = {
  id: "b", kind: "spec", producer_step: "s", producer_agent: "s",
  task_id: null, content_hash: "h2", version: 2, visibility: "private",
  retention: "run_ttl", location: "l", parents: [], derived_from: "a", children: [],
};

export const root: ArtifactNode = {
  id: "a", kind: "spec", producer_step: "s", producer_agent: "s",
  task_id: null, content_hash: "h1", version: 1, visibility: "private",
  retention: "run_ttl", location: "l", parents: [], derived_from: null, children: [child],
};
