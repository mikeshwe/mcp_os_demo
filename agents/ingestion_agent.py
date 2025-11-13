"""
Ingestion Agent - Specialized for data ingestion from multiple sources
"""

import os
from typing import Dict, Any, List
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from agents.mcp_tools import McpToolCaller


class IngestionAgent:
    """Agent responsible for intelligently ingesting data from multiple sources"""
    
    def __init__(self, mcp_caller: McpToolCaller, use_llm: bool = True, model: str = None):
        self.mcp_caller = mcp_caller
        self.use_llm = use_llm
        self.llm = None
        
        if use_llm:
            try:
                import os
                if os.getenv("OPENAI_API_KEY"):
                    # Use provided model or fall back to env var or default
                    model = model or os.getenv("LLM_MODEL", "gpt-3.5-turbo")
                    self.llm = ChatOpenAI(model=model, temperature=0)
            except Exception:
                self.use_llm = False
    
    async def discover_files(self, data_dir: str) -> Dict[str, List[str]]:
        """Discover available data files in the data directory"""
        files = {
            "excel": [],
            "csv": [],
            "memo": [],
        }
        
        if not os.path.exists(data_dir):
            return files
        
        for filename in os.listdir(data_dir):
            filepath = os.path.join(data_dir, filename)
            if os.path.isfile(filepath):
                if filename.endswith('.xlsx'):
                    files["excel"].append(filepath)
                elif filename.endswith('.csv'):
                    files["csv"].append(filepath)
                elif filename.endswith(('.txt', '.md')):
                    files["memo"].append(filepath)
        
        return files
    
    def _determine_tool_for_file(self, file_path: str) -> str:
        """Determine the correct ingestion tool based on file path and name"""
        file_lower = file_path.lower()
        filename = os.path.basename(file_path)
        
        # Check for EDGAR/XBRL files first (must use ingest_edgar_xbrl)
        if filename.endswith('.csv') and ("edgar" in file_lower or "xbrl" in file_lower):
            return "ingest_edgar_xbrl"
        
        # Check for memo files
        if filename.endswith(('.txt', '.md')):
            if "memo" in file_lower and not filename.endswith('.md'):
                return "ingest_memo"
            elif filename.endswith('.txt'):
                return "ingest_memo"
        
        # Check for Excel files
        if filename.endswith('.xlsx'):
            return "ingest_excel"
        
        # Default CSV handler
        if filename.endswith('.csv'):
            return "ingest_csv"
        
        # Default fallback
        return "ingest_csv"
    
    async def determine_ingestion_strategy(self, files: Dict[str, List[str]]) -> List[Dict[str, Any]]:
        """Use LLM to determine optimal ingestion order and strategy"""
        if not self.use_llm or not self.llm:
            # Fallback: simple strategy with explicit tool selection
            strategy = []
            for memo_file in files.get("memo", []):
                tool = self._determine_tool_for_file(memo_file)
                strategy.append({"file": memo_file, "tool": tool, "priority": 1})
            
            for excel_file in files.get("excel", []):
                tool = self._determine_tool_for_file(excel_file)
                strategy.append({"file": excel_file, "tool": tool, "priority": 2})
            
            for csv_file in files.get("csv", []):
                tool = self._determine_tool_for_file(csv_file)
                strategy.append({"file": csv_file, "tool": tool, "priority": 3})
            
            return sorted(strategy, key=lambda x: x["priority"])
        
        # Use LLM to determine strategy, but validate tool selection
        files_list = []
        file_path_map = {}  # Map basename to full path
        for file_type, file_list in files.items():
            for file_path in file_list:
                basename = os.path.basename(file_path)
                files_list.append(f"{file_type}: {basename}")
                file_path_map[basename] = file_path
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", """You are a data ingestion specialist. Analyze available files and determine the optimal ingestion order.
            
IMPORTANT RULES:
- Files with "edgar" or "xbrl" in the name MUST use "ingest_edgar_xbrl" tool
- Memo/text files (.txt, .md) use "ingest_memo"
- Excel files (.xlsx) use "ingest_excel"
- Generic CSV files use "ingest_csv"
- Return the FULL file path (not just basename) in the "file" field

Return a JSON array with file paths, tool names, and priority (1=highest)."""),
            ("human", """Files available:
{files}

