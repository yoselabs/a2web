package a2kit

# REGO-GHA-* — GitHub Actions supply-chain hygiene.
#
# Three rules over `input.workflows`:
#
#   REGO-GHA-PIN-SHA       Third-party `uses:` must be pinned to a 40-char SHA.
#                          Allowlist (per-vendor "unpinned OK" carve-out):
#                          policies/data.json
#                          a2kit.allowlist.github_actions_vendor_unpinned
#
#   REGO-GHA-PERMISSIONS   Every workflow must declare a top-level
#                          `permissions:` block. Defence in depth — per-job
#                          permissions alone do not satisfy this.
#
#   REGO-GHA-VENDOR-ALLOW  Every `uses:` vendor must be on the allowlist
#                          policies/data.json
#                          a2kit.allowlist.github_actions_vendor
#
# Rule reference: woodruffw/zizmor audit catalog. We author bespoke Rego
# rather than wrap zizmor to keep the substrate (OPA) singular.

# ---- REGO-GHA-PIN-SHA -----------------------------------------------------

deny contains msg if {
	some wi, ji, si
	wf := input.workflows[wi]
	job := wf.jobs[ji]
	step := job.steps[si]
	step.uses != null
	not step.has_pinned_sha
	not _gha_vendor_unpinned_allowed(step.vendor)
	msg := {
		"rule": "REGO-GHA-PIN-SHA",
		"file": wf.file,
		"line": 0,
		"col": 0,
		"message": sprintf(
			"workflow step uses '%s' is not pinned to a 40-char SHA (job '%s'); pin to immutable SHA or allowlist vendor in policies/data.json",
			[step.uses, job.name],
		),
	}
}

_gha_vendor_unpinned_allowed(vendor) if {
	some entry in policy_allowlist("github_actions_vendor_unpinned")
	entry.vendor == vendor
}

# ---- REGO-GHA-PERMISSIONS -------------------------------------------------

deny contains msg if {
	some wi
	wf := input.workflows[wi]
	wf.permissions == null
	msg := {
		"rule": "REGO-GHA-PERMISSIONS",
		"file": wf.file,
		"line": 0,
		"col": 0,
		"message": sprintf(
			"workflow '%s' has no top-level `permissions:` block — declare one (e.g. `permissions: {contents: read}`) for defence in depth",
			[wf.file],
		),
	}
}

# ---- REGO-GHA-VENDOR-ALLOW ------------------------------------------------

deny contains msg if {
	some wi, ji, si
	wf := input.workflows[wi]
	job := wf.jobs[ji]
	step := job.steps[si]
	step.uses != null
	not _gha_vendor_allowlisted(step.vendor)
	msg := {
		"rule": "REGO-GHA-VENDOR-ALLOW",
		"file": wf.file,
		"line": 0,
		"col": 0,
		"message": sprintf(
			"workflow step uses unknown vendor '%s' (job '%s', step uses '%s'); add to policies/data.json a2kit.allowlist.github_actions_vendor with documented reason",
			[step.vendor, job.name, step.uses],
		),
	}
}

_gha_vendor_allowlisted(vendor) if {
	some entry in policy_allowlist("github_actions_vendor")
	entry.vendor == vendor
}

# ---- Allowlist hygiene (every entry must carry a non-empty reason) --------

deny contains msg if {
	some entry in policy_allowlist("github_actions_vendor")
	not entry.reason
	msg := {
		"rule": "REGO-ALLOWLIST",
		"file": "policies/data.json",
		"line": 0,
		"col": 0,
		"message": sprintf("github_actions_vendor allowlist entry missing required 'reason' field: %v", [entry]),
	}
}

deny contains msg if {
	some entry in policy_allowlist("github_actions_vendor")
	entry.reason == ""
	msg := {
		"rule": "REGO-ALLOWLIST",
		"file": "policies/data.json",
		"line": 0,
		"col": 0,
		"message": sprintf("github_actions_vendor allowlist entry has empty 'reason': %v", [entry]),
	}
}

deny contains msg if {
	some entry in policy_allowlist("github_actions_vendor_unpinned")
	not entry.reason
	msg := {
		"rule": "REGO-ALLOWLIST",
		"file": "policies/data.json",
		"line": 0,
		"col": 0,
		"message": sprintf("github_actions_vendor_unpinned allowlist entry missing required 'reason': %v", [entry]),
	}
}

deny contains msg if {
	some entry in policy_allowlist("github_actions_vendor_unpinned")
	entry.reason == ""
	msg := {
		"rule": "REGO-ALLOWLIST",
		"file": "policies/data.json",
		"line": 0,
		"col": 0,
		"message": sprintf("github_actions_vendor_unpinned allowlist entry has empty 'reason': %v", [entry]),
	}
}
