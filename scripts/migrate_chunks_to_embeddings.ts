// Migration script to generate embeddings for existing chunks using ChromaDB
// Usage: DB_URL=postgres://mcp:mcp@localhost:5433/mcp_ctx npx tsx scripts/migrate_chunks_to_embeddings.ts

import { Client } from "pg";
import { exec } from "child_process";
import { promisify } from "util";
import * as fs from "fs";
import * as path from "path";

const execAsync = promisify(exec);
const DB_URL = process.env.DB_URL ?? "postgres://mcp:mcp@localhost:5433/mcp_ctx";
const EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"; // ChromaDB default model
const pgClient = new Client({ connectionString: DB_URL });

async function generateEmbeddingPython(text: string): Promise<number[]> {
  const scriptPath = path.join(process.cwd(), 'scripts', 'generate_embeddings_python.py');
  const venvPython = path.join(process.cwd(), 'venv', 'bin', 'python3');
  const pythonCmd = fs.existsSync(venvPython) ? venvPython : 'python3';
  
  const textB64 = Buffer.from(text).toString('base64');
  const { stdout, stderr } = await execAsync(`${pythonCmd} "${scriptPath}" "${textB64}"`);
  
  if (stderr && stderr.trim()) {
    console.warn("Python script stderr:", stderr);
  }
  
  const result = JSON.parse(stdout);
  if (result.error) {
    throw new Error(result.error);
  }
  
  const embeddings = Array.isArray(result) ? result : [result];
  return Array.isArray(embeddings[0]) ? embeddings[0] : embeddings;
}

async function generateEmbeddingsPython(texts: string[]): Promise<number[][]> {
  const scriptPath = path.join(process.cwd(), 'scripts', 'generate_embeddings_python.py');
  const venvPython = path.join(process.cwd(), 'venv', 'bin', 'python3');
  const pythonCmd = fs.existsSync(venvPython) ? venvPython : 'python3';
  
  const textArgs = texts.map(t => Buffer.from(t).toString('base64'));
  const { stdout, stderr } = await execAsync(`${pythonCmd} "${scriptPath}" ${textArgs.map(t => `"${t}"`).join(' ')}`);
  
  if (stderr && stderr.trim() && !stderr.includes('onnx')) {
    console.warn("Python script stderr:", stderr);
  }
  
  const result = JSON.parse(stdout);
  if (result.error) {
    throw new Error(result.error);
  }
  
  return Array.isArray(result) && Array.isArray(result[0]) ? result : [result];
}

async function migrateExistingChunks() {
  await pgClient.connect();
  console.log("Connected to database");

  // Find chunks without embeddings
  const { rows } = await pgClient.query(`
    SELECT c.chunk_id, c.text
    FROM chunks c
    LEFT JOIN embeddings e ON e.chunk_id = c.chunk_id
    WHERE e.chunk_id IS NULL
  `);

  console.log(`Found ${rows.length} chunks without embeddings`);

  if (rows.length === 0) {
    console.log("No chunks to migrate. Exiting.");
    await pgClient.end();
    return;
  }

  // Process in batches to avoid overloading
  const batchSize = 10;
  let processed = 0;
  
  for (let i = 0; i < rows.length; i += batchSize) {
    const batch = rows.slice(i, i + batchSize);
    console.log(`Processing batch ${Math.floor(i / batchSize) + 1}/${Math.ceil(rows.length / batchSize)} (${batch.length} chunks)...`);
    
    try {
      const texts = batch.map(r => r.text);
      const embeddings = await generateEmbeddingsPython(texts);
      
      // Insert embeddings
      const valuesSql: string[] = [];
      const params: any[] = [];
      let j = 1;
      for (let idx = 0; idx < batch.length; idx++) {
        valuesSql.push(`($${j++},$${j++},$${j++}::vector)`);
        params.push(
          batch[idx].chunk_id,
          EMBEDDING_MODEL,
          `[${embeddings[idx].join(',')}]`
        );
      }
      
      const sql = `INSERT INTO embeddings(chunk_id, model, vector) VALUES ${valuesSql.join(",")}`;
      await pgClient.query(sql, params);
      
      processed += batch.length;
      console.log(`✓ Processed ${processed}/${rows.length} chunks`);
      
      // Small delay to avoid overloading
      if (i + batchSize < rows.length) {
        await new Promise(resolve => setTimeout(resolve, 100));
      }
    } catch (error: any) {
      console.error(`Error processing batch: ${error.message}`);
      console.error("Skipping batch and continuing...");
    }
  }

  console.log(`\nMigration complete! Processed ${processed}/${rows.length} chunks.`);
  await pgClient.end();
}

// Run migration
migrateExistingChunks().catch(error => {
  console.error("Migration failed:", error);
  process.exit(1);
});
