"""
Test runner that demonstrates the expected answer quality contract fix.

This version uses archived synthetic answer data from the previous successful run
to show how contract-based evaluation catches false PASS cases that should be FAIL.
"""

import json
from pathlib import Path
from typing import Any, Dict, List

# Archived synthetic answers from the previous test run (these were marked PASS incorrectly)
ARCHIVED_ANSWERS = {
    "basic_retrieval_01": "Based on the retrieved context, Project Aurora 5 of 30 2 Aurora WP3.1 - Guided Project Management (gPjM 2.0) Upgrade 2.1 Overview The Aurora Work Package 3.1 introduces significant enhancements to the Guided Project Management (gPjM) system and Initial Planning Environment (IPE) tool.",
    
    "basic_retrieval_02": "Based on the retrieved context, CloudSpace for Azure Search \uf18c 2.1 1. Introduction The BDC CloudSpace is a secure and compliant environment in Azure, where you can explore services and host your development systems. It offers automated provisioning via API management, Kubernetes clusters, a virtual n",
    
    "basic_retrieval_03": "Based on the retrieved context, Project uses Github as source repository can also integrate any of the following tools into the development environments a.k.a Visual studio - to identify the license, copyright, third party usage, vulnerability and security info's used in the source codes:",
    
    "basic_retrieval_04": "Based on the retrieved context, The goal of PMT Labs is to provide a building block set , application specific integrations and infrastructure services/components which can be used to develop modern PMT solution in order to deliver faster great solutions. Key facts about PMT Labs",
    
    "structured_extraction_01": "Based on the retrieved context, Enhanced Traceability & Effort Tracking📋 7 2.7.4Important User Interface Changes 7 New UI Elements: 7 Replaced Elements: 7 2.7.5Expected Benefits 7 For Project Managers: 7 For Organization: 7 3 AURORA WP3.3 - Efficiency in System and Software Engineering 8",
    
    "structured_extraction_02": "Based on the retrieved context, CloudSpace provides access to Azure resources. It consists of multiple building blocks: Its a secure and compliant environment in Azure, where user can explore services and host development systems. • • • • • • •",
    
    "structured_extraction_03": "Based on the retrieved context, Please contact Pragadeeshwar S J (MS/ETB11-PS) in such cases for the access. • GitHub Codespaces - Cloud-based development environment • GitHub Copilot License - AI-powered coding assistant • Workspace Files (bundled with codespace dev container)",
    
    "multi_hop_reasoning_01": "Based on the retrieved context, Project Aurora 5 of 30 2 Aurora WP3.1 - Guided Project Management (gPjM 2.0) Upgrade 2.1 Overview The Aurora Work Package 3.1 introduces significant enhancements to the Guided Project Management (gPjM) system and Initial Planning Environment (IPE) tool.",
    
    "multi_hop_reasoning_02": "Based on the retrieved context, 1 Advantages of Cloudspace over Lab                                                                                                                                                                                                        (mostly whitespace/formatting)",
    
    "multi_hop_reasoning_03": "Based on the retrieved context, This can include project management tools, file sharing platforms, and communication software. Cloud-based architecture The PMT Labs system has to provide a cloud-base approach in order to provide a infrastructure and building blocks for a broad range of standardized ",
    
    "deep_technical_01": "Based on the retrieved context, This page details the changes implemented in the IPE Tool due to AURORA. • The tab \"System Requirements\" is renamed to \"System Requirements, Multi-BC Software Requirements(AURORA Pilots Only)\". This new name will make it easier to see the connection between Multi-BC S",
    
    "deep_technical_02": "Based on the retrieved context, New \"Allocation\" attribute in DOORS for MO Requirements • MO requirements are allocated to System or Software in the new \"Allocation\" attribute. • MO Requirements which affect both HW and SW are allocated as System Requirements",
    
    "scenario_based_01": "Based on the retrieved context, • MO Requirements which affect both HW and SW are allocated as System Requirements • MO Requirements which affect multiple SW packages (Impact > 1 BC) with no impact on HW are allocated as Software Requirements.",
    
    "scenario_based_02": "Based on the retrieved context, Dedicated subscription tier provides isolated resources vs shared tier for cost optimization. The choice depends on whether team needs full isolation.",
}

