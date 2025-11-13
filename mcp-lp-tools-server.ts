// MCP LP One-Pager Tools – Complete MCP server (TypeScript)
// Implements all ingestion tools, compute tools, and rendering tools per PRD v0.2.0
//
// Tools:
//  Ingestion: ingest_excel, ingest_csv, ingest_memo, ingest_billing, ingest_edgar_xbrl, ingest_snowflake
//  Compute: compute_kpis
//  Rendering: get_golden_facts, get_kpi_lineage, render_onepager_markdown, register_output
//
// Prereqs:
//  - Node 20+
//  - Postgres running the context-store schema (see sql/01_schema.sql)
//  - npm i @modelcontextprotocol/sdk zod pg dayjs xlsx csv-parse express cors
//
// Start:
//  DB_URL=postgres://mcp:mcp@localhost:5433/mcp_ctx npx tsx mcp-lp-tools-server.ts

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StreamableHTTPServerTransport } from "@modelcontextprotocol/sdk/server/streamableHttp.js";
import { z } from "zod";
import { Pool } from "pg";
import dayjs from "dayjs";
import * as fs from "fs";
import * as path from "path";
import * as crypto from "crypto";
import * as XLSX from "xlsx";
// @ts-ignore
import { parse as parseCsvSync } from "csv-parse/sync";
import { isInitializeRequest } from "@modelcontextprotocol/sdk/types.js";
import { randomUUID } from "crypto";
import express from "express";
import cors from "cors";
import dotenv from "dotenv";

// Load environment variables from .env file
dotenv.config();

// ---------- DB helpers ----------
const DB_URL = process.env.DB_URL ?? "postgres://mcp:mcp@localhost:5433/mcp_ctx";
// Use Pool instead of Client for better concurrency and connection management
const pgPool = new Pool({ 
  connectionString: DB_URL,
  max: 20, // Maximum number of clients in the pool
  idleTimeoutMillis: 30000, // Close idle clients after 30 seconds
  connectionTimeoutMillis: 2000, // Return an error after 2 seconds if connection could not be established
});

// ---------- Embedding helpers ----------
// Uses ChromaDB via Python script for local embeddings (no API key needed)

async function generateEmbeddingPython(text: string): Promise<number[]> {
  const { exec } = await import('child_process');
  const { promisify } = await import('util');
  const execAsync = promisify(exec);
  
  try {
    const scriptPath = path.join(process.cwd(), 'scripts', 'generate_embeddings_python.py');
    const venvPython = path.join(process.cwd(), 'venv', 'bin', 'python3');
    const pythonCmd = fs.existsSync(venvPython) ? venvPython : 'python3';
    
    // Properly escape text for shell - use base64 encoding to avoid shell injection
    const textB64 = Buffer.from(text).toString('base64');
    const { stdout, stderr } = await execAsync(`"${pythonCmd}" "${scriptPath}" "${textB64}"`);
    
    if (stderr && stderr.trim()) {
      console.warn("Python script stderr:", stderr);
    }
    
    const result = JSON.parse(stdout);
    if (result.error) {
      throw new Error(result.error);
    }
    
    // Handle both single embedding and array of embeddings
    const embeddings = Array.isArray(result) ? result : [result];
    return Array.isArray(embeddings[0]) ? embeddings[0] : embeddings;
  } catch (error: any) {
    console.error("Error generating embedding via Python:", error.message);
    throw new Error(`Failed to generate embedding: ${error.message}`);
  }
}

async function generateEmbeddingsPython(texts: string[]): Promise<number[][]> {
  const { exec } = await import('child_process');
  const { promisify } = await import('util');
  const execAsync = promisify(exec);
  
  try {
    const scriptPath = path.join(process.cwd(), 'scripts', 'generate_embeddings_python.py');
    const venvPython = path.join(process.cwd(), 'venv', 'bin', 'python3');
    const pythonCmd = fs.existsSync(venvPython) ? venvPython : 'python3';
    
    // Use base64 encoding to avoid shell injection issues
    const textArgs = texts.map(t => Buffer.from(t).toString('base64'));
    const { stdout, stderr } = await execAsync(`"${pythonCmd}" "${scriptPath}" ${textArgs.map(t => `"${t}"`).join(' ')}`);
    
    if (stderr && stderr.trim() && !stderr.includes('onnx')) {
      console.warn("Python script stderr:", stderr);
    }
    
    const result = JSON.parse(stdout);
    if (result.error) {
      throw new Error(result.error);
    }
    
    // Return as array of arrays
    return Array.isArray(result) && Array.isArray(result[0]) ? result : [result];
  } catch (error: any) {
    console.error("Error generating embeddings via Python:", error.message);
    throw new Error(`Failed to generate embeddings: ${error.message}`);
  }
}

async function generateEmbedding(text: string): Promise<number[]> {
  // Use ChromaDB via Python script
  return await generateEmbeddingPython(text);
}

async function generateEmbeddings(texts: string[]): Promise<number[][]> {
  // Use ChromaDB via Python script
  return await generateEmbeddingsPython(texts);
}

// Pool handles connection management automatically, no need for manual initDb
async function initDb() {
  // Test connection with a simple query
  try {
    await pgPool.query('SELECT 1');
  } catch (error: any) {
    console.error('Database connection error:', error.message);
    throw error;
  }
}

function sha256File(filePath: string): string {
  const h = crypto.createHash("sha256");
  h.update(fs.readFileSync(filePath));
  return h.digest("hex");
}

// Insert a Documents row; return document_id
async function registerDocument(
  deal_id: string,
  filePath: string,
  kind: string,
  version = "v1"
): Promise<string> {
  await initDb();
  const name = path.basename(filePath);
  const hash = sha256File(filePath);
  const sql =
    "INSERT INTO documents(deal_id,name,kind,version,sha256) VALUES ($1,$2,$3,$4,$5) RETURNING document_id";
  const { rows } = await pgPool.query(sql, [deal_id, name, kind, version, hash]);
  return rows[0].document_id as string;
}

// Create a Tables row and return table_id
async function registerTable(
  document_id: string,
  name: string,
  sheet?: string,
  note?: string
): Promise<string> {
  await initDb();
  const sql =
    "INSERT INTO tables_norm(document_id,name,sheet,note) VALUES ($1,$2,$3,$4) RETURNING table_id";
  const { rows } = await pgPool.query(sql, [document_id, name, sheet ?? null, note ?? null]);
  return rows[0].table_id as string;
}

// Bulk insert table_cells
async function insertCells(
  cells: Array<{
    table_id: string;
    row_idx: number;
    col_idx: number;
    label?: string | null;
    period?: string | null;
    value?: number | null;
    unit?: string | null;
    currency?: string | null;
    source_ref?: string | null;
  }>
) {
  if (!cells.length) return;
  await initDb();
  const cols = [
    "table_id",
    "row_idx",
    "col_idx",
    "label",
    "period",
    "value",
    "unit",
    "currency",
    "source_ref",
  ];
  const valuesSql: string[] = [];
  const params: any[] = [];
  let i = 1;
  for (const c of cells) {
    valuesSql.push(
      `($${i++},$${i++},$${i++},$${i++},$${i++},$${i++},$${i++},$${i++},$${i++})`
    );
    params.push(
      c.table_id,
      c.row_idx,
      c.col_idx,
      c.label ?? null,
      c.period ? dayjs(c.period).format("YYYY-MM-DD") : null,
      c.value ?? null,
      c.unit ?? null,
      c.currency ?? null,
      c.source_ref ?? null
    );
  }
  const sql = `INSERT INTO table_cells(${cols.join(",")}) VALUES ${valuesSql.join(",")}`;
  await pgPool.query(sql, params);
}

