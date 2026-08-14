---
name: aws-cloud-patterns
display_name: AWS Cloud Patterns
description: AWS cloud patterns for Lambda, ECS, S3, DynamoDB, and Infrastructure as Code with CDK/Terraform.
category: workflow
isBeta: false
tags:
- aws
- lambda
- dynamodb
- ecs
- s3
- cdk
- serverless
- cloud-architecture
---

# AWS Cloud Patterns

## Lambda Function Pattern

```typescript
import { APIGatewayProxyHandlerV2 } from "aws-lambda";
import { DynamoDBClient } from "@aws-sdk/client-dynamodb";
import { DynamoDBDocumentClient, GetCommand } from "@aws-sdk/lib-dynamodb";

const client = DynamoDBDocumentClient.from(new DynamoDBClient({}));

export const handler: APIGatewayProxyHandlerV2 = async (event) => {
  const id = event.pathParameters?.id;
  if (!id) {
    return { statusCode: 400, body: JSON.stringify({ error: "Missing id" }) };
  }

  const result = await client.send(
    new GetCommand({ TableName: process.env.TABLE_NAME!, Key: { pk: id } })
  );

  if (!result.Item) {
    return { statusCode: 404, body: JSON.stringify({ error: "Not found" }) };
  }

  return {
    statusCode: 200,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(result.Item),
  };
};
```

Initialize SDK clients outside the handler to reuse connections across invocations.

## DynamoDB Single-Table Design

```typescript
interface OrderItem {
  pk: string;          // USER#<userId>
  sk: string;          // ORDER#<orderId>
  gsi1pk: string;      // ORDER#<orderId>
  gsi1sk: string;      // ITEM#<itemId>
  entityType: string;  // "Order" | "OrderItem"
  data: Record<string, any>;
  ttl?: number;
}
```

## Key AWS Patterns

| Pattern | Service | Use Case |
|---------|---------|----------|
| Event-Driven | Lambda + SQS/SNS | Async processing |
| API Gateway | API GW + Lambda | REST/HTTP APIs |
| Container Services | ECS/Fargate | Long-running services |
| Static Hosting | S3 + CloudFront | Frontend apps |
| Data Lake | S3 + Glue + Athena | Analytics |

## Best Practices

1. **Initialize outside handler**: Reuse SDK clients across invocations
2. **Use environment variables**: Never hardcode resource names or ARNs
3. **Least privilege IAM**: Scope permissions to specific resources and actions
4. **Enable encryption**: S3 SSE, DynamoDB encryption at rest, KMS for secrets
5. **Use VPC endpoints**: Avoid NAT Gateway costs for AWS service access
6. **Tag everything**: Cost allocation, environment, team ownership
7. **Set alarms**: CloudWatch alarms on error rates and latency
