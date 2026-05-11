# Phase C TF Security Audit

Branch: `infra-agent-integration` (byte-identical to `infra` for the TF tree).
Scope: security-only audit of the Terraform tree at `/Users/1000060523/Documents/Work/UKI/Flowin/flowin/infra/`. Correctness/breakage findings (broken refs, deprecated features, lifecycle race conditions) are the sibling agent's territory and are deliberately not covered here.

## Summary

The Terraform suite is unusually disciplined for a single-EC2 deployment: account/region guards, KMS with rotation, IMDSv2 required, EBS encryption, S3 TLS-only + KMS-only PUT, AWS Backup with optional vault lock, VPC flow logs, VPC endpoint policies pinning `aws:PrincipalAccount`, confused-deputy guards on every service trust policy, and exclusive IAM resources to lock the role's permission set. The most acute security gaps are not in the AWS plumbing — they are in the **secret-handling chain that connects SSM SecureStrings to the running app**: `SECRET_KEY` is rendered into a plaintext systemd EnvironmentFile readable by anyone who lands an SSM session, has no rotation tooling, and is stored as plaintext in Terraform state. The second cluster is **container resource limits + observability gaps that turn an authenticated RCE (the PPTX-export Node subprocess flagged by Phase B) into a host-takeover with no defense-in-depth**: the Docker daemon has no memory/CPU/network namespace cap on the Node child, no CloudTrail/EventBridge alarm on sensitive SSM reads, and the only credential-leak control is the IAM scope of the instance role itself. Beyond those two themes the residual findings are defense-in-depth (KMS condition tightening, missing `kms:ViaService` on a SSM-decrypt statement, a missing `aws:SourceAccount` on the KMS-grants-SNS branch) and one ECR repository-policy gap that lets the instance role pull alone but does not deny others.

## CRITICAL findings

### 1. `SECRET_KEY` rendered to plaintext `/etc/flowin/app.env` reachable via SSM Session Manager
- **Files:**
  - `infra/scripts/bootstrap-ec2.sh:478-507` (loader writes SSM plaintext into EnvironmentFile)
  - `infra/scripts/bootstrap-ec2.sh:425-427` (`chmod 0640 /etc/flowin/app.env`, `chown root:flowin`)
  - `infra/modules/iam/main.tf:184-189` + `infra/modules/iam/variables.tf:47-51` (`attach_ssm_managed_policy=true` enables Session Manager)
- **Exploit chain:** `aws ssm start-session --target $INSTANCE_ID` (granted to anyone with `ssm:StartSession`) → `sudo cat /etc/flowin/app.env` (or run as a member of group `flowin` UID 10001 via `docker exec` from any container that bind-mounts the same group). Reading `SECRET_KEY` is game-over for HS256 JWTs (per `section_3_1_auth.md` C2/C4): an attacker can mint arbitrary `sub` claims for any user with a 24h validity that the per-jti revocation table cannot stop because the attacker controls `jti`. The same file also contains `DATABASE_URL` (so Postgres is one TCP hop away over the docker bridge), `LANGSMITH_API_KEY` if set, and `BEDROCK_INFERENCE_PROFILE_ID`.
- **Aggravators:** The KMS protection chain (`infra/modules/kms/main.tf:9-16` symmetric CMK with `enable_key_rotation=true` and `multi_region=false`) defends only the SSM at-rest store. Once the bootstrap pipeline reaches the `aws ssm get-parameters-by-path --with-decryption ... --output text` call at `bootstrap-ec2.sh:492-495`, the plaintext lives on local disk for the host's lifetime.
- **Mitigation sketch:** Two layers. (a) Eliminate the on-disk plaintext: rewrite the secret-load step to use systemd `LoadCredentialEncrypted=` (systemd-creds) so the decrypted value is only readable by the credentialed unit, or use `aws ssm get-parameter` per-secret at app start and stream the value into a fifo / unix-domain socket consumed by the FastAPI process. (b) Sever the SSM→cat path: drop `attach_ssm_managed_policy=true` for the prod IAM role, restrict `ssm:StartSession` via the IAM consumer's identity policy + a SCP, and gate session login via SSM `aws:userid` conditions. Until (a) is in place, this is a 24h-window key-leak surface for every operator with `ssm:StartSession`.

### 2. No memory / CPU / network-namespace cap on the LLM-generated Node subprocess; RCE turns into host-takeover
- **Files:**
  - `backend/app/services/pptx_export.py:157-160` (subprocess.run with timeout only)
  - `docker-compose.yml:108-112` (8 GB container limit, but no per-process / no Node `--max-old-space-size`)
  - `infra/modules/compute/main.tf:85-100` (IMDSv2 + hop_limit=2 — the hop_limit is required for Docker but it ALSO means the Node child can reach IMDS and steal instance-role credentials)
  - `infra/policies/bedrock-invoke.json` + `ssm-read.json` + `kms-decrypt.json` + `s3-backup-rw.json` + `s3-config-read.json` (the credentials Node can exfil)
