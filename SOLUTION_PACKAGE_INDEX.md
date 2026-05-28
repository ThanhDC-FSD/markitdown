# Grounding Summary Schema Mismatch - Complete Solution Package

## 📋 Documentation Index

### Start Here 👇

#### 1. **[QUICK_FIX_GROUNDING_SUMMARY.md](QUICK_FIX_GROUNDING_SUMMARY.md)** ⭐ START HERE
- Problem in 30 seconds
- 3 fix options with code
- Testing instructions
- Debugging checklist
- **Read time**: 5 minutes

#### 2. **[COMPLETE_ANALYSIS_AND_SOLUTION.md](COMPLETE_ANALYSIS_AND_SOLUTION.md)** - Full Context
- Executive summary
- Technical analysis
- Two-layer problem breakdown
- Implementation details
- Testing & validation
- **Read time**: 15 minutes

#### 3. **[GROUNDING_SUMMARY_FIX_GUIDE.md](GROUNDING_SUMMARY_FIX_GUIDE.md)** - Deep Dive
- Root cause analysis
- Evidence-based findings
- Verification steps
- Implementation checklist
- Files to modify
- **Read time**: 20 minutes

#### 4. **[DIAGNOSTIC_ENHANCEMENTS.md](DIAGNOSTIC_ENHANCEMENTS.md)** - Tool Details
- What was enhanced
- Before/after comparison
- How to use enhanced tool
- Key discoveries
- Next steps
- **Read time**: 10 minutes

---

## 🔍 The Problem

```json
{
  "success": false,
  "error": {
    "code": "RESPONSE_SCHEMA_MISMATCH",
    "detail": {"field": "grounding_summary", "expected": "dict"}
  }
}
```

**Root Cause**: Copilot API's LLM returns a response that fails provider's schema validation.

**Evidence**: `llm_response_schema_valid: false`

**Impact**: Queries return empty answers, no generation executed.

---

## ✅ What Was Done

### 1. **Enhanced Diagnostic Tool**
Added schema analysis capabilities to `grounded_qa_diagnostic.py`:

```python
# New function
analyze_grounding_summary_schema(copilot_json)
```

**Capabilities**:
- Validates `grounding_summary` structure
- Lists expected vs actual fields
- Detects type mismatches
- Reports issues clearly
- Generates JSON analysis file

**Output**:
```json
{
  "schema_valid": true,
  "expected_fields": [...],
  "present_fields": [...],
  "missing_fields": [],
  "field_types": {...},
  "issues": [],
  "debug_info": "✓ grounding_summary schema is valid"
}
```

### 2. **New Diagnostic Output File**
Each diagnostic run now generates:
```
diagnostics/grounded_qa_runs/diag_*/grounding_summary_analysis.json
```

### 3. **Enhanced Summary**
Diagnostic summary now includes detailed section:
```markdown
## Grounding Summary Schema Analysis
- schema_valid: [true/false]
- grounding_summary_present: [true/false]
- expected_fields: [list]
- present_fields: [list]
- missing_fields: [list]
- field_types: {mapping}
- issues: [list]
- debug_info: [string]
```

### 4. **Comprehensive Documentation**
Created 4 detailed guides + this index:
- Quick fix reference (5 min read)
- Complete analysis (15 min read)
- Fix guide with verification (20 min read)
- Diagnostic enhancements (10 min read)

---

## 🛠️ The Solution

### Three Fix Options (Choose One)

#### **Option 1: Update LLM Prompt** ⭐ RECOMMENDED
**Why**: Fixes root cause at source  
**Where**: Copilot API LLM system prompt  
**Time**: 30 minutes  
**How**: Add explicit `grounding_summary` format to prompt

#### **Option 2: Add Response Normalization**
**Why**: Defensive layer, handles provider variations  
**Where**: RAG response adapter  
**Time**: 20 minutes  
**How**: Normalize invalid grounding_summary to valid structure

#### **Option 3: Relax Provider Validation**
**Why**: Graceful fallback  
**Where**: Copilot API response validator  
**Time**: 30 minutes  
**How**: Log warning but don't fail on schema mismatch

---

## 🚀 Quick Start

### 1. Run Enhanced Diagnostic
```bash
cd /path/to/markitdown
python src/diagnostics/grounded_qa_diagnostic.py \
  --cases-file src/diagnostics/grounded_qa_cases.json \
  --output-dir diagnostics/grounded_qa_runs
```

### 2. Check Analysis
```bash
cat diagnostics/grounded_qa_runs/diag_*/grounding_summary_analysis.json
```

### 3. Choose Fix
Open [QUICK_FIX_GROUNDING_SUMMARY.md](QUICK_FIX_GROUNDING_SUMMARY.md)
- Pick Option 1, 2, or 3
- Follow code example
- Modify one file
- Test

### 4. Verify
```bash
# Rerun diagnostic
python src/diagnostics/grounded_qa_diagnostic.py ...

# Check for:
# llm_response_schema_valid: true ✅
# answer: "..." (not empty) ✅
# grounding_summary_analysis.schema_valid: true ✅
```

---

## 📊 Key Findings

### Finding 1: Layered Issue
- **Response Layer**: ✅ Valid (fallback is correct)
- **Provider Layer**: ❌ Invalid (LLM output fails validation)

