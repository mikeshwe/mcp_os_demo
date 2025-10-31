-- 02_seed.sql
INSERT INTO deals(deal_id, name) VALUES
  ('00000000-0000-0000-0000-000000000001','Acme Software, Inc.')
ON CONFLICT DO NOTHING;

INSERT INTO documents(document_id, deal_id, name, kind, version, sha256)
VALUES ('00000000-0000-0000-0000-000000000101',
        '00000000-0000-0000-0000-000000000001',
        'financials_Q3_2025.xlsx','xlsx','v1', repeat('a',64))
ON CONFLICT DO NOTHING;

INSERT INTO tables_norm(table_id, document_id, name, sheet, note)
VALUES ('00000000-0000-0000-0000-000000000201',
        '00000000-0000-0000-0000-000000000101',
        'P&L','P&L','Normalized extraction')
ON CONFLICT DO NOTHING;

INSERT INTO table_cells(cell_id, table_id, row_idx, col_idx, label, period, value, unit, currency, source_ref)
VALUES 
 ('00000000-0000-0000-0000-000000000301','00000000-0000-0000-0000-000000000201',1,2,'Revenue','2025-09-30',124.3,'USD_mm','USD','financials!B6'),
 ('00000000-0000-0000-0000-000000000302','00000000-0000-0000-0000-000000000201',1,2,'Revenue','2024-09-30',96.8,'USD_mm','USD','financials!B2'),
 ('00000000-0000-0000-0000-000000000303','00000000-0000-0000-0000-000000000201',2,2,'GrossMargin','2025-09-30',72.1,'pct',NULL,'financials!GM_row'),
 ('00000000-0000-0000-0000-000000000304','00000000-0000-0000-0000-000000000201',3,2,'EBITDA_Margin','2025-09-30',18.6,'pct',NULL,'financials!E6');

INSERT INTO kpis(kpi_id, name, description) VALUES
 ('00000000-0000-0000-0000-000000000401','Revenue_LTM','Revenue last twelve months (USD mm)'),
 ('00000000-0000-0000-0000-000000000402','YoY_Growth','Year-over-year revenue growth (%)'),
 ('00000000-0000-0000-0000-000000000403','Gross_Margin','Gross margin (%)'),
 ('00000000-0000-0000-0000-000000000404','EBITDA_Margin','EBITDA margin (%)')
ON CONFLICT DO NOTHING;

INSERT INTO kpi_values(kpi_value_id, kpi_id, deal_id, as_of, value, unit, formula)
VALUES
 ('00000000-0000-0000-0000-000000000501','00000000-0000-0000-0000-000000000401','00000000-0000-0000-0000-000000000001','2025-09-30',124.3,'USD_mm','SUM(LTM revenue)'),
 ('00000000-0000-0000-0000-000000000502','00000000-0000-0000-0000-000000000402','00000000-0000-0000-0000-000000000001','2025-09-30',28.4,'pct','(Rev_t-Rev_t-4)/Rev_t-4'),
 ('00000000-0000-0000-0000-000000000503','00000000-0000-0000-0000-000000000403','00000000-0000-0000-0000-000000000001','2025-09-30',72.1,'pct','GrossProfit/Revenue'),
 ('00000000-0000-0000-0000-000000000504','00000000-0000-0000-0000-000000000404','00000000-0000-0000-0000-000000000001','2025-09-30',18.6,'pct','EBITDA/Revenue');

INSERT INTO kpi_value_sources(kpi_value_id, source_type, source_id) VALUES
 ('00000000-0000-0000-0000-000000000501','cell','00000000-0000-0000-0000-000000000301'),
 ('00000000-0000-0000-0000-000000000502','cell','00000000-0000-0000-0000-000000000301'),
 ('00000000-0000-0000-0000-000000000502','cell','00000000-0000-0000-0000-000000000302'),
 ('00000000-0000-0000-0000-000000000503','cell','00000000-0000-0000-0000-000000000303'),
 ('00000000-0000-0000-0000-000000000504','cell','00000000-0000-0000-0000-000000000304');

