#!/usr/bin/env python3
"""
Workflow Gate Contract Assertion

Validates that the GitHub Actions workflow (.github/workflows/deploy.yml) enforces
the deployment quality gate as a mandatory dependency on the path to production.

Contract: Every job on the dependency path from source to `deploy` must transitively
depend on the `gate` job. This ensures no CI shortcut or refactoring can bypass the
reusable gate job that validates tests, linting, and security scans.

Rationale:
  - The gate job runs tests, security scanning, and linting
  - The build job creates Docker images and pushes to ECR
  - The deploy job redeploys to production via SSM
  - Without gate as a dependency, a failure in tests/scanning/lint could be
    bypassed by editing the workflow, allowing broken code to reach production

Current correct state:
  - gate -> build -> deploy (gate blocks both build and deploy via transitive deps)
  - resolve -> build (resolve feeds build but doesn't need gate)
  - resolve -> deploy (resolve feeds deploy but doesn't need gate)

This script enforces:
  1. `build` job must have `gate` in its needs (explicit)
  2. `deploy` job must have both `gate` and `build` in its needs (explicit)
  3. No future bypass route to deploy can omit gate
  4. Phase 10: No `continue-on-error: true` on security/scanner steps
  5. Phase 10: No `|| true` in scanner invocations (gitleaks, checkov, trivy, etc.)
  6. Phase 10: All `trivy image` commands use `--exit-code 1`
  7. Phase 10: All `flip-to-failing` dates are not expired

Exit codes:
  0 - Contract satisfied, workflow is safe
  1 - Contract violated, workflow has a bypass route
"""

import sys
import yaml
from pathlib import Path
from typing import Dict, Set, List, Optional
from datetime import datetime
import re


def load_workflow(workflow_path: str) -> Dict:
    """Load and parse the GitHub Actions workflow YAML."""
    try:
        with open(workflow_path, 'r') as f:
            workflow = yaml.safe_load(f)
        return workflow
    except FileNotFoundError:
        print(f"ERROR: Workflow file not found: {workflow_path}")
        sys.exit(1)
    except yaml.YAMLError as e:
        print(f"ERROR: Failed to parse YAML: {e}")
        sys.exit(1)


def extract_job_needs(job_def: Optional[Dict]) -> Set[str]:
    """
    Extract the set of jobs a given job depends on.
    
    Returns:
      - Empty set if job has no `needs` declaration
      - Set of job names if `needs` is an array or string
    """
    if not job_def:
        return set()
    
    needs = job_def.get('needs')
    if needs is None:
        return set()
    
    # `needs` can be a string (single job) or list (multiple jobs)
    if isinstance(needs, str):
        return {needs}
    elif isinstance(needs, list):
        return set(needs)
    else:
        return set()


def compute_transitive_dependencies(jobs: Dict[str, Dict], start_job: str) -> Set[str]:
    """
    Compute the transitive closure of dependencies for a given job.
    
    Args:
        jobs: Dictionary of job_name -> job_definition
        start_job: Name of the job to start from
    
    Returns:
        Set of all jobs (directly or transitively) that must complete before start_job
    """
    visited = set()
    to_visit = [start_job]
    all_deps = set()
    
    while to_visit:
        current = to_visit.pop(0)
        if current in visited:
            continue
        visited.add(current)
        
        if current not in jobs:
            # Job not found in the workflow (shouldn't happen in valid workflows)
            continue
        
        job_def = jobs[current]
        direct_deps = extract_job_needs(job_def)
        
        for dep in direct_deps:
            all_deps.add(dep)
            if dep not in visited:
                to_visit.append(dep)
    
    return all_deps