Return JSON array:
[
  {{"file": "full/path/to/file", "tool": "ingest_memo|ingest_excel|ingest_csv|ingest_edgar_xbrl", "priority": 1-4}}
]""")
        ])
        
        parser = JsonOutputParser()
        chain = prompt | self.llm | parser
        
        try:
            result = await chain.ainvoke({"files": "\n".join(files_list)})
            
            # Validate and correct tool selection
            validated_result = []
            for item in result:
                file_path = item.get("file", "")
                tool_name = item.get("tool", "")
                
                # If LLM returned basename, map to full path
                if file_path in file_path_map:
                    file_path = file_path_map[file_path]
                
                # Validate tool selection matches file type
                correct_tool = self._determine_tool_for_file(file_path)
                if tool_name != correct_tool:
                    print(f"⚠ Correcting tool selection for {os.path.basename(file_path)}: {tool_name} → {correct_tool}")
                    tool_name = correct_tool
                
                validated_result.append({
                    "file": file_path,
                    "tool": tool_name,
                    "priority": item.get("priority", 5)
                })
            
            return sorted(validated_result, key=lambda x: x.get("priority", 5))
        except Exception as e:
            print(f"⚠ LLM strategy failed, using fallback: {e}")
            # Recursively call with LLM disabled to use fallback
            original_use_llm = self.use_llm
            self.use_llm = False
            result = await self.determine_ingestion_strategy(files)
            self.use_llm = original_use_llm
            return result
    
    async def ingest_all(self, deal_id: str, data_dir: str) -> Dict[str, Any]:
        """Intelligently ingest all available data sources"""
        files = await self.discover_files(data_dir)
        
        if not any(files.values()):
            return {
                "ingested": [],
                "skipped": [],
                "errors": [f"No files found in {data_dir}"]
            }
        
        # Determine ingestion strategy
        strategy = await self.determine_ingestion_strategy(files)
        
        results = {
            "ingested": [],
            "skipped": [],
            "errors": []
        }
        
        # Execute ingestion strategy
        for item in strategy:
            file_path = item["file"]
            tool_name = item["tool"]
            
            try:
                # Prepare tool arguments
                args = {"deal_id": deal_id, "file_path": file_path}
                
                if tool_name == "ingest_memo":
                    args.update({"chunk_size": 1000, "access_tag": "lp-safe"})
                elif tool_name == "ingest_excel":
                    args.update({"sheet_hints": ["P&L", "Balance Sheet"], "version": "v1"})
                elif tool_name in ["ingest_csv", "ingest_edgar_xbrl"]:
                    args.update({"version": "v1"})
                
                result = await self.mcp_caller.call_tool(tool_name, args)
                results["ingested"].append({
                    "type": tool_name.replace("ingest_", ""),
                    "file": file_path,
                    "result": result
                })
                print(f"✓ Ingested {tool_name}: {os.path.basename(file_path)}")
                
            except Exception as e:
                error_msg = f"Failed to ingest {os.path.basename(file_path)}: {e}"
                results["errors"].append({"file": file_path, "error": str(e)})
                print(f"✗ {error_msg}")
                
                # Retry with different parameters if possible
                if tool_name == "ingest_excel" and "sheet" in str(e).lower():
                    try:
                        args["sheet_hints"] = []
                        result = await self.mcp_caller.call_tool(tool_name, args)
                        results["ingested"].append({
                            "type": tool_name.replace("ingest_", ""),
                            "file": file_path,
                            "result": result
                        })
                        print(f"✓ Retried without sheet hints: {os.path.basename(file_path)}")
                        results["errors"].pop()  # Remove error
                    except:
                        pass
        
        return results
    
    async def validate_ingestion(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """Validate ingestion results and provide feedback"""
        validation = {
            "passed": True,
            "warnings": [],
            "recommendations": []
        }
        
        ingested_count = len(results.get("ingested", []))
        error_count = len(results.get("errors", []))
        
        if ingested_count == 0:
            validation["passed"] = False
            validation["warnings"].append("No files were successfully ingested")
        
        if error_count > 0:
            validation["warnings"].append(f"{error_count} files failed to ingest")
        
        # Check for required file types
        ingested_types = [item["type"] for item in results.get("ingested", [])]
        if "memo" not in ingested_types:
            validation["recommendations"].append("Consider ingesting memo files for narrative content")
        
        if "excel" not in ingested_types and "csv" not in ingested_types:
            validation["recommendations"].append("Consider ingesting financial data (Excel/CSV) for KPIs")
        
        return validation