INSERT INTO golden_facts(gf_id, kpi_id, deal_id, kpi_value_id, ttl_until, status)
VALUES
 ('00000000-0000-0000-0000-000000000601','00000000-0000-0000-0000-000000000401','00000000-0000-0000-0000-000000000001','00000000-0000-0000-0000-000000000501', now() + interval '90 days','approved'),
 ('00000000-0000-0000-0000-000000000602','00000000-0000-0000-0000-000000000402','00000000-0000-0000-0000-000000000001','00000000-0000-0000-0000-000000000502', now() + interval '90 days','approved'),
 ('00000000-0000-0000-0000-000000000603','00000000-0000-0000-0000-000000000403','00000000-0000-0000-0000-000000000001','00000000-0000-0000-0000-000000000503', now() + interval '90 days','approved'),
 ('00000000-0000-0000-0000-000000000604','00000000-0000-0000-0000-000000000404','00000000-0000-0000-0000-000000000001','00000000-0000-0000-0000-000000000504', now() + interval '90 days','approved');

-- Add memo document and chunks
INSERT INTO documents(document_id, deal_id, name, kind, version, sha256)
VALUES ('00000000-0000-0000-0000-000000000102',
        '00000000-0000-0000-0000-000000000001',
        'memo_q3_2025.txt','txt','v1', repeat('b',64))
ON CONFLICT DO NOTHING;

INSERT INTO chunks(chunk_id, document_id, section, text, access_tag)
VALUES 
 ('00000000-0000-0000-0000-000000000701','00000000-0000-0000-0000-000000000102','Executive Summary','Acme Software continues to demonstrate strong execution in Q3 2025, with revenue growth accelerating and margin expansion driven by enterprise customer adoption and operational efficiency improvements.','internal'),
 ('00000000-0000-0000-0000-000000000702','00000000-0000-0000-0000-000000000102','Financial Performance','Revenue reached $124.3M in Q3 2025, representing 28% year-over-year growth. This growth was primarily driven by: Enterprise Segment: Strong expansion within existing customers, with average contract value increasing 35% year-over-year. New Customer Acquisition: Added 12 enterprise customers in Q3, contributing $18M in new ARR. Geographic Expansion: European operations exceeded targets, accounting for 22% of total revenue. Gross margins improved to 72.1%, up from 68.5% in the prior year quarter, driven by product mix shift toward higher-margin SaaS offerings, infrastructure cost optimization initiatives, and scale efficiencies in customer support operations. EBITDA margins reached 18.6%, reflecting disciplined cost management while maintaining investment in R&D and sales capacity.','lp-safe'),
 ('00000000-0000-0000-0000-000000000703','00000000-0000-0000-0000-000000000102','Product & Market','Product Highlights: Acme Platform 3.0 Launch: Successfully launched next-generation platform with AI-powered workflows, seeing strong adoption with 60% of enterprise customers upgrading within first quarter. Integration Marketplace: Expanded partner ecosystem with 15 new integrations, driving increased platform stickiness. Market Position: Acme maintains its market leadership position in the workflow automation space, with Gartner recognizing the company as a "Leader" in the Magic Quadrant for the third consecutive year.','lp-safe'),
 ('00000000-0000-0000-0000-000000000704','00000000-0000-0000-0000-000000000102','Key Risks & Mitigants','Risk: Competitive Pressure. Mitigant: Continuous product innovation and deep customer relationships provide strong moat. Status: Competitive landscape stable, no new material threats. Risk: Customer Concentration. Mitigant: Top 10 customers now represent 42% of revenue (down from 48% last year), diversification improving. Status: Healthy customer base expansion. Risk: Macroeconomic Uncertainty. Mitigant: Strong retention metrics (95%+ net revenue retention) and long-term contracts provide stability. Status: No material impact observed to date.','lp-safe'),
 ('00000000-0000-0000-0000-000000000705','00000000-0000-0000-0000-000000000102','Outlook','Management expects Q4 revenue to continue strong momentum, with full-year guidance reaffirmed. Investment priorities remain focused on product development and international expansion, with disciplined approach to cost management.','lp-safe');

