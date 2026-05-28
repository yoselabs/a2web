package a2kit

# REGO-PYPROJECT-UPPER-BOUND — every runtime dependency must declare an
# upper bound. Catches sloppy specifiers (`httpx`, `pydantic>=2`) before
# they break on a major-version bump in CI or for downstream consumers.
#
# Scope: `[project.dependencies]` only. `[project.optional-dependencies]`
# (test/otel/code-mode/examples-mcp-google-auth groups) and
# `[build-system].requires` are NOT gated — optional groups are opt-in
# by the consumer and build deps don't ship to runtime.
#
# Suppress with: policies/data.json a2kit.allowlist.pyproject_upper_bound
# entries `{name: "<dep>", reason: "<why>"}`.

deny contains msg if {
	some i
	dep := input.pyproject.dependencies[i]
	not dep.has_upper_bound
	not _pyproject_upper_bound_allowlisted(dep.name)
	msg := {
		"rule": "REGO-PYPROJECT-UPPER-BOUND",
		"file": "pyproject.toml",
		"line": 0,
		"col": 0,
		"message": sprintf(
			"runtime dep '%s' has no upper bound (spec: '%s'); add `<X.Y` or `~=X.Y` or allowlist in policies/data.json",
			[dep.name, dep.spec],
		),
	}
}

_pyproject_upper_bound_allowlisted(name) if {
	some entry in policy_allowlist("pyproject_upper_bound")
	entry.name == name
}

# ---- Allowlist hygiene ----------------------------------------------------

deny contains msg if {
	some entry in policy_allowlist("pyproject_upper_bound")
	not entry.reason
	msg := {
		"rule": "REGO-ALLOWLIST",
		"file": "policies/data.json",
		"line": 0,
		"col": 0,
		"message": sprintf("pyproject_upper_bound allowlist entry missing required 'reason': %v", [entry]),
	}
}

deny contains msg if {
	some entry in policy_allowlist("pyproject_upper_bound")
	entry.reason == ""
	msg := {
		"rule": "REGO-ALLOWLIST",
		"file": "policies/data.json",
		"line": 0,
		"col": 0,
		"message": sprintf("pyproject_upper_bound allowlist entry has empty 'reason': %v", [entry]),
	}
}
