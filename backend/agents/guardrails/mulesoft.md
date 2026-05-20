# MuleSoft Integration Rules

## Inventory and Discovery

- For every Mule application, document: application name, Mule runtime version (3.x or 4.x), flows and sub-flows with their triggers, connectors in use, DataWeave transforms, and exception strategies.
- Identify shared resources: global configs, secure properties, and API Manager policies.
- Flag migration risk hotspots — flows that rely on proprietary Mule features with no direct equivalent in the target stack (AnypointMQ FIFO ordering, custom Java components, complex DataWeave streaming).

## Flow Design

- Name flows in kebab-case, prefixed by the business capability they serve (e.g., `order-fulfilment-http-listener`).
- Keep flows focused on a single responsibility; extract reusable logic into sub-flows.
- Use `on-error-continue` for recoverable errors and `on-error-propagate` for fatal ones; always configure a dead-letter queue for async flows.
- Document the trigger type (HTTP listener, scheduler, JMS, Salesforce, etc.) and downstream connectors for every flow.

## DataWeave Transforms

- Prefer external `.dwl` files over inline transforms for any logic longer than 5 lines.
- Document input and output media types and a one-line description of the transformation intent.
- Note semantic gaps when porting to Java: implicit type coercion, currency rounding modes, locale-sensitive date parsing.
- When migrating DataWeave to Java, use MapStruct mappers for declarative mappings; fall back to hand-written `@Component` translators for conditional branching or recursion.

## Connectors and Integrations

- Catalogue every connector (HTTP, Database, Salesforce, SAP, File, JMS, AnypointMQ, Object Store) with its configuration and the flows that use it.
- Map AnypointMQ queues to SQS standard queues and AnypointMQ topics to SNS topics in the target architecture.
- Replace Anypoint Connectors that have no OSS analogue with the closest AWS or Spring Cloud equivalent; document the behavioural difference.

## Error Handling

- Every flow must have an explicit error handler; do not rely on the default Mule error handler in production flows.
- Configure DLQs with a redrive policy and a CloudWatch alarm on `ApproximateNumberOfMessagesVisible`.
- Log correlation IDs through all error paths to enable end-to-end tracing.

## Migration Guardrails

- Prefer 3–7 microservices for a typical Mule estate; splitting too fine creates choreography pain.
- Distinguish strangler-pattern services (peeling off one Mule flow at a time) from clean greenfield rewrites.
- Run a parallel-run validation harness before cutover; define explicit numeric cutover gates.