// Insert chunks for memo/text documents
async function insertChunks(
  document_id: string,
  chunks: Array<{
    section?: string | null;
    text: string;
    page_from?: number | null;
    page_to?: number | null;
    access_tag?: string | null;
  }>
) {
  if (!chunks.length) return;
  await initDb();
  const valuesSql: string[] = [];
  const params: any[] = [];
  let i = 1;
  for (const c of chunks) {
    valuesSql.push(`($${i++},$${i++},$${i++},$${i++},$${i++},$${i++})`);
    params.push(
      document_id,
      c.section ?? null,
      c.text,
      c.page_from ?? null,
      c.page_to ?? null,
      c.access_tag ?? "internal"
    );
  }
  const sql = `INSERT INTO chunks(document_id,section,text,page_from,page_to,access_tag) VALUES ${valuesSql.join(",")} RETURNING chunk_id`;
  const { rows } = await pgPool.query(sql, params);
  const chunkIds = rows.map(r => r.chunk_id);

  // Generate embeddings using local model (no API key needed)
  try {
    const texts = chunks.map(c => c.text);
    const embeddings = await generateEmbeddings(texts);
    
    // Insert embeddings into embeddings table
    const embeddingValuesSql: string[] = [];
    const embeddingParams: any[] = [];
    let j = 1;
    for (let idx = 0; idx < chunkIds.length; idx++) {
      embeddingValuesSql.push(`($${j++},$${j++},$${j++}::vector)`);
      embeddingParams.push(chunkIds[idx], 'sentence-transformers/all-MiniLM-L6-v2', `[${embeddings[idx].join(',')}]`);
    }
    if (embeddingValuesSql.length > 0) {
      const embeddingSql = `INSERT INTO embeddings(chunk_id, model, vector) VALUES ${embeddingValuesSql.join(",")}`;
      await pgPool.query(embeddingSql, embeddingParams);
    }
  } catch (error: any) {
    // Log error but don't fail chunk insertion
    console.warn(`Failed to generate embeddings for chunks: ${error.message}`);
  }
}

// ---------- Utility parsing ----------
function detectUnitAndCurrency(header: string): { unit: string | null; currency: string | null } {
  const h = header.toLowerCase();
  const isPct = /%|pct/.test(h);
  if (isPct) return { unit: "pct", currency: null };
  const cur = /(usd|eur|gbp)/.exec(h)?.[1]?.toUpperCase() ?? null;
  const unit = /(mm|million|millions)/.test(h)
    ? "USD_mm"
    : /(k|thousand)/.test(h)
    ? "USD_k"
    : cur
    ? `${cur}_raw`
    : null;
  return { unit, currency: cur };
}

function parsePeriod(input: any): string | null {
  if (!input) return null;
  if (typeof input === "number") {
    const excelEpoch = new Date(1899, 11, 30).getTime();
    const ms = excelEpoch + Math.round(input) * 86400000;
    return dayjs(ms).format("YYYY-MM-DD");
  }
  const s = String(input).trim();
  if (/^\d{4}-\d{2}-\d{2}$/.test(s)) return s;
  if (/^\d{4}[\/\-]Q[1-4]$/.test(s)) {
    const [y, q] = s.replace("-", "/").split("/Q");
    const m = { "1": "03", "2": "06", "3": "09", "4": "12" }[q as "1" | "2" | "3" | "4"];
    return `${y}-${m}-01`;
  }
  if (/^[A-Za-z]{3}\s+\d{4}$/.test(s)) {
    return dayjs(s).endOf("month").format("YYYY-MM-DD");
  }
  return null;
}

// ---------- Server setup ----------
const server = new McpServer({ name: "mcp-lp-tools", version: "0.2.0" });

// ============================================================================
// INGESTION TOOLS
// ============================================================================

// ---------- Tool: ingest_excel ----------
server.tool("ingest_excel", "Ingest Excel (.xlsx) file and extract tables into table_cells. Detects periods, units, currency; supports multi-sheet import.", {
  deal_id: z.string().uuid(),
  file_path: z.string(),
  sheet_hints: z.array(z.string()).optional(),
  version: z.string().default("v1"),
}, async ({ deal_id, file_path, sheet_hints, version }) => {
  await initDb();
  if (!fs.existsSync(file_path)) {
    throw new Error(`File not found: ${file_path}`);
  }

  const doc_id = await registerDocument(deal_id, file_path, "xlsx", version);
  const fileBuffer = fs.readFileSync(file_path);
  const workbook = XLSX.read(fileBuffer, { type: 'buffer' });
  const sheets = sheet_hints?.length ? sheet_hints : workbook.SheetNames;
  const allCells: any[] = [];
  let tableCount = 0;

  for (const sheetName of sheets) {
    if (!workbook.Sheets[sheetName]) continue;
    const worksheet = workbook.Sheets[sheetName];
    const data = XLSX.utils.sheet_to_json(worksheet, { header: 1, defval: null });

    if (!data.length) continue;
    const table_id = await registerTable(doc_id, `Table_${sheetName}`, sheetName, `Extracted from ${sheetName}`);

    // Assume first row is headers
    const headers = (data[0] as any[]).map((h, i) => ({
      idx: i,
      text: String(h || "").trim(),
      unit: detectUnitAndCurrency(String(h || "")).unit,
      currency: detectUnitAndCurrency(String(h || "")).currency,
    }));

    // Process data rows
    for (let rowIdx = 1; rowIdx < data.length; rowIdx++) {
      const row = data[rowIdx] as any[];
      if (!row || row.every(cell => cell == null || cell === "")) continue;

      // Try to detect label (first non-empty column)
      const label = row.find(cell => cell != null && String(cell).trim()) as string | undefined;

      // Process each column
      for (const header of headers) {
        const cellValue = row[header.idx];
        if (cellValue == null || cellValue === "") continue;

        const period = parsePeriod(cellValue) || parsePeriod(row[0]); // Try first column as period
        const numValue = typeof cellValue === "number" ? cellValue : parseFloat(String(cellValue));

        if (!isNaN(numValue) || period) {
          allCells.push({
            table_id,
            row_idx: rowIdx,
            col_idx: header.idx,
            label: label ? String(label).trim() : header.text,
            period,
            value: !isNaN(numValue) ? numValue : null,
            unit: header.unit,
            currency: header.currency,
            source_ref: `${sheetName}!${XLSX.utils.encode_cell({ r: rowIdx, c: header.idx })}`,
          });
        }
      }
    }
    tableCount++;
  }

  await insertCells(allCells);
  return {
    content: [{
      type: 'text',
      text: JSON.stringify({
        document_id: doc_id,
        tables_created: tableCount,
        cells_inserted: allCells.length,
      })
    }]
  };
});

