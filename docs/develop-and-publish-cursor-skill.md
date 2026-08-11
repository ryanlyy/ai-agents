# Step-by-Step: Develop and Publish a Cursor Skill

A "skill" in Cursor is a markdown file (`SKILL.md`) that teaches the agent how to perform a specific workflow. Here is the full lifecycle, from idea to shareable artifact.

---

## Step 1 — Define the Skill

Answer these four questions before you write anything:

| Question | Example |
|---|---|
| **What** does it do? | "Generate Conventional Commits messages from a git diff" |
| **When** should the agent use it? | "Whenever the user asks for a commit message or stages files" |
| **Who** is it for? | Just me / my team / the public |
| **What format** is the output? | Specific template, freeform text, JSON, etc. |

If you can't answer all four in one sentence, your skill scope is too vague.

---

## Step 2 — Pick a Storage Location

| Scope | Path (Windows) | Use when |
|---|---|---|
| **Personal** | `C:\Users\<you>\.cursor\skills\<skill-name>\` | Only you need it, across all projects |
| **Project** | `<repo>\.cursor\skills\<skill-name>\` | Should ship with the repo for the whole team |

Do **not** put skills in `~/.cursor/skills-cursor/` — that folder is reserved for Cursor's built-in skills.

---

## Step 3 — Create the Directory

A skill is a folder, not a single file. Minimum layout:

```text
commit-helper/
└── SKILL.md
```

Optional supporting files (used via "progressive disclosure"):

```text
commit-helper/
├── SKILL.md          # Always loaded — keep under 500 lines
├── reference.md      # Loaded on demand
├── examples.md       # Loaded on demand
└── scripts/
    └── analyze_diff.py
```

---

## Step 4 — Write `SKILL.md`

Every skill needs YAML frontmatter + a markdown body.

````markdown
---
name: commit-helper
description: Generates Conventional Commits messages by analyzing staged git diffs. Use when the user asks for a commit message, says "write a commit", or has staged changes ready to commit.
---

# Commit Helper

## Instructions
1. Run `git diff --staged` to inspect changes.
2. Classify the change: feat, fix, docs, refactor, test, chore.
3. Produce one subject line (<=72 chars) + optional body.

## Output template
```
<type>(<scope>): <imperative summary>

<why the change was made, not what>
```

## Example
Input: Added JWT login endpoint and middleware
Output:
```
feat(auth): implement JWT-based authentication

Add login endpoint and token validation middleware
```
````

### Frontmatter rules
- `name`: lowercase letters/numbers/hyphens only, max 64 chars.
- `description`: max 1024 chars, **third person**, must include *what* AND *when* (trigger words matter — that's how the agent decides to load it).
- Add `disable-model-invocation: true` if the skill should only load when the user names it explicitly.

---

## Step 5 — Understand `reference.md` (and other supporting files)

### What is `reference.md`?

`reference.md` is an **optional companion file** that lives next to `SKILL.md` inside the skill folder. It exists because Cursor follows a pattern called **progressive disclosure**:

- `SKILL.md` is **always loaded** into the agent's context the moment the skill is invoked. Every token in it costs context window space shared with the user's conversation, other skills, and tool outputs.
- `reference.md` is **only loaded when the agent decides it needs it** (typically when `SKILL.md` links to it with text like *"For full API details, see [reference.md](reference.md)"*).

This lets you keep `SKILL.md` short and decision-focused, while still making deep detail available on demand.

### What goes inside `reference.md`?

Anything the agent needs *sometimes* but not *every time*:

| Put in `SKILL.md` (always loaded) | Put in `reference.md` (loaded on demand) |
|---|---|
| Trigger conditions / when to use | Full API parameter tables |
| Step-by-step workflow | Edge-case handling matrices |
| Output template / format | Long error-code lookups |
| One or two short examples | Exhaustive example library |
| Names of helper scripts | Library version notes, deprecated patterns |

### How to reference it from `SKILL.md`

```markdown
## Additional resources
- For complete API parameters, see [reference.md](reference.md)
- For more usage examples, see [examples.md](examples.md)
```

**Rule:** keep references **one level deep**. Linking from `SKILL.md` → `reference.md` is fine. Linking `SKILL.md` → `reference.md` → `deep/nested/notes.md` can result in partial reads and is discouraged.

### Sibling files you may also see

| File | Purpose |
|---|---|
| `reference.md` | Detailed API / option / spec documentation |
| `examples.md` | Larger gallery of input → output examples |
| `STANDARDS.md` | Team coding standards or style rules referenced by the skill |
| `scripts/` | Executable helper scripts (see Step 6) |

You don't need every one of these — add a file only when its content would bloat `SKILL.md` past ~500 lines or hurt the agent's focus.

---

## Step 6 — Add Optional Scripts (and why scripts matter)

### What "scripts" means here

A `scripts/` folder inside the skill holds **pre-written executable helpers** (Python, Bash, PowerShell, Node, etc.) that the agent can run instead of writing equivalent code on the fly.

```text
commit-helper/
└── scripts/
    └── analyze_diff.py
