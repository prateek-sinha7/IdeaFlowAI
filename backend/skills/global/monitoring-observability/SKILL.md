---
name: monitoring-observability
display_name: Monitoring & Observability
description: Monitoring and observability with OpenTelemetry, Prometheus, Grafana dashboards, and structured logging.
category: testing
isBeta: false
tags:
- opentelemetry
- prometheus
- grafana
- structured-logging
- tracing
- metrics
- distributed-systems
- alerting
---

# Monitoring & Observability

## OpenTelemetry Setup

```typescript
import { NodeSDK } from "@opentelemetry/sdk-node";
import { OTLPTraceExporter } from "@opentelemetry/exporter-trace-otlp-http";
import { OTLPMetricExporter } from "@opentelemetry/exporter-metrics-otlp-http";
import { HttpInstrumentation } from "@opentelemetry/instrumentation-http";
import { PgInstrumentation } from "@opentelemetry/instrumentation-pg";
import { PeriodicExportingMetricReader } from "@opentelemetry/sdk-metrics";

const sdk = new NodeSDK({
  serviceName: "order-service",
  traceExporter: new OTLPTraceExporter({
    url: "http://otel-collector:4318/v1/traces",
  }),
  metricReader: new PeriodicExportingMetricReader({
    exporter: new OTLPMetricExporter({
      url: "http://otel-collector:4318/v1/metrics",
    }),
    exportIntervalMillis: 15000,
  }),
  instrumentations: [
    new HttpInstrumentation(),
    new PgInstrumentation(),
  ],
});

sdk.start();
process.on("SIGTERM", () => sdk.shutdown());
```

## Custom Spans and Metrics

```typescript
import { trace, metrics, SpanStatusCode } from "@opentelemetry/api";

const tracer = trace.getTracer("order-service");
const meter = metrics.getMeter("order-service");

const orderCounter = meter.createCounter("orders.created", {
  description: "Number of orders created",
});

const orderDuration = meter.createHistogram("orders.processing_duration_ms", {
  description: "Order processing duration in milliseconds",
  unit: "ms",
});

async function createOrder(input: CreateOrderInput) {
  return tracer.startActiveSpan("createOrder", async (span) => {
    try {
      span.setAttributes({
        "order.customer_id": input.customerId,
        "order.item_count": input.items.length,
      });

      const start = performance.now();
      const order = await db.order.create({ data: input });

      orderCounter.add(1, { status: "success" });
      orderDuration.record(performance.now() - start);

      span.setStatus({ code: SpanStatusCode.OK });
      return order;
    } catch (error) {
      span.setStatus({ code: SpanStatusCode.ERROR, message: error.message });
      orderCounter.add(1, { status: "error" });
      throw error;
    } finally {
      span.end();
    }
  });
}
```

## Three Pillars

| Pillar  | Purpose                          | Tools                      |
|---------|----------------------------------|----------------------------|
| Logs    | Event records with context       | Structured JSON, ELK, Loki |
| Metrics | Aggregated numerical measurements | Prometheus, Grafana        |
| Traces  | Request flow across services     | Jaeger, Tempo, Zipkin      |

## Best Practices

1. **Instrument at boundaries**: HTTP handlers, database calls, external APIs
2. **Use structured logging**: JSON format with correlation IDs
3. **Set meaningful alerts**: Alert on symptoms, not causes
4. **Track SLIs/SLOs**: Latency, error rate, throughput, saturation
5. **Propagate context**: Pass trace IDs across service boundaries
6. **Dashboard hierarchy**: Overview → Service → Detail views
