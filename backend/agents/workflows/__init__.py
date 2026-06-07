"""agents/workflows/ — declarative workflow data layer (no engine/api imports).

This package holds the workflow-agnostic declaration layer for the universal
runtime kernel:

  - ``plan.py``      — the typed §6 contract (``CompiledWorkflow``/``Step``/
                       ``Task`` + the inert forward types, D-06). The shared seam
                       type consumed by both the compiler and the kernel.
  - ``manifest.py``  — ``WorkflowManifest`` + ``ManifestValidationError`` + the
                       file-backed YAML loader/validator (D-10 / MAN-01).
  - ``compiler.py``  — (04-03) the thin no-DSL compiler manifest → CompiledWorkflow.

Hexagonal direction (Ports & Adapters): this layer imports only stdlib + ``yaml``
(+ ``agents.capabilities`` for capability-name validation in the compiler). It
NEVER imports the kernel (``agents.execution_engine``) or the web layer
(``app.*``) — the dependency points the other way (kernel → these types).
"""
