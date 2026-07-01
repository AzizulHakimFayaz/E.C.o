# The E.Co Git & GitHub Workflow Handbook
## A Professional Engineering Guide for Large-Scale AI Desktop Applications

This guide outlines a production-grade, enterprise-scale Git and GitHub workflow. It is designed to keep the **E.Co** repository clean, structured, and reproducible for years, scaling seamlessly from a solo developer to a large engineering team.

---

## 1. Core Git Philosophy: History as a Log Book

In high-performing tech companies, Git history is not treated as a backup mechanism; it is treated as a **curated public log book**. 
- **The "Why" matters:** Every commit should explain *why* a change was made, not just *what* changed.
- **Atomic Commits:** Each commit must do exactly one thing. This makes rollback and debugging (`git bisect`) trivial.
- **Never break the main line:** Branch protection and automated continuous integration (CI) ensure that the primary branch is always buildable and deployable.

---

## 2. Branching Strategy: Trunk-Based Development with Short-Lived Feature Branches

For a modern desktop application that releases updates regularly (and integrates VS Code extensions/plugins), **Trunk-Based Development with Short-Lived Feature Branches** is preferred over old-school, heavy "GitFlow". It prevents "merge hell" and facilitates continuous integration.

### ASCII Branching Flow

```text
main      =========================== [v1.0.0] =========================== [v1.1.0] ==> (Production Releases)
           \                          /                                    /
develop     \===========*===*========*==================*===*=============*===> (Integration/Testing)
             \         /   /        /                  /   /             /
feature/      \---[ ]-/   /        /                  /   /             /  (Short-lived features)
feat-chat      \_________/        /                  /   /             /
                                 /                  /   /             /
release/                        /                  /   /             /
v1.0.0-rc1                     /                  /   /             /  (Stabilization branch)
                              /                  /   /             /
bugfix/                      /                  /   /             /  (Post-release bug fixes)
fix-voice-stt               /                  /   /             /
                           /                  /   /             /
hotfix/                   /                  /   /             /  (Direct emergency fixes)
hotfix-auth-leak ________/                  /   /             /
                                           /   /             /
feature/                                  /   /             /
feat-vscode-ext _________________________/___/             /
                                                          /
release/                                                 /
v1.1.0-rc1 _____________________________________________/
```

### Branch Roles
1. **`main` (Production)**: Holds the current stable release. Code only enters `main` via formal release branches or emergency hotfixes. Every merge to `main` corresponds to a production release.
2. **`develop` (Integration)**: The integration branch for features. This is the staging ground. Nightly builds and internal testing are triggered from here.
3. **`feature/*` (Short-Lived Feature)**: Used for developing new features. Spun off `develop`, merged back to `develop`.
4. **`bugfix/*` (Standard Bug Fixes)**: Used to fix bugs discovered during integration tests or QA. Spun off `develop`, merged back to `develop`.
5. **`release/*` (Release Candidate)**: Created when `develop` is ready for a release. Used for final polishing, version-bumping, and translation updates. No new features enter this branch. Merged into both `main` and `develop`.
6. **`hotfix/*` (Emergency Production Fixes)**: Used to patch critical production bugs (e.g. security leak, immediate crash). Spun off `main` and merged into both `main` and `develop`.

---

## 3. Repository Directory Standards

To support multiple targets (Desktop App, VS Code Extension, backend, DB integrations), organize the repository clearly:

```text
e-co/
├── .github/                  # GitHub configurations
│   ├── workflows/            # CI/CD pipelines (GitHub Actions)
│   ├── ISSUE_TEMPLATE/       # Structured bug/feature templates
│   └── PULL_REQUEST_TEMPLATE.md
├── app/                      # Desktop Application code (Electron, Tauri, etc.)
├── backend/                  # Python Agent core & server logic
├── extension/                # VS Code Extension source code
├── memory/                   # Database configurations (SQLite, Neo4j, ChromaDB)
├── tests/                    # Testing Suites (unit, integration, end-to-end)
├── .gitattributes            # Git attributes file (LFS, line endings)
├── .gitignore                # Global ignores
├── README.md                 # Project introduction and developer setup
└── CHANGELOG.md              # Auto-generated changelog
```

### Git Attributes (`.gitattributes`)
Ensures consistent line endings across Windows, Mac, and Linux, and configures Large File Storage (LFS) for heavy ML weight models or icons:
```text
# Force LF line endings for all text files (prevents Windows CRLF conflicts)
* text=auto eol=lf

# Configure LFS for binary assets
*.png filter=lfs diff=lfs merge=lfs -text
*.onnx filter=lfs diff=lfs merge=lfs -text
*.db filter=lfs diff=lfs merge=lfs -text
```

---

## 4. Naming Conventions

Consistency ensures clarity across automated pipelines.

### Branch Names
Format: `<type>/<issue-number>-<short-description>`

