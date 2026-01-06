# How I Start Every Claude Code Project (PSB System)

## Intro: The Mistake to Avoid

I used to start my Claude Code projects completely wrong. I would type `claude` into my terminal and start freestyle prompting with no planning, no setup, and no system for building. It was like trying to build a house without blueprints. I eventually got something built, but it was messy, inefficient, and full of avoidable problems.

After building dozens of Claude Code projects over the past year, I’ve discovered a simple three‑part system that makes every project **10x** easier from day one. In this video, I’ll share the exact system I use to start every new Claude Code project. I call it the **PSB system**:

- **P**lan  
- **S**etup  
- **B**uild  

This system will save you months of frustration and wasted time, even if you only adopt a handful of the tips.

---

## Overview of the PSB System

1. **Phase 1: Plan**  
   - Set up your project for success *before* writing a single line of code.  
   - Answer two critical questions.  
   - Create a project spec doc that combines both product requirements and engineering design so Claude can build what you want, the way you want it.

2. **Phase 2: Setup**  
   - Configure Claude Code with everything it needs to build effectively.  
   - Follow a seven‑step setup checklist (GitHub repo, `claude.md`, env vars, plugins, MCPs, custom commands, etc.).

3. **Phase 3: Build**  
   - Start writing code by having Claude build your MVP and then subsequent milestones.  
   - Use three core development workflows (general, issue‑based, multi‑agent).  
   - Apply key productivity tips to keep the build process efficient.

Whether this is your first Claude Code project or you use Claude Code daily, you’ll find techniques that help you build faster and smarter.

---

## Phase 1: Plan

Planning feels boring when you just want to code, but investing even 15 minutes up front will save hours or days later. Before you open Claude Code:

- Do a quick **brainstorm** of what you want to achieve.  
- Capture notes using pen and paper or a simple Google Doc / markdown file.

### Two Questions to Ask Before Starting

**1. What are you actually trying to do? (Project Goal)**

Clarify the primary goal of your project. For example:

- Are you trying to learn a new technology?
- Are you validating an idea with customers?
- Are you building an alpha version of a product or feature?
- Are you prototyping to see if something is even possible?

This clarity changes everything about how you approach the project:

- It tells you what is important to build vs. what you can skip.
- It sets the bar for quality, polish, and robustness.

**Example:**

- If you’re **just prototyping** to see if a feature is a good idea:
  - Focus on core functionality only.
  - Ignore production‑ready code, edge cases, and heavy robustness.
  - Move fast and break things.

- If you’re **shipping to real users**:
  - Consider security, error handling, edge cases.
  - Add all the details that make the product feel polished.

The clearer you are, the better Claude will understand what you’re trying to achieve and build accordingly.

---

**2. What are the milestones of functionality you want?**

Break the project into **clear phases** or versions:

- What does **Version 1** look like?
  - Maybe it focuses on one core feature.
- What are you okay with **leaving out** or saving for Version 2 / 3?

A common pattern:

- **MVP (Minimum Viable Product)**  
  - The absolute minimum needed to validate the idea or prove the concept.

- **Version 2, Version 3**  
  - Add scaffolding, polish, optimizations, secondary features.

Define what **“done”** looks like for each milestone so you have a clear target.

---

### Using AI to Help You Plan

Once you have a rough brainstorm, let AI help you refine it.

**Pro tip:** Tell the AI to **ask you questions**.

Example workflow:

1. Put your brainstorm into a markdown file.
2. Paste it into Claude and say something like:

   > “Hey Claude, I want to build this project. What are the three most important questions I need to answer to successfully build an MVP of this?”

3. Let Claude ask you clarifying questions:
   - This reveals missing decisions and gaps in your thinking.
   - Answering them gives you much more clarity about what you’re actually trying to build.

You can repeat this “AI asks you questions” pattern for:

- Product requirements
- Technical tool / stack choices
- Debugging tricky issues

---

### Voice‑Mode Planning

Another tool: **voice conversation** with an AI assistant (Claude, ChatGPT, etc.).

Workflow:

- Talk through your project idea out loud:
  - Describe the different features.
  - Walk through user flows.
- Then ask the assistant to:
  - Summarize the conversation.
  - Output it as a markdown file.

This markdown file becomes a great starting point for Claude Code. Voice is especially helpful when:

- Your ideas are still fuzzy.
- It’s hard to write things down because you don’t yet know exactly what you think.

---

## Project Spec Doc

The main deliverable of the planning phase is your **project spec doc**.

This document has two main parts:

1. **Product requirements**  
2. **Technical requirements (engineering design)**

