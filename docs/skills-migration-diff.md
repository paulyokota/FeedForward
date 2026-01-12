# Skills Migration Diff (v1 → v2)

> **For repos that already adopted the agent-based process docs**
>
> This document summarizes what changed with the skills-with-identity architecture.
> Read this if you have an existing `.claude/agents/` setup and want to upgrade.

---

## TL;DR

| v1 (Agents)             | v2 (Skills)                                                      |
| ----------------------- | ---------------------------------------------------------------- |
| `.claude/agents/kai.md` | `.claude/skills/kai-prompt-engineering/SKILL.md` + `IDENTITY.md` |
| Single file per agent   | Folder per skill with split concerns                             |
| `.claude/memory/kai/`   | `.claude/skills/kai-prompt-engineering/memories/`                |
| Implicit deployment     | Explicit `triggers:` in YAML frontmatter                         |
| Manual context loading  | `context/keywords.yaml` declarative loading                      |

**What stayed the same:** Learning Loop, 5-Personality Review, Kenji Gate, Priya-First, Session Touch Log, Functional Testing.

---

## Part 1: Structural Changes

### 1.1 Directory Structure

**Before (v1):**

```
.claude/
├── agents/
│   ├── kai.md
│   ├── marcus.md
│   └── reginald.md
├── memory/
│   ├── kai/
│   │   └── 2026-01-02-lesson.md
│   └── claude/
└── docs/
    ├── learning-loop.md
    └── review-protocol.md
```

**After (v2):**

```
.claude/
├── skills/
│   ├── kai-prompt-engineering/
│   │   ├── SKILL.md          # Procedures
│   │   ├── IDENTITY.md       # Personality
│   │   ├── memories/         # Collocated
│   │   └── context/
│   │       └── keywords.yaml # Declarative loading
│   ├── learning-loop/
│   │   └── SKILL.md          # Pure procedural (no identity)
│   └── review-5personality/
│       ├── SKILL.md
│       └── personalities/
│           ├── reginald.md
│           └── ...
├── agents/                   # DEPRECATED (kept as readonly archive)
└── docs/                     # Still exists for reference docs
```

### 1.2 File Split: SKILL.md + IDENTITY.md

**Before:** Single agent file mixed procedures with personality.

```markdown
# Kai - AI/Prompt Engineering Specialist

## Role

You are Kai, the prompt engineering specialist...

## Procedures

1. Research best practices
2. Make targeted changes
3. Run functional test

## Lessons Learned

- 2026-01-02: Never tune prompts without functional test
```

**After:** Separate concerns into two files.

**SKILL.md** (procedures only):

```yaml
---
name: prompt-engineering
identity: ./IDENTITY.md
triggers:
  keywords: [prompt, evaluator, agent]
  file_patterns: [src/lib/agents/*.ts]
dependencies:
  skills: [learning-loop, functional-testing]
---
# Prompt Engineering

## Workflow
1. Research best practices
2. Make targeted changes
3. Run functional test (MANDATORY)
```

**IDENTITY.md** (personality only):

```yaml
---
name: kai
pronouns: they/them
domain: AI/Prompt Engineering
ownership:
  - src/lib/agents/*.ts
---

# Kai - AI/Prompt Engineering Specialist

## Philosophy
[Core beliefs]

## Lessons Learned
- 2026-01-02: Never tune prompts without functional test
```

### 1.3 Skill Types

| Type                    | Has Identity? | Has Memories? | Example                |
| ----------------------- | ------------- | ------------- | ---------------------- |
| **Skill with Identity** | Yes           | Yes           | kai-prompt-engineering |
| **Pure Procedural**     | No            | No            | learning-loop          |
| **Multi-Identity**      | Multiple      | Shared        | review-5personality    |

**Rule:** Pure procedural skills cannot be learning loop targets (no identity to route to).

---

## Part 2: New Concepts

### 2.1 Triggers

Skills now declare when they should activate:

```yaml
triggers:
  keywords:
    - prompt
    - evaluator
    - model
  file_patterns:
    - src/lib/agents/**/*.ts
    - src/lib/keywords/**
```

**Priority when multiple skills match:**

1. Most specific file pattern match
2. Highest keyword count
3. Tech Lead choice

### 2.2 Dependencies (Must Be Acyclic)

Skills can depend on other skills:

```yaml
dependencies:
  skills:
    - learning-loop # Process dependency
    - functional-testing # Must run functional tests
  tools:
    - WebSearch # MCP tool
  runtime:
    - npm run test # Must pass before completion
```