def check_continue_on_error_on_security_steps(jobs: Dict[str, Dict], verbose: bool = False) -> bool:
    """
    Phase 10: Check that no security or scanner steps have `continue-on-error: true`.
    
    Returns:
        True if no violations, False otherwise
    """
    security_keywords = {
        'security', 'scan', 'gitleaks', 'checkov', 'trivy', 
        'tflint', 'codeql', 'bandit', 'semgrep', 'sast'
    }
    
    violations = []
    
    for job_name, job_def in jobs.items():
        if not job_def or 'steps' not in job_def:
            continue
        
        for step_idx, step in enumerate(job_def['steps'], 1):
            if not step:
                continue
            
            step_name = step.get('name', f'Step {step_idx}')
            # Check if this is a security-related step
            is_security_step = any(keyword in step_name.lower() for keyword in security_keywords)
            
            if is_security_step and step.get('continue-on-error') is True:
                violations.append(f"  {job_name}/{step_name}: continue-on-error: true")
    
    if violations:
        print("VIOLATION: Security/scanner steps have continue-on-error: true (Phase 10)")
        for v in violations:
            print(v)
        return False
    elif verbose:
        print("✓ No security/scanner steps have continue-on-error: true")
    
    return True


def check_scanner_exit_codes(jobs: Dict[str, Dict], verbose: bool = False) -> bool:
    """
    Phase 10: Check that scanner invocations don't use `|| true` and use proper exit codes.
    
    Returns:
        True if no violations, False otherwise
    """
    violations = []
    
    for job_name, job_def in jobs.items():
        if not job_def or 'steps' not in job_def:
            continue
        
        for step_idx, step in enumerate(job_def['steps'], 1):
            if not step or 'run' not in step:
                continue
            
            run_command = step.get('run', '')
            step_name = step.get('name', f'Step {step_idx}')
            
            # Check for scanner commands with || true
            scanners = ['gitleaks', 'checkov', 'trivy', 'tflint', 'bandit', 'semgrep']
            for scanner in scanners:
                if scanner in run_command:
                    # Check for || true pattern
                    if '|| true' in run_command:
                        violations.append(
                            f"  {job_name}/{step_name}: '{scanner}' invocation has '|| true'"
                        )
                    # For trivy image: ensure --exit-code 1 is used
                    if 'trivy image' in run_command and '--exit-code 1' not in run_command:
                        violations.append(
                            f"  {job_name}/{step_name}: 'trivy image' missing '--exit-code 1'"
                        )
    
    if violations:
        print("VIOLATION: Scanner commands have || true or missing exit-code (Phase 10)")
        for v in violations:
            print(v)
        return False
    elif verbose:
        print("✓ All scanner invocations have proper exit-code handling")
    
    return True


def check_flip_to_failing_dates(workflow_path: str, verbose: bool = False) -> bool:
    """
    Phase 10: Check that all `flip-to-failing` dates are not expired.
    
    This looks for comments like:
      # flip-to-failing: 2026-12-31 (reason: ...)
    
    And validates the date is in the future.
    
    Returns:
        True if no violations, False otherwise
    """
    violations = []
    today = datetime.now().date()
    
    try:
        with open(workflow_path, 'r') as f:
            lines = f.readlines()
    except Exception as e:
        if verbose:
            print(f"Note: Could not read workflow for flip-to-failing check: {e}")
        return True
    
    for line_idx, line in enumerate(lines, 1):
        # Match: # flip-to-failing: YYYY-MM-DD
        match = re.search(r'#\s*flip-to-failing:\s*(\d{4}-\d{2}-\d{2})', line)
        if match:
            date_str = match.group(1)
            try:
                flip_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                if flip_date < today:
                    violations.append(
                        f"  Line {line_idx}: flip-to-failing date '{date_str}' is expired (today: {today})"
                    )
            except ValueError:
                print(f"  Line {line_idx}: Invalid date format: {date_str}")
    
    if violations:
        print("VIOLATION: flip-to-failing dates are expired (Phase 10)")
        for v in violations:
            print(v)
        return False
    elif verbose:
        print("✓ All flip-to-failing dates are valid/future")
    
    return True