It should contain just enough product and engineering detail to let Claude Code build your project successfully. How detailed it needs to be depends on your project goal and milestones.

If you’ve worked in software companies, this is like a lightweight combination of:

- PRD (Product Requirements Document)  
- EDD (Engineering Design Document)

…tailored for building with Claude Code.

---

### Part 1: Product Requirements

Product requirements answer:

1. Who is the product for?
2. What problems does it solve?
3. What should the product do?

This is where you apply your creativity, insight, and product sense.

**Key guidance:**

- Think concretely about *who* you’re building for and *what problems* you’re solving.
- Spend time outlining exactly **how** those problems are solved from the **user’s perspective**.

If you’re not specific about user interactions, Claude will make assumptions you may not like.

**Example: journaling app**

Instead of writing:

> “Users can create journal entries.”

Be specific:

- Do users start with a **blank page** or **prompts**?
- Can they **add photos**?
- Can they **edit past entries**?
- What does the **workflow** look like from start to finish?

The more specific you are about the user experience, the better Claude can implement it.

**Milestones for capabilities:**

- Don’t try to build everything at once.
- Break capabilities into milestones.
- Use the milestone question from earlier:
  - What’s most important to build **first**?
  - What does **done** look like for each milestone?

**Iterate your product requirements:**

- If you’re not sure what you want, that’s fine.
- Build **Version 1** first.
- Based on what you like / dislike:
  - Adjust the plan.
  - Write new requirements for Version 2.

---

### Part 2: Technical Requirements (Engineering Design)

While product requirements describe **what** you’re building, the engineering design describes **how** you’re building it.

#### Choose Your Tech Stack

This is the first and most important part of the technical requirements.

You need to decide:

- Programming language  
- Frontend framework  
- Backend framework  
- Database  
- Hosting / infra provider  
- Auth & login solution  
- Payments provider  
- Email provider  
- Object storage  
- AI models and image generation tools  

If you **don’t** specify your stack, Claude may pick random technologies you don’t want. Instead, be explicit.

**Example preferred stack (for web apps):**

- **Frontend / Hosting**
  - Vercel (hosting)
  - Next.js (framework)
  - Tailwind CSS (styling)
  - shadcn/ui (components)

- **Backend / Database**
  - MongoDB or Supabase (depending on project)

- **Auth**
  - Clerk

- **Payments**
  - Stripe

- **Email**
  - Resend

- **Backend hosting (if needed)**
  - DigitalOcean

- **Object storage**
  - Cloudflare R2

- **AI**
  - Anthropic models (for AI features)
  - Google Gemini “nano banana” (for images)

You don’t have to use this exact stack—use what you prefer. The important thing is to clearly tell Claude what to use.

#### If You’re Unsure About the Stack

If you’re not sure what tech or components you need:

- Describe your project requirements to Claude.
- Ask Claude Code to:
  - Create a **research report**.
  - Compare options.
  - Recommend choices for your use case.

Claude Code can use web search to pull in the latest docs, tools, and frameworks and give you informed recommendations.

---

#### Define Technical Architecture

The second part of your technical requirements is your **technical architecture**. This can include:

- System design overview  
- Key app components and how they interact  
- Database schema  
- API design (if any)  
- Other technical details that matter (queues, cron jobs, etc.)

You can delegate much of this to Claude, but:

- If you’re working on a team, you may want to be more prescriptive.
- Document any **company patterns** or **best practices** Claude should follow.

**Infrastructure provisioning:**

Once you decide on the infra:

- Create your databases.
- Set up hosting.
- Generate and store API keys.
- Make sure Claude can access everything it needs when it starts building.

At the end of the planning phase, you should have:

- Clear goals and milestones.  
- Product requirements.  
- Technical requirements.  
- A project spec doc ready for Claude Code.

---

## Phase 2: Setup

Phase 2 is the **Setup** phase. This is where you configure Claude Code to feel like a perfectly tuned instrument with:

- The right shortcuts  
- Helpful automations  
- Sufficient context  

You do *not* need to use every recommendation—pick what’s relevant— but there is a seven‑step checklist that works great as a baseline.

### Step 1: Set Up a GitHub Repo

You can build locally with Git, but setting up a **GitHub repo from the start** is strongly recommended.

Why:

1. You can use Claude Code on the **web and mobile**, coding from anywhere.
2. You get access to:
   - GitHub CLI  
   - Claude Code GitHub Action (for automated PR reviews, commenting on issues, etc.).
