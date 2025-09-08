#!/bin/bash
# Setup all infrastructure dependencies

echo "🔧 Setting up infrastructure..."

# Check system requirements
echo "Checking requirements..."
command -v mamba >/dev/null 2>&1 || { echo "❌ Mamba not found. Please install miniforge."; exit 1; }
command -v redis-cli >/dev/null 2>&1 || { echo "⚠️  Redis not found. Installing..."; sudo apt install redis-server -y; }
command -v ollama >/dev/null 2>&1 || { echo "⚠️  Ollama not found. Installing..."; curl -fsSL https://ollama.ai/install.sh | sh; }

# Pull Qwen model for RTX 4070
echo "📥 Pulling Qwen model..."
ollama pull qwen:7b-q4_K_M

echo "✅ Infrastructure setup complete!"