def check_gate_contract(workflow_path: str, verbose: bool = False) -> bool:
    """
    Verify that the gate contract is satisfied.
    
    Returns:
        True if contract is satisfied, False otherwise
    """
    workflow = load_workflow(workflow_path)
    
    if 'jobs' not in workflow:
        print("ERROR: Workflow has no 'jobs' section")
        return False
    
    jobs = workflow['jobs']
    
    # Check for required jobs
    required_jobs = {'gate', 'resolve', 'build', 'deploy'}
    missing_jobs = required_jobs - set(jobs.keys())
    if missing_jobs:
        print(f"ERROR: Workflow is missing required jobs: {missing_jobs}")
        return False
    
    contract_satisfied = True
    
    # Contract 1: `build` must directly depend on `gate`
    build_needs = extract_job_needs(jobs.get('build'))
    if 'gate' not in build_needs:
        print("VIOLATION: 'build' job does not directly depend on 'gate'")
        print(f"  Current 'build' needs: {build_needs if build_needs else '(none)'}")
        contract_satisfied = False
    elif verbose:
        print("✓ 'build' job correctly depends on 'gate'")
    
    # Contract 2: `deploy` must directly depend on `gate` and `build`
    deploy_needs = extract_job_needs(jobs.get('deploy'))
    if 'gate' not in deploy_needs:
        print("VIOLATION: 'deploy' job does not directly depend on 'gate'")
        print(f"  Current 'deploy' needs: {deploy_needs if deploy_needs else '(none)'}")
        contract_satisfied = False
    elif verbose:
        print("✓ 'deploy' job correctly depends on 'gate'")
    
    if 'build' not in deploy_needs:
        print("VIOLATION: 'deploy' job does not directly depend on 'build'")
        print(f"  Current 'deploy' needs: {deploy_needs if deploy_needs else '(none)'}")
        contract_satisfied = False
    elif verbose:
        print("✓ 'deploy' job correctly depends on 'build'")
    
    # Contract 3: No route to `deploy` can omit `gate`
    # Compute all transitive dependencies of deploy
    deploy_all_deps = compute_transitive_dependencies(jobs, 'deploy')
    if 'gate' not in deploy_all_deps:
        print("VIOLATION: No path from 'deploy' includes 'gate' in transitive dependencies")
        print(f"  Transitive dependencies of 'deploy': {deploy_all_deps if deploy_all_deps else '(none)'}")
        contract_satisfied = False
    elif verbose:
        print("✓ 'gate' is transitively required by 'deploy'")
    
    # Phase 10: Check scanner step safeguards
    if not check_continue_on_error_on_security_steps(jobs, verbose):
        contract_satisfied = False
    
    if not check_scanner_exit_codes(jobs, verbose):
        contract_satisfied = False
    
    if not check_flip_to_failing_dates(workflow_path, verbose):
        contract_satisfied = False
    
    # Additional analysis: show the dependency chain for documentation
    if verbose and contract_satisfied:
        print("\nDependency chain:")
        print(f"  gate:")
        print(f"    depends on: {extract_job_needs(jobs.get('gate')) or '(independent)'}")
        print(f"  resolve:")
        print(f"    depends on: {extract_job_needs(jobs.get('resolve')) or '(independent)'}")
        print(f"  build:")
        print(f"    depends on: {extract_job_needs(jobs.get('build'))}")
        print(f"  deploy:")
        print(f"    depends on: {extract_job_needs(jobs.get('deploy'))}")
        print(f"\nTransitive dependencies to deploy:")
        print(f"  {sorted(deploy_all_deps)}")
    
    return contract_satisfied


def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Verify GitHub Actions workflow gate contract (Phase 10)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s .github/workflows/deploy.yml
  %(prog)s .github/workflows/deploy.yml --verbose
  %(prog)s .github/workflows/deploy.yml --verbose --exit-0

Exit codes:
  0  Contract satisfied (or --exit-0 is set)
  1  Contract violated or workflow error
        """
    )
    parser.add_argument(
        'workflow',
        default='.github/workflows/deploy.yml',
        nargs='?',
        help='Path to the workflow file (default: .github/workflows/deploy.yml)'
    )
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Print detailed analysis and dependency chain'
    )
    parser.add_argument(
        '--exit-0',
        action='store_true',
        help='Exit with 0 even if contract is violated (use only for debugging)'
    )
    
    args = parser.parse_args()
    
    contract_ok = check_gate_contract(args.workflow, verbose=args.verbose)
    
    if contract_ok:
        print(f"\n✓ Workflow gate contract is satisfied")
        sys.exit(0)
    else:
        print(f"\n✗ Workflow gate contract is VIOLATED")
        if args.exit_0:
            print("  (Exiting with 0 due to --exit-0)")
            sys.exit(0)
        else:
            sys.exit(1)


if __name__ == '__main__':
    main()