3. Many infra providers (like Vercel) let you:
   - Deploy by just connecting a GitHub repo.
   - Use **deploy previews** per branch.
4. GitHub enables **issue‑based development**:
   - Issues become the source of truth for bugs and feature requests.
   - Multiple Claude Code instances can tackle issues concurrently.

A good pattern:

- Ask Claude Code to use a **new branch** for each big feature.
- When done, merge via PR into `main` (or whatever your primary branch is).

---

### Step 2: Create Your Env File

Set up your environment variables early.

Workflow:

1. Ask Claude to create an example `.env` file based on:
   - Your project spec
   - Your tech stack

2. Create a copy (e.g., `.env.local`) and fill in:
   - Credentials
   - API keys
   - Secrets

This lets Claude build without constantly stopping to ask you for missing env vars.

---

### Step 3: Create `claude.md`

Think of `claude.md` as your project’s **long‑term memory**.

- It is always included in context for every Claude Code chat.
- Its space is **finite**, so don’t bloat it.

**Goal:** Keep `claude.md` focused on the most important information Claude must always know.

Recommended contents:

- Project goals  
- Architecture overview  
- Folder layout / high‑level structure  
- Design style guide and UX guidelines  
- Constraints and policies, e.g.:
  - Never push directly to `main`
  - Always use env vars for secrets
- Repository etiquette:
  - When to use PRs vs direct merges
  - How to name branches
  - Git workflow conventions
- Frequently used commands:
  - Build commands
  - Test commands
  - Useful dev scripts
- Testing instructions and other rules you want enforced.

**Keep `claude.md` concise:**

- Link out to other files instead of duplicating content.
  - Example: link to your project spec, `architecture.md`, feature docs.
- Tell Claude in `claude.md` where it can find additional context.

Don’t worry about making `claude.md` perfect at the start—you’ll refine it as you go.

---

### Step 4: Automated Project Documentation

Automated documentation = a set of docs **separate** from `claude.md` that track project context and history, which Claude can read when needed.

These are the docs you **link from** `claude.md`.

You ask Claude to keep these docs updated as it works so they are always current.

Core docs to create:

1. `architecture.md`  
   - Documents system design, app structure, major components.
   - Update after adding **big features**.

2. `changelog.md`  
   - List of what changed over time.
   - Similar to public changelogs companies publish with releases.

3. **Project status doc** (e.g., `status.md`)  
   - Project milestones.
   - What you have accomplished so far.
   - Where you left off last time.

   Helpful if:
   - You work in bursts.
   - You sometimes don’t touch a project for days or weeks.

4. **Reference docs for key features**  
   - Optional but useful.
   - Provide a high‑level overview of specific features.
   - Examples:
     - For an iOS app: onboarding, push notifications.
     - For a web app: payments flow, time zone handling, email reminders.

**Keeping docs updated:**

- Ask Claude to automatically update these docs as it works:
  - Instruct this via `claude.md`.
  - Or create a custom slash command that updates docs after each feature.

---

### Step 5: Install Plugins

Plugins extend Claude Code with specialized commands and workflows. A plugin may include:

- Slash commands  
- Subagents  
- MCP servers  
- Hooks  
- Skills  

They let you import powerful customizations from other users instead of re‑creating everything from scratch.

You can:

- Discover plugins via plugin marketplaces.
- Manage them with `/plugins` in Claude Code.

**Recommended starter plugins:**

- **Anthropic Frontend plugin**
  - Specialized skills for frontend development.
  - Helps get better UI and avoid generic “AI‑ish” styling.

- **Anthropic Feature Dev plugin**
  - Streamlines feature development workflows.

- **Every Compound Engineering plugin**
  - Provides a suite of slash commands and subagents.
  - Aims to make each new feature easier to develop than the last.

---

### Step 6: Install MCP Servers

**MCP (Model Context Protocol) servers** connect Claude Code to external tools and services.

They let Claude:

- Interact with your database.
- Test your frontend.
- Deploy to hosting.
- Integrate with analytics and project management tools.

Which MCPs to use depends on your tech stack:

- **Database MCP**
  - Use one for your chosen DB (e.g., MongoDB, Supabase).
  - Useful for rapidly iterating and letting Claude update the schema automatically.

- **Web app testing**
  - Playwright MCP or Puppeteer MCP.
  - Lets Claude “see” your web app and:
    - Run automated UI tests.
    - Validate user flows.

- **Other suggested MCPs** (from the example stack)
  - Vercel MCP (deployment)
  - Mixpanel MCP (analytics)
  - Linear MCP (project management)

