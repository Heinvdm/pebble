from typing import Any

from ..laws import LAWS, PAST_LAWS

GOAL_LIMIT_RULE = "At most 3 goals and 5 tasks at once. Finish or drop one before adding more."


def without_goal_limit(core: Any) -> dict | None:
    rules = core.get("tool_rules") if isinstance(core, dict) else None
    if not isinstance(rules, list) or GOAL_LIMIT_RULE not in rules:
        return None
    return {**core, "tool_rules": [rule for rule in rules if rule != GOAL_LIMIT_RULE]}


def _older_laws(core: dict) -> list[dict]:
    if list(core.get("laws") or []) != list(LAWS):
        return []
    return [{**core, "laws": list(past)} for past in PAST_LAWS]


def _older_rules(core: dict) -> list[dict]:
    rules = core.get("tool_rules")
    if not isinstance(rules, list) or GOAL_LIMIT_RULE in rules:
        return []
    return [{**core, "tool_rules": rules[:at] + [GOAL_LIMIT_RULE] + rules[at:]} for at in range(len(rules) + 1)]


STEPS = (_older_laws, _older_rules)


def older_forms(core: Any) -> list[dict]:
    if not isinstance(core, dict):
        return []
    forms = [core]
    for step in STEPS:
        forms = forms + [older for form in forms for older in step(form)]
    return forms[1:]