- **Exploit chain:** Per Phase B `section_3_8_artifacts.md` C-1..C-6 and `section_3_3_history.md` C2-C4, an authenticated user POSTs LLM-generated Node code to `/api/workflows/export-pptx`; the backend `subprocess.run`s it with NO `env=`, NO `prlimit`, NO `unshare`. The Node child:
  - Inherits every env var (SECRET_KEY, DATABASE_URL, LANGSMITH_API_KEY, BEDROCK_INFERENCE_PROFILE_ID, AWS_REGION). Confirmed at `bootstrap-ec2.sh:469-503` — the loader writes them straight into the systemd EnvironmentFile that `docker compose up` then exports into the container.
  - Reaches IMDSv2 at `169.254.169.254` (hop_limit=2 allows it through Docker's bridge). Token-fetch → IAM-role-credentials → free use of every action in the seven instance-role policies until the STS credential expires (~6h). Bedrock invoke for arbitrary spend, SSM `GetParameter`/`GetParametersByPath` on the entire `/flowin/${env}/*` namespace (i.e. SECRET_KEY, DB password, LangSmith key), S3 PutObject on the backup bucket, KMS Decrypt against the project CMK.
  - Reaches `host.docker.internal:5432` (postgres) because the host firewall allows the docker bridge (`bootstrap-ec2.sh:139`); the DB password is in the inherited env.
- **The TF tree owns this control surface:** Container isolation, IAM scope, and IMDS reachability are all Terraform-controlled. The IAM scope is already as tight as the application needs (`ssm:GetParameter*` on `/flowin/${env}/*` is the loosest grant, and that namespace contains every app secret). The container isolation isn't.
- **Mitigation sketch:** (a) Compose-level: drop the network namespace for the export workload to a separate container with `network_mode: none` and `read_only: true`, `cap_drop: [ALL]`, `pids_limit: 32`, `memory: 256m`, `cpus: 0.5`, executing the Node binary via the FastAPI request handler over a unix socket. (b) IAM-level: split the EC2 instance role into a "always-on app role" with only Bedrock+CloudWatch and a "deploy role" only assumed via SSM RunCommand for SSM/KMS/S3-backup; this prevents IMDS exfil of the secret-reading credentials by an LLM-generated subprocess. Today both bundles ride the same role.

### 3. SECRET_KEY plaintext in Terraform state (S3 backend) — no separate state-access control
- **Files:**
  - `infra/modules/secrets/main.tf:104-122` (random_password + aws_ssm_parameter with `value = random_password.app_secret_key.result`)
  - `infra/modules/secrets/main.tf:18-22` (`random_password.app_secret_key` 64-char alnum)
  - `infra/envs/prod/backend.tf:12-20` (`encrypt = true` + `dynamodb_table = "flowin-tfstate-locks"`; no separate KMS key reference — relies on bootstrap CMK from `infra/bootstrap/main.tf:45-72`)
- **Exploit chain:** Both the `random_password` resource and the `aws_ssm_parameter` resource serialize the 64-char SECRET_KEY plaintext into the prod tfstate file. Anyone with `s3:GetObject` on `s3://flowin-tfstate-<acct>-<region>/envs/prod/terraform.tfstate` (and `kms:Decrypt` against the bootstrap CMK at `infra/bootstrap/main.tf:45-72`) can run `terraform state pull | jq '.resources[] | select(.type=="aws_ssm_parameter")'` and exfiltrate every SSM parameter value the module writes — SECRET_KEY, DATABASE_PASSWORD, LANGSMITH_API_KEY.
- **Aggravator:** There is no `aws_cloudtrail_event_data_store` watching `s3:GetObject` on the state bucket nor any EventBridge → SNS rule. CloudTrail management events capture the call but no on-call rule pages on it.
- **Mitigation sketch:** Move SECRET_KEY out of Terraform's value space entirely. Two safer options: (a) use the new TF 1.11+ ephemeral `aws_ssm_parameter`'s `value_wo` (write-only attribute — value never lands in state); (b) provision SECRET_KEY via `aws ssm put-parameter` from a one-shot operator-side script and use `terraform_data` to read the ARN, never the value. The current `lifecycle.ignore_changes = [value]` mitigates re-render but does NOT remove the plaintext that's already there.

### 4. KMS service grant to SNS lacks `aws:SourceAccount`/`aws:SourceArn` conditions
- **File:** `infra/modules/kms/main.tf:71-83` (`AllowSns` statement)
- **Exploit chain:** The KMS policy statement `AllowSns` grants `kms:Decrypt + kms:GenerateDataKey` to the `sns.amazonaws.com` service principal with NO condition. The other service-principal grants (S3 at `:85-103` and Backup at `:104-137`) both pin `aws:SourceAccount` (and Backup pins `aws:SourceArn` too). Today this is bounded by who can create an SNS topic that references this CMK (account-scoped via the `kms_master_key_id` API call), but the asymmetry is a defense-in-depth gap. Should a future regression to the bucket policy / KMS grants list this CMK as a cross-account key, the SNS branch is the open door — confused-deputy class.
- **Mitigation sketch:** Add to `AllowSns`:
  ```
  Condition = {
    StringEquals = {
      "aws:SourceAccount" = var.account_id
    }
  }
  ```
  (matching the S3 and Backup statements). Audit `section_2_cross_cutting.md` TF #6 calls this out explicitly.

## HIGH findings

### 5. `kms-decrypt.json` SSM-SecureString statement lacks `kms:ViaService`
- **File:** `infra/policies/kms-decrypt.json:4-14` (`DecryptSsmSecureStrings`)
- **Risk:** The first statement scopes `kms:Decrypt` to the SSM-parameter namespace via `kms:EncryptionContext:PARAMETER_ARN` but does NOT set `kms:ViaService = ssm.<region>.amazonaws.com`. The other three statements in the same file (`DecryptEbsViaEc2`, `DecryptBackupS3ViaService`, `DecryptEcrImagesViaService`) all do. If any other AWS service ever holds a value encrypted with this CMK and an `EncryptionContext:PARAMETER_ARN` matching the regex, this statement permits decryption via that service. Narrow today, but inconsistent with the sibling statements.
- **Mitigation:** Add `kms:ViaService = ssm.${region}.amazonaws.com` to the StringEquals condition.

### 6. `bedrock:GetAuthorizationToken` and ECR `GetAuthorizationToken` granted with Resource:* (unavoidable AWS API behavior, but document the residual risk)
- **Files:** `infra/policies/ecr-pull.json:5-14`, and the comment at `infra/modules/iam/main.tf:130-149`
- **Risk:** `ecr:GetAuthorizationToken` cannot be scoped to a repository — AWS doesn't accept resource-level scoping for it. The current policy mitigates by adding `aws:RequestedRegion = ${region}` (line 9-12 of the JSON). However:
  - A leaked instance credential can pull from any ECR repo IN THIS ACCOUNT that lists the instance role in its repository policy, OR any repo that has a `Principal: "*"` policy in this account.
  - More acutely: the token is short-lived (~12h) but valid for the ECR docker login API — an attacker who exfiltrates instance credentials can `docker login` and pull arbitrary images during that window (then run them on attacker-owned infra).
- **Mitigation:** Add an explicit `aws:SourceVpce` condition (the project's S3 gateway endpoint at `infra/modules/network/main.tf:374-385` is an analog) pinning ECR pulls to the project's VPC endpoint, blocking exfiltrated-credential pulls from outside AWS. Alternatively, replicate the EU-region pin (`aws:RequestedRegion`) already present.

### 7. ECR repository policy is additive-allow, not deny-by-default
- **File:** `infra/modules/ecr/main.tf:120-142` (`aws_ecr_repository_policy.this`)
- **Risk:** The repo policy adds `Allow` for the instance role's pull verbs, but does NOT add an `Effect:Deny` blocking principals other than the instance role from pulling. ECR's evaluation logic: a user identity with `ecr:BatchGetImage*` on this repo's ARN (granted via an account-level IAM policy, an org SCP-permitted role, or another IAM role with a wildcard ECR statement) can pull these images. The intent expressed by the comment ("pull-only, instance-role-only") is NOT enforced.
- **Aggravator:** ECR images contain SECRET_KEY-related code at minimum (`backend/app/core/security.py` imports SECRET_KEY from settings; the image doesn't bake the key itself, but it does carry the entire deploy code). An adversary pulling the image gains static analysis insight into auth flows.
- **Mitigation:** Add a Deny statement for `Principal: *` with a `Condition: StringNotEquals: aws:PrincipalArn: <instance_role_arn>`. Note: the comment at `infra/modules/ecr/main.tf:111-119` correctly explains why pushes aren't granted (CI uses identity-side IAM), so push-side is fine — pull-side is the gap.

### 8. CloudWatch log groups encrypted with project CMK; key policy `AllowCloudWatchLogs` matches `/flowin/*` (multi-environment scope)
- **File:** `infra/modules/kms/main.tf:49-69` (`AllowCloudWatchLogs` statement) + `infra/modules/monitoring/main.tf:37-62` (log groups under `/flowin/${var.environment}/...`)
- **Risk:** The KMS policy's `kms:EncryptionContext:aws:logs:arn` pattern is `arn:.../log-group:/flowin/*` — matches every environment. The project uses one CMK per environment, so today this is benign. But if a future stack ever shares this CMK across environments (e.g. staging using prod's CMK to read prod logs during a debug window), the pattern is the gate that fails open. Defense-in-depth: should be `/flowin/${var.environment}/*`. Per `section_2_cross_cutting.md` TF #2 — confirmed.
- **Mitigation:** Add `environment` as a KMS module variable; tighten the condition pattern to `/flowin/${var.environment}/*`. Note: the same audit-trail finding also exists for `kms-decrypt.json:54-61` where the EC2 instance can decrypt logs in any `/flowin/*` pattern — same fix shape, scope by environment in the JSON template.

### 9. No CloudTrail data-events monitoring on the SSM SecureStrings or the KMS key
- **Files:** `infra/modules/monitoring/main.tf` (no `aws_cloudtrail_*` and no `aws_cloudwatch_event_rule` watching SSM/KMS) + `infra/modules/secrets/main.tf:104-122`
- **Risk:** A `GetParameter` for `/flowin/${env}/SECRET_KEY` from anything other than the EC2 instance role should page on-call. Currently there is no alarm, no EventBridge rule, no metric filter. CloudTrail management events capture the call (per AWS default), but no actionable signal goes to the alert-email pipeline.
- **Why HIGH not MEDIUM:** This is the "find out" alarm for finding 1 (SECRET_KEY plaintext). Without it, an SSM-session-mediated `cat /etc/flowin/app.env` is undetectable.
- **Mitigation:** Add an EventBridge rule on the SSM data plane:
  ```
  source: ["aws.ssm"]
  eventName: ["GetParameter", "GetParameters", "GetParametersByPath"]
  requestParameters.name: ["/flowin/${env}/SECRET_KEY"]
  userIdentity.arn: !instance_role_arn
  ```
  → SNS alerts topic. Same shape for `kms:Decrypt` against the project CMK from a non-allowlist principal.

### 10. SSM parameter tier is `Standard` for `SECRET_KEY` — no parameter-policy expiry / no history audit trail beyond 100 entries
- **File:** `infra/modules/secrets/main.tf:104-122` (`tier = "Standard"`)
- **Risk:** SSM `Standard` tier (a) caps history at 100 entries — once exceeded, older versions roll off — and (b) does not support parameter policies (`Expiration`, `ExpirationNotification`, `NoChangeNotification`). The rotation discipline depends on operator memory, and the only mitigation is the `description` field saying "Rotate yearly". Per `section_3_1_auth.md` TF1, there's no enforcement.
- **Mitigation:** Promote SECRET_KEY (and DATABASE_PASSWORD) to `Advanced` tier; add a `policies` JSON with `ExpirationNotification: { After: 365, Unit: Days }`. EventBridge → SNS pages the operator at rotation-due time. Cost: $0.05/month per Advanced parameter; well worth it.

### 11. `random_password` does not include the `keepers` block; `taint` is a no-op due to lifecycle.ignore_changes
- **File:** `infra/modules/secrets/main.tf:18-22` (random_password) + `infra/modules/secrets/main.tf:116-121` (ignore_changes = [value])
- **Risk:** A `terraform taint random_password.app_secret_key` (or `terraform apply -replace=...`) regenerates the value, but the downstream `aws_ssm_parameter.app_secret_key` has `lifecycle.ignore_changes = [value]` — so the new SECRET_KEY is **not propagated to SSM**. Operators believing they've rotated by taint are running on the old key. Per `section_3_1_auth.md` TF7.
- **Mitigation:** Either remove the `ignore_changes = [value]` on rotation events (so the new random_password propagates), or document explicitly that taint of `random_password` is a no-op and rotation MUST be done via `aws ssm put-parameter --overwrite` outside Terraform. Currently the docs don't say either.

### 12. Bootstrap CMK key policy lacks an explicit "deny all but root" guard for state access
- **File:** `infra/bootstrap/main.tf:45-72` (the bootstrap CMK)
- **Risk:** The bootstrap CMK's policy grants only `AWS = arn:aws:iam::${var.expected_account_id}:root`, which delegates authorization to the account's IAM identity policies. That's the standard AWS pattern. But because there's no `Deny` for principals lacking `s3:GetObject` permission on the state bucket, any IAM principal in the account that holds `kms:Decrypt` against this key (via a managed policy or wildcard role) can read the state when combined with `s3:GetObject`. The state bucket policy (`infra/bootstrap/main.tf:125-149`) only denies insecure transport — no IAM scoping.
- **Aggravator:** The state file contains SECRET_KEY, DATABASE_PASSWORD, and LANGSMITH_API_KEY plaintext (finding 3).
- **Mitigation:** Tighten via a permission boundary on Terraform operator roles, OR add a separate `aws_s3_bucket_policy` Deny statement: deny `s3:GetObject` on the state bucket unless `aws:PrincipalArn` is one of an explicit allowlist (Terraform CI role + named operators). This requires knowing the allowlist at bootstrap time, but it's the only way to keep state access tightly held.

### 13. Sudoers rule for `flowin-deploy` accepts any image URI matching a permissive regex
- **File:** `infra/scripts/bootstrap-ec2.sh:802-819` (sudoers stanza) + `:777-799` (wrapper script)
- **Risk:** The sudoers entry lets `flowin-deploy ALL=(root) NOPASSWD: /usr/local/bin/flowin-update-image-tag (backend|frontend) *`. The wrapper validates `^[a-z0-9._/:-]+$` and 255 chars — that's good. BUT: the regex permits the image URI `<other-account>.dkr.ecr.<region>.amazonaws.com/anything:bad`. The wrapper writes this verbatim into `/etc/flowin/app.env`'s `BACKEND_IMAGE=` line and `systemctl restart flowin-app.service` pulls and runs whatever container the URI points to. If `flowin-deploy`'s SSH key is compromised (via a stolen CI deploy key), the attacker has a one-shot container-substitution that pulls an arbitrary attacker-owned ECR-shaped image — the host IAM role's `ecr:GetAuthorizationToken` is account-wide, so a foreign ECR could only be reached if the foreign ECR's policy allows public pull (rare but exists), and pulling from `docker.io` works regardless because `flowin-ecr-login` only authenticates against ECR but doesn't restrict the daemon to ECR-only.
- **Mitigation:** Tighten the wrapper regex to enforce the image URI starts with `<account>.dkr.ecr.${region}.amazonaws.com/flowin-${environment}-(backend|frontend):`. Even better: don't accept a URI at all — accept only a git-SHA tag and compose the URI from `FLOWIN_ECR_REGISTRY` (which is operator-controlled at TF apply time).

### 14. Docker daemon defaults to bridge networking; no host-firewall isolation between containers
- **Files:** `infra/scripts/bootstrap-ec2.sh:316-329` (Docker install — no daemon config) + `bootstrap-ec2.sh:127-140` (UFW allows the docker bridge subnet `172.16.0.0/12`)
- **Risk:** UFW allows any container in the `172.16.0.0/12` range to reach Postgres on `127.0.0.1:5432` (line 139). With the docker-compose default bridge, the backend and frontend containers share a network namespace; any other container (whether docker-compose'd or independently `docker run`'d) on the host can reach the same Postgres port. There's no `iptables`/UFW segmentation between containers, no `userland-proxy=false`, no `icc=false` daemon flag. A future ops mistake of `docker run --rm -it alpine` on the host gets free network access to Postgres with the host-network bridge.
- **Mitigation:** Configure `/etc/docker/daemon.json` with `{"icc": false, "userland-proxy": false}` and explicitly attach the backend container to an isolated user-defined network with only the database peer allowed. Alternatively bind Postgres to the docker-compose-internal bridge gateway IP and tighten UFW to only that.

## MEDIUM findings

### 15. KMS key not `multi_region` — DR plan implicitly single-region
- **File:** `infra/modules/kms/main.tf:13-15` (`multi_region = false`)
- **Risk:** A region failover (eu-central-1 → eu-west-1) cannot decrypt SSM SecureStrings or the EBS snapshot. Acceptable for the current single-region deployment, but the DR runbook (per `section_3_1_auth.md` TF3) names a second region as recovery target — this is the gating gap. Multi-region keys propagate the key material to up to ~8 replica regions; the encryption context and ARN format change.
- **Mitigation:** Flip to `multi_region = true` IF the DR plan requires cross-region recovery. Document trade-off: multi-region keys cannot be deleted independently and key policy must be replicated across replicas.

### 16. KMS key rotation rotates DEK material, not the underlying SSM-stored SECRET_KEY
- **File:** `infra/modules/kms/main.tf:12` (`enable_key_rotation = true`)
- **Risk:** Per `section_3_1_auth.md` TF4. The rotation handles the KMS data-key wrapping; the plaintext SECRET_KEY value in the SSM parameter is unchanged across the rotation, so JWTs signed with the old SECRET_KEY remain valid. The combined "we rotate keys" + "we don't rotate the secret" gives a false sense of security in the audit trail. Compounded with finding 11 (taint is a no-op).
- **Mitigation:** Document in `infra/README.md` rotation section that `enable_key_rotation` does NOT invalidate signed JWTs.

### 17. EBS data volume encrypted, but snapshot copies (via AWS Backup) inherit the same single-region CMK
- **Files:** `infra/modules/compute/main.tf:50-68` (data EBS, KMS-encrypted) + `infra/modules/backups/main.tf:222-234` (AWS Backup vault with `kms_key_arn = var.kms_key_arn`)
- **Risk:** AWS Backup recovery points are encrypted with the same CMK that protects the source EBS volume. If the CMK is somehow disabled, EVERY snapshot is unrecoverable — there's no cross-CMK backup. Single point of failure on the project CMK.
- **Mitigation:** AWS Backup vault can be configured with a separate KMS key. Document the trade-off (operational simplicity vs. blast-radius reduction) and decide explicitly.

### 18. No symmetric/asymmetric verification on the inference-profile region in `bedrock-invoke.json`
- **File:** `infra/policies/bedrock-invoke.json:14-17`
- **Risk:** The inference-profile ARN is built with `${region}` from variables — i.e., the EC2 deployment region (eu-central-1 in prod). However, the EU cross-region inference profile (`eu.anthropic.claude-haiku-4-5-...`) exists in a SPECIFIC home region. If `var.region` is changed to eu-west-1 but the profile lives in eu-central-1, this Allow does not match the actual ARN; every InvokeModel call against the profile gets 403. Per `section_3_5_pipeline_and_backend.md` T2 — confirmed.
- **Mitigation:** Change the Resource ARN to `arn:${partition}:bedrock:*:${account_id}:inference-profile/${inference_profile_id}` (region wildcard) — the `aws:RequestedRegion` condition already restricts to EU regions, so the wildcard is safe. Documented as a security issue because a silent 403 storm is hard to triage and looks like a credential leak; tightening the policy correctly removes this red herring.

### 19. VPC flow logs capture-mode is `ALL` (good); retention is variable-driven, default 30d (acceptable but verify against forensics requirements)
- **Files:** `infra/modules/network/main.tf:432-484` (flow logs + log group + IAM)
- **Risk:** 30d default retention (`infra/modules/network/variables.tf:89-98`) may be too short for incident-response timeline. If an incident is detected at T+45 days from event, no flow logs are available. The forensic value is real (per `infra/README.md` Phase 3 item 17).
- **Mitigation:** Bump default to 90d, or override in `log_retention_overrides` for `/flowin/${env}/vpc-flow-logs`. Currently this group is created in the network module, not the monitoring module, so the overrides map (`infra/envs/prod/terraform.tfvars.example:170-173`) doesn't apply to it. Should the network module honor `log_retention_overrides` similarly?

### 20. CloudWatch alarm coverage is excellent for operational metrics but absent for security events
- **File:** `infra/modules/monitoring/main.tf` (alarms list at `:354-977`)
- **Risk:** Coverage exists for: CPU, memory, disk, inode, nginx 5xx, DB connection errors, Bedrock throttles/server-errors/tokens, billing, WS disconnects, pg-dump heartbeat, cert renewal failure/heartbeat, agent error rate, stuck workflows. **Missing**:
  - Failed login surges (auth events; no metric filter on `/flowin/${env}/auth` group — see `section_3_1_auth.md` H6)
  - SSH login from new IP (auth.log shipped but not metric-filtered)
  - `sudo` use outside the documented sudoers entries
  - KMS denials (a `kms:Decrypt` denied event is a red flag and would catch finding 1's "deny by default" failure)
  - SSM Session Manager session-start (`StartSession` event from a non-allowlist principal)
  - AWS GuardDuty findings (per `infra/README.md:115` GuardDuty is org-managed; need to verify the alerts pipe through to project SNS)
- **Mitigation:** Add the metric filters + alarms above. Particularly the KMS-denial alarm — it's the canary for misconfigured IAM that this audit identified.

### 21. SNS topic `kms_master_key_id` on the eu-central-1 topic is the project CMK; the us-east-1 billing topic uses `alias/aws/sns` (AWS-managed)
- **Files:** `infra/modules/monitoring/main.tf:81-89` (project CMK on project topic) + `:255-266` (AWS-managed key on billing topic)
- **Risk:** Per the comment at `infra/modules/monitoring/main.tf:74-79`, the us-east-1 billing topic deliberately uses `alias/aws/sns` (the AWS-managed key) because the project CMK is region-pinned to eu-central-1. The risk is small (billing topic carries only operational metadata — account ID + USD threshold). However, AWS-managed keys are not under customer control: rotation, key-policy changes, and access patterns are AWS-defined. The choice is documented and intentional, but worth flagging: anyone with `sns:Subscribe` on the topic (gated by topic policy at `:283-344`) AND `kms:Decrypt` against `alias/aws/sns` (a wide allow by AWS default) can subscribe and read. The topic policy restricts subscribe to the topic owner (`Principal: root`), so this is OK today.
- **Mitigation:** None required if the policy stays restrictive. Worth a periodic review.

### 22. The SNS topic policy enumerated action list is correct (PascalCase) — RESOLUTION of the lowercase-vs-PascalCase question raised in the brief
- **File:** `infra/modules/monitoring/main.tf:113-145` (project topic) + `:283-344` (billing topic)
- **AWS documentation:** Per the official AWS docs at https://docs.aws.amazon.com/sns/latest/dg/sns-access-policy-language-api-permissions-reference.html, all SNS resource-policy actions are PascalCase: `sns:Publish`, `sns:Subscribe`, `sns:GetTopicAttributes`, etc. SNS resource policies inherit the AWS IAM action naming convention (PascalCase), NOT the AWS CLI command convention (lowercase-hyphen). The current code is **correct**.
- **Also correct:** The decision to enumerate actions instead of using `sns:*`. The comment at `infra/modules/monitoring/main.tf:114-119` is right: the `sns:*` wildcard expansion includes service-level actions (`sns:CreateTopic`, `sns:ListTopics`) that only work via IAM identity policies and are rejected by SNS's resource-policy validator. So the enumerated form is required AND PascalCase.
- **No action needed.** §2 audit's hint that "PascalCase might be correct, lowercase wrong" is resolved: PascalCase is correct.

### 23. `aws_iam_role_policies_exclusive` enforces inline-policy locks but is brittle to new policy additions
- **File:** `infra/modules/iam/main.tf:226-238` (`aws_iam_role_policies_exclusive.instance`)
- **Risk:** The `policy_names` list at `:228-237` is the canonical list of inline policies. Anyone adding a new `aws_iam_role_policy.X` to this module who forgets to update the list will have their policy silently DELETED on the next apply. The comment at `:212-224` acknowledges this is a foot-gun. It's the right control (drift detection) but with a sharp edge.
- **Mitigation:** No fix per se — this is a design trade-off. Document in the modular-IAM contract and consider a `lifecycle` block on the exclusive resource that requires explicit human approval for changes.

### 24. PostgreSQL `pg_hba.conf` is scram-sha-256 for host (good), but `listen_addresses = '*'` exposes via every interface
- **File:** `infra/scripts/bootstrap-ec2.sh:253-275`
- **Risk:** scram-sha-256 is correctly enforced for host-mode connections (`:271-274`). `listen_addresses = '*'` is paired with UFW's `ufw allow from 172.16.0.0/12 to any port 5432` (line 139) and the VPC security group blocking external 5432. Today this is safe. But:
  - The `*` bind means a UFW reload or `/etc/ufw/` config drift removes the network-layer guard, instantly exposing 5432 on the EIP IPv4 to the public internet.
  - The container `host.docker.internal` resolution (line 244-252) requires `*` per the comment, so this isn't easily fixable without redesigning the network architecture.
- **Mitigation:** Add a CloudWatch metric filter on `/flowin/${env}/postgres` for `connection authorized: user=flowin database=flowin host=<non-docker-IP>` patterns, alarming on any connection from outside `172.16.0.0/12` and `127.0.0.1`. Belt-and-suspenders.

### 25. The setfacl rules on `/var/lib/docker/containers` open the directory to `other:r-x`
- **File:** `infra/scripts/bootstrap-ec2.sh:336-347` and `:710-712`
- **Risk:** `setfacl -R -m u:cwagent:rX,o::r /var/lib/docker/containers` (lines 346-347, 711-712) makes container metadata directory readable by ALL users on the host (`o::r` is the load-bearing bit per the comment). The comment explains this is required for non-root containers (UID 10001 flowin) to read /etc/hosts. The trade-off is that ANY user on the host can read container metadata, including the JSON log files (`/var/lib/docker/containers/*/json.log`) which may contain partial application logs.
- **Mitigation:** Replace the ACL trick with a more targeted fix: bind-mount a custom `/etc/hosts` into the backend container via docker-compose's `extra_hosts` (or rebuild the image with `getent` fallback). The `o::r` ACL is a workaround for a containerization edge case; the right fix is at the compose layer.

### 26. EBS encryption is enabled but key-rotation behavior is opaque
- **Files:** `infra/modules/compute/main.tf:50-68` (data EBS) + `:114-127` (root EBS)
- **Risk:** Both volumes set `encrypted = true` with `kms_key_id = var.kms_key_arn`. The project CMK has `enable_key_rotation = true` (good), but the EBS volume's at-rest encryption uses a derived data-encryption key that's NOT rotated on KMS rotation — only the wrapping key rotates. Volume re-encryption to a new key requires snapshot + restore with the new key. This is standard AWS behavior, but the operational implication ("KMS key rotation doesn't rotate EBS at-rest crypto") should be documented.
- **Mitigation:** Note in runbook. No action required.

### 27. `ssh_allowed_cidrs` defaults to empty but the example tfvars suggests `203.0.113.10/32` — and the variable validation only rejects `0.0.0.0/0`
- **Files:** `infra/modules/network/variables.tf:49-65` + `infra/envs/prod/terraform.tfvars.example:41-43`
- **Risk:** Validation rejects `0.0.0.0/0` (good) but accepts any other CIDR. An operator who fat-fingers `203.0.113.0/0` (which is malformed but `can(cidrnetmask())` returns true on it) or `0.0.0.0/1` (which is half the internet) passes validation. The current pattern is "user-chosen CIDR allowlist," but there's no upper-bound check.
- **Mitigation:** Add a validation that `cidrhost(cidr, 0)` is not in any of the well-known overly-broad ranges (`0.0.0.0/0..8`, `0.0.0.0/0`, etc.) or restrict to /20 or tighter.

### 28. Bootstrap doesn't drop the docker socket protection
- **Files:** `infra/scripts/bootstrap-ec2.sh:316-329` (Docker install) + `infra/scripts/bootstrap-ec2.sh:170-180` (flowin user creation)
- **Risk:** Docker is installed with default settings. The Docker socket at `/var/run/docker.sock` is root:docker (mode 0660). The `flowin` system user is NOT in the docker group (verified at `:174-180`). Good. However:
  - The setfacl trick at `:336-347` for the containers directory implies someone considered putting flowin in the docker group; it was correctly avoided.
  - `flowin-deploy` user (per `:769-775`) is also NOT in the docker group. Good.
  - But if anyone ever adds the flowin or flowin-deploy user to `docker` group, they get root-equivalent via `docker run --privileged --volume /:/host alpine chroot /host`. The bootstrap doesn't have a recurring check for this. A future operator typing `usermod -aG docker flowin` to "fix a permission issue" silently grants root.
- **Mitigation:** Add a systemd post-install check that fails the bootstrap if any non-root user is in the docker group. Or run `chown root:adm /var/run/docker.sock; chmod 0660 /var/run/docker.sock` to make the socket admin-only and explicitly add the few automation accounts as needed.

### 29. Container image scanning is enabled but findings don't gate deployment
- **File:** `infra/modules/ecr/main.tf:47-49` (`scan_on_push = true`)
- **Risk:** ECR scans on push, but there's no admission-control gate that prevents the EC2 from pulling an image with HIGH/CRITICAL findings. The deploy.sh CI pipeline doesn't reference scan results. An image with a known RCE in pptxgenjs (or its transitive deps) could be pushed and pulled silently.
- **Mitigation:** Add a CI gate that calls `aws ecr describe-image-scan-findings` after push and fails the deploy if HIGH/CRITICAL count > 0. Or integrate with Inspector v2 (Amazon Inspector for ECR) which auto-blocks per a policy. Note: `infra/README.md:115` excludes account-level `aws_inspector_*` resources, so Inspector v2 must be configured outside this Terraform.

### 30. No image-vulnerability alarm on the ECR scanning results
- **File:** `infra/modules/monitoring/main.tf` (no ECR-scan alarm)
- **Risk:** Even with scan_on_push, the findings are visible only in the AWS console. No EventBridge → SNS rule fires on scan-completion-with-findings. The development team learns about a CVE in pptxgenjs only when manually checking.
- **Mitigation:** Add an EventBridge rule on `source: ["aws.ecr"]`, `eventName: ["scan-completion"]` with `findingSeverityCounts.HIGH > 0 OR CRITICAL > 0` → SNS alerts.

### 31. Bootstrap installs `fail2ban` and `auditd` but doesn't configure them
- **File:** `infra/scripts/bootstrap-ec2.sh:98-104` (apt install line)
- **Risk:** fail2ban and auditd are installed but the script never writes a config or enables custom rules. They run with their distro defaults — fail2ban watches `/var/log/auth.log` for SSH brute-force (good baseline); auditd watches the kernel audit subsystem with a minimal default ruleset (poor for compliance). For a "single-EC2 with SSM-as-primary-SSH" deployment, fail2ban for SSH is a defense-in-depth win, but it's running on the default jail config (which is generally sane).
- **Aggravator:** The CW Agent ships `auth.log` and `audit.log` to CloudWatch (per `bootstrap-ec2.sh:752-754` and `:751`), so the rules-vs-default-detection signal is captured. But no metric filter on those log groups for failed-SSH-spike or audit-rule-trigger.
- **Mitigation:** Either remove fail2ban/auditd (if not used) or configure them with explicit rules + add the metric filters in finding 20.

### 32. Bootstrap CMK at `infra/bootstrap/main.tf` doesn't have `multi_region` or `enable_key_rotation` audit signals
- **File:** `infra/bootstrap/main.tf:45-72`
- **Risk:** `enable_key_rotation = true` (good) but `multi_region` not set (defaults false). Deletion window 30d (max — good). The key has `prevent_destroy = true` lifecycle (good). The policy is `account-root only` — relies entirely on IAM identity-side scoping for who can use it. No CloudTrail data-event watching this key specifically; relies on management-event capture.
- **Mitigation:** Document the trust assumption (operator IAM must restrict `kms:Decrypt` on this key to Terraform-CI roles + named operators) and consider adding `multi_region = true` if DR needs cross-region state recovery.

## LOW findings (cosmetic / belt-and-suspenders)

### L-1. Comment drift in `iam/main.tf:50-55` lists 3 EU regions; the actual JSON has 7
- **File:** `infra/modules/iam/main.tf:50-55` (comment) vs `infra/policies/bedrock-invoke.json:20-28` (7 regions)
- **Risk:** Cosmetic. Per `section_3_5_pipeline_and_backend.md` T1/T10.

### L-2. `aws_kms_alias` lacks `prevent_destroy`
- **File:** `infra/modules/kms/main.tf:170-173`
- **Risk:** The CMK key has `prevent_destroy = true` at `:160-162` but the alias doesn't. Operators sometimes `terraform destroy -target` the alias to break a dependency; doing so leaves the key orphaned. Per `section_2_cross_cutting.md` TF #7.
- **Mitigation:** Add `lifecycle { prevent_destroy = true }` to `aws_kms_alias.this`.

### L-3. `aws_kms_alias.bootstrap` similarly lacks `prevent_destroy`
- **File:** `infra/bootstrap/main.tf:70-73`
- **Mitigation:** Same as L-2.

### L-4. Default tags on the prod provider include `Repo = "gitlab.com/hexaware-uki/flowin"` — discloses internal repo location
- **File:** `infra/envs/prod/providers.tf:13-22`
- **Risk:** Every resource carries this tag. AWS Resource Tagging API is queryable by anyone with `tag:GetResources` in the account. The tag value reveals the internal GitLab project location, which is a small information disclosure to anyone with read on Resource Tags. Aligned with the org's transparency posture — likely intentional — but worth flagging.

### L-5. SSM Parameter for `cors_origins` is a String type (not SecureString) — fine, but the value goes plaintext into state
- **File:** `infra/modules/secrets/main.tf:46-64`
- **Risk:** Acceptable — CORS origins aren't secret. Just noting that `Standard` tier String parameters are also in plaintext state.

### L-6. The bootstrap script's `aws ssm get-parameter ... --output text` at `:292-294` and `:493` discloses the value to bash's argv and process listing transiently
- **File:** `infra/scripts/bootstrap-ec2.sh:292-294, 358-359`
- **Risk:** During the milliseconds between `aws ssm get-parameter` returning and the value being consumed, `ps auxef` reveals the plaintext to any other user on the host. The only user that could see it is `flowin` or `root` (host is single-user, no UI), so blast radius is tiny. Defense in depth would use `aws ssm get-parameter --output json | jq -r ...` (still passes through argv) or read via the AWS SDK from a Python process where the value never leaves memory.

### L-7. `unattended-upgrades` is enabled with `Automatic-Reboot "true"` at 04:00 — auto-patching is correct, but no maintenance-window coordination
- **File:** `infra/scripts/bootstrap-ec2.sh:163-169`
- **Risk:** Auto-reboot at 04:00 UTC has no coordination with active pipelines or pg_dump windows. If a 03:30 UTC-scheduled pg_dump is in flight, the 04:00 reboot interrupts it. Operational, not security, but worth noting.

### L-8. `apt-get install` runs unpinned versions of nginx, postgresql-16, certbot, ufw, etc.
- **File:** `infra/scripts/bootstrap-ec2.sh:98-104`
- **Risk:** Re-running the bootstrap on a new EC2 may install slightly different versions of the same packages. Reproducibility / supply-chain hygiene gap. Acceptable for a single-instance deployment but flag for the next refactor.

### L-9. The `egress all-ports` rule via the app SG's `app_https`, `app_http`, `app_dns_*` allows outbound to `0.0.0.0/0`
- **File:** `infra/modules/network/main.tf:247-297`
- **Risk:** Egress rules allow the EC2 to reach the entire internet on 80/443/53. This is required for apt updates, Bedrock fallback, OCSP, ACME, etc. — but it also lets a successful RCE exfiltrate freely to any domain. Tightening to a domain-allowlist (using AWS Network Firewall + a managed rule set) would block exfiltration to arbitrary domains. Beyond scope for a single-EC2 design but flag for security maturity.

### L-10. Tagging convention enforces `Environment = var.environment` everywhere, BUT some resources tag with `Backup = "true"` (compute) for the data volume only
- **File:** `infra/modules/compute/main.tf:59-64`
- **Risk:** Tag-based AWS Backup selection at `infra/modules/backups/main.tf:278-294` keys on `Backup=true`. Anyone in the account with `ec2:CreateTags` on EC2 volumes can opportunistically backup arbitrary volumes by tagging them. The backup vault then encrypts them with the project CMK. Not a direct exfil, but a billing risk + a way for an outside-the-project resource to land in the project backup space.
- **Mitigation:** Pin the AWS Backup selection condition to `aws:ResourceTag/Environment = ${var.environment}` AND `Project = flowin` to lock down the selection scope.

### L-11. The bootstrap user_data shell script doesn't escape `${k}=${v}` for the extra_env iteration
- **File:** `infra/modules/compute/user_data.sh.tpl:60-62`
- **Risk:** `extra_env` is set in `infra/envs/prod/main.tf:178-212`. Values like `FLOWIN_ACME_EMAIL = var.alert_email` flow through — Terraform validates the email format at `infra/envs/prod/variables.tf:344-347`, so injection is bounded. But if a future variable carries a string with `$` or backtick, the heredoc at `user_data.sh.tpl:52-57` does substitution. Defense in depth would single-quote-escape the values.

### L-12. `_DEFAULT_SECRET_KEY` mismatch between code defaults and bootstrap path
- **File:** `backend/app/core/config.py:43-135` (mentioned in `section_2_cross_cutting.md` LOW #6)
- **Risk:** A developer who copies `env-templates/.env.development:28` (SECRET_KEY = "dev-secret-change-this-to-random-string") into `.env` and forgets to rotate passes the length check. Not strictly TF but flagged because the TF secrets module's `random_password` default would override this in any production-via-Terraform path.

## Verified clean (explicit non-issues — items we explicitly checked and OK'd)

The following are CHECKED and CORRECT — not findings, but worth documenting that they were specifically examined:

- **SNS topic policy uses PascalCase actions** (`infra/modules/monitoring/main.tf:128-142, 297-311`). Per the AWS SNS API permissions reference at https://docs.aws.amazon.com/sns/latest/dg/sns-access-policy-language-api-permissions-reference.html, SNS resource-policy actions ARE PascalCase. The enumerated form (not `sns:*` wildcard) is required because SNS's resource-policy validator rejects `sns:*`. **Resolution of the brief's open question: PascalCase is correct.**
- **IMDSv2 enforcement** (`infra/modules/compute/main.tf:85-100`): `http_tokens = "required"`, `http_put_response_hop_limit = 2` (justified by the inline comment — Docker needs 2 hops). IMDSv1 is disabled. Per `section_3_5_pipeline_and_backend.md` T4.
- **EBS root + data volume encryption** (`infra/modules/compute/main.tf:50-68, 114-127`): Both encrypted with the project CMK; data volume has `prevent_destroy = true`.
- **S3 backup bucket policy** (`infra/modules/backups/main.tf:108-157`): TLS-only (`aws:SecureTransport = false → Deny`), unencrypted PUT denied, wrong-KMS-key PUT denied. Public-access block enabled (`:44-51`). Versioning enabled (`:35-41`). KMS-encrypted (`:53-63`). Object Lock supported (opt-in, default off — correct trade-off given the irreversibility).
- **AWS Backup vault** (`infra/modules/backups/main.tf:222-234`): KMS-encrypted with project CMK; `prevent_destroy = true`. Vault Lock supported (opt-in, default off — correct given the 3-day cooling-off window).
- **AWS Backup service role trust policy** (`infra/modules/backups/main.tf:174-196`): Includes both `aws:SourceAccount` AND `aws:SourceArn` confused-deputy guards.
- **VPC flow logs role trust policy** (`infra/modules/network/main.tf:399-419`): Includes `aws:SourceAccount` confused-deputy guard.
- **VPC interface endpoint policies** (`infra/modules/network/main.tf:14-30, 56-92`): All include `aws:PrincipalAccount` pin. The S3 gateway endpoint additionally scopes Resource to the project backup bucket + the ECR starport layer bucket (with documented reason for the starport-bucket allowance).
- **VPC default security group + route table locked down** (`infra/modules/network/main.tf:133-153`): Empty ingress, empty egress; safety net for any future resource accidentally landing in the default SG.
- **Public subnet `map_public_ip_on_launch = false`** (`infra/modules/network/main.tf:161`): EIP is the only public IP path. Verified.
- **Application SG ingress** (`infra/modules/network/main.tf:206-245`): 80, 443 from 0.0.0.0/0 (HTTP/HTTPS — required for ACME and the LB-less single-EC2 design); 22 only via `ssh_allowed_cidrs` for_each (`:232-245`). SSH validation rejects `0.0.0.0/0` (`infra/modules/network/variables.tf:54-58`).
- **Application SG egress** (`infra/modules/network/main.tf:247-310`): Explicit 80/443/53/443-to-endpoints; no implicit allow-all. Tighter than the default Terraform behavior (which is to NOT create the default allow-all egress in newer providers).
- **Endpoints SG** (`infra/modules/network/main.tf:314-340`): Only the app SG allowed in on 443; no default egress.
- **Account-guard preconditions** (`infra/modules/account_guard/main.tf:9-46`): Two `lifecycle.precondition` blocks on account_id and region + two `check` blocks for plan-time warnings. Excellent control.
- **KMS key trust policy structure** (`infra/modules/kms/main.tf:17-158`): Granular per-service statements with conditions on `aws:SourceAccount`, `aws:SourceArn`, `kms:ViaService`, `kms:GrantIsForAWSResource`. Backup statement is exemplary.
- **`aws_iam_role_policies_exclusive` + `aws_iam_role_policy_attachments_exclusive`** (`infra/modules/iam/main.tf:226-250`): Locks the role's permission set against out-of-band drift. This is the right control for a project-critical role.
- **`prevent_destroy` discipline:** KMS key, S3 backup bucket, EBS data volume, EIP, IAM instance role, IAM instance profile, AWS Backup vault, AWS Backup plan, AWS Backup selection, and CloudWatch log groups all carry `prevent_destroy = true`. Audit B `prevent_destroy` discipline is solid.
- **ECR `image_tag_mutability = IMMUTABLE`** (`infra/modules/ecr/main.tf:40`): Prevents the "someone re-pushed latest and broke prod" failure mode. Plus `force_delete = false` (explicit) so destroy doesn't silently nuke pushed artifacts.
- **ECR `scan_on_push = true`** (`infra/modules/ecr/main.tf:47-49`): Vulnerability scanning at upload time. (Gating gap noted in finding 29.)
- **SSM Parameter Store paths** under `/flowin/${env}/` are correctly partitioned. IAM read scope (`infra/policies/ssm-read.json:11-15`) matches with parent + recursive children.
- **Bootstrap script `set -euo pipefail`** (`infra/scripts/bootstrap-ec2.sh:27`): Fast-fail on any error.
- **Bootstrap script root-user check** (`infra/scripts/bootstrap-ec2.sh:31-34`): Refuses to run as non-root.
- **Bootstrap script SSH hardening** (`infra/scripts/bootstrap-ec2.sh:142-161`): Disables root login, password auth, X11, agent forwarding, tunnel; sets `MaxAuthTries 3`, `LoginGraceTime 30`. Strong baseline.
- **Bootstrap script PostgreSQL `auth-host=scram-sha-256`** (`infra/scripts/bootstrap-ec2.sh:236, 269-275`): Strongest currently-supported PostgreSQL auth.
- **Bootstrap script sudoers stanza via `visudo -cf`** (`infra/scripts/bootstrap-ec2.sh:802-819`): Validates the sudoers syntax before installation. Failure aborts. Good defensive coding.
- **Bootstrap script EnvironmentFile mode** (`infra/scripts/bootstrap-ec2.sh:425-427, 445, 506`): `0640 root:flowin`. The group-read bit is required for the docker-compose mount; the not-world-readable bit is correct.
- **The bootstrap state bucket policy** (`infra/bootstrap/main.tf:125-149`): Denies non-TLS access.
- **DynamoDB state-lock table** (`infra/bootstrap/main.tf:154-178`): PAY_PER_REQUEST, KMS-encrypted with the bootstrap CMK, point-in-time recovery enabled, `prevent_destroy = true`.
- **No `aws_*default*` resources at account-level** (per `infra/README.md:115`): The two `aws_default_security_group.vpc_default` and `aws_default_route_table.vpc_default` are vpc-scoped (intentional exception, documented).
- **No `aws_organizations_*`, `aws_iam_account_*`, `aws_s3_account_public_access_block`, `aws_config_*`, `aws_securityhub_*`, `aws_macie2_account`, `aws_guardduty_detector`** (per `infra/README.md:122-126`): The `grep -rE ...` in the README returns zero matches — confirmed by inspection of every file. The org-wide hygiene rule holds.
- **Tagging convention** (`infra/envs/prod/providers.tf:13-22`): `Project`, `Environment`, `ManagedBy`, `Repo`, `Owner`, `CostCenter` + per-resource `Component` and `Name`. Resource Groups can navigate the tree.
- **`enable_key_rotation = true`** on both the project CMK (`infra/modules/kms/main.tf:12`) and the bootstrap CMK (`infra/bootstrap/main.tf:48`). Both rotate annually.
- **No grants auto-issued by KMS** — the key policy uses statements only; grants are issued by AWS services on demand (verified by absence of `aws_kms_grant` resources).
- **Bedrock policy `aws:RequestedRegion`** (`infra/policies/bedrock-invoke.json:18-30`): Pins invocation to the 7 EU regions of the cross-region inference profile. Even if instance credentials leak, Bedrock calls outside EU regions are blocked.
- **Symmetric (not asymmetric) KMS key** (`infra/modules/kms/main.tf:14-15`): `customer_master_key_spec = "SYMMETRIC_DEFAULT"`. Symmetric is correct for the use cases here (envelope encryption for EBS/SSM/S3/Backup). Asymmetric (for `kms:Sign` of JWTs) is a separate improvement vector and is the right path for the RS256 migration noted in `section_3_1_auth.md` C2 — but not a current-state gap.
- **VPC flow logs enabled with `traffic_type = "ALL"`** (`infra/modules/network/main.tf:473-484`): Captures both accepts and rejects.
- **Subnet is "public" but EC2 has no public IP except via EIP** (`infra/modules/compute/main.tf:83`, `associate_public_ip_address = false`): The EIP is the only public path. Auto-assign disabled.
- **CloudWatch log groups encrypted with project CMK** (`infra/modules/monitoring/main.tf:46`): All eight log groups + the VPC flow logs group.
- **`flowin-deploy` user is a system account with no shell other than for git access** (`infra/scripts/bootstrap-ec2.sh:770-775`): Limited blast radius from SSH compromise.

---

## File:line index (every finding)

| # | Severity | Title | Primary file:line |
|---|----------|-------|---|
| 1 | CRITICAL | SECRET_KEY in plaintext EnvironmentFile reachable via SSM | infra/scripts/bootstrap-ec2.sh:478-507, infra/modules/iam/main.tf:184-189 |
| 2 | CRITICAL | No Docker/IAM isolation around Node subprocess (RCE → host-takeover) | infra/modules/compute/main.tf:85-100 (IMDS), infra/policies/ssm-read.json + bedrock-invoke.json + kms-decrypt.json |
| 3 | CRITICAL | SECRET_KEY plaintext in Terraform state | infra/modules/secrets/main.tf:104-122, infra/envs/prod/backend.tf:12-20 |
| 4 | CRITICAL | KMS `AllowSns` grant lacks aws:SourceAccount | infra/modules/kms/main.tf:71-83 |
| 5 | HIGH | `kms-decrypt.json` SSM statement lacks kms:ViaService | infra/policies/kms-decrypt.json:4-14 |
| 6 | HIGH | `ecr:GetAuthorizationToken` granted Resource:* (AWS-required, but no VPC endpoint pin) | infra/policies/ecr-pull.json:5-14 |
| 7 | HIGH | ECR repo policy additive-only, no deny | infra/modules/ecr/main.tf:120-142 |
| 8 | HIGH | KMS `AllowCloudWatchLogs` matches `/flowin/*` not `/flowin/${env}/*` | infra/modules/kms/main.tf:49-69 |
| 9 | HIGH | No CloudTrail data-event alarm on SSM/KMS | infra/modules/monitoring/main.tf (whole), infra/modules/secrets/main.tf |
| 10 | HIGH | SECRET_KEY in `Standard` SSM tier (no parameter policies) | infra/modules/secrets/main.tf:104-122 |
| 11 | HIGH | random_password taint is a no-op due to ignore_changes | infra/modules/secrets/main.tf:18-22, 116-121 |
| 12 | HIGH | Bootstrap CMK key policy delegates to IAM (no explicit deny) | infra/bootstrap/main.tf:45-72 |
| 13 | HIGH | flowin-deploy sudoers regex accepts any image URI | infra/scripts/bootstrap-ec2.sh:777-799, 802-819 |
| 14 | HIGH | Docker daemon defaults — no inter-container firewall | infra/scripts/bootstrap-ec2.sh:316-329 |
| 15 | MEDIUM | KMS not multi_region (DR gap) | infra/modules/kms/main.tf:13-15 |
| 16 | MEDIUM | enable_key_rotation rotates DEK only, not SSM value | infra/modules/kms/main.tf:12 |
| 17 | MEDIUM | EBS snapshots share single CMK with source | infra/modules/compute/main.tf:50-68, infra/modules/backups/main.tf:222-234 |
| 18 | MEDIUM | bedrock-invoke.json inference-profile ARN region-pinned | infra/policies/bedrock-invoke.json:14-17 |
| 19 | MEDIUM | VPC flow log retention default 30d | infra/modules/network/main.tf:432-484, variables.tf:89-98 |
| 20 | MEDIUM | No CW alarms on security events (failed login, SSM session, KMS denies) | infra/modules/monitoring/main.tf (whole) |
| 21 | MEDIUM | us-east-1 billing topic uses alias/aws/sns | infra/modules/monitoring/main.tf:255-266 |
| 22 | MEDIUM (resolved) | SNS action format — PascalCase IS correct | infra/modules/monitoring/main.tf:113-145, 283-344 |
| 23 | MEDIUM | aws_iam_role_policies_exclusive brittle to additions | infra/modules/iam/main.tf:226-238 |
| 24 | MEDIUM | PG listen_addresses = '*' reliant on UFW | infra/scripts/bootstrap-ec2.sh:253-275 |
| 25 | MEDIUM | setfacl o::r on /var/lib/docker/containers | infra/scripts/bootstrap-ec2.sh:336-347, 710-712 |
| 26 | MEDIUM | KMS rotation doesn't re-encrypt EBS | infra/modules/compute/main.tf:50-68, 114-127 |
| 27 | MEDIUM | ssh_allowed_cidrs validation only rejects 0.0.0.0/0 | infra/modules/network/variables.tf:49-65 |
| 28 | MEDIUM | Docker socket protection relies on group membership discipline | infra/scripts/bootstrap-ec2.sh:316-329 |
| 29 | MEDIUM | ECR scan_on_push exists but doesn't gate deployment | infra/modules/ecr/main.tf:47-49 |
| 30 | MEDIUM | No EventBridge → SNS rule on ECR scan findings | infra/modules/monitoring/main.tf |
| 31 | MEDIUM | fail2ban / auditd installed but not configured | infra/scripts/bootstrap-ec2.sh:98-104 |
| 32 | MEDIUM | Bootstrap CMK lacks multi_region | infra/bootstrap/main.tf:45-72 |
| L-1 | LOW | Comment drift in iam/main.tf | infra/modules/iam/main.tf:50-55 |
| L-2 | LOW | aws_kms_alias lacks prevent_destroy | infra/modules/kms/main.tf:170-173 |
| L-3 | LOW | aws_kms_alias.bootstrap lacks prevent_destroy | infra/bootstrap/main.tf:70-73 |
| L-4 | LOW | Default tags disclose internal repo URL | infra/envs/prod/providers.tf:13-22 |
| L-5 | LOW | cors_origins String type — plaintext in state | infra/modules/secrets/main.tf:46-64 |
| L-6 | LOW | aws ssm get-parameter --output text discloses to argv | infra/scripts/bootstrap-ec2.sh:292-294 |
| L-7 | LOW | Unattended-upgrades auto-reboot at 04:00 UTC uncoordinated | infra/scripts/bootstrap-ec2.sh:163-169 |
| L-8 | LOW | apt-get install unpinned versions | infra/scripts/bootstrap-ec2.sh:98-104 |
| L-9 | LOW | Egress to 0.0.0.0/0 on 80/443/53 | infra/modules/network/main.tf:247-297 |
| L-10 | LOW | Backup=true tag-based selection broad | infra/modules/backups/main.tf:278-294, infra/modules/compute/main.tf:59-64 |
| L-11 | LOW | user_data extra_env heredoc not shell-escaped | infra/modules/compute/user_data.sh.tpl:60-62 |
| L-12 | LOW | _DEFAULT_SECRET_KEY placeholder passes length check (non-TF; flagged in §2) | env-templates/.env.development:28 |

---

## Cross-references to Phase B aggregate (Group 5 expansion)

The Phase B `docs/_audit/TRIAGE.md` Group 5 listed:
- IAM permission scope → covered by findings 1 (SECRET_KEY scope), 2 (RCE → IAM), 6 (ECR token), 13 (sudoers).
- SNS topic policy validation → resolved as MEDIUM #22 (PascalCase is correct).
- KMS multi-region / rotation → finding 15.
- CloudWatch alarm thresholds / coverage → MEDIUM #20.
- Disk usage observability (/tmp + EBS) → covered by Phase B `section_3_3_history.md` T1-T3, infrastructure-side fix is finding 14 (container isolation), with finding 20's missing /tmp metric.
- Container resource limits (cgroup CPU/memory caps) → CRITICAL #2.
- Backup vault / object lock → verified clean (opt-in default off is correct).
- DB connection pool tuning → out of scope (application).
- ECR image lifecycle (size growth) → MEDIUM #29 (scan gate) + #30 (alarm).
- `enable_object_lock` / `enable_vault_lock` defaults → verified clean.

The 8 remaining TF items in Group 5 are absorbed by the granular findings above.
