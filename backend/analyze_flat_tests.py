#!/usr/bin/env python3
"""Analyze flat test files and suggest migration targets."""

import re
from pathlib import Path

def extract_imports(file_path):
    """Extract import patterns to detect the module being tested."""
    try:
        content = file_path.read_text(encoding="utf-8")
        # Find all imports of app.* and agents.*
        imports = re.findall(r'from\s+(app|agents)\.([\w.]+)', content)
        return set(imports)
    except Exception:
        return set()

def guess_target(file_name, imports):
    """Guess the target path based on file name and imports."""
    # Map file name patterns to target modules
    name_lower = file_name.lower()
    
    # Admin/capacity
    if "admin" in name_lower and "capacity" in name_lower:
        return "tests/unit/api", "admin_capacity"
    if "admin" in name_lower:
        return "tests/unit/api", "admin"
    
    # API endpoints
    if "api" in name_lower or "endpoint" in name_lower:
        return "tests/unit/api", "generic"
    
    # Auth/Cognito
    if "cognito" in name_lower or "login" in name_lower or "logout" in name_lower or "mfa" in name_lower or "totp" in name_lower:
        return "tests/unit/core", "auth"
    
    # Users/deletion/groups
    if "user" in name_lower or "delete" in name_lower or "group" in name_lower or "entitlement" in name_lower:
        return "tests/unit/app", "users"
    
    # Execution engine / agents
    if "execution" in name_lower or "engine" in name_lower or "clarify" in name_lower:
        return "tests/unit/agents/execution_engine", "engine"
    
    if "agent" in name_lower and "skill" not in name_lower:
        return "tests/unit/agents", "agents"
    
    # Skills
    if "skill" in name_lower:
        return "tests/unit/agents/capabilities", "skills"
    
    # Workflows
    if "workflow" in name_lower:
        return "tests/unit/agents/workflows", "workflows"
    
    # Runs API
    if "run" in name_lower:
        return "tests/unit/api", "runs"
    
    # Chat/SSE
    if "chat" in name_lower or "sse" in name_lower or "stream" in name_lower or "event" in name_lower:
        return "tests/unit/api", "chat"
    
    # Artifacts/deliverables
    if "artifact" in name_lower or "deliverable" in name_lower:
        return "tests/unit/app", "artifacts"
    
    # Revisions
    if "revision" in name_lower:
        return "tests/unit/app", "revisions"
    
    # Templates/PPTX
    if "template" in name_lower or "pptx" in name_lower or "carousel" in name_lower or "catalog" in name_lower:
        return "tests/unit/app", "templates"
    
    # Services (various)
    if "concierge" in name_lower:
        return "tests/unit/services", "concierge"
    
    # Core
    if "config" in name_lower or "security" in name_lower or "exception" in name_lower:
        return "tests/unit/core", "config"
    
    # Default: app
    return "tests/unit/app", "generic"

# Analyze unit flat files
unit_flat = sorted(Path("tests/unit").glob("test_*.py"))
unit_flat = [f for f in unit_flat if f.is_file() and f.parent == Path("tests/unit")]

print(f"Unit flat files: {len(unit_flat)}")
print("\nFirst 20 unit files and guessed targets:")
for f in unit_flat[:20]:
    imports = extract_imports(f)
    target_dir, category = guess_target(f.name, imports)
    print(f"  {f.name:45} -> {target_dir}/{f.name:30} (category: {category})")

# Analyze integration flat files
integration_flat = sorted(Path("tests/integration").glob("test_*.py"))
integration_flat = [f for f in integration_flat if f.is_file() and f.parent == Path("tests/integration")]

print(f"\n\nIntegration flat files: {len(integration_flat)}")
print("\nIntegration files and guessed targets:")
for f in integration_flat:
    imports = extract_imports(f)
    print(f"  {f.name:45}")
    for imp in sorted(imports):
        print(f"    imports {imp[0]}.{imp[1]}")
