---
name: k6-load-testing
display_name: k6 Load Testing
description: Comprehensive k6 load testing for API, browser, and scalability testing with realistic scenarios, CI/CD integration, and results analysis.
category: testing
isBeta: false
tags:
- k6
- load-testing
- performance
- api-testing
- ci-cd
- stress-testing
- websocket
- thresholds
---

# k6 Load Testing

## Overview

k6 is a modern, developer-centric load testing tool for HTTP APIs, WebSocket endpoints, and browser scenarios. This skill provides comprehensive guidance on writing realistic load tests, configuring test scenarios (smoke, load, stress, spike, soak), analyzing results, and integrating with CI/CD pipelines.

## When to Use This Skill

- Load test HTTP APIs, WebSocket endpoints, or browser scenarios
- Set up performance regression tests in CI/CD
- Analyze system behavior under various load conditions
- Compare performance between code changes
- Validate SLA requirements and performance budgets

## Test Types

| Type        | Use Case                  | Configuration                  |
|-------------|---------------------------|--------------------------------|
| Smoke Test  | Verify basic functionality | Low VUs (1-5), short duration  |
| Load Test   | Normal expected load       | Target VUs based on traffic    |
| Stress Test | Find breaking point        | Ramp beyond capacity           |
| Spike Test  | Sudden traffic spikes      | Rapid increase/decrease        |
| Soak Test   | Long-term stability        | Extended duration              |

## Quick Start

```javascript
import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  vus: 10,
  duration: '30s',
};

export default function () {
  const res = http.get('https://api.example.com/health');
  check(res, {
    'status is 200': (r) => r.status === 200,
    'response time < 500ms': (r) => r.timings.duration < 500,
  });
  sleep(1);
}
```

## Test Configuration

```javascript
export const options = {
  stages: [
    { duration: '30s', target: 20 },
    { duration: '1m', target: 100 },
    { duration: '30s', target: 0 },
  ],
  thresholds: {
    http_req_duration: ['p(95)<500'],
    http_req_failed: ['rate<0.01'],
  },
};
```

## CI/CD Integration (GitLab)

```yaml
load_test:
  image: grafana/k6:latest
  script:
    - k6 run load-test.js
  artifacts:
    when: always
    paths:
      - results.json
```

## Results Interpretation

| Metric                   | Good     | Warning    | Bad      |
|--------------------------|----------|------------|----------|
| http_req_duration (p95)  | < 300ms  | 300-500ms  | > 500ms  |
| http_req_failed          | < 0.1%   | 0.1-1%     | > 1%     |
| http_reqs (rate)         | Meeting target | Near limit | At limit |

## Best Practices

- Start with smoke test (1-5 VUs) before scaling up
- Use realistic data with parameterization
- Set meaningful thresholds matching SLA requirements
- Include ramp-up time in stages
- Use tags for granular analysis
- Monitor external dependencies alongside your APIs
- Keep tests focused: one file per scenario
