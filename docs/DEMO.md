# Ariadne: 3-minute demo script

## Before you present (30 minutes ahead)

- [ ] **Deploy the latest backend:** `cd backend && modal deploy modal_deploy.py`
- [ ] **GitHub token is valid:** the current token expires on **23 Nov 2026**; renew it and run `modal secret create devcopilot-secrets --from-dotenv .env --force` if needed.
- [ ] **Warm up the server:** open the site 10 minutes before. It stays warm for 20 minutes after the last request.
- [ ] **Pre-index the demo repos** (each reopens instantly afterwards):
  - `https://github.com/pallets/flask`: the map
  - `https://github.com/pallets/itsdangerous`: the issue fix and sandbox tests
  - `https://github.com/Padala-Varun/spotmies-landing`: the live preview
- [ ] **Rehearse the fix once** on issue #429. AI output varies between runs; know what both outcomes look like (see "If something goes wrong").
- [ ] **Backup recording:** record one full run of this script on the day before and keep it open in another tab.
- [ ] Browser zoom at 90–100%, dark theme, notifications off, phone hotspot ready.

## The script

### 0:00–0:20 · The problem
> "When a team takes over someone else's codebase, the first weeks go to reading undocumented code and guessing what's safe to touch. AI assistants write code, but they don't know the repository, can't tell you what a change breaks, and can't prove their code works. Ariadne does all three."

### 0:20–0:50 · Understand: paste a link, get the map
1. On the connect screen, click **pallets/flask** under *Recently analyzed* (opens instantly).
2. The architecture map appears with the **Brief** tab.
> "Ariadne indexed every file, class and import into a knowledge graph. Each color is a module; bigger nodes are imported by more files. The brief on the right was written from that graph: what the project is, where to start reading, which files are risky."
3. Switch the map to **Risk**, open **Overview → Risk hotspots**, click the top one.
> "`flask/__init__.py` is imported by 49 files. Change it carelessly and half the project breaks."

### 0:50–1:40 · Fix a real GitHub issue
1. Switch to the **itsdangerous** repo (sidebar ↻ → recent repos), go to **Chat**, choose **Fix issue**.
2. Paste `https://github.com/pallets/itsdangerous/issues/429` and press Enter.
> "This is a real open issue in a library millions of projects depend on. Watch the team: a supervisor assigns the Explorer to find the cause, the Engineer writes the fix and tests, and the Critic reviews it, and sends it back if it's not good enough."
3. When it finishes, point at the **Critic's verdict** and the **Impact analysis** card; click **Show on map**.
> "Before anything ships, Ariadne walks the import graph: this change touches the serializer, and these files depend on it. The changed file pulses red."

### 1:40–2:30 · Verify: prove it works
1. Back in Chat, in **Ship this change**, click **Review diff** and expand one file.
> "Complete files, with the fix merged into the existing code, so nothing gets overwritten."
2. Click **Verify in sandbox**.
> "Now Ariadne spins up an isolated sandbox, clones the repo, installs it, and runs the project's own test suite, once on the original code and once with the change."
3. Read the result.
> "297 tests before, 301 after, the four new tests pass, and nothing regressed. That's the difference: it doesn't just suggest a fix, it proves it."

### 2:30–3:00 · Ship, and close
1. Click **Open pull request**. Show the title *Fix #429…* and point at the description fields (review, impact, test results, *Closes #429*). **Close the dialog; don't submit** on Pallets' repository.
> "One click opens the PR with the evidence attached. If you don't have write access, Ariadne forks the repository for you."
2. Close:
> "Understand, fix, protect, verify, ship: an AI team that takes over any codebase in minutes, and shows its work at every step."

## Optional: live preview (+40 seconds)

On **spotmies-landing**, Code mode: *"Change the hero subtitle text 'Experience the excellence' to 'Built by humans and AI, together'."* Tick **Live preview**, click **Verify in sandbox**, then **Open**.
> "For web apps, Ariadne builds the changed site in the sandbox and gives you a link. Here's the new subtitle, live, before anything is merged."

## If something goes wrong

| Situation | What to do |
|---|---|
| **The sandbox says "Tests failed"** | It's a feature: *"The AI's first attempt broke a test, and Ariadne caught it."* Click **Ask the Engineer to fix**: the failing output goes back to the Engineer and the next round builds on the previous one. Verify again. |
| **"The AI provider is rate-limiting requests"** | Wait 30 seconds and retry, or switch to the backup recording. |
| **The map or brief is slow** | The server was cold; it's warm after the first request. Keep talking through the problem slide. |
| **No internet** | Play the backup recording. |

## Questions judges may ask

- **"How is this different from Copilot or Cursor?"** They work file by file. Ariadne builds a knowledge graph of the whole repository, so it can rate a change's blast radius, and it verifies changes against the real test suite before a PR exists.
- **"How do you stop the AI from breaking things?"** Three layers: the Critic reviews every change, impact analysis shows what depends on it, and the sandbox runs the tests before and after.
- **"Is the risk score made up?"** No: it's computed from the graph (how many files import a file, how much code it contains, whether tests reference it), and every score lists its reasons.
- **"Is running AI-written code safe?"** It runs in a throwaway Modal Sandbox, isolated from the server, and is deleted afterwards.
- **"Which model?"** Mistral Codestral for the agents and Mistral embeddings, configurable with one setting; a stronger model raises fix quality.
- **"Does it scale to big repositories?"** Indexing is parallel and saved per repository; Flask (126 files) indexes in about 15 seconds, and the map shows the 600 most connected files of larger codebases.
