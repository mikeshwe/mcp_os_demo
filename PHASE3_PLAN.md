# Phase 3: Security & Governance Implementation Plan

## Overview

Phase 3 adds security and governance features to ensure data access control, auditability, and policy compliance.

## Components to Implement

### 3.1 Access Tagging System ✅ (Partially Implemented)

**Current State:**
- ✅ `chunks` table has `access_tag` field (default: 'internal')
- ✅ `ingest_memo` tool accepts `access_tag` parameter
- ❌ `table_cells` table doesn't have `access_tag` field
- ❌ No access filtering in query tools
- ❌ No access_tag inheritance from documents

**What Needs to be Added:**

1. **Add `access_tag` to `table_cells` table**
   ```sql
   ALTER TABLE table_cells ADD COLUMN access_tag TEXT DEFAULT 'internal';
   ```

2. **Add `access_tag` parameter to all ingestion tools**
   - `ingest_excel` - tag extracted cells
   - `ingest_csv` - tag extracted cells
   - `ingest_billing` - tag extracted cells
   - `ingest_edgar_xbrl` - tag extracted cells (typically 'lp-safe')
   - `ingest_snowflake` - tag extracted cells

3. **Add access filtering to read tools**
   - `get_golden_facts` - filter by access_tag (e.g., only 'lp-safe' for LP users)
   - `get_kpi_lineage` - filter source cells by access_tag

4. **Add access check helper function**
   ```typescript
   async function checkAccess(objectKind: string, objectId: string, requiredTag: string): Promise<boolean>
   ```

---

### 3.2 Audit Logging System ❌ (Not Implemented)

**What Needs to be Added:**

1. **Create audit_log table** (if not exists)
   ```sql
   CREATE TABLE IF NOT EXISTS audit_log (
     audit_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
     tool_name TEXT NOT NULL,
     tool_params JSONB NOT NULL,
     user_id TEXT,
     session_id TEXT,
     deal_id UUID REFERENCES deals(deal_id),
     execution_time_ms INT,
     status TEXT CHECK (status IN ('success','error')),
     error_message TEXT,
     created_at TIMESTAMPTZ NOT NULL DEFAULT now()
   );
   
   CREATE INDEX idx_audit_log_deal_id ON audit_log(deal_id);
   CREATE INDEX idx_audit_log_tool_name ON audit_log(tool_name);
   CREATE INDEX idx_audit_log_created_at ON audit_log(created_at);
   ```

2. **Add audit logging wrapper**
   ```typescript
   async function auditToolCall(
     toolName: string,
     params: any,
     options: {
       userId?: string;
       sessionId?: string;
       dealId?: string;
     }
   ): Promise<void>
   ```

3. **Wrap all tool handlers** with audit logging
   - Log before execution (with params)
   - Log after execution (with result status, timing)
   - Log errors (with error message)

4. **Add execution timing**
   ```typescript
   const startTime = Date.now();
   try {
     const result = await toolLogic();
     await auditToolCall(toolName, params, { status: 'success', executionTime: Date.now() - startTime });
     return result;
   } catch (error) {
     await auditToolCall(toolName, params, { status: 'error', errorMessage: error.message });
     throw error;
   }
   ```

---

### 3.3 Policy Checks System ❌ (Not Implemented)

**What Needs to be Added:**

1. **Policy validation helper**
   ```typescript
   async function checkPolicy(
     policyName: string,
     context: {
       toolName: string;
       dealId: string;
       userId?: string;
       params: any;
     }
   ): Promise<{ allowed: boolean; reason?: string }>
   ```

2. **Policy evaluation logic**
   - Load policy from `policies` table
   - Evaluate rules (JSONB structure)
   - Examples:
     - "Only allow compute_kpis if deal status is 'active'"
     - "Require approval workflow for MNPI data"
     - "Rate limit: max 10 ingestions per hour per deal"

3. **Add policy checks to critical tools**
   - Before `compute_kpis` - check if deal allows computation
   - Before `ingest_*` tools - check rate limits, access permissions
   - Before `render_onepager_markdown` - check if output policy allows

4. **Policy enforcement points**
   ```typescript
   const policyCheck = await checkPolicy('compute_kpis_policy', {
     toolName: 'compute_kpis',
     dealId,
     params
   });
   if (!policyCheck.allowed) {
     throw new Error(`Policy violation: ${policyCheck.reason}`);
   }
   ```

---

### 3.4 Access Control Lists (ACLs) ❌ (Not Implemented)

**What Needs to be Added:**

