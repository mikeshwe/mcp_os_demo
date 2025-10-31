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
    
    async def determine_ingestion_strategy(self, files: Dict[str, List[str]]) -> List[Dict[str, Any]]:
        """Use LLM to determine optimal ingestion order and strategy"""
        if not self.use_llm or not self.llm:
            # Fallback: simple strategy
            strategy = []
            for memo_file in files.get("memo", []):
                if "memo" in memo_file.lower() and not memo_file.endswith('.md'):
                    strategy.append({"file": memo_file, "tool": "ingest_memo", "priority": 1})
            
            for excel_file in files.get("excel", []):
                strategy.append({"file": excel_file, "tool": "ingest_excel", "priority": 2})
            
            for csv_file in files.get("csv", []):
                if "edgar" in csv_file.lower() or "xbrl" in csv_file.lower():
                    strategy.append({"file": csv_file, "tool": "ingest_edgar_xbrl", "priority": 3})
                else:
                    strategy.append({"file": csv_file, "tool": "ingest_csv", "priority": 4})
            
            return sorted(strategy, key=lambda x: x["priority"])
        
        # Use LLM to determine strategy
        files_list = []
        for file_type, file_list in files.items():
            for file_path in file_list:
                files_list.append(f"{file_type}: {os.path.basename(file_path)}")
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", """You are a data ingestion specialist. Analyze available files and determine the optimal ingestion order.
            Return a JSON array with file paths, tool names, and priority (1=highest)."""),
            ("human", """Files available:
{files}

Return JSON array:
[
  {{"file": "path/to/file", "tool": "ingest_memo|ingest_excel|ingest_csv|ingest_edgar_xbrl", "priority": 1-4}}
]""")
        ])
        
        parser = JsonOutputParser()
        chain = prompt | self.llm | parser
        
        try:
            result = await chain.ainvoke({"files": "\n".join(files_list)})
            return sorted(result, key=lambda x: x.get("priority", 5))
        except Exception as e:
            print(f"⚠ LLM strategy failed, using fallback: {e}")
            return await self.determine_ingestion_strategy(files)  # Fallback
    
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

