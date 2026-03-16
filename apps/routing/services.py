"""Routing service — evaluates routing rules to determine target queue."""

import logging
import operator

from apps.queues.models import Queue

from .models import RoutingRule

logger = logging.getLogger(__name__)

# Supported operators for match_json evaluation
OPERATORS = {
    "eq": operator.eq,
    "ne": operator.ne,
    "in": lambda val, choices: val in choices,
    "contains": lambda val, substr: substr in val,
}


class RoutingService:
    """Evaluates routing rules against conversation attributes to select a queue."""

    def evaluate(self, *, org_id: str, tier: str, issue_category: str, severity: str) -> Queue:
        """Evaluate active routing rules in priority order.

        Returns the target queue of the first matching rule, or the default
        soc-triage queue if no rules match.

        match_json format: {"field": "severity", "operator": "eq", "value": "critical"}
        """
        input_fields = {
            "org_id": org_id,
            "tier": tier,
            "issue_category": issue_category,
            "severity": severity,
        }

        rules = RoutingRule.objects.filter(active=True).select_related("target_queue").order_by("priority")

        for rule in rules:
            if self._matches(rule.match_json, input_fields):
                logger.info(
                    "Routing rule '%s' matched (priority %d) → queue '%s'",
                    rule.name, rule.priority, rule.target_queue.key,
                )
                return rule.target_queue

        # Default fallback
        default_queue = Queue.objects.get(key="soc-triage")
        logger.info("No routing rules matched, using default queue 'soc-triage'")
        return default_queue

    def _matches(self, match_json: dict, input_fields: dict) -> bool:
        """Check if a single match_json condition matches the input fields."""
        field_name = match_json.get("field", "")
        op_name = match_json.get("operator", "eq")
        expected_value = match_json.get("value", "")

        actual_value = input_fields.get(field_name, "")
        op_func = OPERATORS.get(op_name)

        if op_func is None:
            logger.warning("Unknown operator '%s' in routing rule", op_name)
            return False

        try:
            return op_func(actual_value, expected_value)
        except Exception:
            logger.warning("Error evaluating routing rule: field=%s, op=%s", field_name, op_name, exc_info=True)
            return False