-- Add EDGAR XBRL document and table_cells
INSERT INTO documents(document_id, deal_id, name, kind, version, sha256)
VALUES ('00000000-0000-0000-0000-000000000103',
        '00000000-0000-0000-0000-000000000001',
        'edgar_xbrl_q3_2025.csv','csv','v1', repeat('c',64))
ON CONFLICT DO NOTHING;

INSERT INTO tables_norm(table_id, document_id, name, sheet, note)
VALUES ('00000000-0000-0000-0000-000000000203',
        '00000000-0000-0000-0000-000000000103',
        'EDGAR_XBRL','EDGAR_XBRL','SEC EDGAR XBRL export')
ON CONFLICT DO NOTHING;

INSERT INTO table_cells(cell_id, table_id, row_idx, col_idx, label, period, value, unit, currency, source_ref)
VALUES 
 ('00000000-0000-0000-0000-000000000401','00000000-0000-0000-0000-000000000203',1,0,'Revenue','2025-09-30',124300000,'USD','USD','us-gaap:Revenues'),
 ('00000000-0000-0000-0000-000000000402','00000000-0000-0000-0000-000000000203',2,0,'GrossProfit','2025-09-30',89600000,'USD','USD','us-gaap:GrossProfit'),
 ('00000000-0000-0000-0000-000000000403','00000000-0000-0000-0000-000000000203',3,0,'OperatingIncome','2025-09-30',23100000,'USD','USD','us-gaap:OperatingIncomeLoss'),
 ('00000000-0000-0000-0000-000000000404','00000000-0000-0000-0000-000000000203',4,0,'NetIncome','2025-09-30',17500000,'USD','USD','us-gaap:NetIncomeLoss'),
 ('00000000-0000-0000-0000-000000000405','00000000-0000-0000-0000-000000000203',5,0,'Assets','2025-09-30',485000000,'USD','USD','us-gaap:Assets'),
 ('00000000-0000-0000-0000-000000000406','00000000-0000-0000-0000-000000000203',6,0,'Liabilities','2025-09-30',198000000,'USD','USD','us-gaap:Liabilities'),
 ('00000000-0000-0000-0000-000000000407','00000000-0000-0000-0000-000000000203',7,0,'StockholdersEquity','2025-09-30',287000000,'USD','USD','us-gaap:StockholdersEquity'),
 ('00000000-0000-0000-0000-000000000408','00000000-0000-0000-0000-000000000203',8,0,'Revenue','2024-09-30',96800000,'USD','USD','us-gaap:Revenues'),
 ('00000000-0000-0000-0000-000000000409','00000000-0000-0000-0000-000000000203',9,0,'GrossProfit','2024-09-30',66300000,'USD','USD','us-gaap:GrossProfit'),
 ('00000000-0000-0000-0000-000000000410','00000000-0000-0000-0000-000000000203',10,0,'OperatingIncome','2024-09-30',14500000,'USD','USD','us-gaap:OperatingIncomeLoss'),
 ('00000000-0000-0000-0000-000000000411','00000000-0000-0000-0000-000000000203',11,0,'NetIncome','2024-09-30',10800000,'USD','USD','us-gaap:NetIncomeLoss'),
 ('00000000-0000-0000-0000-000000000412','00000000-0000-0000-0000-000000000203',12,0,'Assets','2024-09-30',412000000,'USD','USD','us-gaap:Assets'),
 ('00000000-0000-0000-0000-000000000413','00000000-0000-0000-0000-000000000203',13,0,'Liabilities','2024-09-30',178000000,'USD','USD','us-gaap:Liabilities'),
 ('00000000-0000-0000-0000-000000000414','00000000-0000-0000-0000-000000000203',14,0,'StockholdersEquity','2024-09-30',234000000,'USD','USD','us-gaap:StockholdersEquity');
