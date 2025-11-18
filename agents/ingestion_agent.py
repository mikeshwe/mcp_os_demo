"""
Ingestion Agent - Specialized for data ingestion from multiple sources
"""

import os
from typing import Dict, Any, List, Optional
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from agents.mcp_tools import McpToolCaller


class IngestionAgent:
    """Agent responsible for intelligently ingesting data from multiple sources"""
    
    def __init__(self, mcp_caller: McpToolCaller, use_llm: bool = True, model: str = None, use_tool_discovery: bool = False):
        self.mcp_caller = mcp_caller
        self.use_llm = use_llm
        self.use_tool_discovery = use_tool_discovery
        self.llm = None
        self._discovered_tools: Optional[List[Dict[str, Any]]] = None
        
        if use_llm:
            try:
                import os
                if os.getenv("OPENAI_API_KEY"):
                    # Use provided model or fall back to env var or default
                    model = model or os.getenv("LLM_MODEL", "gpt-3.5-turbo")
                    self.llm = ChatOpenAI(model=model, temperature=0)
            except Exception:
                self.use_llm = False
    
    async def _discover_tools(self) -> List[Dict[str, Any]]:
        """Discover available ingestion tools from MCP server"""
        if self._discovered_tools is not None:
            return self._discovered_tools
        
        print("🔍 Discovering ingestion tools from MCP server...")
        try:
            all_tools = await self.mcp_caller.list_tools()
            print(f"   Found {len(all_tools)} total tools from server")
            
            # Filter to ingestion tools (those starting with "ingest_")
            ingestion_tools = [
                tool for tool in all_tools 
                if tool.get("name", "").startswith("ingest_")
            ]
            
            print(f"   Discovered {len(ingestion_tools)} ingestion tools:")
            for tool in ingestion_tools:
                tool_name = tool.get("name", "")
                tool_desc = tool.get("description", "")
                print(f"     • {tool_name}: {tool_desc[:80]}{'...' if len(tool_desc) > 80 else ''}")
            
            self._discovered_tools = ingestion_tools
            return ingestion_tools
        except Exception as e:
            print(f"⚠ Failed to discover tools: {e}")
            return []
    
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
        """Use LLM to determine optimal ingestion order and strategy
        
        When use_tool_discovery is enabled, queries MCP server for available tools
        and uses LLM to select the appropriate tool based on tool descriptions and schemas.
        """
        # If discovery mode is enabled, discover tools first
        if self.use_tool_discovery:
            discovered_tools = await self._discover_tools()
            
            if discovered_tools and self.use_llm and self.llm:
                # Use LLM with discovered tools to select appropriate tool for each file
                return await self._determine_strategy_with_discovery(files, discovered_tools)
            elif discovered_tools:
                # Discovery enabled but no LLM - use discovered tools with fallback logic
                return await self._determine_strategy_with_discovered_tools(files, discovered_tools)
        
        # Fallback to original logic (hardcoded tool selection)
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
    
    async def _determine_strategy_with_discovery(self, files: Dict[str, List[str]], discovered_tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Use LLM with discovered tools to determine ingestion strategy"""
        print("🤖 Using LLM to select tools based on discovered tool schemas...")
        
        # Format discovered tools for LLM
        tools_info = []
        for tool in discovered_tools:
            tool_name = tool.get("name", "")
            tool_desc = tool.get("description", "")
            tool_schema = tool.get("inputSchema", {})
            tools_info.append(f"- {tool_name}: {tool_desc}")
            if tool_schema.get("properties"):
                props = tool_schema["properties"]
                required = tool_schema.get("required", [])
                param_info = ", ".join([f"{k}{' (required)' if k in required else ''}" for k in props.keys()])
                tools_info.append(f"  Parameters: {param_info}")
        
        # Format files for LLM
        files_list = []
        file_path_map = {}
        for file_type, file_list in files.items():
            for file_path in file_list:
                basename = os.path.basename(file_path)
                files_list.append(f"{file_type}: {basename} ({file_path})")
                file_path_map[basename] = file_path
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", """You are a data ingestion specialist. Analyze available files and select the appropriate ingestion tool from the discovered MCP tools.

Available MCP Tools:
{tools}

Your task: For each file, select the most appropriate tool based on:
1. File type/extension
2. File name patterns (e.g., "edgar" or "xbrl" in name → ingest_edgar_xbrl)
3. Tool descriptions and capabilities

Return a JSON array with file paths, tool names, and priority (1=highest)."""),
            ("human", """Files to ingest:
{files}

Return JSON array:
[
  {{"file": "full/path/to/file", "tool": "tool_name_from_discovered_tools", "priority": 1-4}}
]""")
        ])
        
        parser = JsonOutputParser()
        chain = prompt | self.llm | parser
        
        try:
            result = await chain.ainvoke({
                "tools": "\n".join(tools_info),
                "files": "\n".join(files_list)
            })
            
            print("   LLM tool selection results:")
            
            # Validate tool names are in discovered tools
            discovered_tool_names = {tool.get("name") for tool in discovered_tools}
            validated_result = []
            for item in result:
                file_path = item.get("file", "")
                tool_name = item.get("tool", "")
                
                # If LLM returned basename, map to full path
                if file_path in file_path_map:
                    file_path = file_path_map[file_path]
                
                # Validate tool is in discovered tools and allowed
                if tool_name not in discovered_tool_names:
                    # Fallback to hardcoded logic
                    original_tool = tool_name
                    tool_name = self._determine_tool_for_file(file_path)
                    print(f"     ⚠ {os.path.basename(file_path)}: '{original_tool}' not in discovered tools → using {tool_name}")
                else:
                    print(f"     ✓ {os.path.basename(file_path)} → {tool_name} (priority: {item.get('priority', 5)})")
                
                validated_result.append({
                    "file": file_path,
                    "tool": tool_name,
                    "priority": item.get("priority", 5)
                })
            
            return sorted(validated_result, key=lambda x: x.get("priority", 5))
        except Exception as e:
            print(f"⚠ Discovery-based strategy failed: {e}, falling back to hardcoded logic")
            return await self._determine_strategy_with_discovered_tools(files, discovered_tools)
    
    async def _determine_strategy_with_discovered_tools(self, files: Dict[str, List[str]], discovered_tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Use discovered tools with fallback logic (no LLM)"""
        print("📋 Using discovered tools with fallback logic (no LLM)...")
        discovered_tool_names = {tool.get("name") for tool in discovered_tools}
        strategy = []
        
        for memo_file in files.get("memo", []):
            tool = self._determine_tool_for_file(memo_file)
            if tool in discovered_tool_names:
                print(f"     ✓ {os.path.basename(memo_file)} → {tool}")
                strategy.append({"file": memo_file, "tool": tool, "priority": 1})
        
        for excel_file in files.get("excel", []):
            tool = self._determine_tool_for_file(excel_file)
            if tool in discovered_tool_names:
                print(f"     ✓ {os.path.basename(excel_file)} → {tool}")
                strategy.append({"file": excel_file, "tool": tool, "priority": 2})
        
        for csv_file in files.get("csv", []):
            tool = self._determine_tool_for_file(csv_file)
            if tool in discovered_tool_names:
                print(f"     ✓ {os.path.basename(csv_file)} → {tool}")
                strategy.append({"file": csv_file, "tool": tool, "priority": 3})
        
        return sorted(strategy, key=lambda x: x["priority"])
    
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

