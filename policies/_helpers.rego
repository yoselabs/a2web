package a2kit

# Shared helpers for a2kit Rego policies.
#
# Consumed by:
#   - body_dup.rego        (REGO-BODY-DUP)
#   - name_collision.rego  (REGO-NAME-COLLISION)
#
# All policies live in package a2kit and aggregate findings into
# data.a2kit.deny — a single set the wrapper queries to render
# LintMessage-shaped findings.

# A function is suppressed for a rule when a noqa directive on the
# function's def line names that rule. Grammar enforced in
# scripts/extract_facts.py: REGO-* rules require ` -- <reason>`.
suppressed(fn, rule) if {
	some sup in input.suppressions
	sup.file == fn.file
	sup.rule_id == rule
	sup.line == fn.line
}

# Allowlist entries for a policy. Each entry is {names: [...], reason: "..."}.
# Allowlist with missing/empty reason raises REGO-ALLOWLIST (see policy files).
policy_allowlist(policy_name) := entries if {
	entries := data.a2kit.allowlist[policy_name]
}