### Finding 2: Root Cause
The Copilot API's LLM is not explicitly told to include a properly formatted `grounding_summary` field.

### Finding 3: Not a Format Issue
This is NOT about how the response is structured. It's about what the LLM generates internally before schema validation.

### Finding 4: Multiple Model Failures
All attempted models failed:
- gpt-5-mini
- gpt-4.1
- gpt-4o
- claude-sonnet-4.6

This suggests the issue is with the prompt, not the models.

---

## 📁 Modified Files

### 1. **src/diagnostics/grounded_qa_diagnostic.py** (Enhanced)
```python
# Added function (70 lines)
def analyze_grounding_summary_schema(copilot_json):
    """Analyze grounding_summary field for schema compliance."""
    ...

# Integrated into make_summary()
grounding_analysis = analyze_grounding_summary_schema(copilot_json)

# New output in run_case()
write_json(case_output_dir / "grounding_summary_analysis.json", grounding_analysis)
```

### 2. **New Documentation Files**
- `QUICK_FIX_GROUNDING_SUMMARY.md`
- `COMPLETE_ANALYSIS_AND_SOLUTION.md`
- `GROUNDING_SUMMARY_FIX_GUIDE.md`
- `DIAGNOSTIC_ENHANCEMENTS.md`
- `SOLUTION_PACKAGE_INDEX.md` (this file)

---

## ✨ Tool Improvements

### Before Enhancement
```
❌ Error: field=grounding_summary, expected=dict
❌ No insight into schema requirements
❌ No field analysis
❌ Manual JSON inspection needed
```

### After Enhancement
```
✅ Detailed schema analysis
✅ Lists all expected vs actual fields
✅ Automatic issue detection
✅ JSON analysis file for programmatic use
✅ Human-readable summaries
✅ Clear debugging information
```

---

## 🎯 Success Metrics

After implementing a fix, verify:
- [ ] `llm_response_schema_valid: true`
- [ ] `answer` is not empty
- [ ] `grounding_summary` contains used_context_ranks
- [ ] Diagnostic runs without errors
- [ ] `grounding_summary_analysis.json` shows `schema_valid: true`
- [ ] End-to-end query succeeds

---

## 📚 Reading Guide

**If you have 5 minutes**: Read [QUICK_FIX_GROUNDING_SUMMARY.md](QUICK_FIX_GROUNDING_SUMMARY.md)

**If you have 15 minutes**: Read [QUICK_FIX_GROUNDING_SUMMARY.md](QUICK_FIX_GROUNDING_SUMMARY.md) + [COMPLETE_ANALYSIS_AND_SOLUTION.md](COMPLETE_ANALYSIS_AND_SOLUTION.md)

**If you have 30 minutes**: Read all 4 documents in order:
1. QUICK_FIX_GROUNDING_SUMMARY.md
2. DIAGNOSTIC_ENHANCEMENTS.md
3. COMPLETE_ANALYSIS_AND_SOLUTION.md
4. GROUNDING_SUMMARY_FIX_GUIDE.md

---

## 🔧 Next Actions

1. **Understand the Problem** (5 min)
   - Read QUICK_FIX_GROUNDING_SUMMARY.md

2. **Choose Your Fix** (5 min)
   - Option 1: Update LLM prompt (recommended)
   - Option 2: Add normalization
   - Option 3: Relax validation

3. **Implement Fix** (20-30 min)
   - Modify appropriate file
   - Test with one query

4. **Validate** (10 min)
   - Run enhanced diagnostic
   - Verify success metrics
   - Test with multiple queries

5. **Document** (10 min)
   - Record what was changed
   - Note what worked
   - Plan for similar issues

---

## 📞 Diagnostics Commands

### Run Full Diagnostic
```bash
python src/diagnostics/grounded_qa_diagnostic.py \
  --cases-file src/diagnostics/grounded_qa_cases.json \
  --output-dir diagnostics/grounded_qa_runs
```

### Run with Specific Query
```bash
python src/diagnostics/grounded_qa_diagnostic.py \
  --query "Why are internet based clients important?" \
  --mode both \
  --output-dir diagnostics/grounded_qa_runs
```

### Run with Log Files
```bash
python src/diagnostics/grounded_qa_diagnostic.py \
  --cases-file src/diagnostics/grounded_qa_cases.json \
  --output-dir diagnostics/grounded_qa_runs \
  --copilot-log-file /path/to/copilot-api.log \
  --rag-log-glob "/path/to/logs/api_*.log"
```

---

## 🎓 Learning Resources

- **Request-ID anchored logging**: See `collect_log_excerpt()` in diagnostic tool
- **Schema validation**: See `analyze_grounding_summary_schema()` implementation
- **Response normalization**: See Option 2 code example
- **LLM prompting**: See Option 1 prompt template

---

## Summary

✅ **Root Cause Identified**: LLM not generating valid grounding_summary  
✅ **Evidence Found**: Schema validation fails at provider level  
✅ **Solution Provided**: 3 fix options with code examples  
✅ **Tool Enhanced**: Diagnostic now analyzes grounding_summary schema  
✅ **Documentation Created**: 4 comprehensive guides  

**Status**: Ready to implement and deploy fix.

