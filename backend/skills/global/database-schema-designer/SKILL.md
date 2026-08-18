---
name: database-schema-designer
display_name: Database Schema Designer
description: Design robust, scalable database schemas for SQL and NoSQL databases. Provides normalization guidelines, indexing strategies, migration patterns, constraint design, and performance optimization.
category: specialist
isBeta: false
tags:
- database
- schema
- sql
- nosql
- normalization
- indexing
---

# Database Schema Designer

Design production-ready database schemas with best practices built-in.

## Quick Start

Describe your data model:
```
design a schema for an e-commerce platform with users, products, orders
```

You'll get a complete SQL schema with proper constraints, indexes, and relationships.

## Core Principles

| Principle | WHY | Implementation |
|-----------|-----|----------------|
| Model the Domain | UI changes, domain doesn't | Entity names reflect business concepts |
| Data Integrity First | Corruption is costly to fix | Constraints at database level |
| Optimize for Access Pattern | Can't optimize for both | OLTP: normalized, OLAP: denormalized |
| Plan for Scale | Retrofitting is painful | Index strategy + partitioning plan |

## Process Overview

```
Your Data Requirements
    → Phase 1: ANALYSIS (entities, relationships, access patterns)
    → Phase 2: DESIGN (normalize, keys, data types, constraints)
    → Phase 3: OPTIMIZE (indexing, denormalization, timestamps)
    → Phase 4: MIGRATE (scripts, backward compatibility, zero-downtime)
    → Production-Ready Schema
```

## Quick Reference

| Task | Approach | Key Consideration |
|------|----------|-------------------|
| New schema | Normalize to 3NF first | Domain modeling over UI |
| SQL vs NoSQL | Access patterns decide | Read/write ratio matters |
| Primary keys | INT or UUID | UUID for distributed systems |
| Foreign keys | Always constrain | ON DELETE strategy critical |
| Indexes | FKs + WHERE columns | Column order matters |
| Migrations | Always reversible | Backward compatible first |

## Anti-Patterns

| Avoid | Why | Instead |
|-------|-----|---------|
| VARCHAR(255) everywhere | Wastes storage, hides intent | Size appropriately per field |
| FLOAT for money | Rounding errors | DECIMAL(10,2) |
| Missing FK constraints | Orphaned data | Always define foreign keys |
| No indexes on FKs | Slow JOINs | Index every foreign key |
| Storing dates as strings | Can't compare/sort | DATE, TIMESTAMP types |
| Non-reversible migrations | Can't rollback | Always write DOWN migration |

## Normalization Guidelines

| Form | Rule | Violation Example |
|------|------|-------------------|
| **1NF** | Atomic values, no repeating groups | `product_ids = '1,2,3'` |
| **2NF** | 1NF + no partial dependencies | customer_name in order_items |
| **3NF** | 2NF + no transitive dependencies | country derived from postal_code |

### When to Denormalize

| Scenario | Strategy |
|----------|----------|
| Read-heavy reporting | Pre-calculated aggregates |
| Expensive JOINs | Cached derived columns |
| Analytics dashboards | Materialized views |

## Indexing Strategy

### When to Create Indexes

| Always Index | Reason |
|--------------|--------|
| Foreign keys | Speed up JOINs |
| WHERE clause columns | Speed up filtering |
| ORDER BY columns | Speed up sorting |
| Unique constraints | Enforced uniqueness |

### Composite Index Order
```sql
CREATE INDEX idx_customer_status ON orders(customer_id, status);
-- Uses index: WHERE customer_id = 123
-- Uses index: WHERE customer_id = 123 AND status = 'pending'
-- Does NOT use index: WHERE status = 'pending' (alone)
```

**Rule:** Most selective column first, or column most queried alone.

## Relationship Patterns

### One-to-Many
```sql
CREATE TABLE order_items (
  id INT PRIMARY KEY,
  order_id INT NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
  product_id INT NOT NULL,
  quantity INT NOT NULL
);
```

### Many-to-Many
```sql
CREATE TABLE enrollments (
  student_id INT REFERENCES students(id) ON DELETE CASCADE,
  course_id INT REFERENCES courses(id) ON DELETE CASCADE,
  enrolled_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (student_id, course_id)
);
```

## Migration Best Practices

### Adding a Column (Zero-Downtime)
```sql
-- Step 1: Add nullable column
ALTER TABLE users ADD COLUMN phone VARCHAR(20);
-- Step 2: Deploy code that writes to new column
-- Step 3: Backfill existing rows
UPDATE users SET phone = '' WHERE phone IS NULL;
-- Step 4: Make required (if needed)
ALTER TABLE users MODIFY phone VARCHAR(20) NOT NULL;
```

## NoSQL Design (MongoDB)

### Embedding vs Referencing

| Factor | Embed | Reference |
|--------|-------|-----------|
| Access pattern | Read together | Read separately |
| Relationship | 1:few | 1:many |
| Document size | Small | Approaching 16MB |
| Update frequency | Rarely | Frequently |

## Verification Checklist

- [ ] Every table has a primary key
- [ ] All relationships have foreign key constraints
- [ ] ON DELETE strategy defined for each FK
- [ ] Indexes exist on all foreign keys
- [ ] Indexes exist on frequently queried columns
- [ ] Appropriate data types (DECIMAL for money, etc.)
- [ ] NOT NULL on required fields
- [ ] UNIQUE constraints where needed
- [ ] CHECK constraints for validation
- [ ] created_at and updated_at timestamps
- [ ] Migration scripts are reversible
