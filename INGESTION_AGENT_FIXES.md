# Ingestion Agent Fixes

## Problem
The ingestion agent was using `ingest_csv` instead of `ingest_edgar_xbrl` for EDGAR/XBRL files, causing label mismatches that prevented KPI computation.

## Root Causes

1. **LLM tool selection**: When using LLM, it wasn't explicitly guided to use `ingest_edgar_xbrl` for EDGAR files
2. **No validation**: LLM-selected tools weren't validated against file patterns
3. **File path handling**: LLM received basenames but expected to return full paths, causing mismatches
4. **Fallback logic**: Fallback strategy worked but wasn't used when LLM was available

## Fixes Applied

### 1. Added `_determine_tool_for_file()` Helper Method
```python
def _determine_tool_for_file(self, file_path: str) -> str:
    """Determine the correct ingestion tool based on file path and name"""
    file_lower = file_path.lower()
    filename = os.path.basename(file_path)
    
    # Check for EDGAR/XBRL files first (must use ingest_edgar_xbrl)
    if filename.endswith('.csv') and ("edgar" in file_lower or "xbrl" in file_lower):
        return "ingest_edgar_xbrl"
    
    # ... other file type checks
```

**Benefits:**
- Centralized tool selection logic
- Explicit check for EDGAR/XBRL files
- Reusable in both LLM and fallback paths

### 2. Enhanced LLM Prompt
Added explicit rules to the system prompt:
```
IMPORTANT RULES:
- Files with "edgar" or "xbrl" in the name MUST use "ingest_edgar_xbrl" tool
- Memo/text files (.txt, .md) use "ingest_memo"
- Excel files (.xlsx) use "ingest_excel"
- Generic CSV files use "ingest_csv"
```

**Benefits:**
- Guides LLM to make correct choices
- Reduces ambiguity in tool selection

### 3. Added Tool Selection Validation
After LLM returns results, validate and correct tool selection:
```python
# Validate tool selection matches file type
correct_tool = self._determine_tool_for_file(file_path)
if tool_name != correct_tool:
    print(f"⚠ Correcting tool selection for {os.path.basename(file_path)}: {tool_name} → {correct_tool}")
    tool_name = correct_tool
```

**Benefits:**
- Ensures correct tool is always used, even if LLM makes a mistake
- Provides visibility when corrections are made

### 4. Fixed File Path Mapping
Added mapping from basename to full path:
```python
file_path_map = {}  # Map basename to full path
for file_path in file_list:
    basename = os.path.basename(file_path)
    files_list.append(f"{file_type}: {basename}")
    file_path_map[basename] = file_path
```

**Benefits:**
- Handles cases where LLM returns basename instead of full path
- Ensures correct file paths are used

### 5. Improved Fallback Strategy
Updated fallback to use the helper method:
```python
for csv_file in files.get("csv", []):
    tool = self._determine_tool_for_file(csv_file)
    strategy.append({"file": csv_file, "tool": tool, "priority": 3})
```

**Benefits:**
- Consistent tool selection logic
- Guarantees correct tool selection in fallback mode

## Expected Behavior After Fix

1. **EDGAR/XBRL files** (`edgar_xbrl_q3_2025.csv`) will use `ingest_edgar_xbrl`
2. **Labels will be normalized** (e.g., `"us-gaap:Revenues"` → `"Revenue"`)
3. **KPI computation will work** because labels match what `compute_kpis` expects
4. **Tool selection is validated** even when LLM is used

## Testing

Run the demo to verify:
```bash
python demo_nondet_workflow.py
```

Expected output:
```
✓ Ingested ingest_edgar_xbrl: edgar_xbrl_q3_2025.csv
```

Instead of:
```
✓ Ingested ingest_csv: edgar_xbrl_q3_2025.csv  # ❌ Wrong tool
```

