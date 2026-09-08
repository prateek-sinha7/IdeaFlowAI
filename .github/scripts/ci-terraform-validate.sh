#!/usr/bin/env bash
# Validate every Terraform root statically.
#
# `init -backend=false` is what keeps this CI-safe: no remote state is read, no
# credentials are needed, and no cloud resource can be touched. This script must
# never call plan, apply, destroy, import or state — a contract test asserts it.
set -euo pipefail

roots_dir="infra/terraform"
failed=()

if [[ ! -d "${roots_dir}" ]]; then
  echo "::error::${roots_dir} does not exist."
  exit 1
fi

# A Terraform root is any directory holding a versions.tf or a backend
# declaration. Discovering them beats a hand-maintained list that silently
# stops covering a newly added root.
mapfile -t roots < <(
  find "${roots_dir}" -maxdepth 2 -type f -name '*.tf' -printf '%h\n' \
    | sort -u
)

if ((${#roots[@]} == 0)); then
  echo "::error::no Terraform roots found under ${roots_dir}."
  exit 1
fi

for root in "${roots[@]}"; do
  echo "::group::terraform validate ${root}"
  if terraform -chdir="${root}" init -backend=false -input=false -no-color \
     && terraform -chdir="${root}" validate -no-color; then
    echo "OK ${root}"
  else
    echo "::error::terraform validate failed for ${root}"
    failed+=("${root}")
  fi
  echo "::endgroup::"
done

if ((${#failed[@]} > 0)); then
  echo "::error::Terraform validation failed for: ${failed[*]}"
  exit 1
fi

echo "All ${#roots[@]} Terraform root(s) validated."
