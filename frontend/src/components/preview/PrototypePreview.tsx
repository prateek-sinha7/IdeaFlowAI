"use client";

import { useState } from "react";
import { Layout, Navigation, Zap, Box, Layers, Database, Monitor } from "lucide-react";
import type { PrototypeDefinition, PrototypeComponent } from "@/types";

interface PrototypePreviewProps {
  content?: string;
  isStreaming?: boolean;
}

const COMPONENT_TYPE_COLORS: Record<string, string> = {
  button: "text-blue-400 bg-blue-400/10",
  input: "text-emerald-400 bg-emerald-400/10",
  form: "text-purple-400 bg-purple-400/10",
  header: "text-amber-400 bg-amber-400/10",
  nav: "text-cyan-400 bg-cyan-400/10",
  card: "text-rose-400 bg-rose-400/10",
  list: "text-orange-400 bg-orange-400/10",
  modal: "text-indigo-400 bg-indigo-400/10",
  table: "text-teal-400 bg-teal-400/10",
  sidebar: "text-violet-400 bg-violet-400/10",
  avatar: "text-pink-400 bg-pink-400/10",
  badge: "text-lime-400 bg-lime-400/10",
  tabs: "text-sky-400 bg-sky-400/10",
  text: "text-slate-400 bg-slate-400/10",
  link: "text-blue-300 bg-blue-300/10",
  logo: "text-amber-300 bg-amber-300/10",
  default: "text-grey/70 bg-grey/10",
};

const STATE_COLORS: Record<string, string> = {
  loading: "text-blue-400 bg-blue-400/10 border-blue-400/20",
  empty: "text-grey/60 bg-grey/10 border-grey/20",
  error: "text-rose-400 bg-rose-400/10 border-rose-400/20",
  success: "text-emerald-400 bg-emerald-400/10 border-emerald-400/20",
};

function getComponentColor(type: string): string {
  const lower = type.toLowerCase();
  for (const [key, value] of Object.entries(COMPONENT_TYPE_COLORS)) {
    if (key !== "default" && lower.includes(key)) return value;
  }
  return COMPONENT_TYPE_COLORS.default;
}

/**
 * Renders the UI prototype definition showing Pages with screen states,
 * Components with data flow, Navigation with icons, and Behavior.
 * Features connecting lines, color-coded types, state tabs, and data flow descriptions.
 */