To connect an MCP, follow the server’s docs; usually there’s a one‑liner install and some basic configuration in Claude Code.

---

### Step 7: Slash Commands and Subagents

Slash commands and subagents let Claude **automate** tasks and workflows, but they behave differently.

**Slash commands:**

- Shortcuts to prompts or tasks.
- Use the **same context window** as the main conversation.

**Subagents:**

- Specialized agents for a particular task.
- Use a **forked** context window:
  - They do not share context with the main conversation or each other.
  - Perfect for focused, parallel work.

You can:

- Use built‑in slash commands and subagents that ship with Claude Code.
- Use third‑party ones from plugins.
- Create your own custom ones.

**Subagent ideas:**

- **Changelog subagent**
  - Creates and updates `changelog.md` entries after a feature is finished.

- **Frontend testing subagent**
  - Focused on testing your frontend.
  - Runs Playwright tests automatically.

- **Retro agent**
  - Reflects after a dev session:
    - What went well
    - What can be improved
  - Updates:
    - `claude.md`
    - Prompts
    - Slash commands
  - Forms the basis of a continuous improvement system.

**Slash command ideas:**

- Use commands from plugins like:
  - `/commit`
  - `/pr`
  - Feature‑dev commands

- Create custom commands:
  - One that updates all project docs (architecture, status, changelog) based on recent changes.
  - One that creates GitHub issues from:
    - A project spec
    - A prompt
    - A file / folder

These commands and subagents tie together automated documentation, plugins, and MCPs into a cohesive workflow.

---

### Advanced Setup: Permissions and Hooks

Two advanced configuration techniques for power users:

#### Bonus 1: Preconfigure Permissions and Settings

Pre‑approving or blocking certain commands means:

- Claude Code doesn’t have to ask you every time it needs to do something common.
- You avoid situations where:
  - You think Claude is working.
  - But it’s actually stuck waiting on a permission prompt.

Examples:

- Always allow Claude to:
  - Run Git commands.
  - Edit files in the repo.
- Explicitly block:
  - Pushing to `main`.
  - Running certain destructive or unsafe commands.

#### Bonus 2: Hooks for Advanced Automation

Hooks let you insert **determinism** into the workflow:

- They are scripts that run automatically at specific points in the Claude Code lifecycle.
- For example:
  - Before a tool call
  - After Claude finishes a task

**Example hooks:**

- **Test gate hook**
  - After Claude finishes a task:
    - Run tests.
    - If tests fail:
      - Instruct Claude to keep going and fix them.
- **Notification hook**
  - Send you a Slack message when:
    - Claude needs permission.
    - Something important happens.

Hooks are advanced but extremely powerful—even one well‑designed hook can dramatically improve your workflow.

At this point, after Phase 2, Claude has everything it needs to start building.

---

## Phase 3: Build

Phase 3 is the **Build** phase—the part where you actually start writing code with Claude.

Just like planning and setup, having the right workflows here is the difference between:

- Frustration and chaos vs.  
- Smooth, productive development.

We’ll cover:

- Building your MVP.
- Three go‑to workflows:
  - General single‑feature development
  - Issue‑based development
  - Multi‑agent development
- Four key productivity tips.

---

### Building Your MVP with Claude

Once your **project spec** and **milestones** are defined:

1. Ask Claude to build **Milestone 1 (your MVP)** based on the spec.
2. Encourage Claude to use **parallel subagents** when appropriate, so it can:
   - Work on multiple parts of the project at once.
3. Use **plan mode** first:
   - Claude will translate the spec into an implementation plan.
   - It will break work into steps and ask clarifying questions.

After building your MVP, you can iteratively build out later milestones using structured workflows.

---

## Three Core Development Workflows

### Workflow 1: General Single‑Feature Development

Use this workflow when building a single feature end to end.

Steps:

1. **Research** (optional)
   - Ask Claude to create a research report for:
     - New tools
     - APIs you haven’t used before
     - Tradeoffs between options
   - You can also bring in external research.

2. **Plan**
   - Use **plan mode** heavily.
   - Claude:
     - Thinks through the task.
     - Breaks it into steps.
     - Asks clarifying questions.
   - This step is often where most people under‑invest.

3. **Implement**
   - Let Claude:
     - Write code.
     - Use plugins, MCPs, subagents, slash commands from earlier setup.
   - Example: use the **feature dev slash command** from the Anthropic plugin.

4. **Test**
   - Run tests (possibly automated via hooks or subagents).
   - Iterate until the feature meets the acceptance criteria you defined.

---

### Workflow 2: Issue‑Based Development

