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

  const chipBase =
    "inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-[12px] transition-colors";
  const chipActive = "bg-surface-near-black border-transparent text-white font-medium";
  const chipIdle =
    "bg-surface-card border-line-border text-ink-500 hover:border-line-control hover:text-ink-700";

  const countLine = `${ALL_AGENTS_COMBINED.length} agents · ${SKILLS.length} skills · ${HOOKS.length} hooks`;

  return (
    <div className="h-full overflow-y-auto bg-surface-paper">
      <div className="max-w-[1320px] w-full mx-auto px-8 pt-6 pb-16">
        {/* ── Header — h1 + count + search (leads above the tabs, per the mock) ── */}
        <div className="flex items-end justify-between gap-5 mb-4">
          <div>
            <h1 className="font-sans text-[26px] font-light text-ink-900 tracking-[-0.01em] leading-none mb-1.5">Library</h1>
            <p className="text-[13px] text-ink-400 leading-none">{countLine}</p>
          </div>
          <div className="relative w-[280px] flex-shrink-0">
            <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 h-[15px] w-[15px] text-ink-200" />
            <input type="text"
              value={mainTab === "agents" ? searchQuery : mainTab === "skills" ? skillSearch : hookSearch}
              onChange={e => {
                if (mainTab === "agents") setSearchQuery(e.target.value);
                else if (mainTab === "skills") setSkillSearch(e.target.value);
                else setHookSearch(e.target.value);
              }}
              placeholder={`Search ${mainTab}...`}
              className="w-full pl-10 pr-4 py-[9px] text-[13px] text-ink-800 bg-surface-card border border-line-control rounded-[10px] focus:outline-none focus:border-brand transition-colors placeholder:text-ink-200"
            />
          </div>
        </div>

        {/* ── Tab chrome — Tabs primitive, ND-C purple underline (kept) ── */}
        <Tabs
          tabs={MAIN_TABS}
          active={mainTab}
          onChange={(id) => setMainTab(id as "agents" | "skills" | "hooks")}
          className="mb-5"
        />

        {/* ── AGENTS ── */}
        {mainTab === "agents" && (
          <>
            <div className="flex flex-wrap gap-[7px] mb-5">
              {CATEGORIES.map(cat => {
                const count = cat.id === "all" ? ALL_AGENTS_COMBINED.length
                  : cat.id === "migration" ? ALL_AGENTS_COMBINED.filter(a => MIGRATION_TYPES.has(a.pipeline_type)).length
                  : ALL_AGENTS_COMBINED.filter(a => a.pipeline_type === cat.id).length;
                const isActive = activeCategory === cat.id;
                return (
                  <button key={cat.id} onClick={() => setActiveCategory(cat.id)}
                    className={`${chipBase} ${isActive ? chipActive : chipIdle}`}>
                    {cat.label}<span className="opacity-50">{count}</span>
                  </button>
                );
              })}
            </div>
            <div className="grid grid-cols-[repeat(auto-fill,minmax(288px,1fr))] gap-[13px]">
              {filteredAgents.map((agent, idx) => (
                <Card key={`${agent.pipeline_type}-${agent.id}`}
                  onClick={() => setSelectedAgent({ agent, index: idx })}
                  className="flex flex-col p-[17px] min-h-[180px] hover:border-line-control transition-colors cursor-pointer group"
                >
                  <div className="flex items-center gap-3 mb-3">
                    <div className={`w-10 h-10 rounded-[10px] flex items-center justify-center flex-shrink-0 text-[12px] font-bold ${ICON_TINTS[idx % ICON_TINTS.length]}`}>
                      {getInitials(agent.name)}
                    </div>
                    <div className="min-w-0">
                      <p className="font-sans text-[14px] font-semibold text-ink-900 leading-tight group-hover:text-brand transition-colors">{agent.name}</p>
                      <p className="text-[9px] text-ink-200 mt-1 uppercase tracking-[0.11em] font-semibold">{PIPELINE_LABEL[agent.pipeline_type] ?? agent.pipeline_type}</p>
                    </div>
                  </div>
                  <p className="text-[12px] font-semibold text-ink-700 mb-1.5">{agent.role}</p>
                  <p className="text-[12px] text-ink-400 leading-relaxed line-clamp-3">{agent.description}</p>
                  <span className="flex-1" />
                  <div className="flex items-center gap-2 mt-3.5 pt-3 border-t border-line-divider">
                    <Clock className="h-[13px] w-[13px] text-ink-200" />
                    <span className="text-[11.5px] text-ink-300">~{agent.estimated_duration}s</span>
                    <span className="flex-1" />
                    <span className="text-[11.5px] font-medium text-brand">Configure →</span>
                  </div>
                </Card>
              ))}
            </div>
          </>
        )}

        {/* ── SKILLS ── */}
        {mainTab === "skills" && (
          <>
            <div className="flex flex-wrap gap-[7px] mb-5">
              {SKILL_CATEGORIES.map(cat => {
                const isActive = skillCategory === cat.id;
                return (
                  <button key={cat.id} onClick={() => setSkillCategory(cat.id)}
                    className={`${chipBase} ${isActive ? chipActive : chipIdle}`}>
                    {cat.label}
                  </button>
                );
              })}
            </div>
            <div className="grid grid-cols-[repeat(auto-fill,minmax(360px,1fr))] gap-3">
              {filteredSkills.map((skill) => (
                <Card key={skill.id}
                  onClick={() => setSelectedSkill(skill)}
                  className="p-4 hover:border-line-control transition-colors cursor-pointer group"
                >
                  <div className="flex items-center gap-2.5 mb-2.5">
                    <span className="w-[30px] h-[30px] flex-shrink-0 rounded-lg bg-brand-fill grid place-items-center text-brand">
                      <Puzzle className="h-[15px] w-[15px]" />
                    </span>
                    <div className="min-w-0">
                      <p className="font-sans text-[13.5px] font-semibold text-ink-900 leading-tight group-hover:text-brand transition-colors">{skill.name}</p>
                      <p className="text-[8.5px] text-ink-200 mt-0.5 uppercase tracking-[0.1em] font-semibold capitalize">{skill.category}</p>
                    </div>
                  </div>
                  <p className="text-[12px] text-ink-400 leading-relaxed mb-2.5 line-clamp-2">{skill.description}</p>
                  <div className="flex items-center flex-wrap gap-1.5">
                    {skill.tags.slice(0, 3).map(tag => (
                      <span key={tag} className="text-[10px] px-2 py-1 rounded-[5px] bg-surface-paper border border-line-border text-ink-500 font-medium">{tag}</span>
                    ))}
                    <span className="flex-1" />
                    <span className="text-[11px] font-medium text-brand self-center group-hover:opacity-80 transition-opacity">View →</span>
                  </div>
                </Card>
              ))}
            </div>
          </>
        )}

        {/* ── HOOKS ── */}
        {mainTab === "hooks" && (
          <>
            <div className="flex flex-wrap gap-[7px] mb-5">
              {HOOK_EVENTS.map(ev => {
                const isActive = hookEvent === ev.id;
                return (
                  <button key={ev.id} onClick={() => setHookEvent(ev.id)}
                    className={`${chipBase} ${isActive ? chipActive : chipIdle}`}>
                    {ev.label}
                  </button>
                );
              })}
            </div>
            <div className="grid grid-cols-[repeat(auto-fill,minmax(360px,1fr))] gap-3">
              {filteredHooks.map((hook) => (
                <Card key={hook.id}
                  onClick={() => setSelectedHook(hook)}
                  className="p-4 hover:border-line-control transition-colors cursor-pointer group"
                >
                  <div className="flex items-center gap-2.5 mb-2">
                    <p className="font-sans text-[13.5px] font-semibold text-ink-900 leading-tight group-hover:text-brand transition-colors">{hook.name}</p>
                    <span className="flex-1" />
                    <span className="text-[9px] font-semibold px-2 py-1 rounded-[5px] bg-surface-near-black text-white flex-shrink-0">{hook.event}</span>
                  </div>
                  <p className="text-[11.5px] text-ink-200 italic mb-2">{hook.trigger}</p>
                  <p className="text-[12px] text-ink-400 leading-relaxed mb-2.5 line-clamp-2">{hook.description}</p>
                  <div className="flex items-center flex-wrap gap-1.5">
                    {hook.tags.slice(0, 3).map(tag => (
                      <span key={tag} className="text-[10px] px-2 py-1 rounded-[5px] bg-surface-paper border border-line-border text-ink-500 font-medium">{tag}</span>
                    ))}
                    <span className="flex-1" />
                    <span className="text-[11px] font-medium text-brand self-center group-hover:opacity-80 transition-opacity">View →</span>
                  </div>
                </Card>
              ))}
            </div>
          </>
        )}
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