export function PrototypePreview({ content, isStreaming }: PrototypePreviewProps) {
  const [activeStates, setActiveStates] = useState<Record<number, string>>({});

  if (!content) {
    return (
      <div className="flex h-full flex-col items-center justify-center px-6">
        <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-navy/50 border border-grey/10 mb-4">
          <Layout className="h-7 w-7 text-grey/40" />
        </div>
        <p className="text-sm font-medium text-grey/60 mb-1">No Prototype Yet</p>
        <p className="text-xs text-grey/40 text-center max-w-[200px]">
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
    // While streaming, always show loading — don't flash parse errors
    if (isStreaming) {
      return (
        <div className="flex h-full flex-col items-center justify-center px-6">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-navy/50 border border-grey/10 mb-3 animate-pulse">
            <Layout className="h-5 w-5 text-grey/50" />
          </div>
          <p className="text-xs text-grey/50">Generating prototype...</p>
        </div>
      );
    }
    parseError =
      e instanceof Error ? e.message : "Failed to parse prototype data";
    prototype = { pages: [], navigation: { routes: {} }, behavior: { interactions: {} } };
  }

  if (parseError) {
    return (
      <div className="flex h-full items-center justify-center p-4">
        <div className="rounded-xl border border-grey/20 bg-navy/30 p-4 text-center">
          <p className="text-sm text-grey">{parseError}</p>
        </div>
      </div>
    );
  }

  const handleStateChange = (pageIdx: number, state: string) => {
    setActiveStates(prev => ({ ...prev, [pageIdx]: state }));
  };

  return (
    <div className="space-y-5 overflow-y-auto p-4">
      {/* Pages Section */}
      <section>
        <div className="flex items-center gap-2 mb-3">
          <div className="flex h-5 w-5 items-center justify-center rounded-md bg-blue-400/10">
            <Layers className="h-3 w-3 text-blue-400" />
          </div>
          <h2 className="text-xs font-bold uppercase tracking-wider text-grey/80">
            Pages
          </h2>
          <span className="text-[10px] text-grey/40 ml-auto">{prototype.pages.length} pages</span>
        </div>
        <div className="space-y-3">
          {prototype.pages.map((page, pageIdx) => (
            <div
              key={pageIdx}
              className="rounded-xl border border-grey/15 bg-gradient-to-br from-navy/30 to-black/40 p-3"
            >
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm font-semibold text-white">
                  {page.name}
                </span>
                <span className="rounded-md bg-black/50 px-2 py-0.5 text-[10px] font-mono text-grey/70 border border-grey/10">
                  {page.route}
                </span>
              </div>

              {/* Screen States as tabs */}
              {page.states && Object.keys(page.states).length > 0 && (
                <div className="mb-3">
                  <div className="flex items-center gap-1 mb-1.5">
                    <Monitor className="h-2.5 w-2.5 text-grey/40" />
                    <span className="text-[9px] font-semibold uppercase tracking-wider text-grey/40">States</span>
                  </div>
                  <div className="flex gap-1 flex-wrap">
                    {Object.entries(page.states).map(([state, description]) => {
                      const isActive = (activeStates[pageIdx] || "success") === state;
                      const colorClass = STATE_COLORS[state] || STATE_COLORS.success;
                      return (
                        <button
                          key={state}
                          onClick={() => handleStateChange(pageIdx, state)}
                          className={`rounded-md px-2 py-0.5 text-[9px] font-medium border transition-all duration-150 ${
                            isActive
                              ? colorClass
                              : "text-grey/40 bg-black/20 border-grey/10 hover:border-grey/20"
                          }`}
                          title={description}
                        >
                          {state}
                        </button>
                      );
                    })}
                  </div>
                  {/* Show active state description */}
                  {page.states[activeStates[pageIdx] || "success"] && (
                    <p className="mt-1.5 text-[10px] text-grey/50 italic pl-1">
                      {page.states[activeStates[pageIdx] || "success"]}
                    </p>
                  )}
                </div>
              )}

              {/* Component tree */}
              {page.components.length > 0 && (
                <div className="mt-2 ml-1">
                  <ComponentTree components={page.components} depth={0} />
                </div>
              )}
            </div>
          ))}
          {prototype.pages.length === 0 && (
            <p className="text-xs text-grey/50 italic">No pages defined.</p>
          )}
        </div>
      </section>

      {/* Navigation Section */}
      <section>
        <div className="flex items-center gap-2 mb-3">
          <div className="flex h-5 w-5 items-center justify-center rounded-md bg-cyan-400/10">
            <Navigation className="h-3 w-3 text-cyan-400" />
          </div>
          <h2 className="text-xs font-bold uppercase tracking-wider text-grey/80">
            Navigation
          </h2>
        </div>
        <div className="rounded-xl border border-grey/15 bg-gradient-to-br from-navy/30 to-black/40 p-3">
          {/* New-style navigation with items array */}
          {prototype.navigation.items && prototype.navigation.items.length > 0 ? (
            <ul className="space-y-1.5">
              {prototype.navigation.items.map((item) => (
                <li key={item.label} className="flex items-center gap-2 text-xs">
                  {item.icon && (
                    <span className="text-[10px] text-grey/40 font-mono">{item.icon}</span>
                  )}
                  <span className="font-medium text-white">{item.label}</span>
                  <span className="flex-1 border-b border-dashed border-grey/15" />
                  <span className="font-mono text-[10px] text-grey/60">{item.route}</span>
                </li>
              ))}
            </ul>
          ) : prototype.navigation.routes && Object.keys(prototype.navigation.routes).length > 0 ? (
            <ul className="space-y-1.5">
              {Object.entries(prototype.navigation.routes).map(
                ([name, route]) => (
                  <li key={name} className="flex items-center gap-2 text-xs">
                    <span className="font-medium text-white">{name}</span>
                    <span className="flex-1 border-b border-dashed border-grey/15" />
                    <span className="font-mono text-[10px] text-grey/60">{route}</span>
                  </li>
                )
              )}
            </ul>
          ) : (
            <p className="text-xs text-grey/50 italic">No routes defined.</p>
          )}
          {prototype.navigation.defaultRoute && (
            <p className="mt-2 text-[10px] text-grey/50">
              Default: <span className="font-mono text-grey/70">{prototype.navigation.defaultRoute}</span>
            </p>
          )}
          {prototype.navigation.type && (
            <p className="mt-1 text-[10px] text-grey/50">
              Type: <span className="font-mono text-grey/70">{prototype.navigation.type}</span>
            </p>
          )}
        </div>
      </section>

      {/* Behavior Section */}
      <section>
        <div className="flex items-center gap-2 mb-3">
          <div className="flex h-5 w-5 items-center justify-center rounded-md bg-amber-400/10">
            <Zap className="h-3 w-3 text-amber-400" />
          </div>
          <h2 className="text-xs font-bold uppercase tracking-wider text-grey/80">
            Behavior
          </h2>
        </div>
        <div className="rounded-xl border border-grey/15 bg-gradient-to-br from-navy/30 to-black/40 p-3">
          {Object.keys(prototype.behavior.interactions).length > 0 ? (
            <div className="space-y-1.5">
              <h3 className="text-[10px] font-semibold uppercase tracking-wider text-grey/50 mb-2">Interactions</h3>
              <ul className="space-y-1.5">
                {Object.entries(prototype.behavior.interactions).map(
                  ([trigger, action]) => (
                    <li key={trigger} className="flex items-start gap-2 text-xs">
                      <span className="font-medium text-white flex-shrink-0">{trigger}</span>
                      <span className="text-grey/40 flex-shrink-0">&rarr;</span>
                      <span className="text-grey/70">{action}</span>
                    </li>
                  )
                )}
              </ul>
            </div>
          ) : (
            <p className="text-xs text-grey/50 italic">No interactions defined.</p>
          )}
          {prototype.behavior.animations &&
            Object.keys(prototype.behavior.animations).length > 0 && (
              <div className="mt-3 pt-3 border-t border-grey/10 space-y-1.5">
                <h3 className="text-[10px] font-semibold uppercase tracking-wider text-grey/50 mb-2">Animations</h3>
                <ul className="space-y-1.5">
                  {Object.entries(prototype.behavior.animations).map(
                    ([element, animation]) => (
                      <li
                        key={element}
                        className="flex items-start gap-2 text-xs"
                      >
                        <span className="font-medium text-white flex-shrink-0">{element}</span>
                        <span className="text-grey/40 flex-shrink-0">&rarr;</span>
                        <span className="text-grey/70">{animation}</span>
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
 * Recursively renders a component tree with connecting lines and data flow.
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
      {components.map((comp, idx) => {
        const colorClass = getComponentColor(comp.type);
        const isLast = idx === components.length - 1;
        return (
          <li key={idx} className="relative">
            {/* Connecting line */}
            {depth > 0 && (
              <div className="absolute left-0 top-0 bottom-0 flex flex-col items-center" style={{ left: `${(depth - 1) * 16 + 4}px` }}>
                <div className={`w-px bg-grey/20 ${isLast ? "h-3" : "h-full"}`} />
              </div>
            )}
            <div className="flex items-center gap-2" style={{ paddingLeft: `${depth * 16}px` }}>
              {depth > 0 && (
                <div className="flex items-center">
                  <div className="w-2.5 h-px bg-grey/20" />
                </div>
              )}
              <span className={`inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[10px] font-medium ${colorClass}`}>
                <Box className="h-2.5 w-2.5" />
                {comp.type}
              </span>
              {Object.keys(comp.props).length > 0 && (
                <span className="text-[10px] text-grey/40 font-mono truncate max-w-[120px]">
                  {Object.entries(comp.props)
                    .filter(([key]) => key !== "responsive" && key !== "ariaLabel" && typeof comp.props[key] === "string")
                    .map(([key, val]) => `${key}=${JSON.stringify(val)}`)
                    .slice(0, 2)
                    .join(" ")}
                </span>
              )}
            </div>
            {/* Data flow description */}
            {comp.dataFlow && (
              <div className="flex items-start gap-1 mt-0.5" style={{ paddingLeft: `${depth * 16 + (depth > 0 ? 20 : 0)}px` }}>
                <Database className="h-2.5 w-2.5 text-grey/30 flex-shrink-0 mt-0.5" />
                <span className="text-[9px] text-grey/40 italic leading-tight">{comp.dataFlow}</span>
              </div>
            )}
            {comp.children && comp.children.length > 0 && (
              <ComponentTree components={comp.children} depth={depth + 1} />
            )}
          </li>
        );
      })}
    </ul>
  );
}
