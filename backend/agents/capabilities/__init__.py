"""agents.capabilities — the hexagonal capability seam (Phase 4 / 1A).

``base`` holds the Protocol ports any workflow capability implements; ``registry``
holds the central ``CapabilityRegistry`` of known capability NAMES the compiler
validates declared references against (INV-4). No implementations (Phase 7) and
no trust flags / self-registration (Phase 8) live here yet — see D-07.
"""
