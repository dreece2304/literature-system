# Qwen LLM Setup for RTX 4070 8GB

## Hardware Requirements

### Minimum Requirements
- **GPU**: NVIDIA RTX 4070 (8GB VRAM)
- **RAM**: 16GB+ system memory
- **Storage**: 20GB+ free space for models
- **CUDA**: Version 11.8 or 12.x

### Verify GPU Setup
```bash
# Check GPU is detected
nvidia-smi

# Check CUDA version
nvcc --version

# Check available VRAM
nvidia-smi --query-gpu=memory.free --format=csv

# Monitor GPU usage
watch -n 1 nvidia-smi
```

## Ollama Installation

### Install Ollama on Linux/WSL2
```bash
# Official installation script
curl -fsSL https://ollama.ai/install.sh | sh

# Or manual installation
wget https://github.com/ollama/ollama/releases/download/v0.1.20/ollama-linux-amd64
sudo mv ollama-linux-amd64 /usr/local/bin/ollama
sudo chmod +x /usr/local/bin/ollama

# Start Ollama service
ollama serve

# Verify installation
ollama --version
```

### Configure Ollama for GPU
```bash
# Set environment variables
export OLLAMA_NUM_GPU=1
export CUDA_VISIBLE_DEVICES=0
export OLLAMA_MODELS_PATH=$HOME/.ollama/models

# Add to ~/.bashrc for persistence
echo 'export OLLAMA_NUM_GPU=1' >> ~/.bashrc
echo 'export CUDA_VISIBLE_DEVICES=0' >> ~/.bashrc
```

## Model Selection for RTX 4070 8GB

### Recommended Models by Use Case

| Model | Size | VRAM Usage | Use Case | Quality |
|-------|------|------------|----------|---------|
| **qwen:7b-q4_K_M** | 4.1GB | ~4.5GB | Writing assistance | Good |
| **qwen:7b-q5_K_M** | 5.0GB | ~5.5GB | Better writing | Better |
| **qwen:7b-q8_0** | 7.2GB | ~7.5GB | Maximum quality 7B | Best 7B |
| **qwen:14b-q3_K_M** | 6.2GB | ~6.8GB | Larger model compressed | Good |
| **qwen:14b-q4_K_M** | 7.9GB | ~8.3GB | *Tight fit* | Better |

### Pull Models
```bash
# Recommended for RTX 4070: 7B model with 4-bit quantization
ollama pull qwen:7b-q4_K_M

# Alternative: Better quality if VRAM allows
ollama pull qwen:7b-q5_K_M

# For maximum context understanding (tight on VRAM)
ollama pull qwen:14b-q3_K_M

# List downloaded models
ollama list
```

## Model Configuration

### Create Custom Modelfile
```bash
# Create optimized Qwen for RTX 4070
cat > Modelfile.qwen4070 << 'EOF'
FROM qwen:7b-q4_K_M

# Optimize for RTX 4070 8GB
PARAMETER num_gpu 35           # Layers on GPU (adjust if OOM)
PARAMETER num_thread 8          # CPU threads
PARAMETER num_batch 512         # Batch size
PARAMETER context_length 8192   # Context window
PARAMETER repeat_penalty 1.1
PARAMETER temperature 0.7
PARAMETER top_k 40
PARAMETER top_p 0.9

# System prompt for research assistant
SYSTEM """You are a research assistant helping with academic literature management and paper writing. 
You provide accurate, well-cited responses and help with finding relevant papers, writing suggestions, 
and understanding complex research topics. Always maintain academic rigor and precision."""
EOF

# Create custom model
ollama create qwen-research -f Modelfile.qwen4070

# Test custom model
ollama run qwen-research "What makes a good research paper?"
```

## Python Integration

### Basic Ollama Python Usage
```python
# Install ollama Python package
pip install ollama

import ollama

# Basic completion
response = ollama.generate(
    model='qwen:7b-q4_K_M',
    prompt='Explain reinforcement learning'
)
print(response['response'])

# Chat completion
response = ollama.chat(
    model='qwen:7b-q4_K_M',
    messages=[
        {'role': 'user', 'content': 'What is a neural network?'}
    ]
)
print(response['message']['content'])

# Streaming response
stream = ollama.generate(
    model='qwen:7b-q4_K_M',
    prompt='Write a paragraph about machine learning',
    stream=True
)
for chunk in stream:
    print(chunk['response'], end='', flush=True)
```

