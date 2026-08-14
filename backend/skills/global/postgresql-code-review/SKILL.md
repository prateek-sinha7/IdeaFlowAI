---
name: postgresql-code-review
display_name: PostgreSQL Code Review
description: PostgreSQL-specific code review focusing on best practices, anti-patterns, JSONB operations, array usage, and Row Level Security.
category: collaboration
isBeta: false
tags:
- postgresql
- code-review
- jsonb
- rls
- schema-design
- anti-patterns
- performance
- security
---

# PostgreSQL Code Review

Expert PostgreSQL code review focusing on PostgreSQL-specific best practices, anti-patterns, and quality standards.

## Review Areas

### JSONB Best Practices

```sql
-- BAD: Inefficient JSONB usage (no index support)
SELECT * FROM orders WHERE data->>'status' = 'shipped';

-- GOOD: Indexable JSONB queries
CREATE INDEX idx_orders_status ON orders USING gin((data->'status'));
SELECT * FROM orders WHERE data @> '{"status": "shipped"}';

-- GOOD: Add JSONB validation
ALTER TABLE orders ADD CONSTRAINT valid_status
CHECK (data->>'status' IN ('pending', 'shipped', 'delivered'));
```

### Array Operations

```sql
-- BAD: Inefficient array operations (no index)
SELECT * FROM products WHERE 'electronics' = ANY(categories);

-- GOOD: GIN indexed array queries
CREATE INDEX idx_products_categories ON products USING gin(categories);
SELECT * FROM products WHERE categories @> ARRAY['electronics'];
```

### Schema Design

```sql
-- BAD: Not using PostgreSQL features
CREATE TABLE users (
    id INTEGER,
    email VARCHAR(255),
    created_at TIMESTAMP
);

-- GOOD: PostgreSQL-optimized schema
CREATE TABLE users (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email CITEXT UNIQUE NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'
);
```

### Row Level Security

```sql
-- Enable RLS for multi-tenant data isolation
ALTER TABLE orders ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON orders
  FOR ALL TO app_users
  USING (tenant_id = current_setting('app.current_tenant')::uuid);
```

## Review Checklist

- [ ] Uses `TIMESTAMPTZ` not `TIMESTAMP`
- [ ] Uses `TEXT` not `VARCHAR(n)` or `CHAR(n)`
- [ ] Uses `GENERATED ALWAYS AS IDENTITY` not `SERIAL`
- [ ] FK columns have explicit indexes
- [ ] JSONB columns have GIN indexes for queried paths
- [ ] NOT NULL constraints where semantically required
- [ ] CHECK constraints for value validation
- [ ] Appropriate ON DELETE/UPDATE actions on FKs
- [ ] No `SELECT *` in production queries
- [ ] RLS policies for multi-tenant access
