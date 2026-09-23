// The display name for a saved workflow's pipeline type.
//
// Lives here because BOTH the list card (SavedWorkflowsPage) and the detail view
// (WorkflowDetailView) render this badge. They each carried their own copy, and
// each copy was missing the same entries — so a ppt_v2 workflow showed the raw
// string "ppt_v2" to the user in two different places.
//
// A miss falls back to the raw id, so every type a saved workflow can carry needs
// an entry here. The engine version is deliberately not shown: on these screens a
// workflow is a Presentation whether it compiles through ppt or ppt_v2.
export const PIPELINE_LABEL: Record<string, string> = {
  user_stories: "User Stories",
  ppt: "Presentation",
  ppt_v2: "Presentation",
  prototype: "Prototype",
  prototype_v2: "Prototype",
  pdf_to_prototype: "PDF → Prototype",
  pdf_to_prototype_v2: "PDF → Prototype",
  app_builder: "App Builder",
  custom: "Custom",
  mulesoft_to_springboot: "Mulesoft → Spring Boot",
  dotnet_to_azure: ".NET → Azure",
};

/** The badge text for a pipeline type, falling back to the raw id when unknown. */
export function pipelineLabelFor(type: string): string {
  return PIPELINE_LABEL[type] ?? type;
}
