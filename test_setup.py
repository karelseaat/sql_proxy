#!/usr/bin/env python3
"""
Quick setup verification script.
Tests that all components are properly installed and configured.
"""

import sys
from pathlib import Path


def test_imports():
    """Test that all required packages are installed."""
    print("\n🔍 Testing imports...")
    
    try:
        import requests
        print("  ✓ Requests")
    except ImportError:
        print("  ✗ Requests - NOT INSTALLED")
        return False
    
    try:
        import dotenv
        print("  ✓ python-dotenv")
    except ImportError:
        print("  ✗ python-dotenv - NOT INSTALLED")
        return False
    
    try:
        from config import load_schema_config, get_database_description
        print("  ✓ Config module")
    except ImportError as e:
        print(f"  ✗ Config module - {e}")
        return False
    
    try:
        from llm import OllamaLLM
        print("  ✓ LLM module")
    except ImportError as e:
        print(f"  ✗ LLM module - {e}")
        return False
    
    return True


def test_config():
    """Test that configuration files exist and are valid."""
    print("\n🔍 Testing configuration...")
    
    schema_path = Path("config/database_schema.json")
    if not schema_path.exists():
        print(f"  ✗ Schema file not found: {schema_path}")
        return False
    print(f"  ✓ Schema file exists")
    
    try:
        from config import load_schema_config
        schema = load_schema_config()
        tables = len(schema.get("tables", []))
        print(f"  ✓ Schema is valid JSON ({tables} tables)")
    except Exception as e:
        print(f"  ✗ Schema is invalid: {e}")
        return False
    
    return True


def test_schema_structure():
    """Test that schema has expected structure."""
    print("\n🔍 Testing schema structure...")
    
    try:
        from config import load_schema_config
        schema = load_schema_config()
        
        required_keys = ["database", "tables"]
        for key in required_keys:
            if key not in schema:
                print(f"  ✗ Missing '{key}' in schema")
                return False
        
        tables = {t["name"]: t for t in schema["tables"]}
        expected_tables = ["users", "projects", "tasks"]
        
        for table_name in expected_tables:
            if table_name not in tables:
                print(f"  ✗ Missing table: {table_name}")
                return False
            
            table = tables[table_name]
            if "columns" not in table:
                print(f"  ✗ Table '{table_name}' has no columns")
                return False
        
        print(f"  ✓ Schema has all expected tables and structure")
        
        # Test schema description
        from config import get_database_description
        desc = get_database_description()
        if not desc or "users" not in desc:
            print(f"  ✗ Database description is invalid")
            return False
        
        print(f"  ✓ Database description is valid")
        
    except Exception as e:
        print(f"  ✗ Schema structure test failed: {e}")
        return False
    
    return True


def test_ollama_connection():
    """Test if Ollama is available."""
    print("\n🔍 Testing Ollama connection...")
    
    try:
        from llm import OllamaLLM
        llm = OllamaLLM()
        
        if llm.is_available():
            print("  ✓ Ollama service is available")
            return True
        else:
            print("  ⚠️  Ollama service is NOT available")
            print("     (This is normal if Ollama is not running)")
            print("     Start with: ollama serve")
            return True  # Not a critical failure
    
    except Exception as e:
        print(f"  ⚠️  Could not test Ollama: {e}")
        return True


def main():
    """Run all tests."""
    print("=" * 60)
    print("SQL Proxy - Setup Verification")
    print("=" * 60)
    
    tests = [
        ("Imports", test_imports),
        ("Configuration", test_config),
        ("Schema Structure", test_schema_structure),
        ("Ollama Connection", test_ollama_connection),
    ]
    
    all_passed = True
    for test_name, test_func in tests:
        try:
            if not test_func():
                all_passed = False
        except Exception as e:
            print(f"✗ {test_name} test failed: {e}")
            all_passed = False
    
    print("\n" + "=" * 60)
    if all_passed:
        print("✅ All critical checks passed!")
        print("\n🚀 Next steps:")
        print("  1. Start Ollama: ollama serve")
        print("  2. Start server: python server.py")
        return 0
    else:
        print("❌ Some checks failed. See above for details.")
        return 1


if __name__ == "__main__":
    sys.exit(main())