// ---------- Tool: ingest_csv ----------
server.tool("ingest_csv", "Ingest CSV file and extract structured data into table_cells. Generic ERP/BI data loader.", {
  deal_id: z.string().uuid(),
  file_path: z.string(),
  has_header: z.boolean().default(true),
  version: z.string().default("v1"),
}, async ({ deal_id, file_path, has_header, version }) => {
  await initDb();
  if (!fs.existsSync(file_path)) {
    throw new Error(`File not found: ${file_path}`);
  }

  const doc_id = await registerDocument(deal_id, file_path, "csv", version);
  const content = fs.readFileSync(file_path, "utf-8");
  const records = parseCsvSync(content, { columns: has_header, skip_empty_lines: true });

  if (!records.length) {
    throw new Error("CSV file is empty or has no valid rows");
  }

  const table_id = await registerTable(doc_id, `CSV_${path.basename(file_path)}`, undefined, "CSV import");
  const allCells: any[] = [];

  // Detect headers
  const headers = has_header ? Object.keys(records[0] || {}) : [];
  const headerUnits = headers.map(h => detectUnitAndCurrency(h));

  records.forEach((record: any, rowIdx: number) => {
    headers.forEach((header, colIdx) => {
      const value = record[header];
      if (value == null || value === "") return;

      const period = parsePeriod(value);
      const numValue = typeof value === "number" ? value : parseFloat(String(value));
      const { unit, currency } = headerUnits[colIdx];

      if (!isNaN(numValue) || period) {
        allCells.push({
          table_id,
          row_idx: rowIdx + (has_header ? 1 : 0),
          col_idx: colIdx,
          label: header,
          period,
          value: !isNaN(numValue) ? numValue : null,
          unit,
          currency,
          source_ref: `row${rowIdx + 1}_col${colIdx + 1}`,
        });
      }
    });
  });

  await insertCells(allCells);
  return {
    content: [{
      type: 'text',
      text: JSON.stringify({
        document_id: doc_id,
        tables_created: 1,
        cells_inserted: allCells.length,
      })
    }]
  };
});

