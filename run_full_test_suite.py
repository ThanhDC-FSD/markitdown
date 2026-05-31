#!/usr/bin/env python3
"""
Comprehensive 44+ test suite runner for full RAG validation.
Tests all categories with quality gates and confidence scoring.
"""

from datetime import datetime
import os
import json
import re
from pathlib import Path
import subprocess
import sys
from typing import Any, Dict, List, Optional, Set, Tuple

ROOT = Path(__file__).resolve().parent
GROUNDED_SCRIPT = ROOT / "src" / "tools" / "diagnostics" / "grounded_qa_diagnostic.py"
OUTPUT_DIR = ROOT / "diagnostics" / "comprehensive_test_run"
RAG_BASE_URL = os.getenv("RAG_BASE_URL", "http://127.0.0.1:8001")

# Ensure output directory exists
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Full test suite - 44+ test cases across all categories
FULL_TEST_SUITE = {
    "basic_retrieval": [
        "What is the purpose of Aurora WP3.1 upgrade?",
        "What does gPjM 2.0 improve in project estimation?",
        "What is Work Package-based planning?",
        "What are the target users of Aurora WP3.1?",
        "What is the difference between Work Package and Work Item?",
        "What is CloudSpace in Azure?",
        "What are the two tiers of CloudSpace?",
        "What Azure regions are supported by default?",
        "What is included in a CloudSpace location resource group?",
        "What type of access is provided to CloudSpace users?",
        "What is the purpose of GitHub Safe-Settings App?",
        "What is a GitHub runner?",
        "What are the types of GitHub runners?",
        "What is a pull request?",
        "What is Git LFS used for?",
        "What is PMT Labs?",
        "What is the goal of PMT Labs architecture?",
        "What architecture framework is used in PMT Labs?",
        "What are key PMT architecture building blocks?",
        "What is meant by architecture-as-code?",
    ],
    "structured_extraction": [
        "List all key improvements introduced in Aurora WP3.1.",
        "List the phases in Aurora WP3.1 implementation timeline.",
        "List all GitHub repository visibility types.",
        "List all branch protection rule options.",
        "List all main components of CloudSpace architecture.",
        "List all essential features of PMT Labs.",
        "List all GitHub permission levels for repository access.",
        "List all Azure components used in CloudSpace.",
        "List all required permissions for GitHub App.",
        "List all factors configurable in Aurora technical criteria.",
    ],
    "multi_hop_reasoning": [
        "Why does Aurora introduce Work Package-based planning?",
        "How does traceability improve project estimation accuracy?",
        "Why are dropdowns used instead of checkboxes in gPjM 2.0?",
        "How does GitHub Safe-Settings enforce compliance?",
        "Why is branch protection important in GitHub?",
        "Why is CloudSpace better than traditional lab environments?",
        "How does Kubernetes support CloudSpace use cases?",
        "Why is containerization important in PMT Labs?",
        "How does DevOps relate to PMT architecture goals?",
        "Why is cloud-based architecture critical for PMT Labs?",
    ],
    "deep_technical": [
        "When is a requirement classified as System vs Software in Aurora?",
        "How does the Allocation attribute work in DOORS?",
        "How are MO requirements linked to system elements?",
        "What changes were introduced in system architecture design?",
        "How is SW architecture developed in Aurora WP3.3?",
    ],
    "scenario_based": [
        "A project affects both HW and SW → how should requirements be classified?",
        "A GitHub repo needs stricter control → which branch protection rules should be applied?",
        "A team needs isolated cloud resources → which CloudSpace tier should be used?",
        "A developer needs to run CI jobs in custom environment → which runner type should be used?",
        "A system needs high scalability and fast deployment → why should PMT Labs use cloud-native architecture?",
    ],
    "domain_aurora": [
        "What are the current challenges that made Aurora WP3.1 necessary?",
        "What benefits does Aurora WP3.1 provide for project managers?",
        "What benefits does Aurora WP3.1 provide for the organization?",
        "What is meant by 'Complete Project Coverage' in Aurora WP3.1?",
        "What technical criteria can be configured in Aurora WP3.1 effort estimation?",
        "What user interface elements were replaced in gPjM 2.0?",
        "What are the support channels for Aurora WP3.1 users?",
        "Why are no default values used in the technical criteria configuration?",
        "What is not changing in Aurora WP3.1 despite the upgrade?",
        "Which project types are excluded from Aurora WP3.1 scope?",
    ],
    "domain_cloudspace": [
        "What are the main advantages of CloudSpace over Lab?",
        "What is the role of the location resource group in CloudSpace?",
        "What information is required in the POST request to create a CloudSpace?",
        "What IDM roles are needed before and after CloudSpace creation?",
        "How is the final resource group name formed in CloudSpace?",
        "What kinds of Azure resources can users create inside CloudSpace?",
    ],
    "domain_github": [
        "How does Safe-Settings App enforce policy as code in GitHub organizations?",
        "What is the difference between GitHub-hosted and self-hosted runners?",
        "At which levels can self-hosted runners be configured?",
        "What are the main steps to configure an SL4 VM for a self-hosted GitHub runner?",
        "What is the purpose of CODEOWNERS in GitHub?",
        "What are the main benefits of branch protection rules?",
        "What are the key steps to configure autolink references for IBM EWM work items in GitHub?",
        "What is the purpose of integrating GitHub with IBM EWM?",
    ],
    "domain_pmt": [
        "What are the essential top-level functional requirements of PMT Labs?",
        "What are the essential non-functional requirements of PMT Labs?",
        "Why does PMT Labs require support for internet-based clients?",
        "Why is containerized architecture important in PMT Labs?",
        "What are the key stakeholder groups in PMT Labs architecture?",
        "How does PMT Labs connect cloud architecture, DevOps, and AI support in its vision?",
    ],
}