Here, **GitHub issues** become your main source of truth.

Instead of only prompting Claude directly, you:

- Create GitHub issues describing:
  - Bugs
  - Improvements
  - New features
- Ask Claude Code to work on those issues.

Why this helps:

- Keeps the project tidy:
  - GitHub issues act as your structured backlog.
  - You avoid scattered TODO files and random notes.
- Encourages discipline:
  - You split work into clear, scoped tasks.

**Automation opportunities:**

- Ask Claude to take your project spec + milestones and:
  - Turn them into a set of GitHub issues.
- Use custom slash commands or subagents to:
  - Generate issues from a file or folder.
  - Sync issues from prompts.

**Parallelism:**

- Issue‑based workflow makes parallel work easier:
  - Multiple subagents can handle different issues.
  - Multiple Claude Code instances can work issue‑by‑issue in parallel.

---

### Workflow 3: Multi‑Agent Development (Multi‑Clauding)

The most advanced workflow: **multi‑agent development**, also known as **multi‑clauding**.

Idea:

- Run **multiple Claude Code instances at the same time**, each:
  - Working on a different feature.
  - Using its own dedicated workspace.

Key enabler: **Git worktrees**

- Git worktrees let you:
  - Have multiple working copies of your repo in different directories.
  - Each on a separate branch.
  - All sharing the same Git history.

Pattern:

1. Create a worktree and branch for each major feature.
2. Point a separate Claude Code session at each worktree.
3. Each session works in isolation on its own branch.
4. When finished:
   - Ask Claude to merge the worktrees back together.
   - Either into:
     - `main`
     - Or an integration / feature branch for further testing.

This workflow lets you work on 2–3 features (or more) concurrently, but it does require:

- Comfort with Git worktrees.
- Clear branching and merge discipline.

---

## Tips for Building Productively

To close out the Build phase, here are four tips to keep your Claude Code development **productive and efficient**.

### Tip 1: Use the Best Models Where It Matters

Use the strongest models as much as possible, especially when:

- Planning
- Doing complex reasoning
- Designing architecture

Example usage pattern:

- **Opus 4.5**
  - Default for planning, complex tasks, and hard problems.
- **Sonnet**
  - Workhorse for implementation and everyday coding.
- **Haiku**
  - For simple, straightforward tasks and small bug fixes.

Rationale:

- The time saved by fewer mistakes and better decisions often outweighs:
  - The cost savings from cheaper models that produce more errors.

### Tip 2: Periodically Update `claude.md`

Even though `claude.md` was set up in Phase 2, you should:

- Periodically update it as:
  - New features are added.
  - New patterns emerge.
  - Conventions evolve.

**Pro tip:**

- Create a custom slash command that:
  1. Updates `claude.md` with current rules / patterns.
  2. Creates a Git commit as part of your normal Git workflow.

This keeps **documentation and code in sync**.

---

### Tip 3: Practice Regression Prevention

When Claude makes a mistake:

- Don’t just silently fix it and move on.
- Capture the *lesson* so it doesn’t happen again.

One pattern:

- Use a special marker (e.g., a hash / comment) to give Claude instructions like:
  - “In this project, always do X, never do Y in this situation.”
- Claude can then:
  - Automatically incorporate that instruction into `claude.md`.

This lets you update project rules **on the fly** without manually editing the file every time.

---

### Tip 4: Don’t Be Afraid to Throw Away Work

Remember: **code is cheap**.

If something isn’t working—especially in the prototype stage:

- Don’t be afraid to:
  - Undo it.
  - Delete the feature.
  - Start again from a cleaner design.

Use:

- Claude Code **checkpoints** and **rewind** for session‑level recovery.
- Git for project‑level version control.

Throwing away bad or overly complicated code often helps you reach a solution you’re actually happy with faster.

---

## Closing / Applying the System

The PSB system—**Plan, Setup, Build**—gives you a repeatable way to start Claude Code projects without the usual chaos of freestyle prompting.

If you want to go deeper and get hands‑on help:

- There’s an **AI‑native builder course** on Maven with cohorts running in January and February.
- Viewers get a **$100 discount** using the code `YOUTUBE` at checkout or via the link in the video description.
- The course focuses on:
  - Building projects from scratch with tools like Claude Code and Replit.
  - Learning fundamentals of AI‑assisted development that apply across tools.
  - Getting personalized help via Q&A and office hours.

If this system helps you:

- Like and subscribe for more AI coding videos.
- Leave a comment with what you learned or any questions you have—the creator reads every single one.

Catch you in the next one.