| Type | Description | Example |
| :--- | :--- | :--- |
| `feature/` | Developing a new feature | `feature/ec-104-voice-assistant` |
| `bugfix/` | Fixing an existing bug | `bugfix/ec-201-sqlite-deadlock` |
| `hotfix/` | Emergency production patch | `hotfix/ec-911-api-key-leak` |
| `release/` | Pre-release stabilization | `release/v1.0.0-rc1` |

---

## 5. Commit Message Conventions (Conventional Commits)

E.Co uses the **Conventional Commits** specification (v1.0.0). This standard allows automated tools to build CHANGELOGs, determine Semantic Versioning increments, and trigger specific CI/CD pipelines.

### Commit Format
```text
<type>(<scope>): <description>

[optional body]

[optional footer(s)]
```

### Commit Types
*   `feat`: A new feature (corresponds to a **Minor** version bump in SemVer)
*   `fix`: A bug fix (corresponds to a **Patch** version bump in SemVer)
*   `docs`: Documentation changes
*   `style`: Formatting, missing semi-colons, style tweaks (no production code change)
*   `refactor`: Code changes that neither fix a bug nor add a feature
*   `perf`: A code change that improves performance
*   `test`: Adding missing tests or correcting existing tests
*   `build`: Changes that affect the build system or external dependencies
*   `ci`: Changes to our CI configuration files and scripts
*   `chore`: Other changes that don't modify src or test files

### Real-world Examples for E.Co
```text
feat(chat): add streaming responses and collapsible thought accordion

Implemented FastAPI event stream for local ReAct agent run tokens and designed a
collapsible UI toggle inside styles.css to inspect tool call logs.

Closes: #42
```
```text
fix(memory): resolve SQLite WAL database locked exception

Configured SQLite connection factory in db_sqlite.py to use thread-safe WAL journal
mode and set query execution timeout to 30.0s.

BREAKING CHANGE: The memory model database schema updated to require 'classification'.
```

---

## 6. Pull Request (PR) & Code Review Workflow

Code never enters `develop` or `main` directly. Every change requires a Pull Request (PR) and at least one code review.

```text
[Create Branch] -> [Commit Changes] -> [Open PR] -> [CI Passes] -> [Code Review Approved] -> [Squash & Merge]
```

### PR Rules
1. **Always link an issue**: Link your PR to a GitHub issue (e.g. `Closes #104`) to auto-close the issue on merge.
2. **Squash and Merge**: Use "Squash and Merge" for feature branches. This condenses 20 WIP commits into a single, clean commit on `develop`, keeping history tidy.
3. **PR Template**: Maintain a `PULL_REQUEST_TEMPLATE.md` requiring:
    - Description of changes
    - Testing instructions
    - Checklist (Linter passed, unit tests passed, documentation updated)

---

## 7. Versioning using Semantic Versioning (SemVer)

E.Co releases follow Semantic Versioning 2.0.0 format: `MAJOR.MINOR.PATCH`.

$$\text{Format: } \mathbf{MAJOR.MINOR.PATCH}$$

1.  **MAJOR**: Bumps when you make incompatible API changes (e.g., rewriting the storage engine, removing neo4j client).
2.  **MINOR**: Bumps when you add functionality in a backwards-compatible manner (e.g., adding a new web search tool, introducing VS Code integration).
3.  **PATCH**: Bumps when you make backwards-compatible bug fixes (e.g., fixing voice audio crash, updating CSS styles).

---

## 8. Git Tags & GitHub Releases

*   **Git Tags**: Tags label points in your repository history as being important. Use **annotated tags** for releases.
*   **GitHub Releases**: Create a GitHub Release pointing to the git tag. Upload packaged installers (`.exe`, `.dmg`, `.vsix`) to the release page.

---

## 9. Automated CI/CD (GitHub Actions)

Create automated checks under `.github/workflows/`.

### Flowchart of CI/CD Trigger

```text
                       [ Developer Pushes Code ]
                                  │
                       ┌──────────┴──────────┐
                       ▼                     ▼
              [ Pull Request ]          [ Merge to main ]
                       │                     │
           ┌───────────┴───────────┐         ▼
           ▼                       ▼    [ CD Pipeline ]
     [ Linter Check ]     [ Unit Tests ]     │
           │                       │         ├── Build Electron App
           └───────────┬───────────┘         ├── Compile VS Code Extension
                       ▼                     ├── Sign Installers
               [ Pass Checks? ]              ▼
           ┌───────────┴───────────┐    [ Publish Draft Release ]
           ▼                       ▼
      [ Allow Review ]       [ Block Merge ]
```

### Essential Pipelines
1. **Linter & Test (`ci.yml`)**: Runs on every PR to `develop`. Checks code formatting, runs python tests, and ensures Javascript compiles.
2. **Auto-Draft Release (`release-draft.yml`)**: Runs when a tag is pushed. Builds the executables, signs the code, drafts a release page, and populates the release logs based on Conventional Commits.

---

## 10. Daily Developer Loop (Commands Guide)

Here are the step-by-step console commands for the daily workflow.

### Scenario A: Working on a New Feature (`feat-voice`)

#### 1. Sync local repository with remote
Always start by pulling the latest integration code:
```bash
git checkout develop
git pull origin develop
```

