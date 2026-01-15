# Comprehensive Knowledge Base: Engineering Stories & AI Agent Instructions
## Best Practices for Scoping, Formatting, and Prompting (2026 Edition)

This knowledge base integrates authoritative, evidence-backed best practices for:
- **A)** Engineering story (card/ticket) scoping and formatting
- **B)** AI agent (especially Claude Code Opus 4.5 & Claude 3.7) prompts, instructions, and context files

Organized as a navigable handbook with index, cross-references, templates, and recent research (recency bias for AI/LLM validity through January 2026).

---

## Index

1. [Conceptual Overview](#conceptual-overview)
2. [Engineering Story Formatting & Scoping](#engineering-story-formatting--scoping)
   - 2.1. [INVEST Criteria for High-Quality Stories](#invest-criteria-for-high-quality-stories)
   - 2.2. [The 3 C's: Card, Conversation, Confirmation](#the-3-cs-card-conversation-confirmation)
   - 2.3. [Acceptance Criteria & Story Formatting](#acceptance-criteria--story-formatting)
   - 2.4. [BDD, Gherkin, and Given/When/Then](#bdd-gherkin-and-givenwhen then)
   - 2.5. [Example Mapping for Acceptance Criteria](#example-mapping-for-acceptance-criteria)
   - 2.6. [Three Amigos Meetings](#three-amigos-meetings)
   - 2.7. [Story Splitting Techniques](#story-splitting-techniques)
   - 2.8. [Vertical Slicing vs Horizontal Slicing](#vertical-slicing-vs-horizontal-slicing)
   - 2.9. [Planning Poker & Estimation](#planning-poker--estimation)
   - 2.10. [Ticket Writing & Technical Detail](#ticket-writing--technical-detail)
   - 2.11. [Definition of Done (DoD) vs Definition of Ready (DoR)](#definition-of-done-dod-vs-definition-of-ready-dor)
   - 2.12. [Story Mapping & Product Context](#story-mapping--product-context)
   - 2.13. [Backlog Management & DEEP](#backlog-management--deep)
   - 2.14. [Technical Debt Stories](#technical-debt-stories)
3. [AI Agent Prompts & Instructions](#ai-agent-prompts--instructions)
   - 3.1. [Core Agent Prompting Principles](#core-agent-prompting-principles)
   - 3.2. [Task Specificity & Granularity for Agents](#task-specificity--granularity-for-agents)
   - 3.3. [ReAct Prompting Pattern (Reasoning + Acting)](#react-prompting-pattern-reasoning--acting)
   - 3.4. [Extended Thinking Mode (Claude 3.7+)](#extended-thinking-mode-claude-37)
   - 3.5. [Function Calling & Tool Use Best Practices](#function-calling--tool-use-best-practices)
   - 3.6. [Model Context Protocol (MCP)](#model-context-protocol-mcp)
   - 3.7. [Context Files (CLAUDE.md / AGENTS.md / Skills)](#context-files-claudemd--agentsmd--skills)
   - 3.8. [Prompt Formatting: Markdown, JSON, XML](#prompt-formatting-markdown-json-xml)
   - 3.9. [Instruction Content & Spec-Driven Development](#instruction-content--spec-driven-development)
   - 3.10. [Agent Memory Systems: RAG → Agentic RAG → Memory](#agent-memory-systems-rag--agentic-rag--memory)
   - 3.11. [Multi-Agent Architecture Patterns](#multi-agent-architecture-patterns)
   - 3.12. [Agent Observability, Tracing & Debugging](#agent-observability-tracing--debugging)
   - 3.13. [Evaluation & Production Practices](#evaluation--production-practices)
4. [Crosswalk: Human Stories ↔ AI Agent Specs](#crosswalk-human-stories--ai-agent-specs)
5. [Templates & Patterns](#templates--patterns)
   - 5.1. [Engineering Story Template](#engineering-story-template)
   - 5.2. [AI Coding Agent Task Template](#ai-coding-agent-task-template)
   - 5.3. [CLAUDE.md / AGENTS.md Skeleton](#claudemd--agentsmd-skeleton)
   - 5.4. [Example Mapping Workshop Template](#example-mapping-workshop-template)
   - 5.5. [ReAct Agent Prompt Template](#react-agent-prompt-template)
6. [Authoritative Source Index](#authoritative-source-index)
7. [Conclusion & Recommended Practices](#conclusion--recommended-practices)

---

## Conceptual Overview

Engineering work in 2026 involves **two parallel specification layers**:

- **Human-facing layer**: Classic Agile stories and tickets coordinating humans and aligning stakeholders
- **AI-facing layer**: Prompts, context files, and execution specs driving agentic coding tools (Claude Code, GitHub Copilot, etc.)

These are **complementary views** of the same requirements. This knowledge base provides patterns to keep them consistent while playing to each medium's strengths: human-readable narrative and AI-optimized structure.

---

## Engineering Story Formatting & Scoping

### INVEST Criteria for High-Quality Stories

**INVEST** is the dominant heuristic for judging story quality: **Independent, Negotiable, Valuable, Estimable, Small, Testable**.

- **Independent**: Stories decoupled enough to be scheduled in any order, minimizing cross-dependencies
- **Negotiable**: Stories are conversation starters, not contracts; details refined during grooming
- **Valuable**: Each story delivers clear value to user or stakeholder
- **Estimable**: Teams have enough clarity (scope, constraints, dependencies) to estimate effort
- **Small**: Stories fit within single iteration, often 1-3 days of work
- **Testable**: Clear conditions determine when story is done

**Authoritative Sources:**
- [What does INVEST Stand For? - Agile Alliance](https://agilealliance.org/glossary/invest/)
- [Creating The Perfect User Story With INVEST Criteria - Scrum Master](https://scrum-master.org/en/creating-the-perfect-user-story-with-invest-criteria/)
- [INVEST Criteria for Agile User Stories - Boost](https://www.boost.co.nz/blog/2021/10/invest-criteria)
- [Writing Meaningful User Stories with INVEST - LogRocket](https://blog.logrocket.com/product-management/writing-meaningful-user-stories-invest-principle/)

---

### The 3 C's: Card, Conversation, Confirmation

**Ron Jeffries' formula** captures the essential components of a user story:

1. **Card**: Physical token (card or Post-It) giving tangible, durable form to what would otherwise be abstract
2. **Conversation**: Ongoing dialogue between customers, users, developers, testers occurring at different times and places; largely verbal but supplemented by documentation
3. **Confirmation**: Formal verification that objectives from conversation have been reached; maps to acceptance criteria

This distinguishes "social" user stories from "documentary" requirements practices like use cases.

**Key Principle**: The card is a placeholder for conversation, not a complete specification. The conversation clarifies details. Confirmation validates completion.

**Authoritative Sources:**
- [What are the Three C's - Agile Alliance](https://agilealliance.org/glossary/three-cs/)
- [Ultimate Guide to Agile Testing Part 2 - SJ Innovation](https://sjinnovation.com/ultimate-guide-agile-testing-modern-software-teams-part-2)
- [How to Write Agile Test Requirements - SmartBear](https://smartbear.com/test-management/agile-test-case-requirements/)

---

### Acceptance Criteria & Story Formatting

**Acceptance criteria** transform narrative stories into testable, unambiguous conditions.

**Common Formats:**

1. **Given/When/Then (Gherkin/BDD)** - See next section
2. **Rule-oriented lists** - Business rules, edge cases, UX rules
3. **Scenario tables** - Combinatorial cases (different roles, states)

**Best Practices:**

- Tie each criterion to **observable behavior** (UI state, API response, database changes, logs)
- Use **positive, declarative language** ("system shows X") vs vague negatives
- Separate **functional** (what user sees) from **non-functional** (performance, security)
- Limit each story to 3-7 acceptance criteria to keep scope tight

**Authoritative Sources:**
- [Acceptance Criteria: Purposes, Types, Examples - AltexSoft](https://www.altexsoft.com/blog/acceptance-criteria-purposes-formats-and-best-practices/)
- [Understanding Acceptance Criteria - StoriesOnBoard](https://storiesonboard.com/blog/acceptance-criteria-examples)
- [80+ User Story Examples with Acceptance Criteria - Smartsheet](https://www.smartsheet.com/content/user-story-with-acceptance-criteria-examples)
- [What is Acceptance Criteria? - ProductPlan](https://www.productplan.com/glossary/acceptance-criteria/)

---

### BDD, Gherkin, and Given/When/Then

**Behavior-Driven Development (BDD)** uses domain-specific language to write test scenarios in plain, human-readable text.

**Gherkin** is the foremost DSL for articulating behavior in BDD, employed across 70+ languages.

**Structure:**

```gherkin
Feature: <Feature name>
  <Feature description>

Scenario: <Scenario name>
  Given <precondition>
  And <additional precondition>
  When <action>
  Then <expected outcome>
  And <additional expected outcome>
```

**Keywords:**
- **Given**: Sets initial context/preconditions
- **When**: Describes action or event
- **Then**: Defines expected outcome
- **And/But**: Additional steps within Given/When/Then sections

**Best Practices:**

- Keep scenarios clear and simple; avoid jargon
- Focus on high-level behavior (what system does, not how)
- Be specific about expected outcomes (avoid vague expectations)
- Make scenarios precise and realistic using real data when possible
- Scenarios act as "living documentation" ensuring alignment

**Authoritative Sources:**
- [Gherkin and BDD Scenarios - BrowserStack](https://www.browserstack.com/guide/gherkin-and-its-role-bdd-scenarios)
- [Beginner's Guide to BDD - Qase](https://qase.io/blog/behavior-driven-development/)
- [Guide to BDD Testing - VirtuosoQA](https://www.virtuosoqa.com/post/bdd-testing)
- [Behavior-driven Development - Wikipedia](https://en.wikipedia.org/wiki/Behavior-driven_development)
- [BDD - Inflectra](https://www.inflectra.com/Ideas/Topic/Behavior-Driven-Development.aspx)

---

### Example Mapping for Acceptance Criteria

**Example Mapping** is a collaborative technique for extracting acceptance criteria through concrete examples, using a 4-color card system.

**Process:**

1. **Yellow Card**: Write the user story at top of table
2. **Blue Cards**: Capture business rules as you discuss the story
3. **Green Cards**: Write concrete examples illustrating each rule (placed below the rule)
4. **Red Cards**: Capture open questions that can't be answered immediately

**"Friends Episode Naming Convention"**: Create examples like "The one where John registers with a valid email address"

**Interpreting Results:**

- **Many red cards**: Story not ready for development
- **Many blue cards**: Story too big, should be split
- **Many green cards per rule**: Rule may be too complex

**Converting to Gherkin**: Green card examples can be directly written as Given/When/Then scenarios.

**Authoritative Sources:**
- [Example Mapping in BDD - Ibuildings](https://ibuildings.com/blog/2018/07/example-mapping/)
- [Mastering Example Mapping in BDD - LinkedIn](https://www.linkedin.com/pulse/mastering-example-mapping-bdd-essential-practices-common-rabih-arabi-fmoxf)
- [Example Mapping - Draft.io](https://draft.io/example/example-mapping)
- [BDD Example Mapping - Automation Panda](https://automationpanda.com/2018/02/27/bdd-example-mapping/)
- [Example Mapping - Cucumber.io](https://cucumber.io/docs/bdd/example-mapping)

---

### Three Amigos Meetings

**Three Amigos** refers to collaboration pattern bringing together three perspectives to validate product before increment of work:

1. **Business Analyst / Product Owner**: Business requirements and value
2. **Developer**: Low-level design and technical implementation
3. **Tester / QA**: Test cases and quality verification

**Purpose**: Bridge gap in understanding business specifications by ensuring orthogonal views:
- Business representative explains business need
- Programmer discusses implementation details
- Tester offers opinions on what might go wrong

**Best Practices:**

- Don't limit to exactly 3 people; invite security experts, DBAs, etc. as needed
- Goal: At least 3 different viewpoints + consensus on acceptance criteria
- Use Example Mapping technique during Three Amigos sessions
- Apply the 3 C's formula (Card, Conversation, Confirmation)
- Determine if feature is ready for refinement or needs to be pushed to another iteration

**Authoritative Sources:**
- [How to Write Agile Test Requirements - SmartBear](https://smartbear.com/test-management/agile-test-case-requirements/)
- [Three Amigos in Scrum - Edinburgh Agile](https://edinburghagile.com/agile-encyclopedia/information-about-scrum/)
- [Ultimate Guide to Agile Testing Part 2 - SJ Innovation](https://sjinnovation.com/ultimate-guide-agile-testing-modern-software-teams-part-2)

---

### Story Splitting Techniques

When stories violate the **Small** principle, split using these patterns:

**Common Patterns:**

- **Workflow step slicing**: Break by process steps (upload → validate → process → notify)
- **Business rule slicing**: Separate complex rules or policy sets
- **CRUD splits**: Create, read, update, delete as separate stories
- **Happy path vs. edge cases**: Deliver core path first, then error handling
- **Persona/role**: Different user types or permission levels
- **Data types/parameters**: Different input types or complexity levels
- **Operations (complexity)**: Simple operations first, complex later
- **Major effort vs. minor effort**: High-value features before polish

**Key Principle**: Maintain **vertical slices** that still deliver value, not technical decomposition.

**Authoritative Sources:**
- [9 Powerful Techniques For Splitting User Stories - StoriesOnBoard](https://storiesonboard.com/blog/9-techniques-for-splitting-user-stories)
- [Humanizing Work Guide to Splitting User Stories](https://www.humanizingwork.com/the-humanizing-work-guide-to-splitting-user-stories/)
- [What is Story Splitting? - Agile Alliance](https://agilealliance.org/glossary/story-splitting/)
- [Splitting User Stories in Scrum - World of Agile](https://worldofagile.com/blog/splitting-user-stories-in-scrum/)

---

### Vertical Slicing vs Horizontal Slicing

**Vertical Slice**: Complete piece of functionality cutting through every layer (UI → logic → database). Build one complete feature before moving to next.

**Horizontal Slice**: Build entire layer first (all UI, then all logic, then all data).

**"Cake Analogy"**: Vertical slice = slice of all layers; each slice is complete and "ready to eat"

**Benefits of Vertical Slicing:**

- Deliver working functionality early that customers can try
- Reduce cycle times by ~40%
- Enable cross-functional collaboration (designers, devs, QA on same feature)
- Improve feedback loops (ship small testable slices in 1-4 weeks)
- Break down silos and reduce handoffs

**Implementation:**

1. **Define slice boundaries**: Smallest complete feature delivering user value
2. **Focus on happy path first**: Save edge cases for later slices
3. **Feature-based organization**: Organize code by feature, not by technology layer
4. **Clean architecture patterns**: Organize around business capabilities
5. **Complete end-to-end**: Each slice includes everything needed for workflow

**Authoritative Sources:**
- [Vertical Slice Explained for 2026 - Monday.com](https://monday.com/blog/rnd/vertical-slice/)
- [User Stories: Making the Vertical Slice - Applied Frameworks](https://agile.appliedframeworks.com/applied-frameworks-agile-blog/user-stories-making-the-vertical-slice)
- [Vertical Slicing Engineering Practice - Reddit](https://www.reddit.com/r/agile/comments/1btxpzd/vertical_slicing_the_single_most_impactful/)
- [Vertical Slice vs Horizontal Slice - Visual Paradigm](https://www.visual-paradigm.com/scrum/user-story-splitting-vertical-slice-vs-horizontal-slice/)
- [Breaking Down User Stories: Vertical Slicing - DEV](https://dev.to/jan/user-stories-and-vertical-slicing-1dpo)

---

### Planning Poker & Estimation

**Planning Poker** is consensus-based technique for agile estimating using modified Fibonacci sequence.

**Process:**

1. Product Owner presents user story
2. Team discusses story, asking clarifying questions
3. Each estimator privately selects card representing estimate
4. All reveal cards simultaneously
5. If discrepancy, high/low estimators share reasoning
6. Repeat until consensus

**Card Values**: 0, 1, 2, 3, 5, 8, 13, 20, 40, 100 (plus ? for unknowns, ∞ for too large)

**Why Fibonacci**: Reflects inherent uncertainty in estimating; as items get larger, uncertainty increases. Larger gaps force more meaningful distinctions.

**Benefits:**

- **Improved accuracy**: Combines multiple perspectives
- **Enhanced collaboration**: Encourages knowledge sharing
- **Reduced anchoring bias**: Anonymous selection before reveal
- **Consensus building**: Discussion leads to shared understanding
- **Team engagement**: All members actively involved

**Best Practices:**

- Prepare adequately: Well-defined stories, PO ready to clarify
- Set clear ground rules: Discussion limits, how consensus determined
- Regular calibration workshops: Ensure story point scale remains relevant
- Document assumptions: Create history for onboarding and future adjustments
- Involve technical and business profiles: Comprehensive risk evaluation

**Authoritative Sources:**
- [Planning Poker: Agile Estimating Technique - Mountain Goat Software](https://www.mountaingoatsoftware.com/agile/planning-poker)
- [Definitive Guide to Planning Poker - PlanningPoker.live](https://planningpoker.live/knowledge-base/planning-poker-guide-agile-estimation-techniques)
- [Story Points and Planning Poker - Edana](https://edana.ch/en/2025/08/17/story-points-and-planning-poker-how-to-estimate-effectively-in-scrum-and-agile/)
- [Planning Poker Strategy - Asana](https://asana.com/resources/planning-poker)
- [Planning Poker Explained - Daily.dev](https://daily.dev/blog/planning-poker-agile-estimation-technique-explained)

---

### Ticket Writing & Technical Detail

Effective tickets combine clear **user-facing intent** with adequate **technical detail**.

**Key Recommendations:**

- **Clear title**: Describes outcome, not implementation
  - ✅ "Enable CSV export on order list"
  - ❌ "Add /api/export-csv endpoint"
- **Short description**: Problem or user value; avoid long narratives
- **Technical constraints**: Explicit where necessary (target APIs, libraries, performance budgets)
- **Checklists**: For sub-tasks but keep story vertical and user-oriented
- **Referenced design docs**: Detailed plan lives in ADRs, linked from ticket

**Pattern**: "Story captures value, ticket holds implementation hints, detailed plan lives in referenced design docs."

**Authoritative Sources:**
- [How To Write An Agile Ticket - Vollcom Digital](https://www.vollcom-digital.com/blog/resources/tutorials/how-to-write-an-agile-ticket/)
- [Understanding Tickets in Agile - LinkedIn](https://www.linkedin.com/pulse/understanding-tickets-agile-project-delivery-book-extract-nattress-ownpe)
- [Engineering Guide to Writing User Stories - DEV](https://dev.to/wemake-services/engineering-guide-to-writing-correct-user-stories-1i7f)
- [How to Write an Effective Ticket - Liip](https://www.liip.ch/en/blog/how-to-write-an-effective-ticket)

---

### Definition of Done (DoD) vs Definition of Ready (DoR)

**Definition of Done (DoD)**: Shared set of criteria determining when product increment is complete and ready for release.

**Key Components:**

1. **Business/Functional Requirements**
   - Acceptance criteria met
   - Functionality aligns with expected behavior

2. **Quality Standards**
   - Code reviews completed
   - Tests passing (unit, integration, e2e)
   - Coding standards adhered to

3. **Documentation**
   - Necessary documentation created/updated
   - Release notes prepared

**Example DoD Criteria:**

- All acceptance criteria met
- All code tested via unit, integration, e2e tests
- Product increment deployed to staging and tested
- All errors resolved
- Documentation written and edited
- Product Owner reviewed and approved

**Definition of Ready (DoR)**: Criteria defining when backlog item is ready for team to work on in upcoming sprint.

**DoD vs DoR:**

- **DoD**: High-level, applies to product increments, used at sprint end
- **DoR**: Low-level, applies to backlog items, used during backlog refinement

**Importance:**

- **Boosts quality**: Ensures consistent standards throughout development
- **Minimizes risk**: Reduces rework and delays
- **Improves alignment**: Shared understanding across team

**Best Practices:**

- Define with whole team (developers, testers, PO, stakeholders)
- Keep visible during sprint planning
- Be practical and realistic (achievable within timeframe/resources)
- Regularly update as team learns and evolves
- Be specific and customer-focused

**Authoritative Sources:**
- [What is Definition of Done - Atlassian](https://www.atlassian.com/agile/project-management/definition-of-done)
- [Definition of Done in Agile - Agilemania](https://agilemania.com/tutorial/definition-of-done-in-agile)
- [Definition of Done in Scrum - Agile Academy](https://www.agile-academy.com/en/scrum-master/what-is-the-definition-of-done-dod-in-agile/)
- [Techniques for Using DoD - Scrum.org](https://www.scrum.org/resources/blog/techniques-using-definition-done-dod)

---

### Story Mapping & Product Context

**Story Mapping** provides two-dimensional structure organizing stories by user journey and detail.

**Structure:**

- **Backbone**: High-level activities user performs (Browse → Select → Checkout → Receive)
- **Steps**: Ordered steps within each activity
- **Details**: Stories living under each step, providing incremental improvements

**Benefits:**

- Makes clear **where** story fits in overall flow
- Encourages **vertical slices** vs layer-based decomposition
- Provides bridge to **agent specs** when AI automates parts of journey

**Authoritative Sources:**
- [User Story Mapping Intro - StoriesOnBoard](https://storiesonboard.com/user-story-mapping-basics.html)
- [Getting Started with Story Mapping - Mind the Product](https://www.mindtheproduct.com/getting-started-with-user-story-mapping-jeff-patton/)
- [Story Map Concepts - Jeff Patton (PDF)](https://www.jpattonassociates.com/wp-content/uploads/2015/03/story_mapping.pdf)

---

### Backlog Management & DEEP

**Roman Pichler's DEEP** acronym: **Detailed appropriately, Estimated, Emergent, Prioritized**

**Key Aspects:**

- **Detailed appropriately**: Near-term items fully fleshed; long-term items coarse-grained
- **Estimated**: Rough sizing for prioritization
- **Emergent**: Backlog continuously refined as team learns
- **Prioritized**: Items ordered by value, risk, dependencies

Maps naturally to **agent task queues** where atomic agent tasks emerge from refined high-priority items.

**Authoritative Sources:**
- [Make the Product Backlog DEEP - Roman Pichler](https://www.romanpichler.com/blog/make-the-product-backlog-deep/)
- [5 Tips for Stocking Product Backlog - Roman Pichler](https://www.romanpichler.com/blog/5-tips-for-stocking-the-product-backlog/)
- [Tips for Reducing Backlog Size - Roman Pichler](https://www.romanpichler.com/blog/how-to-reduce-the-product-backlog-size/)

---

### Technical Debt Stories

Technical debt requires **explicit representation** to avoid invisibility.

**Guidance:**

- Clearly label **debt type** (design, code quality, test coverage, infrastructure)
- Specify **impact** (slower delivery, defects, operational risk)
- Provide **acceptance criteria** oriented around improved maintainability or risk reduction
  - Example: "Cyclomatic complexity under N"
  - Example: "Tests for top 3 failure modes"
- Integrate into normal backlog
- Make value visible to non-engineers

**Authoritative Sources:**
- [What is Technical Debt - Zendesk](https://www.zendesk.com/blog/technical-debt/)
- [Technical Debt Management - Leanware](https://www.leanware.co/insights/technical-debt-management-best-practices)
- [What is Tech Debt - Atlassian](https://www.atlassian.com/agile/software-development/technical-debt)

---

## AI Agent Prompts & Instructions

### Core Agent Prompting Principles

Anthropic, GitHub, and Google converge on foundational principles:

1. **Role & Goal First**
   - Clearly define agent's role and immediate goal
   - Example: "You are a senior backend engineer working in this repo"

2. **Single Responsibility per Task**
   - Narrow scope and clear success criteria
   - Large projects decomposed into sequence of such tasks

3. **Explicit Success Metrics**
   - Define how success evaluated (tests passing, files changed, log messages)

4. **Guardrails & Constraints**
   - Specify allowed operations (no destructive scripts, no secrets in code)

5. **Context-aware**
   - Provide repo and domain context via context files or inline references

**Authoritative Sources:**
- [Building Effective AI Agents - Anthropic Research](https://www.anthropic.com/research/building-effective-agents)
- [Claude Code: Best Practices - Anthropic](https://www.anthropic.com/engineering/claude-code-best-practices)
- [Best Practices for GitHub Copilot Tasks - GitHub Docs](https://docs.github.com/copilot/how-tos/agents/copilot-coding-agent/best-practices-for-using-copilot-to-work-on-tasks)
- [Prompting Best Practices - Claude Docs](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-4-best-practices)

---

### Task Specificity & Granularity for Agents

**Single-Responsibility Tasks:**

- Each prompt asks agent to **do one thing well**
- Narrow tasks improve reliability, performance, debugging
- Similar to small, well-scoped user stories

**Atomic Prompting Architecture:**

- Operations broken into minimal units that can be chained
- Single-purpose prompts produce consistent results
- Enable parallel processing without context contamination

**WRAP Method (GitHub Copilot):**

- **W – Write effective issues**: Clear title, description, scope, acceptance criteria
- **R – Refine instructions**: Iteratively improve based on agent performance
- **A – Atomic tasks**: One well-bounded task per issue
- **P – Prioritize**: Order tasks respecting dependencies and value

**Authoritative Sources:**
- [10 Best Practices for Building AI Agents - UiPath](https://www.uipath.com/blog/ai/agent-builder-best-practices)
- [AI Assistant Builder Engineering Guide - Quiq](https://quiq.com/blog/ai-assistant-builder-guide-part-one/)
- [WRAP Up Your Backlog - GitHub Blog](https://github.blog/ai-and-ml/github-copilot/wrap-up-your-backlog-with-github-copilot-coding-agent/)
- [5 Tips for Better Custom Instructions - GitHub Blog](https://github.blog/ai-and-ml/github-copilot/5-tips-for-writing-better-custom-instructions-for-copilot/)

---

### ReAct Prompting Pattern (Reasoning + Acting)

**ReAct** (Reasoning and Acting) is fundamental paradigm where LLMs generate both **reasoning traces** and **task-specific actions** in interleaved manner.

**Structure:**

```
Thought: <reasoning step>
Action: <tool to invoke with parameters>
Observation: <result from environment/tool>
[Repeat Thought → Action → Observation loop]
Answer: <final response>
```

**How It Works:**

- **Thought**: Internal reasoning about next step (decompose question, extract info, guide search)
- **Action**: Invoke external tool (search engine, API, database, calculator)
- **Observation**: Feedback from environment used in next reasoning step

**Benefits:**

- Addresses CoT limitations (fact hallucination, error propagation)
- Enables dynamic reasoning with external information
- Allows models to maintain and adjust plans
- Creates task-solving trajectories that are traceable

**Use Cases:**

- Task-oriented dialogue systems
- Complex question answering requiring multiple information sources
- Policy research and evidence collection
- Multi-step workflows with tool dependencies

**Implementation:**

- Use few-shot prompting with ReAct-format trajectories
- Provide examples showing Thought-Action-Observation sequences
- Structure templates guide LLM through critical stages

**Authoritative Sources:**
- [ReAct Prompting - Prompt Engineering Guide](https://www.promptingguide.ai/techniques/react)
- [LLM Agents - Prompt Engineering Guide](https://www.promptingguide.ai/research/llm-agents)
- [Exploring ReAct for Task-Oriented Dialogue - ACL 2025 (PDF)](https://aclanthology.org/2025.iwsds-1.12.pdf)
- [Application of ReAct in Policy Collection - ScitePress (PDF)](https://www.scitepress.org/Papers/2025/132430/132430.pdf)
- [Implementing ReAct Pattern - Daily Dose of DS](https://www.dailydoseofds.com/ai-agents-crash-course-part-10-with-implementation/)

---

### Extended Thinking Mode (Claude 3.7+)

**Extended Thinking** allows Claude to adjust "mental effort" spent on questions—fast response mode vs. slower, deliberative thinking mode.

**Architecture:**

- **Hybrid reasoning system**: Dynamically toggles between "Instant" and "Extended Thinking"
- **Instant Mode**: Rapid responses for simple queries
- **Extended Thinking Mode**: Deeper cognitive processing for complex problems
- **Thinking Budget**: Control how many tokens Claude can spend reasoning before answering

**How It Works:**

- Claude generates hidden **chain-of-thought** (internal scratchpad)
- Uses reasoning to produce final answer
- Can reveal thinking process to user or keep it hidden
- Automatically determines when to engage based on task difficulty

**Benefits:**

- 54% improvement in complex coding challenges
- Better performance on multi-step reasoning problems
- Scalable "cognitive effort" dynamically allocated
- More reliable and nuanced results on complex tasks

**Prompt Engineering for Extended Thinking:**

1. **Direct Step-by-Step Requests**
   - "Please show your reasoning step by step before giving the final answer"

2. **Role-Based Prompting**
   - "You are a senior data scientist. Walk through your planning process..."

3. **Few-Shot with Reasoning Examples**
   - Provide examples showing step-by-step thinking patterns

4. **High-Level Instructions**
   - Claude performs better with "think deeply about this task" vs prescriptive step-by-step guidance
   - Model's creativity may exceed human's ability to prescribe optimal process

5. **Multi-Shot Prompting**
   - Provide examples of how to think through problems
   - Claude follows similar reasoning patterns

**Best Practices:**

- Don't iterate code, iterate plans
- Use extended thinking for complex tasks, instant for simple queries
- Combine with clear role definition and success criteria
- Leverage for multi-turn conversations to "reset" or clarify approach

**Authoritative Sources:**
- [How Claude's Thinking Mode Works - Claude-AI.chat](https://claude-ai.chat/blog/extended-thinking-mode/)
- [Extended Thinking Tips - Claude Docs](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/extended-thinking-tips)
- [Mastering Claude's Extended Thinking - Sparkco](https://sparkco.ai/blog/mastering-claudes-extended-thinking-in-ai)
- [Claude 3.7 Sonnet Full System Prompt - Reddit](https://www.reddit.com/r/ClaudeAI/comments/1ixapi4/here_is_claude_sonnet_37_full_system_prompt/)
- [The Think Tool - Anthropic Engineering](https://www.anthropic.com/engineering/claude-think-tool)

---

### Function Calling & Tool Use Best Practices

**Function Calling** is ability to reliably connect LLMs to external tools, enabling effective tool usage and interaction with external APIs.

**How It Works:**

- LLMs fine-tuned to detect when function needs to be called
- Output JSON containing arguments to call function
- LLM identifies function and gathers parameters; doesn't execute
- Application deserializes JSON and executes function

**Structured Tool Invocations:**

- Use defined schemas (typically JSON format)
- Specify function name, parameters, types, required fields
- Provide clear descriptions for each function and parameter

**Template-Based Reasoning for Function Calling:**

Seven-stage framework for structured function calling:

1. **Identify functions**: Which tools are available?
2. **Decision on relevancy**: Are provided functions relevant to query?
3. **Examine documentation**: Review relevant function specs
4. **Extract and validate parameters**: From user query
5. **Conversion**: Type conversion or implicit value handling
6. **Draft function call**: Construct the invocation
7. **Revalidate**: Check function call correctness

**Best Practices:**

- **Intent Detection**: Use LLM to classify user intent, trigger structured tool actions
- **Slot Filling**: Extract parameters from input, feed into tool call
- **Contextual Prompting**: Use conversation memory for missing information
- **One-shot/Few-shot Prompting**: Provide examples of user message → function call pairs
- **Structured Guidance**: Not generic heuristics—domain-adapted scaffolding is essential

**Use Cases:**

- Conversational agents answering questions with external data
- API integration (convert natural language to valid API calls)
- Information extraction from structured sources

**Authoritative Sources:**
- [Function Calling with LLMs - Prompt Engineering Guide](https://www.promptingguide.ai/applications/function_calling)
- [Function Calling in AI Agents - DAIR.AI](https://www.dair.ai/blog/function-calling)
- [Function Calling - Martin Fowler](https://martinfowler.com/articles/function-call-LLM.html)
- [Improving Function Calling - EMNLP 2025 (PDF)](https://aclanthology.org/2025.emnlp-main.1242.pdf)
- [Best Practices to Build LLM Tools - Tech Info](https://techinfotech.tech.blog/2025/06/09/best-practices-to-build-llm-tools-in-2025/)

---

### Model Context Protocol (MCP)

**Model Context Protocol** is open standard (introduced Nov 2024 by Anthropic) enabling secure, two-way connections between AI systems and data sources.

**Key Dates:**

- **November 2024**: Announced by Anthropic
- **December 2025**: Donated to Agentic AI Foundation under Linux Foundation
- **November 2025**: One-year anniversary, new spec release

**Purpose:**

- Standardize how AI systems integrate and share data with external tools, systems, data sources
- Replace fragmented N×M integrations with single protocol
- Universal interface for reading files, executing functions, handling contextual prompts

**Architecture:**

- **MCP Servers**: Expose data through standardized interface
- **MCP Clients**: AI applications connecting to servers
- **Transport**: JSON-RPC 2.0
- **SDKs**: Python, TypeScript, C#, Java

**Features:**

- Data ingestion and transformation
- Contextual metadata tagging
- AI interoperability across platforms
- Bidirectional connections between data sources and AI tools

**Comparison to Earlier Approaches:**

- OpenAI's 2023 function-calling API: Vendor-specific
- ChatGPT plugin framework: Required custom connectors
- MCP: Universal, open standard inspired by Language Server Protocol

**Adoption:**

- Major providers: OpenAI, Google DeepMind
- Tools: Zed, Replit, Codeium, Sourcegraph
- Enterprises: Block, Apollo

**Why It Matters:**

- **Developers**: Reduces development time/complexity
- **AI Applications**: Access to ecosystem of data sources
- **End-users**: More capable AI applications accessing their data

**Governance:**

- Community leaders and Anthropic maintainers collaborate
- Open contribution process
- Sustainable pace with clear governance structure

**Authoritative Sources:**
- [Introducing Model Context Protocol - Anthropic](https://www.anthropic.com/news/model-context-protocol)
- [Model Context Protocol - Wikipedia](https://en.wikipedia.org/wiki/Model_Context_Protocol)
- [What is MCP? - Model Context Protocol](https://modelcontextprotocol.io)
- [Why Companies Should Know About MCP - Nasuni](https://www.nasuni.com/blog/why-your-company-should-know-about-model-context-protocol/)
- [One Year of MCP - MCP Blog](http://blog.modelcontextprotocol.io/posts/2025-11-25-first-mcp-anniversary/)

---

### Context Files (CLAUDE.md / AGENTS.md / Skills)

#### CLAUDE.md

**CLAUDE.md is the single most important file** for Claude Code.

**Size Constraints:**

- Keep under ~300 lines (ideally <60)
- Loaded into every session without overwhelming model

**Content:**

- Repo layout and essential file structure
- Standard commands (build, test, run, format)
- Coding conventions and architectural patterns
- Safety rules (no secrets, environment assumptions)
- "When in doubt" behaviors (ask before refactors, generate tests)

**Principles:**

- **Timeless, universal repo knowledge**—not ticket-specific
- **Progressive disclosure**: Use separate task-specific files for details
- **Shallow hierarchy**: Single H1, handful of H2/H3
- Median length ~500 words
- Prioritize Build/Run, Implementation, Architecture content
- Files grow via small, frequent edits

**Authoritative Sources:**
- [Writing a Good CLAUDE.md - HumanLayer](https://www.humanlayer.dev/blog/writing-a-good-claude-md)
- [Claude Code Best Practices - Anthropic](https://www.anthropic.com/engineering/claude-code-best-practices)
- [Empirical Study of Context Files - arXiv](https://arxiv.org/html/2511.12884v1)
- [Highly Effective CLAUDE.md - Reddit](https://www.reddit.com/r/ClaudeAI/comments/1mgfy4t/highly_effective_claudemd_for_large_codebasees/)

#### AGENTS.md

More **agent behavior-focused** than CLAUDE.md:

- "Do" and "Don't" lists for code generation
- Concrete examples of **good vs bad** files/code
- API docs and environment details
- PR review checklists and quality gates
- Instructions for when agent is stuck (ask, search, propose alternatives)

**Authoritative Sources:**
- [Improve AI Code Output with AGENTS.md - Builder.io](https://www.builder.io/blog/agents-md)

#### Skills and Task-Scoped Files

**Claude Code Skills System:**

- **SKILL.md**: YAML metadata plus high-level description
- **reference.md, examples.md**: Detailed docs loaded only when skill used
- **Progressive disclosure**: Global context (CLAUDE.md) plus localized skill context

**Authoritative Sources:**
- [Agent Skills - Claude Code Docs](https://code.claude.com/docs/en/skills)
- [Common Workflows - Claude Code Docs](https://code.claude.com/docs/en/common-workflows)

---

### Prompt Formatting: Markdown, JSON, XML

#### Choosing a Format

**Markdown:**
- Best default for combined human + AI readability
- Minimal token overhead
- Flexible headings and lists
- Works well for instructions, context, code snippets

**JSON:**
- Best when output needs to be **machine-consumable**
- Use strict schemas and validation
- Specify required fields and allowable values explicitly

**XML:**
- Useful for **instruction-heavy prompts** with deeply nested sections
- Heavier and less ergonomic
- Claude models fine-tuned to pay attention to XML tags
- Experiments show slightly lower performance vs Markdown/JSON
- Avoid for line-based editing (find/replace)

**Key Finding**: Format matters less than clarity and consistency.

#### Structured Prompting Best Practices

- Use **clear section headers**: role, context, tasks, constraints, output format
- For JSON/XML outputs: Show **exact schema** with field names, types, examples
- For Markdown outputs: Specify code blocks, lists, tables expectations
- Consistently separate **instructions** from **examples** from **input data**

**Claude-Specific:**

- Use XML tags to separate instructions from context
- Be direct, concise, specific
- Help Claude with output using `Assistant` message prefill
- Break complex tasks into steps

**Authoritative Sources:**
- [Structured Prompting: XML & JSON - Code Conductor](https://codeconductor.ai/blog/structured-prompting-techniques-xml-json/)
- [Does Output Format Matter? - Checksum.ai](https://checksum.ai/blog/output-format-llm-json-xml-markdown)
- [LLM-Friendly Content in Markdown - Webex](https://developer.webex.com/blog/boosting-ai-performance-the-power-of-llm-friendly-content-in-markdown)
- [12 Prompt Engineering Tips for Claude - Vellum AI](https://www.vellum.ai/blog/prompt-engineering-tips-for-claude)
- [Prompt Engineering Techniques - AWS](https://aws.amazon.com/blogs/machine-learning/prompt-engineering-techniques-and-best-practices-learn-by-doing-with-anthropics-cl)
- [How to Prompt Claude 3.7 - AI Ranking](https://www.airankingskool.com/post/how-to-prompt-anthropics-claude-3-7-sonnet)

---

### Instruction Content & Spec-Driven Development

#### What to Specify in System/Task Instructions

**Consistent Checklist:**

- **Role & Persona**: What agent "is" (e.g., senior backend engineer, security reviewer)
- **Goal/Outcome**: One clear goal per task, stated in outcome form
- **Context**: File paths, architecture notes, business rules, environment constraints
- **Steps or Process**: Outline phases (for complex tasks) while leaving room for planning
- **Success Criteria**: Tests passing, specific diffs, log messages, performance thresholds
- **Guardrails**: What NOT to do (no destructive operations, no secrets, must write tests)

**Instructions Best Practices:**

- **One directive per line**
- Use CAPITALIZATION for strong rules ("ALWAYS include unit tests")
- Describe what TO do (not what NOT to do)
- Provide rationale—helps model apply principles in edge cases
- Specify output format explicitly

**Effectiveness**: 9/10 across all task types when instructions clearly specify requirements, format, success criteria.

#### Spec-Driven Development

**Workflow:**

1. **Specification**: Functional/non-functional requirements, user stories, acceptance criteria, API contracts
2. **Plan**: High-level decomposition into tasks (sometimes written by agent)
3. **Tasks**: Human stories and AI tasks both aligned to spec
4. **Implement**: With quality gates (tests, static analysis, code review)

**Benefits:**

- Executable specifications
- Consistent implementation
- Self-updating documentation
- Quality gates at each phase

For agents, spec documents (often Markdown) become **prime context files** driving accurate implementation.

**Authoritative Sources:**
- [UiPath Agent Builder Best Practices](https://www.uipath.com/blog/ai/agent-builder-best-practices)
- [Best Practices for AI Agent Action - Tines](https://explained.tines.com/en/articles/11644147-best-practices-for-the-ai-agent-action)
- [Guidelines for Automating with AI - Webex](https://help.webex.com/en-us/article/nelkmxk/Guidelines-and-best-practices-for-automating-with-AI-agent)
- [Spec-Driven Development Explained - Augment Code](https://www.augmentcode.com/guides/spec-driven-development-ai-agents-explained)
- [Spec-Driven Approach for AI - JetBrains](https://blog.jetbrains.com/junie/2025/10/how-to-use-a-spec-driven-approach-for-coding-with-ai/)
- [Spec-Driven Development Complete Guide - Software Seni](https://www.softwareseni.com/spec-driven-development-in-2025-the-complete-guide-to-using-ai-to-write-production-code/)
- [How Spec-Driven Improves Quality - Red Hat](https://developers.redhat.com/articles/2025/10/22/how-spec-driven-development-improves-ai-coding-quality)
- [We Tested 25 Claude Techniques - DreamHost](https://www.dreamhost.com/blog/claude-prompt-engineering/)

---

### Agent Memory Systems: RAG → Agentic RAG → Memory

**Evolution of memory/retrieval systems** represents fundamental shift in AI architecture.

#### RAG: Read-Only, Single-Pass Retrieval

- Query knowledge base
- Retrieve relevant documents
- Generate response from static snapshot
- Data store updated offline
- No state carried forward

**Use**: Fixed knowledge, rigid interaction model.

#### Agentic RAG: Intelligent Retrieval Control

- **Still read-only** but adds reasoning layer
- Agent decides:
  - Do I need to retrieve?
  - Which source to pull from?
  - Is returned context useful?
- Strategic retrieval vs "retrieve everything always"

#### Agent Memory: Read-Write Knowledge Interaction

- **Write operations during inference**
- System becomes stateful and adaptive
- Agent can:
  - Persist new information from conversations
  - Update or refine previously stored data
  - Capture events as long-term memory
  - Build personalized knowledge profile over time

**Memory Types:**

- **Procedural**: Behavioral rules ("always respond with emojis")
- **Episodic**: User-specific events ("trip mentioned on Oct 30")
- **Semantic**: Factual knowledge ("Eiffel Tower height 330m")

**Storage:**

- Vector databases: pgvector, Pinecone, Weaviate, Milvus
- High-dimensional embeddings
- Fast similarity search, incremental updates
- Multi-tenant collections

**Challenges:**

- What to remember vs discard (memory pollution)
- Memory decay/forgetting strategies
- Conflict resolution and data correction
- Long-term vs short-term context separation
- Semantic garbage collection needed

**Key Takeaway:**

- **RAG** made AI informed
- **Agentic RAG** made it strategic
- **Agent Memory** makes it adaptive

**Authoritative Sources:**
- [RAG → Agentic RAG → Memory - Yugensys](https://www.yugensys.com/2025/11/19/evolution-of-rag-agentic-rag-and-agent-memory/)
- [RAG, Agentic RAG, and Memory - Daily Dose DS](https://blog.dailydoseofds.com/p/rag-agentic-rag-and-ai-memory)
- [From RAG to Context 2025 Review - RAGFlow](https://ragflow.io/blog/rag-review-2025-from-rag-to-context)
- [Ultimate AI Agent Roadmap 2025 - The AI Corner](https://www.the-ai-corner.com/p/ai-agents-roadmap-2025-best-projects-rag-mcp-memory)

---

### Multi-Agent Architecture Patterns

Modern agentic AI uses **five distinct patterns** for enterprise operations.

#### 1. Task-Oriented Agents

- Execute specific, well-defined workflows without human intervention
- **Bounded autonomy**: Operate independently within defined parameters
- Architecture: Reasoning engine (LLM) + execution modules (APIs, DBs) + guardrails (validation, approval)

#### 2. Reflective Agents

- Self-monitor and self-correct
- Evaluate own outputs for quality, accuracy, adherence to constraints
- Maintain internal feedback loops

#### 3. Collaborative Agents (Multi-Agent Systems)

- Specialized agents with different capabilities work together
- One retrieves data, another analyzes, third explains
- Architecture: Orchestration layers managing communication, shared memory, conflict resolution

**Patterns:**

- **Coordinator Pattern**: Central agent routes tasks to specialized agents
- **Hierarchical (Vertical)**: Leader coordinates subtasks, subordinates execute
- **Decentralized (Horizontal)**: Peers collaborate without central leader
- **Hybrid**: Dynamic leadership shifting based on task

#### 4. Self-Improving Agents

- Monitor prediction accuracy and data distribution
- Detect drift, trigger retraining
- Automated ML pipelines with versioning
- Validation frameworks, rollback mechanisms

#### 5. RAG (Retrieval-Augmented Generation) Agents

- Combine generation with dynamic retrieval
- Access external knowledge bases during inference
- Update understanding in real-time

**Workload Patterns:**

- **Static orchestration**: Predefined workflows
- **Dynamic orchestration**: Agents determine best way to proceed
  - Single agent pattern
  - Multi-agent coordinator
  - Hierarchical task decomposition
  - Swarm pattern

**Authoritative Sources:**
- [5 Agentic AI Design Patterns - Shakudo](https://www.shakudo.io/blog/5-agentic-ai-design-patterns-transforming-enterprise-operations-in-2025)
- [Agentic AI Architecture - Exabeam](https://www.exabeam.com/explainers/agentic-ai/agentic-ai-architecture-types-components-best-practices/)
- [Implementing Agentic AI Architecture - Fabrix](https://fabrix.ai/blog/implementing-agentic-ai-a-technical-overview-of-architecture-and-frameworks/)
- [Choose Design Pattern for Agentic AI - Google Cloud](https://docs.cloud.google.com/architecture/choose-design-pattern-agentic-ai-system)
- [Advanced Prompt Engineering Techniques - Maxim AI](https://www.getmaxim.ai/articles/advanced-prompt-engineering-techniques-in-2025/)

---

### Agent Observability, Tracing & Debugging

**Observability is practice** of monitoring and understanding full set of behaviors autonomous agent performs.

#### Why Observability Matters

- **Root-cause analysis**: Reconstruct agent's entire decision process
- **Accountability**: Required by governance and regulatory standards
- **Security monitoring**: Identify unauthorized tool use, data exposure
- **Behavioral variability**: Distinguish normal variation from design flaws

#### What to Capture

- **Distributed tracing**: Every LLM call, tool execution, retrieval, decision point
- **Session tracking**: Group traces into conversational threads
- **Span-level evaluation**: Assess quality at individual steps
- **Performance metrics**: Latency, token usage, cost
- **Tool calls**: Inputs and outputs for each invocation
- **Reasoning paths**: Step-by-step agent execution

#### Analysis & Issue Detection

**Process & Causal Discovery:**

- Treat execution traces as event logs
- Detect dependencies between actions
- Observe where paths diverge
- Identify unexpected behaviors

**Anomaly Detection:**

- Workflow failures and incomplete tasks
- Degraded output quality or low-confidence responses
- Repeated tool errors or inefficient patterns
- Deviations from compliance/safety policies
- Signals indicating prompt manipulation or unauthorized access

#### Action & Automation

- **Reproducible records**: Replay execution path
- **Root-cause analysis**: Exact moment behavior diverged
- **Behavioral observability**: Answer "is system behaving as intended?"
- **LLM-based static analysis**: Check if specifications are too loose, conflicting, incomplete

#### Best Practices

- **Embed observability throughout lifecycle**: Not just deploy-time
- **Evaluation suites**: Deterministic tests, scenario-based flows, LLM-as-judge scoring
- **Focus on behavioral/decision observability**: Traditional monitoring answers "is it up?"; agent observability answers "is it behaving correctly?"
- **Manage memory pollution**: Semantic garbage collection to prune outdated context

**Top Platforms (2026):**

- Maxim AI: Comprehensive end-to-end with simulation and cross-functional collaboration
- Braintrust: Comprehensive tracing with AI-powered debugging
- LangSmith: LangChain-native with deep integration
- Arize Phoenix: Open-source with strong LLM evaluation
- Weights & Biases: ML platform with agent observability

**Authoritative Sources:**
- [AI Agent Observability Framework - N-iX](https://www.n-ix.com/ai-agent-observability/)
- [Top 5 AI Agent Observability Platforms - O-mega](https://o-mega.ai/articles/top-5-ai-agent-observability-platforms-the-ultimate-2026-guide)
- [5 Best Agent Debugging Platforms - Maxim AI](https://www.getmaxim.ai/articles/the-5-best-agent-debugging-platforms-in-2026/)
- [Debugging AI Agents at Scale - YouTube](https://www.youtube.com/watch?v=jQwAmwjTsfs)
- [State of Agent Engineering - LangChain](https://www.langchain.com/state-of-agent-engineering)

---

### Evaluation & Production Practices

**Pattern for Productionizing Agent Workflows:**

#### Evaluation Datasets

- Build realistic task datasets (30+ cases)
- Cover breadth and depth of use cases
- Include edge cases and failure scenarios
- Use for regression testing

#### End-to-End Testing

- Not just code correctness
- Test tool use, logging, failure handling
- Mimic real automation workflows
- Validate in full automation contexts

#### Tracing & Observability

- Inspect agent's reasoning and tool calls
- Track performance metrics
- Monitor quality degradation
- Detect behavioral drift

#### Human Review Loops

- Especially around dangerous operations
- High-risk domains require oversight
- Governance and compliance validation

#### Iterative Improvement

- **"Don't iterate code, iterate plans"**
- Refactor agent's strategy and context before re-running
- Keep timelines and change logs in docs
- Track why changes were made

**Authoritative Sources:**
- [UiPath Agent Builder Best Practices](https://www.uipath.com/blog/ai/agent-builder-best-practices)
- [Autonomous Coding Agents - Zencoder](https://zencoder.ai/blog/autonomous-coding-agents)
- [Building Effective Agents - Anthropic](https://www.anthropic.com/research/building-effective-agents)
- [Claude Opus 4.5 Workflow - Remio AI](https://www.remio.ai/post/mastering-the-claude-opus-4-5-workflow-from-40k-lines-to-zero-code-apps)
- [Top 8 LLM Frameworks - Second Talent](https://www.secondtalent.com/resources/top-llm-frameworks-for-building-ai-agents/)
- [Recursive Language Models 2026 - Prime Intellect](https://www.primeintellect.ai/blog/rlm)

---

## Crosswalk: Human Stories ↔ AI Agent Specs

### From User Story to Agent Task

**Mapping:**

- **User Story** → **Goal & Context** in agent prompt
- **Acceptance Criteria** → **Success Metrics & Tests** in agent instructions
- **Technical Notes** → **Guardrails & Constraints** in system message or context file

**Example:**

Story acceptance criterion:
> "Given invalid email, form shows an error and does not submit"

Becomes agent success condition:
> "Ensure email field validates format and shows error message 'Invalid email address'; add tests covering this case."

### Story Splitting vs Task Decomposition

- **Story splitting** (user value, vertical slices) informs **agent task decomposition** (atomic prompts, single responsibility)
- Same decomposition patterns (workflow steps, rules, personas) reused for **separate agent tasks** chained in workflow/orchestrator

### Backlog (DEEP) vs Agent Queues

- **Detailed appropriately** → **Level of detail in prompts/context files**: Near-term tasks have full agent-ready specs
- **Emergent** backlog → **Iterative refinement of context files** (CLAUDE.md/AGENTS.md) as patterns discovered

### Three Amigos → Multi-Perspective Agent Design

- Business, Dev, QA perspectives map to:
  - Agent specification
  - Implementation constraints
  - Success criteria and testing

### Definition of Done → Agent Success Criteria

- DoD components (functional, quality, documentation) become explicit agent success metrics
- "All tests passing" maps directly to agent validation steps

---

## Templates & Patterns

### Engineering Story Template

```markdown
# Story: <Concise, outcome-focused title>

## User Story (3 C's: Card)

As a <role>  
I want <capability>  
So that <business value>

## Context

- Related feature/epic: <link or name>
- User journey step: <from story map, e.g., "Checkout → Payment">
- Dependencies: <other stories, systems, or releases>
- Non-functional constraints: <e.g., latency, security, accessibility>

## Acceptance Criteria (3 C's: Confirmation)

### Given/When/Then Format:

- [ ] **Given** <precondition> **when** <action> **then** <expected outcome>
- [ ] **Given** <precondition> **when** <alternate action> **then** <alternate outcome>
- [ ] [Non-functional] <performance, accessibility, security criteria>
- [ ] [Observability] <logging, monitoring, alerting requirements>

## Technical Notes

- Target components/services: <paths, services, API endpoints>
- Known constraints or tech decisions: <libraries, frameworks, patterns>
- Testing expectations: <unit/integration/e2e; coverage or key scenarios>
- Vertical slice: <which layers this story touches>

## INVEST Check

- [ ] **I**ndependent: Can be developed separately from other stories
- [ ] **N**egotiable: Details can be refined during development
- [ ] **V**aluable: Delivers clear value to user/stakeholder
- [ ] **E**stimable: Team can estimate effort required
- [ ] **S**mall: Completable within single iteration (1-3 days)
- [ ] **T**estable: Clear acceptance criteria define "done"

## Definition of Ready

- [ ] Story discussed in Three Amigos meeting
- [ ] Acceptance criteria defined and agreed upon
- [ ] Dependencies identified and resolved
- [ ] Estimated and fits in sprint

## Notes (3 C's: Conversation)

- Open questions
- Links to design docs or ADRs
- Example mapping session notes
```

---

### AI Coding Agent Task Template

```markdown
# Agent Task: <Atomic, outcome-focused title>

## Role & Context

You are a <seniority level> <role> working in this repository.  
Follow project conventions in `CLAUDE.md` / `AGENTS.md`.

**Repository**: <repo name>  
**Task Type**: <implementation|refactoring|testing|documentation>  
**Related Story**: <link to human story if applicable>

## Goal (Single Responsibility)

<One clear, specific goal aligned to single story or sub-story>

## Context & Architecture

### Relevant Files:
- `path/to/file1` - <brief description>
- `path/to/file2` - <brief description>

### Architecture Notes:
<Short explanation or pointers to design docs>

### Business Rules:
- <Key rule 1 affecting this change>
- <Key rule 2 affecting this change>

### Related Systems:
<APIs, databases, external services this task touches>

## Instructions (Step-by-Step)

1. **Analyze** existing implementation relevant to this task
2. **Propose** brief plan as Markdown list
   - Wait for confirmation if interactive
   - OR proceed if task fully specified
3. **Implement** change according to plan
4. **Add/Update Tests** to cover:
   - <Acceptance criterion 1 translated to test case>
   - <Acceptance criterion 2 translated to test case>
5. **Verify** by running:
   - `<test command>` (see CLAUDE.md)
   - `<lint command>`
   - `<build command>`
6. **Explain** changes at high level in short summary

## Success Criteria (Explicit & Observable)

- [ ] All acceptance criteria from related story satisfied:
  - <Map each criterion to observable behavior or test>
- [ ] All tests pass (existing + new)
- [ ] No regressions in existing behavior
- [ ] Code follows repository standards (see CLAUDE.md)
- [ ] <Performance threshold if applicable>
- [ ] <Security requirement if applicable>

## Guardrails & Constraints

### DO NOT:
- Introduce new dependencies without explicit mention
- Expose secrets or credentials
- Make destructive changes without confirmation
- Modify files outside scope

### ALWAYS:
- Write/update tests for changed code
- Follow coding standards in CLAUDE.md
- Keep changes small and focused
- Add explanatory comments for complex logic

## Function Calling / Tool Use

<If task requires tool use, specify tools and expected invocation pattern>

**Available Tools**:
- `<tool_name>`: <description, parameters>

**Expected Tool Usage**:
- <ReAct-style reasoning about when/how to use tools>

## Extended Thinking Mode

<For complex tasks only>

This task requires extended reasoning. Use thinking budget to:
- Decompose problem into sub-steps
- Consider edge cases and failure modes
- Plan implementation approach before coding
```

---

### CLAUDE.md / AGENTS.md Skeleton

```markdown
# CLAUDE.md

## Project Overview

**Purpose**: <One paragraph describing what this project does>

**Primary Components**:
- `frontend/` – <Description, tech stack>
- `backend/` – <Description, tech stack>
- `infra/` – <Description, deployment info>

**Architecture Style**: <Microservices|Monolith|Vertical Slices|etc.>

## How to Build and Run

```bash
# Install dependencies
<command>

# Run dev server
<command>

# Run tests
<command>

# Lint/format
<command>

# Build for production
<command>
```

## Coding Standards

### Language/Style Guidelines:
- <Language version>
- <Style guide link or inline rules>
- <Formatter config>

### Error Handling Conventions:
- <How to handle errors>
- <Logging requirements>
- <Error message format>

### Testing Expectations:
- **Unit tests**: <What must be tested; frameworks used>
- **Integration tests**: <Scope and requirements>
- **E2E tests**: <Critical paths to cover>
- **Minimum coverage**: <Percentage or specific areas>

## Architecture Notes

### Key Modules and Responsibilities:
- `<module_name>`: <What it does, key interfaces>

### Data Flow:
<High-level description of how data moves through system>

### Important Invariants:
- <System constraints that must never be violated>

### Security/Privacy Considerations:
- <Authentication/authorization approach>
- <Data handling requirements>
- <Secrets management>

## Safety & Guardrails

### NEVER:
- Commit secrets, tokens, or passwords
- Force destructive operations without confirmation
- Modify production database directly
- <Project-specific dangerous operations>

### ALWAYS:
- Add or update tests for new behavior
- Keep changes small and well-factored
- Follow the Boy Scout Rule (leave code better than you found it)
- Update documentation when changing interfaces

## When in Doubt

- Ask clarifying questions about ambiguous requirements
- Propose a short plan before making extensive changes
- Reference specs in `docs/` when available
- Check with team on architectural decisions
- Use CLAUDE.md `#` key for live context updates

## MCP Integration

<If using Model Context Protocol>

**MCP Servers Available**:
- `<server_name>`: <What data/tools it provides>

**How to Use**:
- <Connection details>
- <Common operations>

## Common Workflows

See `docs/workflows/` for:
- Feature development workflow
- Bug fix workflow
- Code review process
- Deployment process
```

---

### Example Mapping Workshop Template

```markdown
# Example Mapping Session

**Date**: <Date>  
**Story**: <Story title/ID>  
**Participants**: <PO, Dev, Tester, + any specialists>

## Story (Yellow Card)

<Write the user story here>

## Rules (Blue Cards)

### Rule 1: <Rule description>

**Examples (Green Cards)**:
- The one where <specific scenario>
- The one where <specific scenario>
- The one where <edge case scenario>

**Questions (Red Cards)**:
- <Open question that needs resolution>

### Rule 2: <Rule description>

**Examples (Green Cards)**:
- <Concrete example>

**Questions (Red Cards)**:
- <Open question>

## Session Outcome

**Story Readiness**:
- [ ] Ready for development (few red cards)
- [ ] Needs splitting (many blue cards)
- [ ] Needs more discovery (many red cards, complex rules)

**Next Steps**:
- <Actions to take before development>

## Gherkin Scenarios (Converted from Green Cards)

```gherkin
Scenario: <Scenario name from green card>
  Given <precondition>
  When <action>
  Then <expected outcome>
```
```

---

### ReAct Agent Prompt Template

```markdown
# ReAct Agent Task

## Role

You are an autonomous agent capable of reasoning and acting to solve complex tasks.

## Available Tools

- **search(query: string)**: Search the web for information
- **get_page(url: string)**: Retrieve content from specific URL
- **calculate(expression: string)**: Perform mathematical calculations
- **<custom_tool>(params)**: <Description of custom tool>

## Task

<Describe the complex task that requires multi-step reasoning and tool use>

## Instructions

Use the ReAct (Reasoning + Acting) pattern to solve this task:

1. **Thought**: Reason about what you need to do next
2. **Action**: Invoke a tool with specific parameters
3. **Observation**: Observe the result from the tool
4. Repeat Thought → Action → Observation until you have enough information
5. **Answer**: Provide final answer based on your observations

## Format

Use this exact format for each step:

```
Thought: <Your reasoning about what to do next>
Action: <tool_name>(<parameters>)
Observation: <Result from the tool will be inserted here>
[Repeat as needed]
Thought: I now have enough information to answer
Answer: <Final answer>
```

## Example

**Task**: What is the population of the capital city of France?

```
Thought: I need to find out what the capital of France is first.
Action: search("capital of France")
Observation: The capital of France is Paris.

Thought: Now I need to find the current population of Paris.
Action: search("population of Paris 2026")
Observation: As of 2026, the population of Paris is approximately 2.2 million in the city proper.

Thought: I now have enough information to answer the question.
Answer: The population of Paris, the capital city of France, is approximately 2.2 million people as of 2026.
```

## Success Criteria

- [ ] Reasoning traces are clear and logical
- [ ] Actions are appropriate for gathering needed information
- [ ] All tool invocations include proper parameters
- [ ] Final answer is based on observations, not assumptions
- [ ] Process is traceable and reproducible
```

---

## Authoritative Source Index

### Engineering Stories - Foundational Sources

**INVEST & User Stories:**
- Agile Alliance: [INVEST criteria](https://agilealliance.org/glossary/invest/), [Story splitting](https://agilealliance.org/glossary/story-splitting/), [Three C's](https://agilealliance.org/glossary/three-cs/)
- Mike Cohn / Mountain Goat Software: [User Stories](https://www.mountaingoatsoftware.com/agile/user-stories), [Planning Poker](https://www.mountaingoatsoftware.com/agile/planning-poker)
- Ron Jeffries: Creator of 3 C's and INVEST (referenced across multiple sources)

**BDD & Gherkin:**
- Dan North: Introduced BDD and Gherkin (2007)
- Cucumber.io: [Example Mapping](https://cucumber.io/docs/bdd/example-mapping)
- BrowserStack, Qase, VirtuosoQA: BDD implementation guides

**Product Management:**
- Roman Pichler: [DEEP framework](https://www.romanpichler.com/blog/make-the-product-backlog-deep/), backlog management
- Jeff Patton: [Story Mapping](https://www.jpattonassociates.com/wp-content/uploads/2015/03/story_mapping.pdf)

**Agile Practices:**
- Atlassian: [Definition of Done](https://www.atlassian.com/agile/project-management/definition-of-done), [Technical Debt](https://www.atlassian.com/agile/software-development/technical-debt)
- Scrum.org: [DoD techniques](https://www.scrum.org/resources/blog/techniques-using-definition-done-dod)

### AI Agents - Recent Authoritative Sources (2024-2026)

**Anthropic Official (High Authority):**
- [Building Effective AI Agents](https://www.anthropic.com/research/building-effective-agents) (Dec 2024)
- [Claude Code Best Practices](https://www.anthropic.com/engineering/claude-code-best-practices) (Apr 2025)
- [Effective Context Engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents) (Sep 2025)
- [Model Context Protocol](https://www.anthropic.com/news/model-context-protocol) (Nov 2024)
- [Claude Opus 4.5 Announcement](https://www.anthropic.com/news/claude-opus-4-5) (Nov 2025)
- [Extended Thinking Tips](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/extended-thinking-tips) (Dec 2025)
- [Claude 4 Best Practices](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-4-best-practices) (Sep 2025)

**GitHub/Microsoft Official:**
- [GitHub Copilot Best Practices](https://docs.github.com/copilot/how-tos/agents/copilot-coding-agent/best-practices-for-using-copilot-to-work-on-tasks) (Dec 2024)
- [WRAP Method](https://github.blog/ai-and-ml/github-copilot/wrap-up-your-backlog-with-github-copilot-coding-agent/) (Dec 2025)
- [Custom Instructions Tips](https://github.blog/ai-and-ml/github-copilot/5-tips-for-writing-better-custom-instructions-for-copilot/) (Sep 2025)

**Google Cloud:**
- [Choose Design Pattern for Agentic AI](https://docs.cloud.google.com/architecture/choose-design-pattern-agentic-ai-system) (Oct 2025)

**Academic & Research:**
- [Empirical Study of Context Files](https://arxiv.org/html/2511.12884v1) (arXiv, Sep 2025)
- [Improving Function Calling](https://aclanthology.org/2025.emnlp-main.1242.pdf) (EMNLP 2025, Nov 2025)
- [ReAct for Task-Oriented Dialogue](https://aclanthology.org/2025.iwsds-1.12.pdf) (ACL 2025, May 2025)
- [Solving Million-Step Tasks](https://arxiv.org/html/2511.09030v1) (arXiv, Sep 2025)

**Industry Practitioners:**
- Martin Fowler: [Function Calling](https://martinfowler.com/articles/function-call-LLM.html) (May 2025)
- LangChain: [State of Agent Engineering](https://www.langchain.com/state-of-agent-engineering) (Jan 2026)
- McKinsey: [The Agentic Organization](https://www.mckinsey.com/capabilities/people-and-organizational-performance/our-insights/the-agentic-organization-contours-of-th) (Sep 2025)

**Model Context Protocol:**
- [MCP One Year Anniversary](http://blog.modelcontextprotocol.io/posts/2025-11-25-first-mcp-anniversary/) (Nov 2025)
- [What is MCP](https://modelcontextprotocol.io) (Maintained)
- Wikipedia: [Model Context Protocol](https://en.wikipedia.org/wiki/Model_Context_Protocol) (Updated Dec 2025)

**Observability & Production:**
- N-iX: [AI Agent Observability Framework](https://www.n-ix.com/ai-agent-observability/) (Dec 2025)
- Maxim AI: [5 Best Debugging Platforms](https://www.getmaxim.ai/articles/the-5-best-agent-debugging-platforms-in-2026/) (Dec 2025)
- O-mega: [Top 5 Observability Platforms](https://o-mega.ai/articles/top-5-ai-agent-observability-platforms-the-ultimate-2026-guide) (Dec 2025)

---

## Conclusion & Recommended Practices

Across **traditional engineering stories** and **AI agent tasks**, the most robust practices converge on core ideas:

### Universal Principles

**Small, Atomic Units of Work**
- INVEST's "Small" and WRAP's "Atomic" are the same idea for humans and agents
- Vertical slices deliver complete value incrementally
- Enable faster feedback and easier debugging

**Explicit, Testable Outcomes**
- Acceptance criteria and success metrics directly observable
- Given/When/Then format works for both human stories and agent specifications
- Definition of Done creates shared understanding

**Clear, Structured Documentation**
- Story templates provide consistency for human teams
- CLAUDE.md/AGENTS.md give agents stable reference
- Spec-driven docs bridge human and AI layers

**Progressive Disclosure**
- Keep global context files lean (CLAUDE.md <300 lines)
- Delegate detail to feature/skill-specific docs
- Maximize signal in each context window

**Iterative Refinement**
- Backlogs, context files, prompts all evolve
- Small, frequent updates more effective than big overhauls
- Learn from agent execution traces and team retrospectives

### 2026-Specific Best Practices

**For Engineering Stories:**

1. **Use Three Amigos** meetings with Example Mapping technique
2. **Apply BDD/Gherkin** for acceptance criteria (Given/When/Then)
3. **Prioritize vertical slicing** over horizontal decomposition
4. **Maintain clear DoD** collaboratively defined and visible
5. **Estimate with Planning Poker** to build consensus
6. **Map stories to user journeys** for context and flow

**For AI Agents:**

1. **Adopt MCP** for standardized tool/data integration
2. **Implement ReAct pattern** for complex multi-step tasks
3. **Use Extended Thinking** mode for reasoning-heavy problems
4. **Structure function calling** with template-based reasoning
5. **Build observability** from day one (distributed tracing, session tracking)
6. **Design memory systems** with read-write capability for adaptive behavior
7. **Choose appropriate multi-agent patterns** based on task complexity

### Joined-Up Specification System

Using these patterns, you can design a system where:

- **Product managers** write DEEP, INVEST-compliant stories with clear acceptance criteria
- **Engineers and agents** share consistent spec and context files
- **AI coding agents** like Claude Code Opus 4.5 operate with well-scoped, tightly formatted prompts
- **Observability** provides continuous feedback loop for both human and agent performance
- **Memory systems** enable agents to learn and adapt over time
- **MCP** standardizes integration across tools and data sources

This comprehensive knowledge base synthesizes best practices from:
- 25+ years of Agile methodology (INVEST, 3 C's, BDD)
- Latest AI research through January 2026
- Production-tested patterns from industry leaders
- Open standards (MCP, Gherkin) with broad adoption

The result: **Reliable, maintainable, and continuously improving** systems for both human teams and AI agents.
