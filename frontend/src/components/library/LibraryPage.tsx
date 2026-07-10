"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import {
  Search, Clock, Puzzle, Webhook, X, Copy, Check,
  Tag, Zap, BookOpen, ChevronRight,
} from "lucide-react";
import { LIBRARY_AGENTS, CUSTOM_AGENTS } from "@/components/workflow/AgentLibraryData";
import { AgentCapabilitiesModal } from "@/components/workflow/AgentsPopup";
import { SKILLS, SKILL_CATEGORIES, type SkillDef } from "@/data/skills";
import { HOOKS, HOOK_EVENTS, type HookDef } from "@/data/hooks";
import { Tabs, type TabItem } from "@/components/ui/Tabs";
import { Card } from "@/components/ui/Card";
import { Pill } from "@/components/ui/Pill";
import type { AgentDef } from "@/types/index";

const ALL_AGENTS_COMBINED = [...LIBRARY_AGENTS, ...CUSTOM_AGENTS];

type CategoryEntry = { id: string; label: string; section?: boolean };

const CATEGORIES: CategoryEntry[] = [
  { id: "all", label: "All" },
  { id: "user_stories", label: "User Stories" },
  { id: "ppt", label: "Presentation" },
  { id: "prototype", label: "Prototype" },
  { id: "app_builder", label: "App Builder" },
  { id: "migration", label: "Platform", section: true },
  { id: "mulesoft_to_springboot", label: "Mulesoft → Spring Boot" },
  { id: "dotnet_to_azure", label: ".NET → Azure" },
  { id: "custom", label: "Custom" },
];

const MIGRATION_TYPES = new Set(["mulesoft_to_springboot", "dotnet_to_azure"]);

const PIPELINE_LABEL: Record<string, string> = {
  user_stories: "User Stories", ppt: "Presentation", prototype: "Prototype",
  app_builder: "App Builder", custom: "Custom",
  mulesoft_to_springboot: "Mulesoft → Spring Boot", dotnet_to_azure: ".NET → Azure",
};

// Token-based avatar tints (was a retired-hex array) — cycle brand/warm
// surfaces + ink/brand text so every agent chip stays on the Phase-32 palette.
const ICON_TINTS = [
  "bg-brand-fill text-brand",
  "bg-surface-warm text-ink-700",
  "bg-brand-fill text-ink-700",
  "bg-surface-warm text-brand",
  "bg-surface-paper text-ink-600",
  "bg-brand-fill text-ink-600",
];

function getInitials(name: string): string {
  const words = name.replace(/\s+agent$/i, "").split(" ");
  if (words.length === 1) return words[0].slice(0, 2).toUpperCase();
  return (words[0][0] + words[1][0]).toUpperCase();
}

// ─── Skill Detail Modal ───────────────────────────────────────────────────────