def run_test(query: str, category: str) -> Dict[str, Any]:
    """Run a single test and return result."""
    cmd = [
        sys.executable,
        str(GROUNDED_SCRIPT),
        "--query", query,
        "--rag-url", RAG_BASE_URL,
        "--mode", "diagnostic",
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
        
        # Parse output to extract diagnostic data
        try:
            # Look for JSON in output
            lines = result.stdout.split('\n')
            json_line = next((l for l in lines if l.strip().startswith('{')), None)
            if json_line:
                data = json.loads(json_line)
                return {
                    "status": "PASS" if result.returncode == 0 else "FAIL",
                    "query": query,
                    "category": category,
                    "answer": data.get("answer", ""),
                    "confidence": data.get("confidence", 0.0),
                    "retrieval_score": data.get("retrieval_score", 0.0),
                    "quality_gates_passed": data.get("quality_gates", {}).get("passed", []),
                    "quality_gates_failed": data.get("quality_gates", {}).get("failed", []),
                }
        except (json.JSONDecodeError, StopIteration):
            pass
        
        return {
            "status": "PASS" if result.returncode == 0 else "FAIL",
            "query": query,
            "category": category,
            "answer": result.stdout[:500],
            "confidence": 0.0,
            "retrieval_score": 0.0,
            "quality_gates_passed": [],
            "quality_gates_failed": [],
        }
    except subprocess.TimeoutExpired:
        return {
            "status": "TIMEOUT",
            "query": query,
            "category": category,
            "answer": "",
            "confidence": 0.0,
            "retrieval_score": 0.0,
            "quality_gates_passed": [],
            "quality_gates_failed": [],
        }
    except Exception as e:
        return {
            "status": "ERROR",
            "query": query,
            "category": category,
            "error": str(e),
            "confidence": 0.0,
            "retrieval_score": 0.0,
        }

def main():
    print("=" * 80)
    print("COMPREHENSIVE 44+ TEST SUITE")
    print("=" * 80)
    print(f"Test Start: {datetime.now().isoformat()}")
    print(f"RAG Server: {RAG_BASE_URL}\n")
    
    all_results = []
    category_results = {}
    total_tests = sum(len(tests) for tests in FULL_TEST_SUITE.values())
    
    print(f"Running {total_tests} tests across {len(FULL_TEST_SUITE)} categories...\n")
    
    for category_idx, (category, queries) in enumerate(FULL_TEST_SUITE.items(), 1):
        print(f"[{category_idx}/{len(FULL_TEST_SUITE)}] {category.upper()}: ", end="", flush=True)
        
        category_results[category] = {"passed": 0, "failed": 0, "timeout": 0, "error": 0, "tests": []}
        
        for query_idx, query in enumerate(queries, 1):
            result = run_test(query, category)
            all_results.append(result)
            category_results[category]["tests"].append(result)
            
            if result["status"] == "PASS":
                category_results[category]["passed"] += 1
                print("✓", end="", flush=True)
            elif result["status"] == "FAIL":
                category_results[category]["failed"] += 1
                print("✗", end="", flush=True)
            elif result["status"] == "TIMEOUT":
                category_results[category]["timeout"] += 1
                print("T", end="", flush=True)
            else:
                category_results[category]["error"] += 1
                print("E", end="", flush=True)
        
        print()
    
    # Generate summary
    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80 + "\n")
    
    total_passed = sum(r["passed"] for r in category_results.values())
    total_failed = sum(r["failed"] for r in category_results.values())
    total_timeout = sum(r["timeout"] for r in category_results.values())
    total_error = sum(r["error"] for r in category_results.values())
    pass_rate = (total_passed / total_tests * 100) if total_tests > 0 else 0
    
    print(f"Total Tests: {total_tests}")
    print(f"Passed: {total_passed} ({pass_rate:.1f}%)")
    print(f"Failed: {total_failed}")
    print(f"Timeouts: {total_timeout}")
    print(f"Errors: {total_error}\n")
    
    for category, results in category_results.items():
        total = results["passed"] + results["failed"] + results["timeout"] + results["error"]
        if total > 0:
            pct = (results["passed"] / total * 100)
            print(f"{category}: {results['passed']}/{total} ({pct:.1f}%)")
    
    # Save results
    results_file = OUTPUT_DIR / "test_results_full.json"
    with open(results_file, "w") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "total_tests": total_tests,
            "passed": total_passed,
            "failed": total_failed,
            "timeout": total_timeout,
            "error": total_error,
            "pass_rate": pass_rate,
            "category_results": category_results,
            "all_results": all_results,
        }, f, indent=2)
    
    print(f"\n✓ Results saved to: {results_file}")

if __name__ == "__main__":
    main()
