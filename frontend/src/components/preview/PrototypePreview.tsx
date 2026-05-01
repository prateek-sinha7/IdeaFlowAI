"use client";

import type { PrototypeDefinition, PrototypeComponent } from "@/types";

interface PrototypePreviewProps {
  content?: string;
}

/**
 * Renders the UI prototype definition showing Pages, Components,
 * Navigation, and Behavior in a structured tree/list view.
 */
export function PrototypePreview({ content }: PrototypePreviewProps) {
  if (!content) {
    return (
      <div className="flex h-full items-center justify-center">
        <p className="text-sm text-grey">
          Prototype content will appear here once generation begins.
        </p>
      </div>
    );
  }

  let prototype: PrototypeDefinition;
  let parseError: string | null = null;

  try {
    prototype = JSON.parse(content) as PrototypeDefinition;
  } catch (e) {
    parseError =
      e instanceof Error ? e.message : "Failed to parse prototype data";
    prototype = { pages: [], navigation: { routes: {} }, behavior: { interactions: {} } };
  }

  if (parseError) {
    return (
      <div className="flex h-full items-center justify-center p-4">
        <div className="rounded-lg border border-grey/30 bg-navy/30 p-4 text-center">
          <p className="text-sm text-grey">{parseError}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4 overflow-y-auto p-4">
      {/* Pages Section */}
      <section>
        <h2 className="mb-2 text-sm font-bold uppercase tracking-wide text-grey">
          Pages
        </h2>
        <div className="space-y-2">
          {prototype.pages.map((page, pageIdx) => (
            <div
              key={pageIdx}
              className="rounded border border-grey/20 bg-navy/30 p-3"
            >
              <div className="flex items-center justify-between">
                <span className="text-sm font-semibold text-white">
                  {page.name}
                </span>
                <span className="rounded bg-black/40 px-2 py-0.5 text-xs text-grey">
                  {page.route}
                </span>
              </div>
              {page.components.length > 0 && (
                <div className="mt-2 pl-3">
                  <ComponentTree components={page.components} depth={0} />
                </div>
              )}
            </div>
          ))}
          {prototype.pages.length === 0 && (
            <p className="text-xs text-grey">No pages defined.</p>
          )}
        </div>
      </section>

      {/* Navigation Section */}
      <section>
        <h2 className="mb-2 text-sm font-bold uppercase tracking-wide text-grey">
          Navigation
        </h2>
        <div className="rounded border border-grey/20 bg-navy/30 p-3">
          {Object.keys(prototype.navigation.routes).length > 0 ? (
            <ul className="space-y-1">
              {Object.entries(prototype.navigation.routes).map(
                ([name, route]) => (
                  <li key={name} className="flex items-center gap-2 text-xs">
                    <span className="text-white">{name}</span>
                    <span className="text-grey">→</span>
                    <span className="text-grey">{route}</span>
                  </li>
                )
              )}
            </ul>
          ) : (
            <p className="text-xs text-grey">No routes defined.</p>
          )}
          {prototype.navigation.defaultRoute && (
            <p className="mt-2 text-xs text-grey">
              Default: {prototype.navigation.defaultRoute}
            </p>
          )}
        </div>
      </section>

      {/* Behavior Section */}
      <section>
        <h2 className="mb-2 text-sm font-bold uppercase tracking-wide text-grey">
          Behavior
        </h2>
        <div className="rounded border border-grey/20 bg-navy/30 p-3">
          {Object.keys(prototype.behavior.interactions).length > 0 ? (
            <div className="space-y-1">
              <h3 className="text-xs font-semibold text-white">Interactions</h3>
              <ul className="space-y-1 pl-2">
                {Object.entries(prototype.behavior.interactions).map(
                  ([trigger, action]) => (
                    <li key={trigger} className="flex items-start gap-2 text-xs">
                      <span className="text-white">{trigger}</span>
                      <span className="text-grey">→</span>
                      <span className="text-grey">{action}</span>
                    </li>
                  )
                )}
              </ul>
            </div>
          ) : (
            <p className="text-xs text-grey">No interactions defined.</p>
          )}
          {prototype.behavior.animations &&
            Object.keys(prototype.behavior.animations).length > 0 && (
              <div className="mt-2 space-y-1">
                <h3 className="text-xs font-semibold text-white">Animations</h3>
                <ul className="space-y-1 pl-2">
                  {Object.entries(prototype.behavior.animations).map(
                    ([element, animation]) => (
                      <li
                        key={element}
                        className="flex items-start gap-2 text-xs"
                      >
                        <span className="text-white">{element}</span>
                        <span className="text-grey">→</span>
                        <span className="text-grey">{animation}</span>
                      </li>
                    )
                  )}
                </ul>
              </div>
            )}
        </div>
      </section>
    </div>
  );
}

/**
 * Recursively renders a component tree.
 */
function ComponentTree({
  components,
  depth,
}: {
  components: PrototypeComponent[];
  depth: number;
}) {
  return (
    <ul className="space-y-1">
      {components.map((comp, idx) => (
        <li key={idx} style={{ paddingLeft: `${depth * 8}px` }}>
          <div className="flex items-center gap-2">
            <span className="h-1 w-1 rounded-full bg-grey/60" />
            <span className="text-xs font-medium text-white">{comp.type}</span>
            {Object.keys(comp.props).length > 0 && (
              <span className="text-xs text-grey">
                ({Object.keys(comp.props).join(", ")})
              </span>
            )}
          </div>
          {comp.children && comp.children.length > 0 && (
            <ComponentTree components={comp.children} depth={depth + 1} />
          )}
        </li>
      ))}
    </ul>
  );
}
