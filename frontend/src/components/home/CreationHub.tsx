"use client";

import { motion } from "motion/react";
import { ArrowRight } from "lucide-react";
import type { WorkflowType } from "@/types/index";

interface CreationHubProps {
  onSelectFeature: (type: WorkflowType) => void;
}

const WORKFLOWS = [
  {
    id: "user_stories",
    type: "user_stories" as WorkflowType,
    label: "Generate product requirements",
    description: "Transform an idea or brief into a structured PRD with epics, user stories, and Gherkin acceptance criteria.",
    badge: null,
  },
  {
    id: "ppt",
    type: "ppt" as WorkflowType,
    label: "Pitch an idea",
    description: "Shape a concept into an enterprise-grade pitch deck — charts, data tables, and executive-ready visuals produced by VelocityAI's presentation agents.",
    badge: null,
  },
  {
    id: "prototype",
    type: "prototype" as WorkflowType,
    label: "Build an interactive prototype",
    description: "Translate stories, requirements, or wireframes into a high-fidelity, navigable HTML prototype.",
    badge: null,
  },
  {
    id: "app_builder",
    type: "app_builder" as WorkflowType,
    label: "Build an end-to-end application",
    description: "Hand VelocityAI a deck, repository, or brief — its guardrails, workflows, and specialist agents stand up a complete enterprise application with infrastructure and tests.",
    badge: null,
  },
  {
    id: "migration",
    type: "migration" as WorkflowType,
    label: "Migration workflows",
    description: "Modernise a legacy estate end-to-end — Mulesoft to Spring Boot microservices on AWS, or .NET to Azure with AI augmentation.",
    badge: "NEW",
  },
  {
    id: "custom",
    type: "custom" as WorkflowType,
    label: "Compose a custom workflow",
    description: "Assemble specialist agents and skills into a custom workflow for tasks outside the standard pipelines.",
    badge: null,
  },
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
          <h1 className="text-[38px] sm:text-[44px] font-bold text-gray-900 leading-tight tracking-tight mb-4">
            Select a workflow to begin
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
              className="group w-full flex items-start justify-between gap-4 py-5 text-left hover:bg-white/60 transition-colors rounded-lg px-3 -mx-3"
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
                <p className="text-[12px] text-gray-500 leading-relaxed">
                  {workflow.description}
                </p>
              </div>
              <div className="flex-shrink-0 mt-1">
                <ArrowRight className="h-4 w-4 text-gray-300 group-hover:text-gray-600 group-hover:translate-x-0.5 transition-all" />
              </div>
            </motion.button>
          ))}
        </div>

      </div>
    </div>
  );
}