// ---------- Tool: ingest_memo ----------
server.tool("ingest_memo", "Ingest memo/text document (.txt/.md) and split into chunks for embeddings/RAG.", {
  deal_id: z.string().uuid(),
  file_path: z.string(),
  chunk_size: z.number().int().min(100).max(10000).default(1000),
  access_tag: z.enum(["internal", "lp-safe", "mnpi"]).default("internal"),
  version: z.string().default("v1"),
}, async ({ deal_id, file_path, chunk_size, access_tag, version }) => {
  await initDb();
  if (!fs.existsSync(file_path)) {
    throw new Error(`File not found: ${file_path}`);
  }

  const kind = file_path.endsWith(".md") ? "markdown" : "txt";
  const doc_id = await registerDocument(deal_id, file_path, kind, version);
  const content = fs.readFileSync(file_path, "utf-8");

  // Simple chunking: split by double newlines or by size
  const sections = content.split(/\n\n+/);
  const chunks: any[] = [];
  let currentChunk = "";
  let chunkIdx = 0;
  let sectionName: string | null = null;

  for (const section of sections) {
    // Try to detect section headers (lines starting with #)
    const headerMatch = section.match(/^(#{1,6})\s+(.+)$/m);
    if (headerMatch) {
      sectionName = headerMatch[2].trim();
    }

    if (currentChunk.length + section.length > chunk_size && currentChunk.length > 0) {
      chunks.push({
        section: sectionName,
        text: currentChunk.trim(),
        access_tag,
      });
      currentChunk = section;
      sectionName = null;
      chunkIdx++;
    } else {
      currentChunk += (currentChunk ? "\n\n" : "") + section;
    }
  }

  if (currentChunk.trim()) {
    chunks.push({
      section: sectionName,
      text: currentChunk.trim(),
      access_tag,
    });
  }

  await insertChunks(doc_id, chunks);
  return {
    content: [{
      type: 'text',
      text: JSON.stringify({
        document_id: doc_id,
        chunks_inserted: chunks.length,
      })
    }]
  };
});

// ---------- Tool: ingest_billing ----------
server.tool("ingest_billing", "Ingest billing data CSV (MRR movements) into table_cells. Stub for future Stripe/Zuora integration.", {
  deal_id: z.string().uuid(),
  file_path: z.string(),
  version: z.string().default("v1"),
}, async ({ deal_id, file_path, version }) => {
  await initDb();
  if (!fs.existsSync(file_path)) {
    throw new Error(`File not found: ${file_path}`);
  }

  const doc_id = await registerDocument(deal_id, file_path, "csv", version);
  const content = fs.readFileSync(file_path, "utf-8");
  const records = parseCsvSync(content, { columns: true, skip_empty_lines: true });

  if (!records.length) {
    throw new Error("Billing CSV file is empty or has no valid rows");
  }

  const table_id = await registerTable(doc_id, "MRR_Movements", undefined, "Billing data import");
  const allCells: any[] = [];

  records.forEach((record: any, rowIdx: number) => {
    // Expect columns: period, mrr, new_mrr, expansion_mrr, contraction_mrr, churn_mrr, etc.
    Object.keys(record).forEach((key, colIdx) => {
      const value = record[key];
      if (!value || value === "") return;

      const period = parsePeriod(key) || parsePeriod(record.period || record.date || record.month);
      const numValue = parseFloat(String(value));

      if (!isNaN(numValue)) {
        allCells.push({
          table_id,
          row_idx: rowIdx + 1,
          col_idx: colIdx,
          label: key,
          period,
          value: numValue,
          unit: /mrr|revenue/i.test(key) ? "USD" : null,
          currency: "USD",
          source_ref: `row${rowIdx + 1}_${key}`,
        });
      }
    });
  });

  await insertCells(allCells);
  return {
    content: [{
      type: 'text',
      text: JSON.stringify({
        document_id: doc_id,
        tables_created: 1,
        cells_inserted: allCells.length,
      })
    }]
  };
});

// ---------- Tool: ingest_edgar_xbrl ----------
server.tool("ingest_edgar_xbrl", "Ingest SEC EDGAR XBRL CSV export and map XBRL concepts to canonical labels into table_cells.", {
  deal_id: z.string().uuid(),
  file_path: z.string(),
  version: z.string().default("v1"),
}, async ({ deal_id, file_path, version }) => {
  await initDb();
  if (!fs.existsSync(file_path)) {
    throw new Error(`File not found: ${file_path}`);
  }

  const doc_id = await registerDocument(deal_id, file_path, "csv", version);
  const content = fs.readFileSync(file_path, "utf-8");
  const records = parseCsvSync(content, { columns: true, skip_empty_lines: true });

  if (!records.length) {
    throw new Error("EDGAR XBRL CSV file is empty or has no valid rows");
  }

  // XBRL mapping: map common XBRL concepts to canonical labels
  // Note: Labels must match what compute_kpis expects (GrossMargin, EBITDA_Margin)
  const xbrlMapping: Record<string, string> = {
    "us-gaap:Revenues": "Revenue",
    "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax": "Revenue",
    "us-gaap:GrossProfit": "GrossMargin",  // Changed from "GrossProfit" to match compute_kpis
    "us-gaap:OperatingIncomeLoss": "OperatingIncome",
    "us-gaap:IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest": "EBITDA_Margin",  // Changed from "EBITDA" to match compute_kpis
    "us-gaap:Assets": "Assets",
    "us-gaap:Liabilities": "Liabilities",
  };

  const table_id = await registerTable(doc_id, "EDGAR_XBRL", undefined, "SEC EDGAR XBRL export");
  const allCells: any[] = [];

  records.forEach((record: any, rowIdx: number) => {
    const concept = record.concept || record.tag || record.element;
    const canonicalLabel = xbrlMapping[concept] || concept?.replace(/^us-gaap:/, "").replace(/([A-Z])/g, " $1").trim();
    const period = parsePeriod(record.endDate || record.period || record.fiscalPeriodEndDate);
    const value = parseFloat(record.value || record.amount || record.value);

    if (!isNaN(value) && canonicalLabel) {
      allCells.push({
        table_id,
        row_idx: rowIdx + 1,
        col_idx: 0,
        label: canonicalLabel,
        period,
        value,
        unit: record.unit || "USD",
        currency: "USD",
        source_ref: concept,
      });
    }
  });

  await insertCells(allCells);
  return {
    content: [{
      type: 'text',
      text: JSON.stringify({
        document_id: doc_id,
        tables_created: 1,
        cells_inserted: allCells.length,
        xbrl_concepts_mapped: Object.keys(xbrlMapping).length,
      })
    }]
  };
});

// ---------- Tool: ingest_snowflake ----------
server.tool("ingest_snowflake", "Ingest Snowflake data warehouse CSV export into table_cells. Proxy for future direct connector.", {
  deal_id: z.string().uuid(),
  file_path: z.string(),
  version: z.string().default("v1"),
}, async ({ deal_id, file_path, version }) => {
  await initDb();
  if (!fs.existsSync(file_path)) {
    throw new Error(`File not found: ${file_path}`);
  }

  // For now, treat as generic CSV - future: direct Snowflake connector
  const doc_id = await registerDocument(deal_id, file_path, "csv", version);
  const content = fs.readFileSync(file_path, "utf-8");
  const records = parseCsvSync(content, { columns: true, skip_empty_lines: true });

  if (!records.length) {
    throw new Error("Snowflake CSV export is empty or has no valid rows");
  }

  const table_id = await registerTable(doc_id, "Snowflake_Export", undefined, "Snowflake DW export");
  const allCells: any[] = [];

  records.forEach((record: any, rowIdx: number) => {
    Object.keys(record).forEach((key, colIdx) => {
      const value = record[key];
      if (!value || value === "") return;

      const period = parsePeriod(key) || parsePeriod(record.date || record.period || record.fiscal_period);
      const numValue = parseFloat(String(value));
      const { unit, currency } = detectUnitAndCurrency(key);

      if (!isNaN(numValue) || period) {
        allCells.push({
          table_id,
          row_idx: rowIdx + 1,
          col_idx: colIdx,
          label: key,
          period,
          value: !isNaN(numValue) ? numValue : null,
          unit,
          currency,
          source_ref: `snowflake_row${rowIdx + 1}_${key}`,
        });
      }
    });
  });

  await insertCells(allCells);
  return {
    content: [{
      type: 'text',
      text: JSON.stringify({
        document_id: doc_id,
        tables_created: 1,
        cells_inserted: allCells.length,
        note: "Future: direct Snowflake connector will replace CSV export",
      })
    }]
  };
});

// ============================================================================
// COMPUTE TOOLS
// ============================================================================

// ---------- KPI compute helpers ----------
async function upsertKpi(name: string, description: string): Promise<string> {
  await initDb();
  let r = await pgPool.query("SELECT kpi_id FROM kpis WHERE name=$1", [name]);
  if (r.rows.length) return r.rows[0].kpi_id as string;
  r = await pgPool.query(
    "INSERT INTO kpis(name, description) VALUES ($1,$2) RETURNING kpi_id",
    [name, description]
  );
  return r.rows[0].kpi_id as string;
}

async function fetchCellsByLabel(deal_id: string, label: string) {
  await initDb();
  const sql = `
    SELECT c.cell_id, c.period::date AS period, c.value, c.unit
    FROM table_cells c
    JOIN tables_norm t ON c.table_id = t.table_id
    JOIN documents d ON t.document_id = d.document_id
    WHERE d.deal_id = $1 AND c.label = $2 AND c.period IS NOT NULL
    ORDER BY c.period DESC`;
  const { rows } = await pgPool.query(sql, [deal_id, label]);
  return rows as Array<{ cell_id: string; period: string; value: number; unit: string | null }>;
}

// ---------- Tool: compute_kpis ----------
server.tool("compute_kpis", "Compute core KPIs (Revenue_LTM, YoY_Growth, Gross_Margin, EBITDA_Margin) from TableCells and write KPIValues + GoldenFacts.", {
  deal_id: z.string().uuid(),
  revenue_label: z.string().default("Revenue"),
  gross_margin_label: z.string().default("GrossMargin"),
  ebitda_margin_label: z.string().default("EBITDA_Margin"),
  periods_to_sum: z.number().int().min(2).max(12).default(4),
  approve: z.boolean().default(true),
  ttl_days: z.number().int().min(1).max(365).default(90),
}, async ({
  deal_id,
  revenue_label,
  gross_margin_label,
  ebitda_margin_label,
  periods_to_sum,
  approve,
  ttl_days,
}) => {
  await initDb();
  const rev = await fetchCellsByLabel(deal_id, revenue_label);
  const gm = await fetchCellsByLabel(deal_id, gross_margin_label);
  const em = await fetchCellsByLabel(deal_id, ebitda_margin_label);
  
  if (rev.length === 0) {
    // Get available labels to help debug
    const { rows: labelRows } = await pgPool.query(`
      SELECT DISTINCT c.label, COUNT(*) as count
      FROM table_cells c
      JOIN tables_norm t ON c.table_id = t.table_id
      JOIN documents d ON t.document_id = d.document_id
      WHERE d.deal_id = $1 AND c.period IS NOT NULL
      GROUP BY c.label
      ORDER BY count DESC
      LIMIT 10
    `, [deal_id]);
    
    const availableLabels = labelRows.map(r => `'${r.label}' (${r.count} cells)`).join(', ');
    throw new Error(
      `No rows found for label '${revenue_label}'. ` +
      `Available labels with periods: ${availableLabels || 'none'}. ` +
      `Make sure data is ingested using ingest_edgar_xbrl (not ingest_csv) for proper label normalization.`
    );
  }

  const latestPeriod = rev[0].period;
  const useRevCells = rev.slice(0, periods_to_sum);
  const revenueLtmVal = useRevCells.reduce((s, r) => s + Number(r.value || 0), 0);
  const revenueUnit = useRevCells[0]?.unit ?? null;

  let yoyVal: number | null = null;
  const prior =
    rev.find((r) =>
      dayjs(r.period).isSame(dayjs(latestPeriod).subtract(1, "year"), "month")
    ) || rev[periods_to_sum] || rev[rev.length - 1];
  if (prior && prior.value && Number(prior.value) !== 0) {
    yoyVal = ((Number(rev[0].value) - Number(prior.value)) / Number(prior.value)) * 100;
  }

  const gmLatest = gm[0]?.value ?? null;
  const emLatest = em[0]?.value ?? null;

  const kpiRevenueLtm = await upsertKpi("Revenue_LTM", "Revenue last N periods (sum)");
  const kpiYoy = await upsertKpi("YoY_Growth", "Year-over-year revenue growth (%)");
  const kpiGM = await upsertKpi("Gross_Margin", "Gross margin (%)");
  const kpiEM = await upsertKpi("EBITDA_Margin", "EBITDA margin (%)");

  async function insertKpiValue(
    kpi_id: string,
    value: number | null,
    unit: string | null,
    formula: string,
    sources: string[]
  ) {
    if (value == null || Number.isNaN(value)) return null;
    const { rows } = await pgPool.query(
      "INSERT INTO kpi_values(kpi_id, deal_id, as_of, value, unit, formula) VALUES ($1,$2,$3,$4,$5,$6) RETURNING kpi_value_id",
      [kpi_id, deal_id, latestPeriod, value, unit, formula]
    );
    const id = rows[0].kpi_value_id;
    for (const cid of sources)
      await pgPool.query(
        "INSERT INTO kpi_value_sources(kpi_value_id, source_type, source_id) VALUES ($1,'cell',$2)",
        [id, cid]
      );
    if (approve)
      await pgPool.query(
        "INSERT INTO golden_facts(kpi_id, deal_id, kpi_value_id, ttl_until, status) VALUES ($1,$2,$3, now() + ($4 || ' days')::interval, 'approved')",
        [kpi_id, deal_id, id, String(ttl_days)]
      );
    return id;
  }

  const revSources = useRevCells.map((r) => r.cell_id);
  const revId = await insertKpiValue(
    kpiRevenueLtm,
    revenueLtmVal,
    revenueUnit,
    "SUM(last periods)",
    revSources
  );
  const yoyId =
    yoyVal == null
      ? null
      : await insertKpiValue(
          kpiYoy,
          yoyVal,
          "pct",
          "(Rev_t - Rev_t-1y)/Rev_t-1y",
          [rev[0].cell_id, prior?.cell_id].filter(Boolean) as string[]
        );
  const gmId =
    gmLatest == null
      ? null
      : await insertKpiValue(kpiGM, gmLatest, "pct", "GrossProfit/Revenue", gm[0] ? [gm[0].cell_id] : []);
  const emId =
    emLatest == null
      ? null
      : await insertKpiValue(kpiEM, emLatest, "pct", "EBITDA/Revenue", em[0] ? [em[0].cell_id] : []);

  const result = {
    as_of: latestPeriod,
    created: [
      { name: "Revenue_LTM", kpi_value_id: revId },
      { name: "YoY_Growth", kpi_value_id: yoyId },
      { name: "Gross_Margin", kpi_value_id: gmId },
      { name: "EBITDA_Margin", kpi_value_id: emId },
    ],
  };

  return { content: [{ type: 'text', text: JSON.stringify(result) }] };
});

// ============================================================================
// RENDERING TOOLS
// ============================================================================

// ---------- Tool: get_golden_facts ----------
server.tool("get_golden_facts", "Fetch approved GoldenFacts (KPI snapshot) for a deal.", {
  deal_id: z.string().uuid(),
  kpis: z.array(z.string()).optional(),
}, async ({ deal_id, kpis }) => {
  await initDb();
  const params: any[] = [deal_id];
  let sql = `
    SELECT k.name AS kpi, kv.value, kv.unit, kv.as_of::date AS as_of, kv.formula
    FROM golden_facts gf
    JOIN kpi_values kv ON kv.kpi_value_id = gf.kpi_value_id
    JOIN kpis k ON k.kpi_id = kv.kpi_id
    WHERE gf.deal_id = $1 AND gf.status='approved'`;
  if (kpis?.length) {
    sql += ` AND k.name = ANY($2)`;
    params.push(kpis);
  }
  sql += " ORDER BY k.name";
  const { rows } = await pgPool.query(sql, params);
  return { content: [{ type: 'text', text: JSON.stringify({ snapshot: rows }) }] };
});

// ---------- Tool: get_kpi_lineage ----------
server.tool("get_kpi_lineage", "Get lineage (underlying cells) for KPI values in a deal.", {
  deal_id: z.string().uuid(),
  kpis: z.array(z.string()).optional(),
}, async ({ deal_id, kpis }) => {
  await initDb();
  const params: any[] = [deal_id];
  let sql = `
    SELECT k.name AS kpi, kv.kpi_value_id, t.name AS table_name,
           c.source_ref, c.label, c.period::date AS period, c.value, c.unit
    FROM kpi_values kv
    JOIN kpis k ON k.kpi_id = kv.kpi_id
    JOIN kpi_value_sources s ON s.kpi_value_id = kv.kpi_value_id AND s.source_type='cell'
    JOIN table_cells c ON c.cell_id = s.source_id
    JOIN tables_norm t ON t.table_id = c.table_id
    WHERE kv.deal_id = $1`;
  if (kpis?.length) {
    sql += ` AND k.name = ANY($2)`;
    params.push(kpis);
  }
  sql += ` ORDER BY k.name, c.period DESC`;
  const { rows } = await pgPool.query(sql, params);
  // Group by KPI for nicer shape
  const byKpi: Record<string, any[]> = {};
  for (const r of rows) {
    (byKpi[r.kpi] ??= []).push(r);
  }
  return { content: [{ type: 'text', text: JSON.stringify({ lineage: byKpi }) }] };
});

// ---------- Vector search helpers ----------
const QUERY_TEMPLATES = {
  thesis: [
    "Investment thesis: strong revenue growth, market leadership, competitive advantages, business performance, financial outlook",
    "Company strengths: revenue growth trajectory, market position, product innovation, customer adoption, operational efficiency",
    "Business highlights: financial performance, market leadership, product development, customer success, growth drivers"
  ].join('. '),
  risks: [
    "Key risks and mitigants: competitive pressure, customer concentration, macroeconomic uncertainty, operational risks",
    "Risk factors: business risks, market risks, competitive threats, customer concentration, financial risks",
    "Risk mitigation: challenges facing the business, mitigation strategies, risk management"
  ].join('. ')
};

function buildQuery(sectionType: 'thesis' | 'risks'): string {
  return QUERY_TEMPLATES[sectionType];
}

async function findRelevantChunksVector(
  deal_id: string,
  query: string,
  sectionType: 'thesis' | 'risks',
  limit: number = 3
): Promise<any[]> {
  await initDb();
  
  // Check if embeddings exist for this deal
  const { rows: embeddingCheck } = await pgPool.query(`
    SELECT COUNT(*) as count
    FROM embeddings e
    JOIN chunks c ON c.chunk_id = e.chunk_id
    JOIN documents d ON d.document_id = c.document_id
    WHERE d.deal_id = $1 AND d.kind IN ('txt', 'md')
  `, [deal_id]);
  
  if (parseInt(embeddingCheck[0]?.count || '0') === 0) {
    // No embeddings available, return empty to trigger fallback
    return [];
  }
  
  // Generate query embedding using local model
  try {
    const queryEmbedding = await generateEmbedding(query);
    
    // Perform vector similarity search using cosine distance
    const sql = `
      SELECT 
        c.chunk_id,
        c.section,
        c.text,
        d.name as document_name,
        1 - (e.vector <=> $1::vector) AS similarity_score
      FROM embeddings e
      JOIN chunks c ON c.chunk_id = e.chunk_id
      JOIN documents d ON d.document_id = c.document_id
      WHERE d.deal_id = $2
        AND d.kind IN ('txt', 'md')
        AND c.access_tag IN ('lp-safe', 'internal')
        AND e.model = $3
      ORDER BY e.vector <=> $1::vector
      LIMIT $4
    `;
    
    const embeddingArray = `[${queryEmbedding.join(',')}]`;
    const { rows } = await pgPool.query(sql, [
      embeddingArray,
      deal_id,
      'sentence-transformers/all-MiniLM-L6-v2',
      limit
    ]);
    
    return rows;
  } catch (error: any) {
    console.warn(`Vector search failed: ${error.message}`);
    return []; // Fallback to rule-based
  }
}

// Rule-based fallback (original implementation)
function findRelevantChunksRuleBased(memoChunks: any[], sectionType: 'thesis' | 'risks'): any[] {
  if (sectionType === 'thesis') {
    // For thesis: match sections that are clearly about business performance/outlook
    const sectionKeywords = ['executive summary', 'financial performance', 'product & market'];
    let matched = memoChunks.filter(chunk => {
      const sectionLower = (chunk.section || '').toLowerCase();
      return sectionKeywords.some(kw => sectionLower.includes(kw));
    });
    
    // Exclude risk-related chunks
    matched = matched.filter(chunk => {
      const sectionLower = (chunk.section || '').toLowerCase();
      return !sectionLower.includes('risk') && !sectionLower.includes('mitigant');
    });
    
    // Deduplicate
    const seen = new Set<string>();
    const unique: any[] = [];
    for (const chunk of matched) {
      const key = `${chunk.section || ''}|${chunk.text.substring(0, 100)}`;
      if (!seen.has(key)) {
        seen.add(key);
        unique.push(chunk);
      }
    }
    return unique.slice(0, 3);
  } else {
    // For risks: match sections specifically about risks
    // Priority: exact match for "Key Risks & Mitigants" or "Risks & Mitigants"
    const exactMatch = memoChunks.find(chunk => {
      const sectionLower = (chunk.section || '').toLowerCase();
      return sectionLower.includes('key risks') || sectionLower.includes('risks & mitigants');
    });
    
    if (exactMatch) {
      return [exactMatch];
    }
    
    // Fallback: find any chunk with "risk" in section name (but not "outlook")
    const matched = memoChunks.filter(chunk => {
      const sectionLower = (chunk.section || '').toLowerCase();
      return sectionLower.includes('risk') && !sectionLower.includes('outlook');
    }).slice(0, 1);
    
    return matched;
  }
}

// ---------- Tool: render_onepager_markdown ----------
server.tool("render_onepager_markdown", "Render a Markdown LP one‑pager from snapshot + optional bullets with lineage links.", {
  company: z.string(),
  period_end: z.string().optional(),
  snapshot: z.array(
    z.object({ kpi: z.string(), value: z.number(), unit: z.string().nullable().optional(), as_of: z.string().optional(), formula: z.string().optional() })
  ),
  bullets: z.object({ thesis: z.array(z.string()).max(5).optional(), risks: z.array(z.string()).max(5).optional(), }).optional(),
  theme: z.object({ brand: z.string().optional() }).optional(),
  deal_id: z.string().uuid().optional(),
  lineage: z.record(z.string(), z.array(z.object({
    table_name: z.string(),
    source_ref: z.string().nullable(),
    label: z.string().nullable(),
    period: z.string().nullable(),
    value: z.union([z.string(), z.number()]).nullable(),
    unit: z.string().nullable(),
  }))).optional(),
}, async ({ company, period_end, snapshot, bullets, theme, deal_id, lineage }) => {
  await initDb();
  
  // Fetch lineage if deal_id provided and lineage not passed
  let lineageData = lineage;
  if (!lineageData && deal_id) {
    const params: any[] = [deal_id];
    let sql = `
      SELECT k.name AS kpi, kv.kpi_value_id, t.name AS table_name,
             c.source_ref, c.label, c.period::date AS period, c.value, c.unit
      FROM kpi_values kv
      JOIN kpis k ON k.kpi_id = kv.kpi_id
      JOIN kpi_value_sources s ON s.kpi_value_id = kv.kpi_value_id AND s.source_type='cell'
      JOIN table_cells c ON c.cell_id = s.source_id
      JOIN tables_norm t ON t.table_id = c.table_id
      WHERE kv.deal_id = $1
      ORDER BY k.name, c.period DESC`;
    const { rows } = await pgPool.query(sql, params);
    lineageData = {};
    for (const r of rows) {
      (lineageData[r.kpi] ??= []).push({
        table_name: r.table_name,
        source_ref: r.source_ref,
        label: r.label,
        period: r.period ? dayjs(r.period).format('YYYY-MM-DD') : null,
        value: r.value,
        unit: r.unit,
      });
    }
  }

  const mm = new Map(snapshot.map((r: any) => [r.kpi, r]));
  
  // Helper to format lineage for a KPI (inline in table cell)
  const formatLineageInline = (kpiName: string): string => {
    if (!lineageData || !lineageData[kpiName] || lineageData[kpiName].length === 0) {
      return "–";
    }
    const sources = lineageData[kpiName];
    // Deduplicate sources by table_name + source_ref + period
    const uniqueSources = new Map<string, any>();
    for (const src of sources) {
      const key = `${src.table_name}|${src.source_ref}|${src.period}`;
      if (!uniqueSources.has(key)) {
        uniqueSources.set(key, src);
      }
    }
    const uniqueList = Array.from(uniqueSources.values());
    
    // Group by table_name for cleaner display
    const byTable: Record<string, any[]> = {};
    for (const src of uniqueList) {
      const table = src.table_name || 'Unknown';
      (byTable[table] ??= []).push(src);
    }
    
    const lines = [];
    for (const [table, tableSources] of Object.entries(byTable)) {
      const tableLines = tableSources.map((src: any) => {
        const ref = src.source_ref || 'N/A';
        const label = src.label || '';
        const period = src.period ? dayjs(src.period).format('MMM YYYY') : '';
        const value = src.value != null ? String(src.value) : '';
        const unit = src.unit || '';
        return `${ref}${label ? ` | ${label}` : ''}${period ? ` (${period})` : ''}${value ? ` = ${value}${unit ? ' ' + unit : ''}` : ''}`;
      });
      lines.push(`<strong>${table}</strong>:`);
      lines.push(...tableLines.map(l => `- ${l}`));
    }
    
    // Put entire details tag on one line for markdown table compatibility
    const content = lines.join('<br>');
    return `<details><summary>📊 View sources</summary>${content}</details>`;
  };

  // Helper function to format values nicely
  const formatValue = (value: any, unit: string | null): string => {
    // Convert to number if it's a string
    const numValue = typeof value === 'string' ? parseFloat(value) : value;
    
    if (isNaN(numValue)) {
      return unit ? `${value} ${unit}` : String(value);
    }
    
    if (unit === 'pct' || unit === 'percent') {
      // Format percentage with one decimal place
      return `${numValue.toFixed(1)}%`;
    }
    
    if (unit === 'USD' || unit === 'USD_mm' || unit === 'USD_k' || unit?.includes('USD')) {
      // Format currency values
      if (unit === 'USD_mm' || (unit === 'USD' && numValue >= 1000000)) {
        // Convert to millions
        const millions = numValue / 1000000;
        return `$${millions.toFixed(2)} M USD`;
      } else if (unit === 'USD_k' || (unit === 'USD' && numValue >= 1000)) {
        // Convert to thousands
        const thousands = numValue / 1000;
        return `$${thousands.toFixed(2)} K USD`;
      } else if (unit === 'USD') {
        // Already in USD, just format with commas
        return `$${numValue.toLocaleString('en-US', { maximumFractionDigits: 0 })} USD`;
      }
    }
    
    // Default: return value with unit
    return unit ? `${numValue} ${unit}` : String(numValue);
  };

  // Helper function to format date (just date, no time)
  const formatDate = (dateStr: string | null): string => {
    if (!dateStr) return "–";
    try {
      return dayjs(dateStr).format("MMM D, YYYY");
    } catch {
      return dateStr;
    }
  };

  const s = (name: string, pretty: string) => {
    const r = mm.get(name);
    if (!r) return `| ${pretty} | – | – | – |`;
    const v = formatValue(r.value, r.unit);
    const d = formatDate(r.as_of);
    const sourceCell = lineageData && lineageData[name] ? formatLineageInline(name) : "–";
    return `| ${pretty} | **${v}** | ${d} | ${sourceCell} |`;
  };

  const title = `# ${company}\n### LP Update${period_end ? ` — ${dayjs(period_end).format("MMM YYYY")}`:""}\n*(Confidential | For Limited Partners only)*`;

  const snapshotTable = [
    "| Metric | Value | As of | Source |",
    "|:--|--:|:--|:--|",
    s("Revenue_LTM","Revenue (LTM)"),
    s("YoY_Growth","YoY Growth (%)"),
    s("Gross_Margin","Gross Margin (%)"),
    s("EBITDA_Margin","EBITDA Margin (%)"),
  ].join("\n");

  // Fetch memo chunks for source attribution
  let memoChunks: any[] = [];
  if (deal_id) {
    try {
      const { rows } = await pgPool.query(`
        SELECT c.section, c.text, d.name as document_name
        FROM chunks c
        JOIN documents d ON d.document_id = c.document_id
        WHERE d.deal_id = $1 AND d.kind IN ('txt', 'md')
        ORDER BY c.created_at
      `, [deal_id]);
      memoChunks = rows;
    } catch (e) {
      // If query fails, continue without chunks
      console.error("Failed to fetch memo chunks:", e);
    }
  }

  // Helper to find relevant chunks for a section (vector search with fallback)
  const findRelevantChunks = async (sectionType: 'thesis' | 'risks'): Promise<any[]> => {
    if (!deal_id) return [];
    
    try {
      // Try vector search first
      const query = buildQuery(sectionType);
      const vectorResults = await findRelevantChunksVector(deal_id, query, sectionType, 3);
      
      if (vectorResults.length > 0) {
        return vectorResults;
      }
    } catch (e) {
      console.warn('Vector search failed, falling back to rule-based:', e);
    }
    
    // Fallback to rule-based matching
    return findRelevantChunksRuleBased(memoChunks, sectionType);
  };

  // Helper to format chunk sources
  const formatChunkSources = (chunks: any[]): string => {
    if (!chunks || chunks.length === 0) {
      return "–";
    }
    const lines = chunks.map(chunk => {
      const section = chunk.section || 'Memo';
      const docName = chunk.document_name || 'memo';
      // Clean text: remove markdown headers at start of lines, trim whitespace
      let cleanText = chunk.text
        .replace(/^#+\s+.+$/gm, '') // Remove markdown headers
        .replace(/^\*\*.+?\*\*$/gm, '') // Remove bold headers on their own line
        .replace(/^-\s+\*\*/, '- ') // Remove bold from bullet points
        .trim();
      
      // For risk chunks, try to extract the first risk description
      if (section.toLowerCase().includes('risk')) {
        const riskMatch = cleanText.match(/Risk:\s*([^.!?]+[.!?]?)/i);
        if (riskMatch) {
          cleanText = riskMatch[0] + ' ' + cleanText.substring(riskMatch[0].length).trim();
        }
      }
      
      // Extract first complete sentence(s) up to 150 chars
      let preview = cleanText.substring(0, 150);
      const sentences = cleanText.match(/[^.!?]+[.!?]+/g) || [];
      if (sentences.length > 0) {
        let snippet = '';
        for (const sent of sentences) {
          if (snippet.length + sent.length <= 150) {
            snippet += sent;
          } else {
            break;
          }
        }
        if (snippet.trim()) preview = snippet.trim();
      }
      
      // Clean up preview: remove extra whitespace and newlines
      preview = preview.replace(/\s+/g, ' ').trim();
      
      return `<strong>${section}</strong> (${docName}): ${preview}${cleanText.length > preview.length ? '...' : ''}`;
    });
    const content = lines.join('<br><br>');
    return `<details><summary>📊 View sources</summary>${content}</details>`;
  };

  const bulletsBlock = async () => {
    const parts: string[] = [];
    if (bullets?.thesis?.length) {
      const thesisChunks = await findRelevantChunks('thesis');
      const sourcesHtml = formatChunkSources(thesisChunks);
      parts.push("\n## Investment Thesis");
      parts.push(bullets.thesis.map(b => `- ${b}`).join("\n"));
      if (sourcesHtml !== "–") {
        parts.push(`\n\n${sourcesHtml}`);
      }
    }
    if (bullets?.risks?.length) {
      const risksChunks = await findRelevantChunks('risks');
      const sourcesHtml = formatChunkSources(risksChunks);
      parts.push("\n## Key Risks & Mitigants");
      parts.push(bullets.risks.map(b => `- ${b}`).join("\n"));
      if (sourcesHtml !== "–") {
        parts.push(`\n\n${sourcesHtml}`);
      }
    }
    return parts.join("\n");
  };

  const md = [
    title,
    "\n---\n\n## Company Snapshot\n",
    snapshotTable,
    await bulletsBlock(),
    "\n---\n\n*Generated by MCP tools: render_onepager_markdown*\n",
  ].join("\n");

  return { content: [{ type: 'text', text: JSON.stringify({ markdown: md, brand: theme?.brand ?? null }) }] };
});

// ---------- Tool: clear_deal_data ----------
server.tool("clear_deal_data", "Clear all ingested data for a deal (documents, table_cells, chunks, KPIs, etc.) to allow re-ingestion.", {
  deal_id: z.string().uuid(),
  confirm: z.boolean().default(false),
}, async ({ deal_id, confirm }) => {
  try {
    await initDb();
    
    if (!confirm) {
      throw new Error("Must set confirm=true to clear deal data. This action cannot be undone.");
    }
    
    const results: Record<string, number> = {};
    
    // Delete in correct order due to foreign key constraints
    let r = await pgPool.query('DELETE FROM golden_facts WHERE deal_id = $1', [deal_id]);
    results.golden_facts = r.rowCount || 0;
  
  r = await pgPool.query(`
    DELETE FROM kpi_value_sources 
    WHERE kpi_value_id IN (SELECT kpi_value_id FROM kpi_values WHERE deal_id = $1)
  `, [deal_id]);
  results.kpi_value_sources = r.rowCount || 0;
  
  r = await pgPool.query('DELETE FROM kpi_values WHERE deal_id = $1', [deal_id]);
  results.kpi_values = r.rowCount || 0;
  
  r = await pgPool.query(`
    DELETE FROM table_cells 
    WHERE table_id IN (
      SELECT table_id FROM tables_norm 
      WHERE document_id IN (SELECT document_id FROM documents WHERE deal_id = $1)
    )
  `, [deal_id]);
  results.table_cells = r.rowCount || 0;
  
  r = await pgPool.query(`
    DELETE FROM embeddings 
    WHERE chunk_id IN (
      SELECT chunk_id FROM chunks 
      WHERE document_id IN (SELECT document_id FROM documents WHERE deal_id = $1)
    )
  `, [deal_id]);
  results.embeddings = r.rowCount || 0;
  
  r = await pgPool.query(`
    DELETE FROM chunks 
    WHERE document_id IN (SELECT document_id FROM documents WHERE deal_id = $1)
  `, [deal_id]);
  results.chunks = r.rowCount || 0;
  
  r = await pgPool.query(`
    DELETE FROM tables_norm 
    WHERE document_id IN (SELECT document_id FROM documents WHERE deal_id = $1)
  `, [deal_id]);
  results.tables_norm = r.rowCount || 0;
  
    r = await pgPool.query('DELETE FROM documents WHERE deal_id = $1', [deal_id]);
    results.documents = r.rowCount || 0;
    
    return {
      content: [{
        type: 'text',
        text: JSON.stringify({
          deal_id,
          cleared: true,
          deleted_counts: results,
          message: `Successfully cleared all data for deal ${deal_id}`
        })
      }]
    };
  } catch (error: any) {
    let errorMessage = 'Unknown error';
    if (error?.message) {
      errorMessage = error.message;
    } else if (error?.errors && Array.isArray(error.errors)) {
      // Handle AggregateError
      errorMessage = error.errors.map((e: any) => e?.message || String(e)).join('; ');
    } else {
      errorMessage = String(error);
    }
    console.error(`Error clearing deal data: ${errorMessage}`);
    console.error('Full error:', error);
    throw new Error(`Failed to clear deal data: ${errorMessage}`);
  }
});

// ---------- Tool: register_output ----------
server.tool("register_output", "Create a Runs/Outputs row to track an artifact and its lineage.", {
  deal_id: z.string().uuid(),
  recipe: z.string().default("LP_OnePager_v1"),
  model: z.string().optional(),
  kind: z.enum(["markdown","docx","pdf","json"]).default("markdown"),
  uri: z.string().optional(),
  summary: z.string().optional()
}, async ({ deal_id, recipe, model, kind, uri, summary }) => {
  await initDb();
  const { rows: runRows } = await pgPool.query(
    `INSERT INTO runs (deal_id, recipe, model) VALUES ($1,$2,$3) RETURNING run_id, started_at`,
    [deal_id, recipe, model ?? null]
  );
  const run = runRows[0];

  const { rows: outRows } = await pgPool.query(
    `INSERT INTO outputs (run_id, kind, uri, summary) VALUES ($1,$2,$3,$4) RETURNING output_id`,
    [run.run_id, kind, uri ?? null, summary ?? null]
  );

  return { content: [{ type: 'text', text: JSON.stringify({ run_id: run.run_id, output_id: outRows[0].output_id }) }] };
});

// ============================================================================
// HTTP SERVER SETUP
// ============================================================================

const app = express();
app.use(express.json());
app.use(cors({
  origin: '*',
  exposedHeaders: ['Mcp-Session-Id']
}));

const transports = new Map<string, StreamableHTTPServerTransport>();

app.post('/mcp', async (req, res) => {
  const sessionId = req.headers['mcp-session-id'] as string | undefined;
  let transport = sessionId ? transports.get(sessionId) : undefined;

  if (!transport) {
    // New session - create transport and connect server
    if (!isInitializeRequest(req.body)) {
      res.status(400).json({ error: 'First request must be initialize' });
      return;
    }
    transport = new StreamableHTTPServerTransport({
      sessionIdGenerator: () => randomUUID(),
      enableJsonResponse: true,
      onsessioninitialized: (sid) => {
        // Store transport when session is initialized
        transports.set(sid, transport!);
      }
    });
    const newSessionId = transport.sessionId || randomUUID();
    await server.connect(transport);
    // Handle the initialize request - this will trigger onsessioninitialized
    await transport.handleRequest(req, res, req.body);
    // Also store with our generated ID as fallback
    if (!transport.sessionId) {
      transports.set(newSessionId, transport);
      res.setHeader('Mcp-Session-Id', newSessionId);
    }
  } else {
    // Existing session - let transport handle it
    await transport.handleRequest(req, res, req.body);
  }
});

const PORT = Number(process.env.PORT ?? 3333);
app.listen(PORT, () => {
  console.log(`[mcp-lp-tools] listening on :${PORT}`);
  console.log(`[mcp-lp-tools] Tools registered: 12 total`);
  console.log(`  - Ingestion: ingest_excel, ingest_csv, ingest_memo, ingest_billing, ingest_edgar_xbrl, ingest_snowflake`);
  console.log(`  - Compute: compute_kpis`);
  console.log(`  - Rendering: get_golden_facts, get_kpi_lineage, render_onepager_markdown, register_output`);
  console.log(`  - Utility: clear_deal_data`);
});

// Graceful shutdown: close pool on process termination
process.on('SIGINT', async () => {
  console.log('\nShutting down gracefully...');
  await pgPool.end();
  process.exit(0);
});

process.on('SIGTERM', async () => {
  console.log('\nShutting down gracefully...');
  await pgPool.end();
  process.exit(0);
});
