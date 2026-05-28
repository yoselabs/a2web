package a2kit

# REGO-BODY-DUP — cross-file function body duplication.
#
# Fires when two functions in different files share the same
# `ast_hash_normalized` (identifier + literal names normalized; see
# scripts/extract_facts.py docstring for the strategy). Catches
# duplications that name-based detection misses (R1: `_call`/`_call`
# identical body) AND name-divergent duplications that token-based
# clone detectors miss (R6: `_format_ldd_line`/`format_ldd_line`,
# same body shape, different names).
#
# Filter: body_stmt_count >= 3 (recursive count, includes nested
# statements inside try/with/if blocks). Trivial 1-2 statement
# collisions (`return x`, `raise X`) are out of scope.
#
# Suppress with: `# noqa: REGO-BODY-DUP -- <why>` on the function def
# line, or add the name(s) to policies/data.json under
# body_dup with a `reason`.

deny contains msg if {
	some i, j
	i < j
	fn_i := input.functions[i]
	fn_j := input.functions[j]
	fn_i.ast_hash_normalized == fn_j.ast_hash_normalized
	fn_i.file != fn_j.file
	fn_i.body_stmt_count >= 3
	not fn_i.is_dunder
	not fn_j.is_dunder
	not _body_dup_allowlisted(fn_i.name, fn_j.name)
	not suppressed(fn_i, "REGO-BODY-DUP")
	not suppressed(fn_j, "REGO-BODY-DUP")
	msg := {
		"rule": "REGO-BODY-DUP",
		"file": fn_i.file,
		"line": fn_i.line,
		"col": 0,
		"message": sprintf(
			"body matches %s:%d (%s) — extract canonical impl or suppress with `# noqa: REGO-BODY-DUP -- <why>`",
			[fn_j.file, fn_j.line, fn_j.name],
		),
	}
}

_body_dup_allowlisted(name_a, name_b) if {
	some entry in policy_allowlist("body_dup")
	name_a in entry.names
	name_b in entry.names
}

# Allowlist hygiene: every entry must carry a non-empty reason.
deny contains msg if {
	some entry in policy_allowlist("body_dup")
	not entry.reason
	msg := {
		"rule": "REGO-ALLOWLIST",
		"file": "policies/data.json",
		"line": 0,
		"col": 0,
		"message": sprintf("body_dup allowlist entry missing required 'reason' field: %v", [entry.names]),
	}
}

deny contains msg if {
	some entry in policy_allowlist("body_dup")
	entry.reason == ""
	msg := {
		"rule": "REGO-ALLOWLIST",
		"file": "policies/data.json",
		"line": 0,
		"col": 0,
		"message": sprintf("body_dup allowlist entry has empty 'reason': %v", [entry.names]),
	}
}
