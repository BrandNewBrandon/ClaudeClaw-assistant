# Tools — Builder Agent

## run_command

Executes shell commands on the local machine.

### Safe commands (run without approval prompt)

These prefixes execute immediately — no YES/NO dialog:

```
git status        git log           git diff
git branch        git show          git stash list
git remote        pytest            python -m pytest
npm test          npm run           npx
make              cargo test        cargo check
cargo build       ls                cat
grep              find              head
tail              wc                echo
```

Prefix-matched: `git status --short` is safe; `git stash drop` is not.

### Destructive commands (always ask first)

These always trigger an approval prompt:

- `git push`, `git reset --hard`, `git rebase`, `git checkout --`
- `rm`, `rmdir`, `mv` (when overwriting)
- `npm install`, `pip install`, `cargo add` (package installs)
- Any command not in the safe list above

### Working directory

Default working directory: `~/Projects`

Use `cd <repo> && <cmd>` for project-specific work:

```bash
cd ~/Projects/my-app && pytest tests/ -v
cd ~/Projects/my-app && git log --oneline -10
```
