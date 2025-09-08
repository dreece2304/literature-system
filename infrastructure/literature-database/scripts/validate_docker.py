#!/usr/bin/env python3
"""
Docker configuration validation script.
Validates Docker files and provides setup instructions.
"""
import os
import yaml
import subprocess
from pathlib import Path

def validate_docker_files():
    """Validate Docker configuration files."""
    print("🐳 Validating Docker Configuration")
    print("=" * 50)
    
    success = True
    
    # Check Dockerfile
    dockerfile = Path("Dockerfile")
    if dockerfile.exists():
        print("✅ Dockerfile exists")
        
        # Check for multi-stage build
        content = dockerfile.read_text()
        if "FROM python:3.11-slim as builder" in content:
            print("✅ Multi-stage build configured")
        else:
            print("⚠️  Multi-stage build not found")
        
        if "USER appuser" in content:
            print("✅ Non-root user configured")
        else:
            print("❌ No non-root user found")
            success = False
            
    else:
        print("❌ Dockerfile not found")
        success = False
    
    # Check docker-compose files
    compose_files = [
        "docker-compose.yml",
        "docker-compose.prod.yml",
        "docker-compose.override.yml"
    ]
    
    for compose_file in compose_files:
        if Path(compose_file).exists():
            try:
                with open(compose_file, 'r') as f:
                    config = yaml.safe_load(f)
                
                if 'services' in config and 'literature-database' in config['services']:
                    print(f"✅ {compose_file} is valid")
                else:
                    print(f"⚠️  {compose_file} missing literature-database service")
                    
            except yaml.YAMLError as e:
                print(f"❌ {compose_file} has YAML syntax error: {e}")
                success = False
        else:
            print(f"ℹ️  {compose_file} not found (optional)")
    
    # Check .dockerignore
    if Path(".dockerignore").exists():
        print("✅ .dockerignore exists")
    else:
        print("⚠️  .dockerignore not found")
    
    # Check environment file
    if Path(".env.docker").exists():
        print("✅ .env.docker template exists")
    else:
        print("⚠️  .env.docker template not found")
    
    return success

def check_docker_available():
    """Check if Docker is available."""
    try:
        result = subprocess.run(['docker', '--version'], 
                              capture_output=True, text=True)
        if result.returncode == 0:
            print(f"✅ Docker available: {result.stdout.strip()}")
            return True
    except FileNotFoundError:
        pass
    
    print("❌ Docker not available")
    return False

def check_docker_compose_available():
    """Check if Docker Compose is available."""
    try:
        result = subprocess.run(['docker-compose', '--version'], 
                              capture_output=True, text=True)
        if result.returncode == 0:
            print(f"✅ Docker Compose available: {result.stdout.strip()}")
            return True
    except FileNotFoundError:
        pass
    
    # Try docker compose (newer syntax)
    try:
        result = subprocess.run(['docker', 'compose', 'version'], 
                              capture_output=True, text=True)
        if result.returncode == 0:
            print(f"✅ Docker Compose (plugin) available: {result.stdout.strip()}")
            return True
    except FileNotFoundError:
        pass
    
    print("❌ Docker Compose not available")
    return False

def print_usage_instructions():
    """Print Docker usage instructions."""
    print("\n📋 Docker Usage Instructions")
    print("=" * 30)
    
    print("\n🚀 Quick Start (SQLite):")
    print("  1. cp .env.docker .env")
    print("  2. docker-compose up -d")
    print("  3. curl http://localhost:8001/health")
    
    print("\n🐘 PostgreSQL Development:")
    print("  1. docker-compose --profile postgres up -d")
    print("  2. Wait for database initialization")
    print("  3. curl http://localhost:8001/health")
    
    print("\n🏭 Production Deployment:")
    print("  1. cp .env.docker .env")
    print("  2. Edit .env with production values")
    print("  3. docker-compose -f docker-compose.prod.yml up -d")
    
    print("\n🔧 Development:")
    print("  - Hot reload: enabled by default in dev mode")
    print("  - Tests: docker-compose exec literature-database python run_tests.py")
    print("  - Shell: docker-compose exec literature-database bash")
    print("  - Logs: docker-compose logs -f literature-database")
    
    print("\n📊 Monitoring:")
    print("  - Health: curl http://localhost:8001/health")
    print("  - API Docs: http://localhost:8001/docs")
    print("  - Logs: docker-compose logs -f")

def main():
    """Main validation function."""
    print("Literature Database Docker Validation")
    print("=" * 50)
    
    # Change to script directory
    os.chdir(Path(__file__).parent.parent)
    
    all_good = True
    
    # Validate configuration files
    if not validate_docker_files():
        all_good = False
    
    print(f"\n🔧 Docker Installation")
    print("=" * 25)
    
    # Check Docker availability
    if not check_docker_available():
        all_good = False
        print("Install Docker: https://docs.docker.com/get-docker/")
    
    if not check_docker_compose_available():
        all_good = False
        print("Install Docker Compose: https://docs.docker.com/compose/install/")
    
    # Print results
    print(f"\n{'='*50}")
    if all_good:
        print("🎉 All Docker configurations are valid!")
        print("✅ Ready for Docker deployment")
        print_usage_instructions()
    else:
        print("❌ Some issues found. Please fix them before deployment.")
        print("📖 See DOCKER.md for detailed instructions")
    
    print(f"{'='*50}")
    return 0 if all_good else 1

if __name__ == "__main__":
    exit(main())