### LangChain Integration
```python
# Install dependencies
pip install langchain langchain-community

from langchain_community.llms import Ollama
from langchain.callbacks.streaming_stdout import StreamingStdOutCallbackHandler

# Initialize Ollama with Qwen
llm = Ollama(
    model="qwen:7b-q4_K_M",
    base_url="http://localhost:11434",
    num_gpu=35,  # Adjust based on model
    num_thread=8,
    temperature=0.7,
    callbacks=[StreamingStdOutCallbackHandler()]
)

# Use in chain
from langchain.prompts import PromptTemplate
from langchain.chains import LLMChain

prompt = PromptTemplate(
    input_variables=["topic"],
    template="Write a research abstract about {topic}"
)
chain = LLMChain(llm=llm, prompt=prompt)

result = chain.run(topic="neural networks")
```

## Memory Management for RTX 4070

### Optimal Settings by Task

#### Writing Assistance (Primary Use)
```python
config = {
    "model": "qwen:7b-q4_K_M",
    "num_gpu": 35,
    "num_batch": 512,
    "context_length": 4096,  # Reduced for stability
    "temperature": 0.7,
}
```

#### Paper Triage (Batch Processing)
```python
config = {
    "model": "qwen:7b-q4_K_M",
    "num_gpu": 30,  # Leave headroom
    "num_batch": 256,  # Smaller batches
    "context_length": 2048,  # Shorter context
    "temperature": 0.3,  # More deterministic
}
```

#### Deep Reading (Q&A)
```python
config = {
    "model": "qwen:7b-q5_K_M",  # Better quality
    "num_gpu": 35,
    "num_batch": 128,  # Small batch
    "context_length": 8192,  # Full context
    "temperature": 0.1,  # Precise answers
}
```

### Handling Out of Memory Errors

```python
import torch
import gc
import ollama

def safe_generate(prompt, model="qwen:7b-q4_K_M", max_retries=3):
    """Generate with automatic OOM recovery."""
    for attempt in range(max_retries):
        try:
            response = ollama.generate(
                model=model,
                prompt=prompt,
                options={
                    "num_gpu": 35 - (attempt * 5),  # Reduce GPU layers
                    "num_batch": 512 // (2 ** attempt),  # Reduce batch
                }
            )
            return response['response']
        except Exception as e:
            if "out of memory" in str(e).lower():
                print(f"OOM on attempt {attempt + 1}, reducing memory usage...")
                # Clear cache if using PyTorch
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
                gc.collect()
                
                # Try unloading and reloading model
                if attempt == max_retries - 1:
                    ollama.generate(model=model, prompt="", keep_alive=0)
                    time.sleep(2)
            else:
                raise e
    
    return "Failed to generate after multiple attempts"
```

## Service Configuration

### Ollama Service File
```ini
# /etc/systemd/system/ollama.service
[Unit]
Description=Ollama LLM Service
After=network.target

[Service]
Type=simple
User=YOUR_USERNAME
Environment="OLLAMA_NUM_GPU=1"
Environment="CUDA_VISIBLE_DEVICES=0"
Environment="OLLAMA_MODELS_PATH=/home/YOUR_USERNAME/.ollama/models"
ExecStart=/usr/local/bin/ollama serve
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

### Start as Service
```bash
# Enable and start service
sudo systemctl enable ollama
sudo systemctl start ollama

# Check status
sudo systemctl status ollama

# View logs
journalctl -u ollama -f
```

## API Configuration for Literature-AI

```python
# infrastructure/literature-ai/config/llm_config.py
import os
from typing import Dict, Any

