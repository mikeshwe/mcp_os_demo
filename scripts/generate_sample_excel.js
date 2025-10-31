// Script to generate sample Excel file for demo
import XLSX from 'xlsx';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// Create workbook
const workbook = XLSX.utils.book_new();

// Create P&L sheet data
const plData = [
  ['Metric', 'Q3 2024', 'Q3 2025', 'Unit'],
  ['Revenue', 96.8, 124.3, 'USD (mm)'],
  ['Gross Profit', 66.3, 89.6, 'USD (mm)'],
  ['Gross Margin', 68.5, 72.1, '%'],
  ['Operating Income', 14.5, 23.1, 'USD (mm)'],
  ['EBITDA', 14.2, 22.9, 'USD (mm)'],
  ['EBITDA Margin', 14.7, 18.6, '%'],
  ['Net Income', 10.8, 17.5, 'USD (mm)'],
];

// Create P&L worksheet
const plSheet = XLSX.utils.aoa_to_sheet(plData);
XLSX.utils.book_append_sheet(workbook, plSheet, 'P&L');

// Create Balance Sheet data
const bsData = [
  ['Metric', 'Q3 2024', 'Q3 2025', 'Unit'],
  ['Total Assets', 412.0, 485.0, 'USD (mm)'],
  ['Cash & Equivalents', 125.0, 145.0, 'USD (mm)'],
  ['Accounts Receivable', 45.2, 52.3, 'USD (mm)'],
  ['Total Liabilities', 178.0, 198.0, 'USD (mm)'],
  ['Current Liabilities', 85.0, 92.0, 'USD (mm)'],
  ['Stockholders Equity', 234.0, 287.0, 'USD (mm)'],
];

// Create Balance Sheet worksheet
const bsSheet = XLSX.utils.aoa_to_sheet(bsData);
XLSX.utils.book_append_sheet(workbook, bsSheet, 'Balance Sheet');

// Write file
const outputPath = path.join(__dirname, '..', 'data', 'financials_Q3_2025.xlsx');
XLSX.writeFile(workbook, outputPath);

console.log(`✓ Created sample Excel file: ${outputPath}`);
console.log(`  - P&L sheet with Q3 2024 and Q3 2025 data`);
console.log(`  - Balance Sheet sheet with Q3 2024 and Q3 2025 data`);

