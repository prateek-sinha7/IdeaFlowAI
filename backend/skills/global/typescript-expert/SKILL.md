---
name: typescript-expert
display_name: TypeScript Expert
description: TypeScript and JavaScript expert with deep knowledge of type-level programming, performance optimization, monorepo management, migration strategies, and modern tooling.
category: specialist
isBeta: false
tags:
- typescript
- javascript
- type-system
- performance
- monorepo
- migration
---

# TypeScript Expert

This technique covers advanced TypeScript expertise: deep, practical knowledge of type-level programming, performance optimization, and real-world problem solving based on current best practices.

## When invoked:

1. Analyze project setup comprehensively:

   ```bash
   # Core versions and configuration
   npx tsc --version
   node -v
   # Detect tooling ecosystem
   node -e "const p=require('./package.json');console.log(Object.keys({...p.devDependencies,...p.dependencies}||{}).join('\n'))" 2>/dev/null | grep -E 'biome|eslint|prettier|vitest|jest|turborepo|nx' || echo "No tooling detected"
   # Check for monorepo
   (test -f pnpm-workspace.yaml || test -f lerna.json || test -f nx.json || test -f turbo.json) && echo "Monorepo detected"
   ```

   **After detection, adapt approach:**
   - Match import style (absolute vs relative)
   - Respect existing baseUrl/paths configuration
   - Prefer existing project scripts over raw tools
   - In monorepos, consider project references before broad tsconfig changes

2. Identify the specific problem category and complexity level

3. Apply the appropriate solution strategy from expertise

4. Validate thoroughly:
   ```bash
   npm run -s typecheck || npx tsc --noEmit
   npm test -s || npx vitest run --reporter=basic --no-watch
   npm run -s build
   ```

## Advanced Type System Expertise

### Type-Level Programming Patterns

**Branded Types for Domain Modeling**
```typescript
type Brand<K, T> = K & { __brand: T };
type UserId = Brand<string, 'UserId'>;
type OrderId = Brand<string, 'OrderId'>;

function processOrder(orderId: OrderId, userId: UserId) { }
```

**Advanced Conditional Types**
```typescript
type DeepReadonly<T> = T extends (...args: any[]) => any 
  ? T 
  : T extends object 
    ? { readonly [K in keyof T]: DeepReadonly<T[K]> }
    : T;

type PropEventSource<Type> = {
  on<Key extends string & keyof Type>
    (eventName: `${Key}Changed`, callback: (newValue: Type[Key]) => void): void;
};
```

**Type Inference Techniques**
```typescript
// Use 'satisfies' for constraint validation (TS 5.0+)
const config = {
  api: "https://api.example.com",
  timeout: 5000
} satisfies Record<string, string | number>;

// Const assertions for maximum inference
const routes = ['/home', '/about', '/contact'] as const;
type Route = typeof routes[number];
```

### Performance Optimization Strategies

**Type Checking Performance**
```bash
npx tsc --extendedDiagnostics --incremental false | grep -E "Check time|Files:|Lines:|Nodes:"
```

**Build Performance Patterns**
- Enable `skipLibCheck: true` for library type checking only
- Use `incremental: true` with `.tsbuildinfo` cache
- Configure `include`/`exclude` precisely
- For monorepos: Use project references with `composite: true`

## Real-World Problem Resolution

### Complex Error Patterns

**"The inferred type of X cannot be named"**
- Cause: Missing type export or circular dependency
- Fix: Export the required type explicitly, use `ReturnType<typeof function>`, or break circular dependencies

**"Excessive stack depth comparing types"**
```typescript
// Bad: Infinite recursion
type InfiniteArray<T> = T | InfiniteArray<T>[];

// Good: Limited recursion
type NestedArray<T, D extends number = 5> = 
  D extends 0 ? T : T | NestedArray<T, [-1, 0, 1, 2, 3, 4][D]>[];
```

