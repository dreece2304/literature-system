# Literature AI Service

LLM-powered services for paper triage, writing assistance, and Q&A.

## Features
- Paper triage and scoring
- Writing assistance
- Question answering about papers
- Embedding generation

## Setup
```bash
mamba create -n litai python=3.11
mamba activate litai
pip install -r requirements.txt
```

## Configuration
- Uses Qwen models via Ollama
- Optimized for RTX 4070 8GB VRAM
