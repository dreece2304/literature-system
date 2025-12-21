---
name: prefer-mamba
enabled: true
event: bash
pattern: pip\s+install
action: warn
---

**Use mamba instead of pip!**

You're about to use `pip install`. Prefer `mamba install` for better dependency resolution and environment management.

**Convert to mamba:**
```bash
# Instead of: pip install package
mamba install package -c conda-forge

# For PyTorch with CUDA:
mamba install pytorch torchvision torchaudio pytorch-cuda=12.1 -c pytorch -c nvidia

# Only use pip for packages not on conda-forge
```

**When pip is acceptable:**
- Package not available on conda-forge
- Installing from git URLs
- Installing local packages with `-e`