**Module Resolution Mysteries**
- Check `moduleResolution` matches your bundler
- Verify `baseUrl` and `paths` alignment
- For monorepos: Ensure workspace protocol (workspace:*)
- Clear cache: `rm -rf node_modules/.cache .tsbuildinfo`

### Migration Expertise

**JavaScript to TypeScript Migration**
```bash
# Incremental migration strategy
# 1. Enable allowJs and checkJs
# 2. Rename files gradually (.js → .ts)
# 3. Add types file by file
# 4. Enable strict mode features one by one
```

**Tool Migration Decisions**

| From | To | When | Migration Effort |
|------|-----|------|-----------------|
| ESLint + Prettier | Biome | Need much faster speed | Low (1 day) |
| TSC for linting | Type-check only | Have 100+ files | Medium (2-3 days) |
| Lerna | Nx/Turborepo | Need caching, parallel builds | High (1 week) |
| CJS | ESM | Node 18+, modern tooling | High (varies) |

### Monorepo Management

**Nx vs Turborepo Decision Matrix**
- Choose **Turborepo** if: Simple structure, need speed, <20 packages
- Choose **Nx** if: Complex dependencies, need visualization, plugins required

**TypeScript Monorepo Configuration**
```json
{
  "references": [
    { "path": "./packages/core" },
    { "path": "./packages/ui" },
    { "path": "./apps/web" }
  ],
  "compilerOptions": {
    "composite": true,
    "declaration": true,
    "declarationMap": true
  }
}
```

## Modern Tooling Expertise

### Biome vs ESLint

**Use Biome when:** Speed is critical, want single tool for lint + format, TypeScript-first project

**Stay with ESLint when:** Need specific rules/plugins, have complex custom rules, need type-aware linting

### Type Testing Strategies

```typescript
// in avatar.test-d.ts
import { expectTypeOf } from 'vitest'
import type { Avatar } from './avatar'

test('Avatar props are correctly typed', () => {
  expectTypeOf<Avatar>().toHaveProperty('size')
  expectTypeOf<Avatar['size']>().toEqualTypeOf<'sm' | 'md' | 'lg'>()
})
```

## Code Review Checklist

### Type Safety
- [ ] No implicit `any` types
- [ ] Strict null checks properly handled
- [ ] Type assertions (`as`) justified and minimal
- [ ] Generic constraints properly defined
- [ ] Return types explicitly declared for public APIs

### TypeScript Best Practices
- [ ] Prefer `interface` over `type` for object shapes
- [ ] Use const assertions for literal types
- [ ] Leverage type guards and predicates
- [ ] Branded types for domain primitives

### Performance Considerations
- [ ] Type complexity doesn't cause slow compilation
- [ ] No excessive type instantiation depth
- [ ] Project references configured for monorepos

### Module System
- [ ] Consistent import/export patterns
- [ ] No circular dependencies
- [ ] ESM/CJS compatibility handled correctly

## Current Best Practices

### Strict by Default
```json
{
  "compilerOptions": {
    "strict": true,
    "noUncheckedIndexedAccess": true,
    "noImplicitOverride": true,
    "exactOptionalPropertyTypes": true,
    "noPropertyAccessFromIndexSignature": true
  }
}
```

### ESM-First Approach
- Set `"type": "module"` in package.json
- Configure `"moduleResolution": "bundler"` for modern tools
- Use dynamic imports for CJS packages

## Quick Decision Trees

### "Which tool should I use?"
```
Type checking only? → tsc
Type checking + linting speed critical? → Biome  
Type checking + comprehensive linting? → ESLint + typescript-eslint
Type testing? → Vitest expectTypeOf
Build tool? → Project size <10 packages? Turborepo. Else? Nx
```

### "How do I fix this performance issue?"
```
Slow type checking? → skipLibCheck, incremental, project references
Slow builds? → Check bundler config, enable caching
Slow tests? → Vitest with threads, avoid type checking in tests
Slow language server? → Exclude node_modules, limit files in tsconfig
```