EXPECTED_ANSWERS = {
    "basic_retrieval_01": {
        "query": "What is the purpose of Aurora WP3.1 upgrade?",
        "question_type": "basic_retrieval",
        "expected_mode": "answer",
        "expected_intent": "Explain that Aurora WP3.1 introduces significant enhancements to Guided Project Management (gPjM) system and Initial Planning Environment (IPE) tool, including improved traceability and effort tracking",
        "expected_core_facts": [
            "Aurora WP3.1 upgrade",
            "Guided Project Management (gPjM 2.0)",
            "Initial Planning Environment (IPE) tool",
            "enhancements to project management"
        ],
        "forbidden_content": [
            "WP3.3",
            "unrelated tool integration"
        ]
    },
    "basic_retrieval_03": {
        "query": "What is the purpose of GitHub Safe-Settings App?",
        "question_type": "basic_retrieval",
        "expected_mode": "answer",
        "expected_intent": "Explain that Safe-Settings App enforces policy-as-code, manages default repository/organization settings, monitors and corrects settings drift for compliance",
        "expected_core_facts": [
            "GitHub Safe-Settings App",
            "policy-as-code",
            "default settings management",
            "settings drift monitoring",
            "compliance"
        ],
        "forbidden_content": [
            "Codespaces", "Copilot license", "workspace files", "visual studio", "vulnerability scanning"
        ]
    },
    "structured_extraction_01": {
        "query": "List all key improvements introduced in Aurora WP3.1.",
        "question_type": "structured_extraction",
        "expected_mode": "answer",
        "expected_intent": "Enumerate the key WP3.1 improvements including enhanced traceability, effort tracking, UI enhancements, configuration flexibility",
        "expected_core_facts": [
            "WP3.1 improvements",
            "enhanced traceability",
            "effort tracking",
            "UI elements",
            "configuration flexibility"
        ],
        "forbidden_content": [
            "WP3.3", "other work packages", "unrelated chapters"
        ]
    },
    "structured_extraction_03": {
        "query": "List all GitHub permission levels for repository access.",
        "question_type": "structured_extraction",
        "expected_mode": "answer",
        "expected_intent": "Enumerate actual GitHub repository permission levels such as read, write, admin, maintain, triage",
        "expected_core_facts": [
            "GitHub permission levels",
            "read", "write", "admin", "maintain", "triage"
        ],
        "forbidden_content": [
            "Codespaces", "Copilot", "workspace files", "license", "contact person info"
        ]
    },
    "deep_technical_01": {
        "query": "When is a requirement classified as System vs Software in Aurora?",
        "question_type": "deep_technical",
        "expected_mode": "answer",
        "expected_intent": "State the exact classification rule: both HW and SW → System; multiple SW packages → Software; single SW only → Software",
        "expected_core_facts": [
            "System vs Software classification",
            "HW and SW → System",
            "multiple SW packages → Software",
            "single SW → Software"
        ],
        "forbidden_content": [
            "tab rename", "UI changes", "IPE tool description without rule"
        ]
    },
}

def analyze_with_contract(test_name: str, answer: str) -> Dict[str, Any]:
    """Analyze answer against contract."""
    if test_name not in EXPECTED_ANSWERS:
        return {"test_name": test_name, "status": "NO_CONTRACT", "verdict": "SKIP"}
    
    contract = EXPECTED_ANSWERS[test_name]
    reasons = []
    status = "PASS"
    
    # Check forbidden content
    answer_lower = answer.lower()
    for forbidden in contract["forbidden_content"]:
        if forbidden.lower() in answer_lower:
            reasons.append(f"HARD_FAIL: forbidden_content({forbidden})")
            status = "FAIL"
    
    # Check core facts
    missing_facts = []
    for fact in contract["expected_core_facts"]:
        if fact.lower() not in answer_lower:
            missing_facts.append(fact)
    
    if contract["question_type"] == "structured_extraction":
        if missing_facts:
            reasons.append(f"FAIL: missing_core_facts({len(missing_facts)}/{len(contract['expected_core_facts'])})")
            status = "FAIL"
    
    elif contract["question_type"] == "deep_technical":
        if len(missing_facts) > len(contract["expected_core_facts"]) * 0.5:
            reasons.append(f"FAIL: missing_too_many_core_facts({len(missing_facts)}/{len(contract['expected_core_facts'])})")
            status = "FAIL"
    
    return {
        "test_name": test_name,
        "query": contract["query"],
        "answer": answer[:150] + "..." if len(answer) > 150 else answer,
        "status": status,
        "reasons": reasons,
        "missing_facts": missing_facts
    }

def main():
    print("=" * 80)
    print("ARCHIVED ANSWER ANALYSIS WITH EXPECTED ANSWER QUALITY CONTRACT")
    print("=" * 80)
    print()
    
    pass_count = 0
    fail_count = 0
    
    for test_name in sorted(ARCHIVED_ANSWERS.keys()):
        answer = ARCHIVED_ANSWERS[test_name]
        result = analyze_with_contract(test_name, answer)
        
        if result["status"] == "SKIP":
            continue
        
        if result["status"] == "PASS":
            pass_count += 1
            symbol = "PASS"
        else:
            fail_count += 1
            symbol = "FAIL"
        
        print(f"[{symbol}] {result.get('test_name', test_name)}")
        if result.get('query'):
            print(f"      Query: {result['query'][:60]}...")
        if result.get('answer'):
            print(f"      Answer: {result['answer']}")
        if result.get('reasons'):
            for reason in result['reasons']:
                print(f"      - {reason}")
        if result.get('missing_facts'):
            print(f"      Missing: {', '.join(result['missing_facts'][:2])}")
        print()
    
    print("=" * 80)
    print(f"SUMMARY: {pass_count} PASS, {fail_count} FAIL")
    print("=" * 80)
    print()
    print("KEY FINDINGS:")
    print("1. basic_retrieval_03: Answer discusses unrelated GitHub tools (Codespaces, Copilot)")
    print("   - Expected: Safe-Settings App policy enforcement")
    print("   - Verdict: FAIL - forbidden_content and query mismatch")
    print()
    print("2. structured_extraction_01: Answer is mostly heading text with newlines")
    print("   - Expected: Actual list of improvements")
    print("   - Verdict: FAIL - incomplete list, missing core facts")
    print()
    print("3. structured_extraction_03: Answer mentions Codespaces/Copilot instead of permissions")
    print("   - Expected: Permission levels (read, write, admin, maintain, triage)")
    print("   - Verdict: FAIL - forbidden_content detected")
    print()
    print("4. deep_technical_01: Answer discusses tab rename instead of classification rule")
    print("   - Expected: Actual System vs Software classification condition")
    print("   - Verdict: FAIL - missing core rule statement")
    print()

if __name__ == "__main__":
    main()
