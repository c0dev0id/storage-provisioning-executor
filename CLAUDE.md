This file contains important informations for AI agents like claude, chatgpt and copilot.

# *MOST IMPORTANT RULES THAT MUST BE FOLLOWED*
- *Always commit* every logical step! Don't batch unrelated changes into one commit.
- *Always rebase* the working branch onto the latest main (or master, if main doesn't exist) at the end of a task. Resolve any conflicts during the rebase.

# Keep A Changelog
Maintain a CHANGELOG.md file in every project, following the specification at:
https://raw.githubusercontent.com/olivierlacan/keep-a-changelog/refs/heads/main/CHANGELOG.md
Update it after each development task with a human-readable description of what changed.
Don't list individual commits. Skip entries for trivial or non-user-facing changes that don't affect app behavior.

# Development Journal
Maintain a file at .github/development-journal.md containing:
- Software Stack Information
- Key Decisions (context and rationale to keep in mind for future work)
- Core Features

# Git Configuration Rules
All git operations are performed on behalf of the user. Before any git operation, configure:
- user.name = c0dev0id
- user.email = sh+git@codevoid.de

Never add Co-Authored-By or any other personal attribution to commits or pull requests.

Remove all lines that contain the word "claude" from pull request and commit messages.

If a .gh_token file is present, use the token to access GitHub and read CI/CD workflow results.

# Build Constraints
Do not attempt to build Android projects locally. All builds are handled by CI/CD.
AGP cannot be accessed due to firewall restrictions. Do not try to work around this.

# Code Style
- KISS — Keep it Simple, Stupid.
- Write testable code.
- Write unit tests that verify assumptions and cover edge cases.
- No database or schema migration code during development (version < 1.0.0).

# Library and Framework Usage
- Always use the latest version available.
- Before implementing a feature from scratch, check whether the libraries and frameworks already in use provide built-in support for it — possibly in a different form than the user requested. If so, explain the available capabilities and let the user decide how to adjust the request.
  - Example: The user asks for a specific animation that would require a custom implementation, but the UI framework already provides a set of built-in animations. Present those options and let the user choose.

# Communication Standards
- Be clear, direct, and evidence-based.
- Push back when something seems wrong or suboptimal.
- If the user uses imprecise terminology, provide the correct term.

# Finding Solutions
- Don't jump to conclusions. If there's any ambiguity, ask for clarification first.
- The obvious fix is often not the right one. Approach problems from multiple angles:
  - Consider whether a design pattern would prevent recurring issues.
  - Evaluate whether a different library, technique, or component is a better fit than working around limitations of the current approach.
  - Step back and examine the architecture — the root cause may point to a structural improvement rather than a local patch.

# About the User (Target Group Definition)
- The user is a minimalist who values performance, low latency and over feature richness.
- The user prefers clean software architecture and technical correctness and will adapt workflow or feature expectations to fit the software stack rather than accept complex code or workarounds.
- The user may not be aware of all capabilities offered by the libraries and frameworks in use.