class QwenConfig:
    """Configuration for Qwen models on RTX 4070."""
    
    BASE_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
    
    # Model selection based on available VRAM
    MODELS = {
        "fast": "qwen:7b-q4_K_M",      # 4.5GB VRAM
        "balanced": "qwen:7b-q5_K_M",   # 5.5GB VRAM
        "quality": "qwen:7b-q8_0",      # 7.5GB VRAM
        "large": "qwen:14b-q3_K_M",     # 6.8GB VRAM
    }
    
    # Task-specific configurations
    TASK_CONFIGS = {
        "writing": {
            "model": MODELS["balanced"],
            "temperature": 0.7,
            "top_p": 0.9,
            "num_gpu": 35,
            "context_length": 4096,
            "num_batch": 512,
        },
        "triage": {
            "model": MODELS["fast"],
            "temperature": 0.3,
            "top_p": 0.8,
            "num_gpu": 30,
            "context_length": 2048,
            "num_batch": 256,
        },
        "reading": {
            "model": MODELS["balanced"],
            "temperature": 0.1,
            "top_p": 0.95,
            "num_gpu": 35,
            "context_length": 8192,
            "num_batch": 128,
        },
        "embedding": {
            "model": MODELS["fast"],
            "temperature": 0,
            "num_gpu": 25,
            "context_length": 512,
            "num_batch": 1024,
        }
    }
    
    @classmethod
    def get_config(cls, task: str) -> Dict[str, Any]:
        """Get configuration for specific task."""
        return cls.TASK_CONFIGS.get(task, cls.TASK_CONFIGS["writing"])
```

## Performance Benchmarks on RTX 4070

### Generation Speed (tokens/second)

| Model | Batch Size | Context | Speed | Quality |
|-------|------------|---------|--------|---------|
| qwen:7b-q4_K_M | 512 | 4096 | ~40 t/s | Good |
| qwen:7b-q5_K_M | 256 | 4096 | ~30 t/s | Better |
| qwen:7b-q8_0 | 128 | 4096 | ~20 t/s | Best 7B |
| qwen:14b-q3_K_M | 128 | 2048 | ~15 t/s | Very Good |

### Memory Usage

```python
# Monitor memory usage
import subprocess
import json

def get_gpu_memory():
    """Get current GPU memory usage."""
    result = subprocess.run(
        ['nvidia-smi', '--query-gpu=memory.used,memory.total', '--format=csv,nounits,noheader'],
        capture_output=True,
        text=True
    )
    used, total = map(int, result.stdout.strip().split(','))
    return {
        "used_mb": used,
        "total_mb": total,
        "used_gb": used / 1024,
        "total_gb": total / 1024,
        "percent": (used / total) * 100
    }

# Monitor during generation
print("Before loading:", get_gpu_memory())
response = ollama.generate(model='qwen:7b-q4_K_M', prompt='Test')
print("After loading:", get_gpu_memory())
```

## Troubleshooting

### Common Issues and Solutions

| Issue | Solution |
|-------|----------|
| **Out of Memory** | Reduce `num_gpu`, use smaller quantization |
| **Slow generation** | Increase `num_batch`, reduce `context_length` |
| **Model not found** | Run `ollama pull model_name` |
| **Connection refused** | Check `ollama serve` is running |
| **CUDA not available** | Verify GPU drivers and CUDA installation |
| **Model keeps unloading** | Set `keep_alive` parameter to -1 |

### Debug Commands
```bash
# Check Ollama logs
journalctl -u ollama -n 100

# Test model loading
ollama run qwen:7b-q4_K_M "test"

# Check model details
ollama show qwen:7b-q4_K_M

# Monitor GPU memory during inference
watch -n 0.5 nvidia-smi

# Clear GPU memory
python -c "import torch; torch.cuda.empty_cache()"
```

## Production Tips

1. **Model Switching**: Unload models when switching to free VRAM
   ```python
   ollama.generate(model="current_model", prompt="", keep_alive=0)
   ```

2. **Batch Processing**: Process papers in small batches to avoid OOM

3. **Fallback Models**: Keep smaller models as fallback options

4. **Memory Monitoring**: Implement automatic memory monitoring and model switching

5. **Caching**: Cache LLM responses to avoid regeneration

6. **Queue Management**: Use Celery to queue and process requests sequentially