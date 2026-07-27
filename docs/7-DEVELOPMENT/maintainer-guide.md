# Maintainer Guide

This guide is for project maintainers to help manage contributions effectively while maintaining project quality and vision.

## Table of Contents

- [Issue Management](#issue-management)
- [Pull Request Review](#pull-request-review)
- [Common Scenarios](#common-scenarios)
- [Communication Templates](#communication-templates)

## Issue Management

### When a New Issue is Created

**1. Initial Triage** (within 24-48 hours)

- Add appropriate labels:
  - `bug`, `enhancement`, `documentation`, etc.
  - `good first issue` for beginner-friendly tasks
  - `needs-triage` until reviewed
  - `help wanted` if you'd welcome community contributions

- Quick assessment:
  - Is it clear and well-described?
  - Is it aligned with project vision? (See [design-principles.md](design-principles.md))
  - Does it duplicate an existing issue?

**2. Initial Response**

```markdown
Thanks for opening this issue! We'll review it and get back to you soon.

[If it's a bug] In the meantime, have you checked our troubleshooting guide?

[If it's a feature] You might find our [design principles](design-principles.md) helpful for understanding what we're building toward.
```

**3. Decision Making**

Ask yourself:
- Does this align with our [design principles](design-principles.md)?
- Is this something we want in the core project, or better as a plugin/extension?
- Do we have the capacity to support this feature long-term?
- Will this benefit most users, or just a specific use case?

**4. Issue Assignment**

If the contributor checked "I am a developer and would like to work on this":

**For Accepted Issues:**
```markdown
Great idea! This aligns well with our goals, particularly [specific design principle].

I see you'd like to work on this. Before you start:

1. Please share your proposed approach/solution
2. Review our [Contributing Guide](contributing.md) and [Design Principles](design-principles.md)
3. Once we agree on the approach, I'll assign this to you

Looking forward to your thoughts!
```

**For Issues Needing Clarification:**
```markdown
Thanks for offering to work on this! Before we proceed, we need to clarify a few things:

1. [Question 1]
2. [Question 2]

Once we have these details, we can discuss the best approach.
```

**For Issues Not Aligned with Vision:**
```markdown
Thank you for the suggestion and for offering to work on this!

After reviewing against our [design principles](design-principles.md), we've decided not to pursue this in the core project because [specific reason].

However, you might be able to achieve this through [alternative approach, if applicable].

We appreciate your interest in contributing! Feel free to check out our [open issues](link) for other ways to contribute.
```

### Labels to Use

**Priority:**
- `priority: critical` - Security issues, data loss bugs
- `priority: high` - Major functionality broken
- `priority: medium` - Annoying bugs, useful features
- `priority: low` - Nice to have, edge cases

**Status:**
- `needs-triage` - Not yet reviewed by maintainer
- `needs-info` - Waiting for more information from reporter
- `needs-discussion` - Requires community/team discussion
- `ready` - Approved and ready to be worked on
- `in-progress` - Someone is actively working on this
- `blocked` - Cannot proceed due to external dependency

**Type:**
- `bug` - Something is broken
- `enhancement` - New feature or improvement
- `documentation` - Documentation improvements
- `question` - General questions
- `refactor` - Code cleanup/restructuring

**Difficulty:**
- `good first issue` - Good for newcomers
- `help wanted` - Community contributions welcome
- `advanced` - Requires deep codebase knowledge

## Pull Request Review

### Initial PR Review Checklist

**Before diving into code:**

- [ ] Is there an associated approved issue?
- [ ] Does the PR reference the issue number?
- [ ] Is the PR description clear about what changed and why?
- [ ] Did the contributor check the relevant boxes in the PR template?
- [ ] Are there tests? Screenshots (for UI changes)?

**Red Flags** (may require closing PR):
- No associated issue
- Issue was not assigned to contributor
- PR tries to solve multiple unrelated problems
- Breaking changes without discussion
- Conflicts with project vision

### Code Review Process

**1. High-Level Review**

- Does the approach align with our architecture?
- Is the solution appropriately scoped?
- Are there simpler alternatives?
- Does it follow our design principles?

**2. Code Quality Review**

Python:
- [ ] Follows PEP 8
- [ ] Has type hints
- [ ] Has docstrings
- [ ] Proper error handling
- [ ] No security vulnerabilities

TypeScript/Frontend:
- [ ] Follows TypeScript best practices
- [ ] Proper component structure
- [ ] No console.logs left in production code
- [ ] Accessible UI components

**3. Testing Review**

- [ ] Has appropriate test coverage
- [ ] Tests are meaningful (not just for coverage percentage)
- [ ] Tests pass locally and in CI
- [ ] Edge cases are tested

**4. Documentation Review**

- [ ] Code is well-commented
- [ ] Complex logic is explained
- [ ] User-facing documentation updated (if applicable)
- [ ] API documentation updated (if API changed)
- [ ] Migration guide provided (if breaking change)

### Providing Feedback

**Positive Feedback** (important!):
```markdown
Thanks for this PR! I really like [specific thing they did well].

[Feedback on what needs to change]
```

**Requesting Changes:**
```markdown
This is a great start! A few things to address:

1. **[High-level concern]**: [Explanation and suggested approach]
2. **[Code quality issue]**: [Specific example and fix]
3. **[Testing gap]**: [What scenarios need coverage]

Let me know if you have questions about any of this!
```

**Suggesting Alternative Approach:**
```markdown
I appreciate the effort you put into this! However, I'm concerned about [specific issue].

Have you considered [alternative approach]? It might be better because [reasons].

What do you think?
```

## Common Scenarios

### Scenario 1: Good Code, Wrong Approach

**Situation**: Contributor wrote quality code, but solved the problem in a way that doesn't fit our architecture.

**Response:**
```markdown
Thank you for this PR! The code quality is great, and I can see you put thought into this.

However, I'm concerned that this approach [specific architectural concern]. In our architecture, we [explain the pattern we follow].

Would you be open to refactoring this to [suggested approach]? I'm happy to provide guidance on the specifics.

Alternatively, if you don't have time for a refactor, I can take over and finish this up (with credit to you, of course).

Let me know what you prefer!
```

### Scenario 2: PR Without Assigned Issue

**Situation**: Contributor submitted PR without going through issue approval process.

**Response:**
```markdown
Thanks for the PR! I appreciate you taking the time to contribute.

However, to maintain project coherence, we require all PRs to be linked to an approved issue that was assigned to the contributor. This is explained in our [Contributing Guide](contributing.md).

This helps us:
- Ensure work aligns with project vision
- Prevent duplicate efforts
- Discuss approach before implementation

Could you please:
1. Create an issue describing this change
2. Wait for it to be reviewed and assigned to you
3. We can then reopen this PR or you can create a new one

Sorry for the inconvenience - this process helps us manage the project effectively.
```

### Scenario 3: Feature Request Not Aligned with Vision

**Situation**: Well-intentioned feature that doesn't fit project goals.

**Response:**
```markdown
Thank you for this suggestion! I can see how this would be useful for [specific use case].

After reviewing against our [design principles](design-principles.md), we've decided not to include this in the core project because [specific reason - e.g., "it conflicts with our 'Simplicity Over Features' principle" or "it would require dependencies that conflict with our privacy-first approach"].

Some alternatives:
- [If applicable] This could be built as a plugin/extension
- [If applicable] This functionality might be achievable through [existing feature]
- [If applicable] You might be interested in [other tool] which is designed for this use case

We appreciate your contribution and hope you understand. Feel free to check our roadmap or open issues for other ways to contribute!
```

### Scenario 4: Contributor Ghosts After Feedback

**Situation**: You requested changes, but contributor hasn't responded in 2+ weeks.

**After 2 weeks:**
```markdown
Hey there! Just checking in on this PR. Do you have time to address the feedback, or would you like someone else to take over?

No pressure either way - just want to make sure this doesn't fall through the cracks.
```

**After 1 month with no response:**
```markdown
Thanks again for starting this work! Since we haven't heard back, I'm going to close this PR for now.

If you want to pick this up again in the future, feel free to reopen it or create a new PR. Alternatively, I'll mark the issue as available for someone else to work on.

We appreciate your contribution!
```

Then:
- Close the PR
- Unassign the issue
- Add `help wanted` label to the issue

### Scenario 5: Breaking Changes Without Discussion

**Situation**: PR introduces breaking changes that weren't discussed.

**Response:**
```markdown
Thanks for this PR! However, I notice this introduces breaking changes that weren't discussed in the original issue.

Breaking changes require:
1. Prior discussion and approval
2. Migration guide for users
3. Deprecation period (when possible)
4. Clear documentation of the change

Could we discuss the breaking changes first? Specifically:
- [What breaks and why]
- [Who will be affected]
- [Migration path]

We may need to adjust the approach to minimize impact on existing users.
```

## Communication Templates

### Closing a PR (Misaligned with Vision)

```markdown
Thank you for taking the time to contribute! We really appreciate it.

After careful review, we've decided not to merge this PR because [specific reason related to design principles].

This isn't a reflection on your code quality - it's about maintaining focus on our core goals as outlined in [design-principles.md](design-principles.md).

We'd love to have you contribute in other ways! Check out:
- Good first issues
- Help wanted issues
- Our roadmap

Thanks again for your interest in Deeper Notebook!
```

### Closing a Stale Issue

```markdown
We're closing this issue due to inactivity. If this is still relevant, feel free to reopen it with updated information.

Thanks!
```

### Asking for More Information

```markdown
Thanks for reporting this! To help us investigate, could you provide:

1. [Specific information needed]
2. [Logs, screenshots, etc.]
3. [Steps to reproduce]

This will help us understand the issue better and find a solution.
```

### Thanking a Contributor

```markdown
Merged!

Thank you so much for this contribution, @username! [Specific thing they did well].

This will be included in the next release.
```

## Best Practices

### Be Kind and Respectful

- Thank contributors for their time and effort
- Assume good intentions
- Be patient with newcomers
- Explain *why*, not just *what*

### Be Clear and Direct

- Don't leave ambiguity about next steps
- Be specific about what needs to change
- Explain architectural decisions
- Set clear expectations

### Be Consistent

- Apply the same standards to all contributors
- Follow the process you've defined
- Document decisions for future reference

### Be Protective of Project Vision

- It's okay to say "no"
- Prioritize long-term maintainability
- Don't accept features you can't support
- Keep the project focused

### Be Responsive

- Respond to issues within 48 hours (even just to acknowledge)
- Review PRs within a week when possible
- Keep contributors updated on status
- Close stale issues/PRs to keep things tidy

## When in Doubt

Ask yourself:
1. Does this align with our [design principles](design-principles.md)?
2. Will we be able to maintain this feature long-term?
3. Does this benefit most users, or just an edge case?
4. Is there a simpler alternative?
5. Would I want to support this in 2 years?

If you're unsure, it's perfectly fine to:
- Ask for input from other maintainers
- Start a discussion issue
- Sleep on it before making a decision

---

**Remember**: Good maintainership is about balancing openness to contributions with protection of project vision. You're not being mean by saying "no" to things that don't fit - you're being a responsible steward of the project.

---

## Plus-Specific Hardening Reference (v0.7.88 → v0.7.118)

This section is specific to the **open-notebook-Plus** desktop fork
(not upstream). It surfaces the surface area added by the v0.7.88+
hardening run so a new maintainer can answer "what knobs do I have
when something breaks in prod?" without grepping the CHANGELOG.

### Operational quick-reference

| Symptom | Likely cause | Knob / fix |
|---|---|---|
| Studio request hangs forever | Local LLM stuck mid-eval | `ONP_STUDIO_PAGE_TIMEOUT_SEC` (default 180) |
| Studio "outline" pass times out | Outline JSON model slow | `ONP_STUDIO_OUTLINE_TIMEOUT_SEC` (default 90) |
| File-upload parse hangs | Pathological PDF / encrypted file | `ONP_STUDIO_EXTRACT_TIMEOUT_SEC` (default 60) |
| Non-streaming `/chat/execute` times out | Local chat model slow | `ONP_CHAT_TIMEOUT_SEC` (default 300) |
| Memory recall slowing chat | Stuck embedder or DB pool | `ONP_MEMORY_RECALL_EMBED_TIMEOUT_SEC`, `_QUERY_TIMEOUT_SEC` (5s each) |
| `POST /notes` hangs on auto-title | Stuck title model | `ONP_NOTE_TITLE_TIMEOUT_SEC` (default 60) — falls back to first line |
| `POST /transformations/execute` hangs | Stuck transformation graph | `ONP_TRANSFORMATION_TIMEOUT_SEC` (default 180) |
| Settings UI "Test connection" hangs | Provider-specific slowness | `ONP_CONNECTION_TEST_TIMEOUT_SEC_<UPPER>` (per-provider) |
| `POST /credentials/{id}/discover` hangs | Provider list-models slow | `ONP_DISCOVER_MODELS_TIMEOUT_SEC` (default 30) |
| `/search` hangs | DB pool saturated | `ONP_SEARCH_TIMEOUT_SEC` (default 60) |
| Bulk vectorize floods worker | Notebook with too many sources | `ONP_BULK_VECTORIZE_MAX_SOURCES` (default 500) |
| Async command submission hangs | Stuck SurrealDB pool | `ONP_SUBMIT_COMMAND_TIMEOUT_SEC` (default 10) |

Full env-knob reference + per-provider connection-test defaults:
[`docs/5-CONFIGURATION/onp-env-reference.md`](../5-CONFIGURATION/onp-env-reference.md).

### Health-check endpoints

| Endpoint | Auth | Use case |
|---|---|---|
| `GET /health` | exempt | Liveness (back-compat) |
| `GET /livez` | exempt | Liveness — process is serving |
| `GET /readyz` | exempt | Readiness — DB + migrations OK |
| `GET /healthz/deep` | exempt | Per-subsystem probe (DB, migrations, embedding-model, chat-model, command-registry) — auto-consumed by the frontend Setup Wizard |

`/healthz/deep` returns `healthy` / `degraded` / `not_ready`. Use it
in monitoring dashboards: `degraded` is 200 (optional subsystems
missing), `not_ready` is 503 (must-have subsystems failed).

### Export / import endpoints (v0.7.90 → v0.7.111)

Notebook export supports six formats and three layouts:
- `folder` / `zip` — markdown
- `html_folder` / `html_zip` — markdown rendered to HTML (XSS-hardened
  per v0.7.117 + v0.7.118 — raw HTML escaped, external links carry
  `rel="noopener noreferrer"`)
- `combined_md` / `combined_html` — single file with all pages
  concatenated (HTML variant has print CSS for browser-PDF export)

Import accepts folder / `.zip` / single `.md` and is bounded by
`_MAX_IMPORT_BYTES` (50 MB) / `_MAX_IMPORT_FILE_BYTES` (5 MB) /
`_MAX_IMPORT_ENTRIES` (500). Zip entries are validated against
path-traversal AND symlink/FIFO/device modes (v0.7.117).

### `except HTTPException: raise` invariant (v0.7.109)

Every router handler must re-raise `HTTPException` before its
generic `except Exception` block. Without this, typed status codes
(404, 400, 504, etc.) get silently rewrapped as 500. 89 guards were
added in v0.7.109; check `api/routers/<router>.py` for the pattern
when adding new handlers:

```python
try:
    ...
    raise HTTPException(404, "...")
except HTTPException:
    raise
except Exception as e:
    raise HTTPException(500, f"Internal error: {e}")
```

### Test suites

| Suite | File pattern | Count | Runtime |
|---|---|---:|---:|
| Backend (pytest) | `tests/test_*.py` | **530+** | ~25 s |
| Frontend (vitest) | `frontend/src/**/*.test.{ts,tsx}` | **58+** | ~30 s |
| Desktop launcher | `desktop/tests/test_*.py` | **14** | ~7 s |

Backend tests deliberately mock at the chain / domain boundary so
no real SurrealDB or LLM is needed. Real-DB integration tests are
intentionally deferred — they'd need a test-infra setup that's its
own project.

### Release checklist (Plus-specific)

Before tagging a `v0.7.NN` release:

1. `uv run pytest tests/ -q` — must pass
2. `uv run ruff check api/ open_notebook/ commands/ desktop/ tests/` — clean
3. `cd frontend && npx vitest run` — must pass (locale parity gate
   in `src/lib/locales/index.test.ts` enforces 10-locale parity)
4. `cd frontend && npx tsc --noEmit` — clean
5. Update `desktop/CHANGELOG.md` "Unreleased" section
6. `make build-mac-pyinstaller && make build-mac-dmg` — produces
   `dist/Deeper Notebook.dmg`
7. Smoke-test: launch the .dmg, hit `http://localhost:5055/healthz/deep`,
   verify `status: healthy` (or `degraded` with diagnostics)
