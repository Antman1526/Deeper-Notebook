"""v0.8.68 — SkillOpt prompt-optimizer integration (microsoft/SkillOpt, MIT).

Treats a Transformation's prompt as SkillOpt's trainable "skill document":
rollouts run the prompt over example sources with the TARGET model, an
LLM judge scores outputs against the user's criteria, the OPTIMIZER model
proposes bounded add/delete/replace edits, and a validation gate accepts
only edits that improve the held-out score. Output: an optimized prompt
the user reviews and applies.

skillopt is an OPTIONAL dependency (same policy as crawl4ai): the feature
detects availability and the API returns an actionable error when the
package isn't installed.
"""

from __future__ import annotations


def skillopt_available() -> bool:
    try:
        import skillopt  # noqa: F401

        return True
    except ImportError:
        return False
