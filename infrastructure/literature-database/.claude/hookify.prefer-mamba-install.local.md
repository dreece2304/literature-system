---
name: prefer-mamba-install
enabled: true
event: bash
pattern: pip install|conda activate
---

**Use mamba properly for this project!**

This project uses miniforge3 with mamba. Follow these patterns:

## Package Installation

**ALWAYS use mamba, not pip:**
```bash
# Direct mamba command (recommended)
/home/dreece23/miniforge3/bin/mamba install -n litdb -c conda-forge package_name -y

# Or use mamba run for commands in the environment
/home/dreece23/miniforge3/bin/mamba run -n litdb python -m pytest
```

**Only use pip as last resort** if package not in conda-forge:
```bash
/home/dreece23/miniforge3/bin/mamba run -n litdb pip install package_name
```

## Environment Activation

**Avoid `conda activate` with source scripts** - they can interfere with mamba.

Instead use `mamba run`:
```bash
# Instead of: source conda.sh && conda activate litdb && python script.py
# Use:
/home/dreece23/miniforge3/bin/mamba run -n litdb python script.py
```

## Why mamba over pip:
- Better dependency resolution
- Binary packages (faster, no compilation)
- Environment consistency
- GPU/CUDA compatibility

## Check package availability:
```bash
/home/dreece23/miniforge3/bin/mamba search -c conda-forge package_name
```