```

### Purpose / why use scripts instead of generated code

| Benefit | Explanation |
|---|---|
| **Reliability** | A tested script behaves the same every run. LLM-generated code can drift in subtle ways each time. |
| **Token savings** | The script body never enters the context window — only the command line and its output do. For a 200-line helper, that's a huge win. |
| **Speed** | No code-generation step; the agent just executes. Less latency, fewer round-trips. |
| **Consistency across users** | Every teammate runs the *same* logic — important for things like linting, validation, or report formatting. |
| **Determinism for fragile ops** | Database migrations, file rewrites, regex replacements: places where "mostly right" causes real damage. A script removes the LLM from the dangerous part of the loop. |
| **Feedback loops** | Validation scripts (e.g. `python scripts/validate.py output/`) let the agent self-check its work and retry until it passes. |
| **Encapsulates expert knowledge** | A single `analyze_form.py` can hide hundreds of lines of brittle PDF-parsing logic the agent would otherwise have to re-derive. |

### Rule of thumb

> If the task is **fragile, repetitive, or quality-critical**, write a script.
> If the task needs **judgment, prose, or context-aware decisions**, leave it to instructions.

### How to reference scripts in `SKILL.md`

Always make it clear whether the agent should **execute** the script or just **read** it.

```markdown
## Utility scripts

**analyze_diff.py** — summarize staged changes.
Execute: `python scripts/analyze_diff.py`

**validate_commit.py** — verify the generated message matches Conventional Commits spec.
Execute: `python scripts/validate_commit.py "<message>"`
Returns: "OK" or a list of issues.
```

### Script hygiene

- Document required packages (a `requirements.txt` or a top-of-file comment).
- Use forward-slash paths (`scripts/helper.py`) — never `scripts\helper.py`.
- Give explicit, actionable error messages — the agent will read stderr to decide its next move.

---

## Step 7 — Follow the Authoring Principles

- **Concise wins.** Every token competes with the conversation. Assume the agent is smart; only add knowledge it lacks.
- **Stay under 500 lines** in `SKILL.md`. Push detail into `reference.md` and link to it.
- **Match degrees of freedom to fragility:**
  - High freedom (prose) → judgment tasks like code review.
  - Medium (templates) → repeatable outputs like reports.
  - Low (scripts) → fragile ops like migrations.
- **Avoid:** Windows-style paths (`scripts\helper.py`), vague names (`utils`, `helper`), time-sensitive phrasing ("before August 2026"), inconsistent terminology.

---

## Step 8 — Verify

Run through this checklist before declaring it done:

- [ ] `SKILL.md` body under 500 lines
- [ ] Description is third-person and contains trigger keywords
- [ ] Consistent terminology throughout
- [ ] File references are one level deep (no nested `docs/sub/sub/x.md`)
- [ ] No Windows backslash paths
- [ ] At least one concrete example
- [ ] If `reference.md` exists, `SKILL.md` actually links to it
- [ ] If `scripts/` exists, each script is documented with execute vs. read intent

### Live test
1. Open a new Cursor chat in a project where the skill is in scope.
2. Phrase a request matching your description's trigger words.
3. Confirm the agent reads the skill (it will mention loading it) and follows the instructions.
4. Iterate on the description if it isn't being picked up — discovery quality lives entirely in that field.

---

## Step 9 — "Publish" / Share

Cursor has no central marketplace; you distribute a skill the same way you distribute any folder. Pick the channel that matches your audience:

| Audience | How to publish |
|---|---|
| **Just you, on multiple machines** | Keep `~/.cursor/skills/<name>/` in a personal dotfiles repo and symlink/sync it. |
| **A specific project's team** | Commit `.cursor/skills/<name>/` into the project repo. Anyone who clones the repo gets it automatically. |
| **An org across many repos** | Publish a Git repo named e.g. `team-cursor-skills`. Tell members to clone it into `~/.cursor/skills/` (or use a sync script / submodule). |
| **The public** | Push the skill folder to a public GitHub repo. Provide a one-liner install in the README: `git clone <url> ~/.cursor/skills/<name>` |

### Recommended public-repo layout

```text
my-cursor-skills/
├── README.md            # What's in the pack + install instructions
├── commit-helper/
│   ├── SKILL.md
│   ├── reference.md
│   └── scripts/
│       └── analyze_diff.py
└── code-review/
    ├── SKILL.md
    └── STANDARDS.md