1. **ACL checking helper**
   ```typescript
   async function checkACL(
     subject: string,  // user_id or role
     objectKind: string,  // 'deal', 'document', 'kpi_value'
     objectId: string,
     permission: string  // 'read', 'write', 'execute'
   ): Promise<boolean>
   ```

2. **Add ACL checks to tools**
   - `get_golden_facts` - check 'read' permission on deal
   - `compute_kpis` - check 'write' permission on deal
   - `ingest_*` tools - check 'write' permission on deal

3. **User context extraction**
   - Extract user_id from MCP session or request headers
   - Pass to ACL checks

---

### 3.5 Read-Only Connector Enforcement ❌ (Not Implemented)

**What Needs to be Added:**

1. **Connector configuration**
   ```typescript
   const CONNECTOR_CONFIG = {
     snowflake: { readOnly: true },
     edgar: { readOnly: true },
     billing: { readOnly: false },  // allows writes
   };
   ```

2. **Enforce read-only for ingestion tools**
   - `ingest_snowflake` - verify no write operations
   - `ingest_edgar_xbrl` - verify read-only mode

---

## Implementation Order

### Priority 1: Audit Logging (Foundation)
1. Create `audit_log` table
2. Add `auditToolCall()` helper
3. Wrap all 11 tools with audit logging
4. Test audit trail generation

### Priority 2: Access Tagging (Data Classification)
1. Add `access_tag` to `table_cells` table
2. Add `access_tag` parameter to ingestion tools
3. Implement access filtering in `get_golden_facts`
4. Implement access filtering in `get_kpi_lineage`

### Priority 3: Policy Checks (Business Rules)
1. Create policy evaluation helper
2. Define default policies in database
3. Add policy checks to critical operations
4. Add policy violation error handling

### Priority 4: ACLs (Fine-grained Access)
1. Implement ACL checking helper
2. Add user context extraction from MCP sessions
3. Add ACL checks to read/write operations
4. Document ACL structure

### Priority 5: Read-Only Enforcement (Connector Safety)
1. Add connector configuration
2. Enforce read-only for external connectors
3. Add validation errors

---

## Database Schema Changes Required

```sql
-- Add access_tag to table_cells
ALTER TABLE table_cells ADD COLUMN IF NOT EXISTS access_tag TEXT DEFAULT 'internal';

-- Create audit_log table
CREATE TABLE IF NOT EXISTS audit_log (
  audit_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  tool_name TEXT NOT NULL,
  tool_params JSONB NOT NULL,
  user_id TEXT,
  session_id TEXT,
  deal_id UUID REFERENCES deals(deal_id),
  execution_time_ms INT,
  status TEXT CHECK (status IN ('success','error')),
  error_message TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_audit_log_deal_id ON audit_log(deal_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_tool_name ON audit_log(tool_name);
CREATE INDEX IF NOT EXISTS idx_audit_log_created_at ON audit_log(created_at);
CREATE INDEX IF NOT EXISTS idx_audit_log_user_id ON audit_log(user_id);

-- Seed default policies
INSERT INTO policies (name, rules) VALUES
  ('compute_kpis_policy', '{"allowed": true, "require_deal_active": true}'::jsonb),
  ('ingestion_rate_limit', '{"max_per_hour": 10, "max_per_deal": 50}'::jsonb),
  ('lp_safe_output', '{"require_lp_safe_tag": true}'::jsonb)
ON CONFLICT (name) DO NOTHING;
```

---

## Code Changes Required

### Estimated Lines of Code
- Audit logging: ~150 lines
- Access tagging: ~200 lines
- Policy checks: ~150 lines
- ACLs: ~100 lines
- Read-only enforcement: ~50 lines
- **Total: ~650 lines**

### Files to Modify
- `mcp-lp-tools-server.ts` - Add all security features
- `sql/01_schema.sql` - Add audit_log table (or create migration)
- `sql/04_security.sql` - New file for security seed data

---

## Testing Requirements

1. **Audit Logging Tests**
   - Verify all tool calls are logged
   - Verify execution times are recorded
   - Verify errors are logged with messages

2. **Access Tagging Tests**
   - Verify LP-safe filtering works
   - Verify MNPI data is excluded from LP views
   - Verify access_tag inheritance

3. **Policy Tests**
   - Verify policy violations are rejected
   - Verify rate limits are enforced
   - Verify business rules are applied

4. **ACL Tests**
   - Verify unauthorized access is denied
   - Verify permission checks work correctly

---

## Success Criteria

✅ All tool calls are audited
✅ Access tags are enforced in queries
✅ Policies can prevent unauthorized operations
✅ ACLs control fine-grained access
✅ Read-only connectors cannot write data
✅ Security features are transparent to LLM agents