#### 2. Create your branch
```bash
git checkout -b feature/ec-104-voice-integration
```

#### 3. Commit code atomically
Make changes to your voice module and add files:
```bash
git add backend/voice_manager.py
git commit -m "feat(voice): initialize speech recognition listener interface"
```
*(Write more code...)*
```bash
git add static/app.js static/index.html
git commit -m "feat(voice): design microphone dictation overlay and waveform UI"
```

#### 4. Rebase to avoid conflicts before pushing
If other developers merged features to `develop` while you worked, pull `develop` and rebase your branch on top of it:
```bash
git fetch origin
git rebase origin/develop
```
*(If conflicts occur, resolve them in your editor, then run `git add <resolved-files>` and `git rebase --continue`)*

#### 5. Push your branch and open PR
```bash
git push -u origin feature/ec-104-voice-integration
```
*Go to GitHub, open a Pull Request to merge into `develop`, let CI run, obtain approval, and select **Squash and Merge**.*

---

### Scenario B: Preparing Release `v1.0.0`

When `develop` is stable and ready to release:

#### 1. Spin off a release branch
```bash
git checkout develop
git pull origin develop
git checkout -b release/v1.0.0
```

#### 2. Bump version & finalize changelog
Update version fields in package configuration files (e.g. `package.json`, python configuration settings) and compile changes:
```bash
git add backend/memory/settings.json
git commit -m "chore(release): bump version to 1.0.0"
```

#### 3. Merge Release to Main and Develop
Merge into `main` (for release) and `develop` (to keep version numbers aligned):
```bash
# Merge into main
git checkout main
git pull origin main
git merge --no-ff release/v1.0.0 -m "chore(release): merge release/v1.0.0 into main"

# Create Annotated Tag
git tag -a v1.0.0 -m "E.Co v1.0.0 Production Release"

# Merge back to develop
git checkout develop
git merge --no-ff release/v1.0.0 -m "chore(release): merge release/v1.0.0 back to develop"

# Push tags and branches
git push origin main develop --tags
```

#### 4. Clean up
```bash
git branch -d release/v1.0.0
git push origin --delete release/v1.0.0
```

---

### Scenario C: Emergency Production Bug (`hotfix-security`)

If a bug is found in production `v1.0.0` that must be patched immediately:

#### 1. Spin off hotfix branch from `main`
```bash
git checkout main
git pull origin main
git checkout -b hotfix/ec-902-auth-bypass
```

#### 2. Fix the bug and test
```bash
# Code fix...
git add backend/server.py
git commit -m "fix(security): resolve auth token validation bypass"
```

#### 3. Merge into main, tag, and merge back to develop
```bash
# Merge into main
git checkout main
git merge --no-ff hotfix/ec-902-auth-bypass -m "fix(security): merge hotfix/ec-902-auth-bypass into main"
git tag -a v1.0.1 -m "E.Co v1.0.1 hotfix patch release"

# Merge back into develop
git checkout develop
git merge --no-ff hotfix/ec-902-auth-bypass -m "fix(security): merge hotfix/ec-902-auth-bypass into develop"

# Push and clean up
git push origin main develop --tags
git branch -d hotfix/ec-902-auth-bypass
```

---

## 11. Common Mistakes to Avoid

1.  **Never force push (`git push --force`) to shared branches (`main`, `develop`)**: Doing so overwrites history and disrupts other developers. Use `--force-with-lease` only on your own feature branch.
2.  **Avoid huge commits**: Committing 50 files across different features makes code review impossible. Commit in logical, compile-safe steps.
3.  **No secrets in commits**: Never commit API keys (`gsk_...`, `sk-...`). Use environment files (`.env`) and add them to `.gitignore`.
4.  **Ignoring Merge Conflicts**: Never resolve merge conflicts by picking "ours" or "theirs" blindly. Go through files line by line.

---

## 12. GitHub Branch Protection & Settings

To enforce this workflow, configure the following settings in your GitHub Repository:

1.  **Branch Protection for `main` and `develop`**:
    *   Go to **Settings** > **Branches** > **Add classic branch protection rule**.
    *   Target: `main` and `develop`.
    *   Enable: **Require a pull request before merging** (Check **Require approvals** - set to 1).
    *   Enable: **Require status checks to pass before merging** (Require tests/linters to pass).
    *   Enable: **Require conversation resolution before merging** (Ensure all review threads are resolved).
    *   Disable: **Allow force pushes** (Block history changes).
    *   Disable: **Allow deletions** (Prevent branch loss).
2.  **Tag Protection**:
    *   Prevent developers from editing or deleting tags like `v*` to guarantee reproducibility.
3.  **Code Owners (`CODEOWNERS`)**:
    *   Create a `.github/CODEOWNERS` file to auto-assign specific developers to review changes in areas of expertise:
    ```text
    # Assign core memory changes to backend engineers
    /memory/ @Shahriar
    # Assign VS Code extension changes to extension team
    /extension/ @ExtensionLead
    ```
