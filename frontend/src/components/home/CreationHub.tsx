"use client";

import { motion } from "motion/react";
import { ArrowRight } from "lucide-react";
import type { WorkflowType } from "@/types/index";

interface CreationHubProps {
  onSelectFeature: (type: WorkflowType) => void;
}

const WORKFLOWS: { id: string; type: WorkflowType; label: string; subtitle: string; badge: string | null }[] = [
  { id: "user_stories", type: "user_stories", label: "Generate product requirements", subtitle: "Epics, user stories, and Gherkin acceptance criteria — ready for Jira.",                  badge: null },
  { id: "ppt",          type: "ppt",          label: "Pitch an idea",                  subtitle: "Executive-grade deck with charts, data, and a clear narrative.",                       badge: null },
  { id: "prototype",    type: "prototype",    label: "Build an interactive prototype", subtitle: "Navigable, high-fidelity HTML prototype from a brief or story set.",                   badge: null },
  { id: "app_builder",  type: "app_builder",  label: "Build an end-to-end application", subtitle: "Full-stack code, tests, and infrastructure from a single requirement.",              badge: null },
  { id: "migration",    type: "migration",    label: "Platform workflows",             subtitle: "Modernise a legacy estate — Mulesoft to AWS or .NET to Azure.",                        badge: "NEW" },
  { id: "custom",       type: "custom",       label: "Compose a custom workflow",      subtitle: "Assemble specialist agents for tasks outside the standard pipelines.",                badge: null },
];

export function CreationHub({ onSelectFeature }: CreationHubProps) {
  return (
    <div
      className="flex h-full flex-col overflow-y-auto"
      style={{ background: "#f5f5f0" }}
    >
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

        {/* Workflow list */}
        <div className="w-full divide-y divide-gray-200/70">
          {WORKFLOWS.map((workflow, idx) => (
            <motion.button
              key={workflow.id}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, delay: 0.1 + idx * 0.06 }}
              onClick={() => onSelectFeature(workflow.type)}
              className="group w-full flex items-center justify-between gap-4 py-5 text-left hover:bg-white/60 transition-colors rounded-lg px-3 -mx-3"
            >
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1">
                  <h2 className="text-[15px] font-semibold text-gray-900 italic leading-snug group-hover:text-[#1B2A4A] transition-colors">
                    {workflow.label}
                  </h2>
                  {workflow.badge && (
                    <span className="text-[9px] font-semibold text-[#1B2A4A] border border-[#1B2A4A]/30 px-1.5 py-0.5 rounded uppercase tracking-wide">
                      {workflow.badge}
                    </span>
                  )}
                </div>
                <p className="text-[12px] italic text-gray-500 leading-snug">
                  {workflow.subtitle}
                </p>
              </div>
              <div className="flex-shrink-0">
                <ArrowRight className="h-4 w-4 text-gray-300 group-hover:text-gray-600 group-hover:translate-x-0.5 transition-all" />
              </div>
            </motion.button>
          ))}
        </div>

      </div>
    </div>
  );
}
