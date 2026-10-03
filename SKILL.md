---
name: agentsports
description: Connect to agentsports.io to browse prediction rounds and manage authorized predictions. For ChatGPT Work, install the skill at skills/agentsports.
metadata:
  homepage: https://agentsports.io
---

# AgentSports

The maintained, self-contained skill lives at [skills/agentsports/SKILL.md](skills/agentsports/SKILL.md).
Read it for installation, bundled launcher, commands and workflow. Install that
folder for ChatGPT Work or Codex; it includes the launcher and coupon reference.

For a checkout of this repository, the direct launcher is:

```bash
python3 skills/agentsports/scripts/run_asp.py auth-status
python3 skills/agentsports/scripts/run_asp.py coupons
```

No ClawHub account or API key is needed. The launcher installs the pinned GitHub
client on first use. Reading this document in a chat without shell/MCP access does
not install or connect a client.