function SkillDetailModal({ skill, onClose }: { skill: SkillDef; onClose: () => void }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    await navigator.clipboard.writeText(skill.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  // Parse content into sections for display
  const lines = skill.content.trim().split("\n");
  const sections: { heading: string | null; lines: string[] }[] = [];
  let current: { heading: string | null; lines: string[] } = { heading: null, lines: [] };
  for (const line of lines) {
    if (line.startsWith("# ") && current.lines.length === 0 && !current.heading) {
      current.heading = line.replace(/^#+\s*/, "");
    } else if (line.startsWith("## ")) {
      if (current.heading || current.lines.length > 0) sections.push(current);
      current = { heading: line.replace(/^#+\s*/, ""), lines: [] };
    } else {
      current.lines.push(line);
    }
  }
  if (current.heading || current.lines.length > 0) sections.push(current);

  return (
    <motion.div
      initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
      className="fixed inset-0 z-[80] flex items-center justify-center p-6 bg-[var(--scrim)] backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        onClick={e => e.stopPropagation()}
        className="bg-surface-white rounded-2xl shadow-2xl border border-line-border w-full max-w-2xl overflow-hidden flex flex-col"
        style={{ maxHeight: "88vh" }}
      >
        {/* Header */}
        <div className="px-6 pt-6 pb-4 border-b border-line-divider flex-shrink-0">
          <div className="flex items-start justify-between gap-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-brand-fill border border-brand-border flex items-center justify-center flex-shrink-0">
                <Puzzle className="h-5 w-5 text-brand" />
              </div>
              <div>
                <h2 className="font-sans text-[16px] font-bold text-ink-900 leading-tight">{skill.name}</h2>
                <div className="flex items-center gap-2 mt-1">
                  <Pill className="capitalize text-ink-600">{skill.category}</Pill>
                </div>
              </div>
            </div>
            <div className="flex items-center gap-2 flex-shrink-0">
              <button
                onClick={handleCopy}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[11px] font-semibold transition-all border ${
                  copied
                    ? "bg-ink-900 text-white border-ink-900"
                    : "bg-surface-white text-ink-600 border-line-control hover:bg-surface-warm hover:border-ink-300"
                }`}
              >
                {copied ? <><Check className="h-3 w-3" /> Copied!</> : <><Copy className="h-3 w-3" /> Copy content</>}
              </button>
              <button onClick={onClose} className="h-8 w-8 flex items-center justify-center rounded-lg text-ink-400 hover:text-ink-700 hover:bg-surface-warm transition-all">
                <X className="h-4 w-4" />
              </button>
            </div>
          </div>
          <p className="text-[12px] text-ink-600 leading-relaxed mt-3">{skill.description}</p>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto">
          {/* Formatted content */}
          <div className="px-6 py-4 space-y-4">
            {sections.map((section, i) => (
              <div key={i}>
                {section.heading && (
                  <div className="flex items-center gap-2 mb-2">
                    <Zap className="h-3.5 w-3.5 text-ink-400 flex-shrink-0" />
                    <h3 className="font-sans text-[12px] font-bold text-ink-800 uppercase tracking-wide">{section.heading}</h3>
                  </div>
                )}
                <div className="space-y-1">
                  {section.lines.filter(l => l.trim()).map((line, j) => {
                    const isBullet = line.trim().startsWith("- ") || line.trim().startsWith("* ");
                    const isNumbered = /^\d+\.\s/.test(line.trim());
                    const text = isBullet ? line.trim().replace(/^[-*]\s+/, "") : isNumbered ? line.trim().replace(/^\d+\.\s+/, "") : line.trim();
                    if (!text) return null;
                    if (isBullet || isNumbered) {
                      return (
                        <div key={j} className="flex items-start gap-2.5 py-0.5">
                          <div className="w-1.5 h-1.5 rounded-full bg-ink-400 flex-shrink-0 mt-1.5" />
                          <p className="text-[12px] text-ink-700 leading-relaxed">{text}</p>
                        </div>
                      );
                    }
                    return (
                      <p key={j} className="text-[12px] text-ink-600 leading-relaxed">{text}</p>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>

          {/* Raw content block */}
          <div className="mx-6 mb-4 rounded-xl border border-line-border overflow-hidden">
            <div className="flex items-center justify-between px-4 py-2.5 bg-surface-warm border-b border-line-border">
              <div className="flex items-center gap-2">
                <BookOpen className="h-3.5 w-3.5 text-ink-400" />
                <span className="text-[10px] font-semibold text-ink-500 uppercase tracking-wide">SKILL.md content</span>
              </div>
              <button
                onClick={handleCopy}
                className="flex items-center gap-1 text-[10px] text-ink-400 hover:text-ink-700 transition-colors"
              >
                {copied ? <><Check className="h-3 w-3" /> Copied</> : <><Copy className="h-3 w-3" /> Copy</>}
              </button>
            </div>
            <pre className="px-4 py-3 text-[11px] text-ink-600 leading-relaxed overflow-x-auto whitespace-pre-wrap font-mono bg-surface-white">
              {skill.content}
            </pre>
          </div>

          {/* Footer meta */}
          <div className="px-6 pb-5 space-y-3">
            {/* Tags */}
            <div className="flex items-center gap-2 flex-wrap">
              <Tag className="h-3 w-3 text-ink-400 flex-shrink-0" />
              {skill.tags.map(tag => (
                <Pill key={tag} className="text-ink-500">{tag}</Pill>
              ))}
            </div>
            {/* Compatible agents */}
            <div>
              <p className="text-[10px] font-semibold text-ink-400 uppercase tracking-wide mb-1.5">Compatible with</p>
              <div className="flex flex-wrap gap-1.5">
                {skill.compatible_agents.slice(0, 6).map(id => (
                  <span key={id} className="text-[10px] px-2 py-0.5 rounded bg-surface-warm border border-line-border text-ink-600 font-medium">{id}</span>
                ))}
                {skill.compatible_agents.length > 6 && (
                  <span className="text-[10px] text-ink-400">+{skill.compatible_agents.length - 6} more</span>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>
    </motion.div>
  );
}


// ─── Hook Detail Modal ────────────────────────────────────────────────────────

function HookDetailModal({ hook, onClose }: { hook: HookDef; onClose: () => void }) {
  const [copied, setCopied] = useState(false);

  const copyText = `Hook: ${hook.name}\nEvent: ${hook.event}\nTrigger: ${hook.trigger}\n\n${hook.description}\n\nTags: ${hook.tags.join(", ")}`;

  const handleCopy = async () => {
    await navigator.clipboard.writeText(copyText);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const EVENT_DESCRIPTION: Record<string, string> = {
    PreToolUse: "Runs before a tool is executed. Can inspect or block the operation.",
    PostToolUse: "Runs after a tool completes. Can validate output or trigger follow-up actions.",
    Stop: "Runs at the end of each agent response. Good for batch operations and cleanup.",
    SessionStart: "Runs when a new session begins. Used for context loading and setup.",
    SessionEnd: "Runs when a session ends. Used for state persistence and cleanup.",
  };

  return (
    <motion.div
      initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
      className="fixed inset-0 z-[80] flex items-center justify-center p-6 bg-[var(--scrim)] backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        onClick={e => e.stopPropagation()}
        className="bg-surface-white rounded-2xl shadow-2xl border border-line-border w-full max-w-xl overflow-hidden flex flex-col"
        style={{ maxHeight: "88vh" }}
      >
        {/* Header */}
        <div className="px-6 pt-6 pb-4 border-b border-line-divider flex-shrink-0">
          <div className="flex items-start justify-between gap-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-brand-fill border border-brand-border flex items-center justify-center flex-shrink-0">
                <Webhook className="h-5 w-5 text-brand" />
              </div>
              <div>
                <h2 className="font-sans text-[16px] font-bold text-ink-900 leading-tight">{hook.name}</h2>
                <div className="flex items-center gap-2 mt-1">
                  <Pill className="bg-ink-900 text-white border-transparent">{hook.event}</Pill>
                </div>
              </div>
            </div>
            <div className="flex items-center gap-2 flex-shrink-0">
              <button
                onClick={handleCopy}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[11px] font-semibold transition-all border ${
                  copied
                    ? "bg-ink-900 text-white border-ink-900"
                    : "bg-surface-white text-ink-600 border-line-control hover:bg-surface-warm hover:border-ink-300"
                }`}
              >
                {copied ? <><Check className="h-3 w-3" /> Copied!</> : <><Copy className="h-3 w-3" /> Copy</>}
              </button>
              <button onClick={onClose} className="h-8 w-8 flex items-center justify-center rounded-lg text-ink-400 hover:text-ink-700 hover:bg-surface-warm transition-all">
                <X className="h-4 w-4" />
              </button>
            </div>
          </div>
          <p className="text-[12px] text-ink-600 leading-relaxed mt-3">{hook.description}</p>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto px-6 py-4 space-y-4">
          {/* Event type explanation */}
          <div className="rounded-xl border border-line-divider bg-surface-warm px-4 py-3">
            <div className="flex items-center gap-2 mb-1.5">
              <Zap className="h-3.5 w-3.5 text-ink-400" />
              <p className="text-[10px] font-semibold text-ink-500 uppercase tracking-wide">Event: {hook.event}</p>
            </div>
            <p className="text-[12px] text-ink-600 leading-relaxed">{EVENT_DESCRIPTION[hook.event] ?? "Triggered by the specified event."}</p>
          </div>

          {/* Trigger */}
          <div className="rounded-xl border border-line-divider bg-surface-warm px-4 py-3">
            <p className="text-[10px] font-semibold text-ink-400 uppercase tracking-wide mb-1.5">When it fires</p>
            <p className="text-[12px] text-ink-700 font-medium">{hook.trigger}</p>
          </div>

          {/* How to use */}
          <div>
            <div className="flex items-center gap-2 mb-2.5">
              <BookOpen className="h-3.5 w-3.5 text-ink-400" />
              <p className="text-[10px] font-semibold text-ink-500 uppercase tracking-wide">How to use</p>
            </div>
            <div className="space-y-2">
              {[
                "Attach this hook to agents in the Advanced → Skills & Hooks panel before running a pipeline.",
                "The hook's behaviour will be injected as a guideline into the agent's execution context.",
                `Best suited for: ${hook.compatible_agents.slice(0, 3).join(", ")}${hook.compatible_agents.length > 3 ? " and more" : ""}.`,
              ].map((step, i) => (
                <div key={i} className="flex items-start gap-2.5">
                  <div className="w-5 h-5 rounded-full bg-brand-fill border border-brand-border flex items-center justify-center flex-shrink-0 text-[9px] font-bold text-brand mt-0.5">{i + 1}</div>
                  <p className="text-[12px] text-ink-600 leading-relaxed">{step}</p>
                </div>
              ))}
            </div>
          </div>

          {/* Compatible agents */}
          <div>
            <p className="text-[10px] font-semibold text-ink-400 uppercase tracking-wide mb-2">Compatible agents</p>
            <div className="flex flex-wrap gap-1.5">
              {hook.compatible_agents.map(id => (
                <div key={id} className="flex items-center gap-1 text-[10px] px-2 py-1 rounded-lg bg-surface-warm border border-line-border text-ink-600">
                  <ChevronRight className="h-2.5 w-2.5 text-ink-400" />
                  {id}
                </div>
              ))}
            </div>
          </div>

          {/* Tags */}
          <div className="flex items-center gap-2 flex-wrap pt-1">
            <Tag className="h-3 w-3 text-ink-400 flex-shrink-0" />
            {hook.tags.map(tag => (
              <Pill key={tag} className="text-ink-500">{tag}</Pill>
            ))}
          </div>

        </div>
      </div>
    </motion.div>
  );
}


// ─── LibraryPage ─────────────────────────────────────────────────────────────

export function LibraryPage() {
  const [activeCategory, setActiveCategory] = useState("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedAgent, setSelectedAgent] = useState<{ agent: AgentDef; index: number } | null>(null);
  const [mainTab, setMainTab] = useState<"agents" | "skills" | "hooks">("agents");
  const [skillCategory, setSkillCategory] = useState("all");
  const [skillSearch, setSkillSearch] = useState("");
  const [hookEvent, setHookEvent] = useState("all");
  const [hookSearch, setHookSearch] = useState("");
  const [selectedSkill, setSelectedSkill] = useState<SkillDef | null>(null);
  const [selectedHook, setSelectedHook] = useState<HookDef | null>(null);

  const MAIN_TABS: TabItem[] = [
    { id: "agents", label: `Agents  ${ALL_AGENTS_COMBINED.length}` },
    { id: "skills", label: `Skills  ${SKILLS.length}`, icon: <Puzzle className="h-3.5 w-3.5" /> },
    { id: "hooks", label: `Hooks  ${HOOKS.length}`, icon: <Webhook className="h-3.5 w-3.5" /> },
  ];

  const filteredAgents = ALL_AGENTS_COMBINED.filter(agent => {
    const matchesCategory =
      activeCategory === "all" ||
      (activeCategory === "migration" && MIGRATION_TYPES.has(agent.pipeline_type)) ||
      agent.pipeline_type === activeCategory;
    const matchesSearch = !searchQuery ||
      agent.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      agent.description.toLowerCase().includes(searchQuery.toLowerCase()) ||
      agent.role.toLowerCase().includes(searchQuery.toLowerCase());
    return matchesCategory && matchesSearch;
  }).sort((a, b) => a.pipeline_type.localeCompare(b.pipeline_type) || a.order - b.order);

  const filteredSkills = SKILLS.filter(s => {
    const matchCat = skillCategory === "all" || s.category === skillCategory;
    const matchSearch = !skillSearch ||
      s.name.toLowerCase().includes(skillSearch.toLowerCase()) ||
      s.description.toLowerCase().includes(skillSearch.toLowerCase());
    return matchCat && matchSearch;
  });

  const filteredHooks = HOOKS.filter(h => {
    const matchEvent = hookEvent === "all" || h.event === hookEvent;
    const matchSearch = !hookSearch ||
      h.name.toLowerCase().includes(hookSearch.toLowerCase()) ||
      h.description.toLowerCase().includes(hookSearch.toLowerCase());
    return matchEvent && matchSearch;
  });

  return (
    <div className="flex flex-col h-full bg-surface-paper">
      {/* ── Top bar — always full width, tabs never shift ── */}
      <div className="flex items-center justify-between px-6 py-4 bg-surface-white border-b border-line-border flex-shrink-0">
        <Tabs
          tabs={MAIN_TABS}
          active={mainTab}
          onChange={(id) => setMainTab(id as "agents" | "skills" | "hooks")}
          className="border-b-0"
        />
        <div className="relative w-56">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-ink-400" />
          <input type="text"
            value={mainTab === "agents" ? searchQuery : mainTab === "skills" ? skillSearch : hookSearch}
            onChange={e => {
              if (mainTab === "agents") setSearchQuery(e.target.value);
              else if (mainTab === "skills") setSkillSearch(e.target.value);
              else setHookSearch(e.target.value);
            }}
            placeholder={`Search ${mainTab}...`}
            className="w-full pl-9 pr-4 py-2 text-[12px] text-ink-800 bg-surface-warm border border-line-control rounded-lg focus:outline-none focus:border-brand transition-colors placeholder:text-ink-400"
          />
        </div>
      </div>

      {/* ── Body — sidebar + content side by side ── */}
      <div className="flex flex-1 overflow-hidden">
        {/* Left sidebar — always rendered, content changes per tab */}
        <div className="w-[200px] flex-shrink-0 bg-surface-white border-r border-line-border flex flex-col py-5">
          {mainTab === "agents" && (
            <>
              <p className="text-[10px] font-semibold text-ink-400 uppercase tracking-[0.15em] px-5 mb-3">Categories</p>
              <nav className="flex flex-col gap-0.5 px-3">
                {CATEGORIES.map(cat => {
                  const count = cat.id === "all" ? ALL_AGENTS_COMBINED.length
                    : cat.id === "migration" ? ALL_AGENTS_COMBINED.filter(a => MIGRATION_TYPES.has(a.pipeline_type)).length
                    : ALL_AGENTS_COMBINED.filter(a => a.pipeline_type === cat.id).length;
                  const isActive = activeCategory === cat.id;
                  const isSubItem = cat.id === "mulesoft_to_springboot" || cat.id === "dotnet_to_azure";
                  return (
                    <button key={cat.id} onClick={() => setActiveCategory(cat.id)}
                      className={`flex items-center justify-between w-full px-3 py-2 rounded-lg border text-[13px] transition-colors text-left ${
                        isActive ? "bg-brand-fill border-brand-border text-brand font-medium"
                        : cat.section ? "border-transparent text-ink-700 font-semibold hover:bg-surface-warm"
                        : "border-transparent text-ink-500 hover:text-ink-900 hover:bg-surface-warm"
                      } ${isSubItem ? "pl-6 text-[12px]" : ""}`}
                    >
                      <span>{cat.label}</span>
                      <span className={`text-[11px] font-medium ${isActive ? "text-brand" : "text-ink-400"}`}>{count}</span>
                    </button>
                  );
                })}
              </nav>
            </>
          )}

          {mainTab === "skills" && (
            <>
              <p className="text-[10px] font-semibold text-ink-400 uppercase tracking-[0.15em] px-5 mb-3">Category</p>
              <nav className="flex flex-col gap-0.5 px-3">
                {SKILL_CATEGORIES.map(cat => {
                  const count = cat.id === "all" ? SKILLS.length : SKILLS.filter(s => s.category === cat.id).length;
                  const isActive = skillCategory === cat.id;
                  return (
                    <button key={cat.id} onClick={() => setSkillCategory(cat.id)}
                      className={`flex items-center justify-between w-full px-3 py-2 rounded-lg border text-[12px] transition-colors text-left ${
                        isActive ? "bg-brand-fill border-brand-border text-brand font-medium" : "border-transparent text-ink-500 hover:text-ink-900 hover:bg-surface-warm"
                      }`}>
                      <span>{cat.label}</span>
                      <span className={`text-[10px] ${isActive ? "text-brand" : "text-ink-400"}`}>{count}</span>
                    </button>
                  );
                })}
              </nav>
            </>
          )}

          {mainTab === "hooks" && (
            <>
              <p className="text-[10px] font-semibold text-ink-400 uppercase tracking-[0.15em] px-5 mb-3">Event</p>
              <nav className="flex flex-col gap-0.5 px-3">
                {HOOK_EVENTS.map(ev => {
                  const count = ev.id === "all" ? HOOKS.length : HOOKS.filter(h => h.event === ev.id).length;
                  const isActive = hookEvent === ev.id;
                  return (
                    <button key={ev.id} onClick={() => setHookEvent(ev.id)}
                      className={`flex items-center justify-between w-full px-3 py-2 rounded-lg border text-[12px] transition-colors text-left ${
                        isActive ? "bg-brand-fill border-brand-border text-brand font-medium" : "border-transparent text-ink-500 hover:text-ink-900 hover:bg-surface-warm"
                      }`}>
                      <span>{ev.label}</span>
                      <span className={`text-[10px] ${isActive ? "text-brand" : "text-ink-400"}`}>{count}</span>
                    </button>
                  );
                })}
              </nav>
            </>
          )}
        </div>

        {/* Main content */}
        <div className="flex-1 flex flex-col min-w-0 overflow-hidden">

        {/* ── AGENTS ── */}
        {mainTab === "agents" && (
          <>
            <div className="px-6 py-2 bg-surface-white border-b border-line-divider flex-shrink-0">
              <p className="text-[11px] text-ink-400">{filteredAgents.length} agents · tap any agent to see its capabilities</p>
            </div>
            <div className="flex-1 overflow-y-auto p-5">
              <div className="grid grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
                {filteredAgents.map((agent, idx) => (
                  <Card key={`${agent.pipeline_type}-${agent.id}`}
                    onClick={() => setSelectedAgent({ agent, index: idx })}
                    className="flex flex-col p-4 hover:border-line-control hover:shadow-md transition-all cursor-pointer group"
                  >
                    <div className="flex items-center gap-3 mb-3">
                      <div className={`w-9 h-9 rounded-lg flex items-center justify-center flex-shrink-0 text-[11px] font-bold group-hover:scale-105 transition-transform ${ICON_TINTS[idx % ICON_TINTS.length]}`}>
                        {getInitials(agent.name)}
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="font-sans text-[12px] font-semibold text-ink-900 leading-tight group-hover:text-brand transition-colors">{agent.name}</p>
                        <p className="text-[10px] text-ink-400 mt-0.5 uppercase tracking-wide font-medium">{PIPELINE_LABEL[agent.pipeline_type] ?? agent.pipeline_type}</p>
                      </div>
                    </div>
                    <p className="text-[10px] font-semibold text-ink-500 mb-1.5">{agent.role}</p>
                    <p className="text-[11px] text-ink-500 leading-relaxed flex-1 mb-3 line-clamp-3">{agent.description}</p>
                    <div className="flex items-center justify-between pt-2 border-t border-line-divider">
                      <span className="flex items-center gap-1 text-[9px] text-ink-400"><Clock className="h-2.5 w-2.5" />~{agent.estimated_duration}s</span>
                      <span className="text-[9px] text-ink-400 group-hover:text-brand transition-colors font-medium">Tap to explore →</span>
                    </div>
                  </Card>
                ))}
              </div>
            </div>
          </>
        )}

        {/* ── SKILLS ── */}
        {mainTab === "skills" && (
          <div className="flex-1 overflow-y-auto p-5">
            <p className="text-[11px] text-ink-400 mb-4">{filteredSkills.length} skills · tap any skill to see its full content</p>
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
                {filteredSkills.map((skill) => (
                  <Card key={skill.id}
                    onClick={() => setSelectedSkill(skill)}
                    className="flex flex-col p-4 hover:border-line-control hover:shadow-md transition-all cursor-pointer group"
                  >
                    <div className="flex items-start justify-between gap-3 mb-2">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                          <p className="font-sans text-[13px] font-semibold text-ink-900 group-hover:text-brand transition-colors">{skill.name}</p>
                        </div>
                        <p className="text-[10px] text-ink-400 uppercase tracking-wide font-medium capitalize">{skill.category}</p>
                      </div>
                      <Puzzle className="h-4 w-4 text-ink-300 group-hover:text-ink-500 transition-colors flex-shrink-0 mt-0.5" />
                    </div>
                    <p className="text-[11px] text-ink-600 leading-relaxed mb-3 flex-1 line-clamp-2">{skill.description}</p>
                    <div className="flex items-center justify-between pt-2 border-t border-line-divider">
                      <div className="flex flex-wrap gap-1">
                        {skill.tags.slice(0, 3).map(tag => (
                          <span key={tag} className="text-[9px] px-1.5 py-0.5 rounded bg-surface-warm border border-line-border text-ink-500">{tag}</span>
                        ))}
                      </div>
                      <span className="text-[9px] text-ink-400 group-hover:text-brand transition-colors font-medium flex-shrink-0 ml-2">View →</span>
                    </div>
                  </Card>
                ))}
              </div>
            </div>
        )}

        {/* ── HOOKS ── */}
        {mainTab === "hooks" && (
          <div className="flex-1 overflow-y-auto p-5">
            <p className="text-[11px] text-ink-400 mb-4">{filteredHooks.length} hooks · tap any hook to see details</p>
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
                {filteredHooks.map((hook) => (
                  <Card key={hook.id}
                    onClick={() => setSelectedHook(hook)}
                    className="flex flex-col p-4 hover:border-line-control hover:shadow-md transition-all cursor-pointer group"
                  >
                    <div className="flex items-start justify-between gap-3 mb-2">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1 flex-wrap">
                          <p className="font-sans text-[13px] font-semibold text-ink-900 group-hover:text-brand transition-colors">{hook.name}</p>
                          <span className="text-[9px] font-semibold px-1.5 py-0.5 rounded bg-ink-900 text-white flex-shrink-0">{hook.event}</span>
                        </div>
                        <p className="text-[10px] text-ink-400 italic">{hook.trigger}</p>
                      </div>
                      <Webhook className="h-4 w-4 text-ink-300 group-hover:text-ink-500 transition-colors flex-shrink-0 mt-0.5" />
                    </div>
                    <p className="text-[11px] text-ink-600 leading-relaxed mb-3 flex-1 line-clamp-2">{hook.description}</p>
                    <div className="flex items-center justify-between pt-2 border-t border-line-divider">
                      <div className="flex flex-wrap gap-1">
                        {hook.tags.slice(0, 3).map(tag => (
                          <span key={tag} className="text-[9px] px-1.5 py-0.5 rounded bg-surface-warm border border-line-border text-ink-500">{tag}</span>
                        ))}
                      </div>
                      <span className="text-[9px] text-ink-400 group-hover:text-brand transition-colors font-medium flex-shrink-0 ml-2">View →</span>
                    </div>
                  </Card>
                ))}
              </div>
            </div>
        )}
      </div>
      </div>

      {/* Modals */}
      <AnimatePresence>
        {selectedAgent && (
          <AgentCapabilitiesModal
            agent={selectedAgent.agent}
            agentIndex={selectedAgent.index}
            onClose={() => setSelectedAgent(null)}
          />
        )}
      </AnimatePresence>
      <AnimatePresence>
        {selectedSkill && <SkillDetailModal skill={selectedSkill} onClose={() => setSelectedSkill(null)} />}
      </AnimatePresence>
      <AnimatePresence>
        {selectedHook && <HookDetailModal hook={selectedHook} onClose={() => setSelectedHook(null)} />}
      </AnimatePresence>
    </div>
  );
}