**CONSTRAINT:** No cycles allowed. If A → B, then B cannot → A.

### 2.3 Declarative Context Loading

**Before:** Manual `retrieve.sh` calls in deployment prompt.

**After:** `context/keywords.yaml` auto-loads based on task keywords.

```yaml
# .claude/skills/kai-prompt-engineering/context/keywords.yaml

load_always:
  - .claude/docs/gold-standard-alignment.md
  - .claude/docs/functional-testing.md

load_for_keywords:
  evaluator|evaluation:
    - memories/*gold-standard*.md
  quote|citation:
    - memories/*quote*.md
```

### 2.4 Progressive Disclosure (Optional Optimization)

**Tier 1 (~100 tokens):** Skill name + triggers only
**Tier 2 (~300 tokens):** + Workflow summary
**Tier 3 (~1500+ tokens):** Full SKILL.md + IDENTITY.md + memories

Start at Tier 3, optimize later if needed.

---

## Part 3: What Stayed the Same

These processes are **unchanged** - just keyed by skill identity instead of agent name:

### 3.1 Learning Loop

- Still routes fixes to original developer
- Session Touch Log now tracks skill identity, not agent name
- `learning-loop` is now a pure procedural skill

### 3.2 5-Personality Review

- Still 5 separate Task calls (not 1 agent playing 5 roles)
- Still 2+ rounds to convergence
- Personalities now live in `review-5personality/personalities/`

### 3.3 Kenji Gate

- Tests still required before review
- `kenji-testing` is now a skill-with-identity

### 3.4 Priya-First

- Still deploy Priya for 2+ skills
- `priya-architecture` is now a skill-with-identity

### 3.5 Functional Testing

- Still required for prompt/pipeline changes
- `functional-testing` is now a pure procedural skill

---

## Part 4: Migration Checklist

### Phase 1: Create Infrastructure (Low Risk)

- [ ] Create `.claude/skills/` directory
- [ ] Create first pure procedural skill (e.g., `learning-loop`)
- [ ] Update `retrieve.sh` to v3 (backwards compatible)

### Phase 2: Migrate Agents (Medium Risk)

For each agent:

- [ ] Create skill folder
- [ ] Split agent file into SKILL.md + IDENTITY.md
- [ ] Copy memories to skill's memories folder
- [ ] Add triggers to SKILL.md frontmatter
- [ ] Create `context/keywords.yaml` if needed

### Phase 3: Update References

- [ ] Update CLAUDE.md skill tables
- [ ] Update Tech Lead Gates
- [ ] Update Session Touch Log format
- [ ] Deprecate `.claude/agents/` (keep as readonly archive)

### Phase 4: Validation

- [ ] Memory retrieval works for all skills
- [ ] Learning loop correctly routes to skill identities
- [ ] 5-personality review works with new structure
- [ ] Full PR cycle succeeds

---

## Part 5: Quick Reference

### Agent → Skill Mapping

| Agent                 | Skill                                         | Type     |
| --------------------- | --------------------------------------------- | -------- |
| kai.md                | kai-prompt-engineering                        | Identity |
| marcus.md             | marcus-backend                                | Identity |
| sofia.md              | sofia-frontend                                | Identity |
| kenji.md              | kenji-testing                                 | Identity |
| priya.md              | priya-architecture                            | Identity |
| theo.md               | theo-documentation                            | Identity |
| claude.md             | claude-tech-lead                              | Identity |
| reginald.md           | review-5personality/personalities/reginald.md | Multi    |
| learning-loop.md      | learning-loop                                 | Pure     |
| functional-testing.md | functional-testing                            | Pure     |

### CLAUDE.md Table Update

**Before:**

```markdown
| Agent | Domain              |
| ----- | ------------------- |
| Kai   | Prompts, evaluators |
```

**After:**

```markdown
| Skill                  | Identity | Domain              |
| ---------------------- | -------- | ------------------- |
| kai-prompt-engineering | Kai      | Prompts, evaluators |
```

---

## Appendix: Why This Change?

1. **Separation of concerns** - "Who" (identity) vs "How" (procedure)
2. **Token efficiency** - Load only what's needed
3. **Portability** - Skills are self-contained folders
4. **Explicit triggers** - Clear when skills activate
5. **Dependencies** - Formal skill relationships

The processes that work (learning loop, 5-personality review) are preserved.
The structure that was awkward (single files mixing everything) is improved.

---

_Last updated: 2026-01-12_
_Source: skills-migration-architecture.md_
