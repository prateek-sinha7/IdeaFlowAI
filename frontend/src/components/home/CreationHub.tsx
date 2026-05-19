"use client";

import { motion } from "motion/react";
import { ArrowRight, Lock } from "lucide-react";
import type { WorkflowType } from "@/types/index";
import type { Tier } from "@/lib/entitlements";
import { canRunPipeline, TIER_LABELS, getUpgradeTier } from "@/lib/entitlements";

interface CreationHubProps {
  onSelectFeature: (type: WorkflowType) => void;
  userTier?: Tier;
}

const WORKFLOWS: {
  id: string;
  type: WorkflowType;
  label: string;
  subtitle: string;
  badge: string | null;
}[] = [
  { id: "user_stories", type: "user_stories", label: "Generate product requirements",    subtitle: "Epics, user stories, and Gherkin acceptance criteria — ready for Jira.",           badge: null },
  { id: "ppt",          type: "ppt",          label: "Pitch an idea",                    subtitle: "Executive-grade deck with charts, data, and a clear narrative.",                   badge: null },
  { id: "prototype",    type: "prototype",    label: "Build an interactive prototype",   subtitle: "Navigable, high-fidelity HTML prototype from a brief or story set.",               badge: null },
  { id: "app_builder",  type: "app_builder",  label: "Build an end-to-end application", subtitle: "Full-stack code, tests, and infrastructure from a single requirement.",            badge: null },
  { id: "migration",    type: "migration",    label: "Platform workflows",               subtitle: "Modernise a legacy estate — Mulesoft to AWS or .NET to Azure.",                    badge: "NEW" },
  { id: "custom",       type: "custom",       label: "Compose a custom workflow",        subtitle: "Assemble specialist agents for tasks outside the standard pipelines.",              badge: null },
];

export function CreationHub({ onSelectFeature, userTier = "basic" }: CreationHubProps) {
  return (
    <div className="flex h-full flex-col overflow-y-auto" style={{ background: "#f5f5f0" }}>
      <div className="flex-1 flex flex-col items-center px-6 py-12 max-w-2xl mx-auto w-full">

        {/* Header */}
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4 }}
          className="text-center mb-12 w-full"
        >
          <p className="text-[10px] font-semibold text-gray-400 uppercase tracking-[0.18em] mb-5">
            VelocityAI
          </p>
          <h1
            className="text-[38px] sm:text-[44px] font-normal italic text-gray-900 leading-tight tracking-tight mb-4"
            style={{ fontFamily: "var(--font-fraunces)" }}
          >
            What would you like to build today?
          </h1>
          <p className="text-[14px] text-gray-500 leading-relaxed max-w-md mx-auto">
            Select a deliverable. The right specialist agents will be assembled — review and configure them before execution.
          </p>
        </motion.div>

        {/* Tier badge */}
        <div className="w-full flex items-center justify-end mb-2">
          <span className="text-[10px] font-semibold text-gray-400 uppercase tracking-widest">
            Plan: <span className="text-[#1B2A4A]">{TIER_LABELS[userTier]}</span>
          </span>
        </div>

        {/* Workflow list */}
        <div className="w-full divide-y divide-gray-200/70">
          {WORKFLOWS.map((workflow, idx) => {
            const allowed = canRunPipeline(userTier, workflow.type);
            const upgradeTo = getUpgradeTier(userTier, workflow.type);

            return (
              <motion.div
                key={workflow.id}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.3, delay: 0.1 + idx * 0.06 }}
                className="relative"
              >
                <button
                  onClick={() => allowed && onSelectFeature(workflow.type)}
                  disabled={!allowed}
                  className={`group w-full flex items-center justify-between gap-4 py-5 text-left rounded-lg px-3 -mx-3 transition-colors ${
                    allowed
                      ? "hover:bg-white/60 cursor-pointer"
                      : "cursor-not-allowed opacity-60"
                  }`}
                >
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      {!allowed && (
                        <Lock className="h-3.5 w-3.5 text-gray-400 flex-shrink-0" />
                      )}
                      <h2 className={`text-[15px] font-semibold italic leading-snug transition-colors ${
                        allowed
                          ? "text-gray-900 group-hover:text-[#1B2A4A]"
                          : "text-gray-400"
                      }`}>
                        {workflow.label}
                      </h2>
                      {workflow.badge && allowed && (
                        <span className="text-[9px] font-semibold text-[#1B2A4A] border border-[#1B2A4A]/30 px-1.5 py-0.5 rounded uppercase tracking-wide">
                          {workflow.badge}
                        </span>
                      )}
                    </div>
                    <p className={`text-[12px] italic leading-snug ${allowed ? "text-gray-500" : "text-gray-400"}`}>
                      {workflow.subtitle}
                    </p>
                    {!allowed && upgradeTo && (
                      <p className="text-[10px] font-semibold text-[#1B2A4A] mt-1">
                        Requires {TIER_LABELS[upgradeTo]} plan
                      </p>
                    )}
                  </div>
                  <div className="flex-shrink-0">
                    {allowed ? (
                      <ArrowRight className="h-4 w-4 text-gray-300 group-hover:text-gray-600 group-hover:translate-x-0.5 transition-all" />
                    ) : (
                      <div className="h-6 w-6 rounded-full bg-gray-100 flex items-center justify-center">
                        <Lock className="h-3 w-3 text-gray-400" />
                      </div>
                    )}
                  </div>
                </button>
              </motion.div>
            );
          })}
        </div>

      </div>
    </div>
  );
}
