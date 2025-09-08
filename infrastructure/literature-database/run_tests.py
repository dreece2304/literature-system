#!/usr/bin/env python3
"""
Test runner script for the literature-database service.

Runs comprehensive tests including API integration and event publishing tests.
Ensures compatibility with existing test infrastructure.
"""
import sys
import subprocess
from pathlib import Path

def main():
    """Run tests with proper configuration."""
    
    # Add src to Python path
    src_path = Path(__file__).parent / "src"
    sys.path.insert(0, str(src_path))
    
    # Check if pytest is available
    try:
        import pytest
    except ImportError:
        print("❌ pytest is not installed. Install it with: pip install pytest")
        return 1
    
    # Check for required test dependencies
    required_packages = ['fastapi', 'sqlalchemy', 'pydantic']
    missing_packages = []
    
    for package in required_packages:
        try:
            __import__(package)
        except ImportError:
            missing_packages.append(package)
    
    if missing_packages:
        print(f"❌ Missing required packages: {', '.join(missing_packages)}")
        print("Install them with: pip install " + " ".join(missing_packages))
        return 1
    
    print("🧪 Running Literature Database Tests")
    print("=" * 50)
    
    # Test arguments
    test_args = [
        "-v",  # Verbose output
        "--tb=short",  # Short traceback format
        "--color=yes",  # Colored output
        "tests/",  # Test directory
    ]
    
    # Add coverage if available
    try:
        import coverage
        test_args.extend([
            "--cov=src",
            "--cov-report=term-missing",
            "--cov-report=html:htmlcov"
        ])
        print("📊 Coverage reporting enabled")
    except ImportError:
        print("ℹ️  Coverage reporting not available (install pytest-cov for coverage)")
    
    # Run specific test categories
    test_categories = [
        ("API Integration Tests", "tests/test_api_integration.py"),
        ("Event Publishing Tests", "tests/test_event_publishing.py"),
    ]
    
    all_passed = True
    
    for category_name, test_file in test_categories:
        print(f"\n🔍 Running {category_name}")
        print("-" * 30)
        
        # Check if test file exists
        if not Path(test_file).exists():
            print(f"⚠️  Test file not found: {test_file}")
            continue
        
        # Run tests for this category
        result = pytest.main([test_file] + test_args[:-1])  # Remove the tests/ directory arg
        
        if result == 0:
            print(f"✅ {category_name} passed")
        else:
            print(f"❌ {category_name} failed")
            all_passed = False
    
    # Summary
    print("\n" + "=" * 50)
    if all_passed:
        print("🎉 All tests passed!")
        print("\nNext steps:")
        print("  1. Review test coverage report (if generated)")
        print("  2. Run integration tests against live database if needed")
        print("  3. Test with Redis server running for full event publishing tests")
    else:
        print("❌ Some tests failed. Check the output above for details.")
        print("\nDebugging tips:")
        print("  1. Check that all dependencies are installed")
        print("  2. Ensure database is accessible")
        print("  3. Review test output for specific failures")
    
    return 0 if all_passed else 1

if __name__ == "__main__":
    exit(main())