```

### Install snippet (Linux/macOS)

```bash
git clone https://github.com/<you>/my-cursor-skills.git ~/cursor-skills-pack
cp -r ~/cursor-skills-pack/commit-helper ~/.cursor/skills/
```

### Install snippet (Windows PowerShell)

```powershell
git clone https://github.com/<you>/my-cursor-skills.git $HOME\cursor-skills-pack
Copy-Item -Recurse $HOME\cursor-skills-pack\commit-helper $HOME\.cursor\skills\
```

---

## Step 10 — How to Actually *Use* a Skill

Once a skill is installed (either in `~/.cursor/skills/<name>/` or `<repo>/.cursor/skills/<name>/`), here's how to put it to work.

### 10.1 Confirm the skill is discoverable

Cursor scans both skill locations on chat startup. Quick sanity check:

```powershell
# Personal skills
ls $HOME\.cursor\skills\

# Project skills (run from repo root)
ls .cursor\skills\
```

Each subfolder must contain a `SKILL.md` with valid frontmatter (`name` + `description`). If frontmatter is malformed, the skill is silently ignored.

> Tip: restart the Cursor chat (or open a new chat) after adding a new skill so the agent rescans the folder.

### 10.2 Two ways to invoke a skill

| Mode | How it triggers | Best for |
|---|---|---|
| **Automatic (model-invoked)** | Agent reads your message, matches it against every skill's `description`, and loads the best fit on its own. | Skills you want to "just work" whenever the topic comes up. |
| **Explicit (user-invoked)** | You name the skill in your prompt, e.g. *"use the commit-helper skill to write a message"*. | Skills with `disable-model-invocation: true`, or when you want to force a specific one. |

### 10.3 Automatic invocation — write prompts that match the description

The agent's only signal for auto-loading is the `description` field. Your prompt should echo its trigger keywords.

Example skill description:
> *"Generates Conventional Commits messages by analyzing staged git diffs. Use when the user asks for a commit message, says 'write a commit', or has staged changes ready to commit."*

Prompts that **will** auto-trigger it:
- "Write a commit message for my staged changes."
- "Give me a Conventional Commits message."
- "I've staged my work — generate a commit message."

Prompts that probably **won't**:
- "Help me with git." (too vague — no trigger keyword)
- "Summarize what I changed." (matches a diff-summary skill, not this one)

### 10.4 Explicit invocation — name the skill

You can always force a specific skill by mentioning its `name` (the value from the frontmatter):

```
Use the commit-helper skill to write a Conventional Commits message for my staged diff.
```

```
Apply the code-review skill to this pull request.
```

This is also the **only** way to load skills that were authored with `disable-model-invocation: true`.

### 10.5 Verify the skill actually loaded

When a skill fires, the agent typically:

1. Mentions it's reading the skill (e.g. *"Reading the commit-helper skill…"*).
2. Calls the Read tool on `SKILL.md`.
3. Follows the workflow defined inside (which may include reading `reference.md` or running a script from `scripts/`).

If none of that happens, the skill didn't trigger — see troubleshooting below.

### 10.6 Combining skills with supporting files and scripts

Once a skill loads, the agent decides on its own whether to:

- **Read `reference.md` / `examples.md`** if `SKILL.md` links to them and the task needs that detail.
- **Execute scripts** in `scripts/` when `SKILL.md` instructs it to (e.g. `python scripts/analyze_diff.py`).

You don't have to ask for these explicitly — a well-written `SKILL.md` will route the agent to the right resource.

### 10.7 Project skills vs personal skills — precedence

Both locations are loaded. If two skills share the same `name`:

- **Project skill** (`.cursor/skills/`) wins over **personal skill** (`~/.cursor/skills/`).

This lets teams override a personal default with a project-specific version (e.g. a team-flavored `commit-helper`).

### 10.8 Disable or temporarily remove a skill

- **Disable auto-invocation, keep available on request:** add `disable-model-invocation: true` to the frontmatter.
- **Disable entirely:** rename the folder (e.g. `commit-helper` → `_commit-helper.disabled`) or move it out of the skills directory.
- **Delete:** just remove the skill folder.

### 10.9 Troubleshooting — "my skill isn't being used"

| Symptom | Likely cause | Fix |
|---|---|---|
| Agent ignores the skill on a matching prompt | `description` is too vague or missing trigger keywords | Rewrite description with explicit *what* + *when* + the exact words users say |
| Skill never appears, even when named explicitly | Folder in wrong path, or YAML frontmatter is broken | Verify path; ensure `---` fences and valid `name`/`description` |
| Skill loads but produces wrong output | Instructions are unclear or output template is missing | Add a concrete example and a strict output template in `SKILL.md` |
| Skill loads but ignores `reference.md` / scripts | `SKILL.md` doesn't link to them or doesn't say to execute | Add explicit links and "Execute: `...`" lines |
| Conflicting behavior between two skills | Two skills with overlapping descriptions | Tighten one description; or set `disable-model-invocation: true` on the less-common one |

### 10.10 End-to-end usage example

Folder on disk:

```text
C:\Users\ryliu\.cursor\skills\commit-helper\
├── SKILL.md
└── scripts\
    └── analyze_diff.py
```

In a Cursor chat (with staged changes in the repo):

> **You:** "Write a Conventional Commits message for my staged changes."
>
> **Agent:**
> 1. Detects "Conventional Commits" + "staged changes" → matches `commit-helper` description.
> 2. Reads `SKILL.md`.
> 3. Executes `python scripts/analyze_diff.py` as instructed.
> 4. Returns a message in the template format defined in `SKILL.md`.

That's the full loop — define, install, prompt, verify.

---

## Step 11 — Maintain

- Version your repo (tags or a `CHANGELOG.md`) so users know when to update.
- Treat the `description` field like a product surface — if a skill isn't being auto-invoked, the fix is almost always richer trigger terms there, not more body content.
- Re-run the verification checklist whenever you edit the skill.

---

## Quick Reference: What goes where?

| File | Loaded? | Use for |
|---|---|---|
| `SKILL.md` | Always, on invocation | Trigger info, workflow, output template, 1–2 examples |
| `reference.md` | On demand (when linked) | Deep API docs, edge cases, exhaustive option lists |
| `examples.md` | On demand (when linked) | Large gallery of input/output pairs |
| `scripts/*.py` (or `.sh`, `.ps1`) | Executed on demand | Reliable, repeatable, fragile, or token-heavy operations |
