"use client";

import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import { CheckCircle2, XCircle, X, ArrowRight } from "lucide-react";
import { getWorkflowLabel } from "@/hooks/useNotifications";
import type { WorkflowType } from "@/types/index";

export interface ToastItem {
  id: string;
  workflowType: WorkflowType;
  title: string;
  status: "completed" | "failed";
  // FIX-202: the backend run id of the completed run — used to navigate
  // directly to that run's preview (not just setMainView("execution")).
  workflowRunId?: string;
}

interface CompletionToastProps {
  toasts: ToastItem[];
  onDismiss: (id: string) => void;
  onViewResults: (toast: ToastItem) => void;
}

function SingleToast({
  toast,
  onDismiss,
  onViewResults,
}: {
  toast: ToastItem;
  onDismiss: () => void;
  onViewResults: () => void;
}) {
  // Auto-dismiss after 7 seconds
  useEffect(() => {
    const t = setTimeout(onDismiss, 7000);
    return () => clearTimeout(t);
  }, [onDismiss]);

  const isSuccess = toast.status === "completed";

  return (
    <motion.div
      layout
      initial={{ opacity: 0, x: 60, scale: 0.95 }}
      animate={{ opacity: 1, x: 0, scale: 1 }}
      exit={{ opacity: 0, x: 60, scale: 0.95 }}
      transition={{ duration: 0.2, ease: "easeOut" }}
      className="flex items-start gap-3 bg-white border border-gray-200 rounded-xl shadow-lg shadow-black/8 px-4 py-3 w-[320px] pointer-events-auto"
    >
      {/* Icon */}
      <div className={`flex-shrink-0 mt-0.5 h-8 w-8 rounded-lg flex items-center justify-center ${
        isSuccess ? "bg-emerald-50" : "bg-red-50"
      }`}>
        {isSuccess
          ? <CheckCircle2 className="h-4 w-4 text-emerald-600" />
          : <XCircle className="h-4 w-4 text-red-500" />
        }
      </div>

      {/* Content */}
      <div className="flex-1 min-w-0">
        <p className="text-[12px] font-semibold text-gray-900">
          {isSuccess ? "Run completed" : `${getWorkflowLabel(toast.workflowType)} failed`}
        </p>
        <p className="text-[11px] text-gray-500 truncate mt-0.5">{toast.title}</p>
        {isSuccess && (
          <button
            onClick={onViewResults}
            className="flex items-center gap-1 mt-2 text-[11px] font-medium text-[#1B2A4A] hover:underline"
          >
            Open <ArrowRight className="h-3 w-3" />
          </button>
        )}
      </div>

      {/* Dismiss */}
      <button
        onClick={onDismiss}
        className="flex-shrink-0 text-gray-300 hover:text-gray-500 transition-colors mt-0.5"
      >
        <X className="h-3.5 w-3.5" />
      </button>
    </motion.div>
  );
}

export function CompletionToast({ toasts, onDismiss, onViewResults }: CompletionToastProps) {
  return (
    <div className="fixed bottom-6 right-6 z-[100] flex flex-col gap-2 pointer-events-none">
      <AnimatePresence mode="popLayout">
        {toasts.map(toast => (
          <SingleToast
            key={toast.id}
            toast={toast}
            onDismiss={() => onDismiss(toast.id)}
            onViewResults={() => onViewResults(toast)}
          />
        ))}
      </AnimatePresence>
    </div>
  );
}
