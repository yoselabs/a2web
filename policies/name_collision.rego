package a2kit

# REGO-NAME-COLLISION — cross-file private-helper name reuse.
#
# Fires when a `_`-prefixed (non-dunder) function name appears in
# 2+ distinct files outside the allowlist. The audit's "someone
# re-implemented because they didn't know the helper existed" payload:
# R1, R3, R4, R5, R7 (`_is_basemodel` × 3), R8 (`_validate_key`),
# R9 (`_is_a2kit_verb_decorator`).
#
# Dunder names (`__init__`, `__getattr__`) are exempt by rule — they
# are legitimate per-class / per-module conventions.
#
# Closure-style helper names (`_wrapped`, `_decorator`, `_wrap`,
# `_factory`) are common patterns inside decorator-returning
# functions; these belong in the allowlist with a one-line reason
# rather than as `# noqa`, because the convergence is by design.
#
# Suppress an individual occurrence with: `# noqa: REGO-NAME-COLLISION
# -- <why>` on the def line, or add the name to
# policies/data.json under name_collision with a `reason`.

deny contains msg if {
	some fn1 in input.functions
	some fn2 in input.functions
	fn1.name == fn2.name
	fn1.file < fn2.file # de-dupe symmetric pair
	fn1.is_private
	fn2.is_private
	not fn1.is_dunder
	not fn2.is_dunder
	not _name_allowlisted(fn1.name)
	not suppressed(fn1, "REGO-NAME-COLLISION")
	not suppressed(fn2, "REGO-NAME-COLLISION")
	msg := {
		"rule": "REGO-NAME-COLLISION",
		"file": fn1.file,
		"line": fn1.line,
		"col": 0,
		"message": sprintf(
			"private name %q reused in %s:%d — lift to a shared module, or add to policies/data.json name_collision with a `reason`",
			[fn1.name, fn2.file, fn2.line],
		),
	}
}

_name_allowlisted(name) if {
	some entry in policy_allowlist("name_collision")
	name in entry.names
}

# Allowlist hygiene: every entry must carry a non-empty reason.
deny contains msg if {
	some entry in policy_allowlist("name_collision")
	not entry.reason
	msg := {
		"rule": "REGO-ALLOWLIST",
		"file": "policies/data.json",
		"line": 0,
		"col": 0,
		"message": sprintf("name_collision allowlist entry missing required 'reason' field: %v", [entry.names]),
	}
}

deny contains msg if {
	some entry in policy_allowlist("name_collision")
	entry.reason == ""
	msg := {
		"rule": "REGO-ALLOWLIST",
		"file": "policies/data.json",
		"line": 0,
		"col": 0,
		"message": sprintf("name_collision allowlist entry has empty 'reason': %v", [entry.names]),
	}
}
