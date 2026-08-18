---
name: gitlab-ci-patterns
display_name: GitLab CI Patterns
description: Build GitLab CI/CD pipelines with multi-stage workflows, caching, and distributed runners for scalable automation.
category: workflow
isBeta: false
tags:
- gitlab
- ci-cd
- pipelines
- docker
- kubernetes
- caching
- deployment
- automation
---

# GitLab CI Patterns

Comprehensive GitLab CI/CD pipeline patterns for automated testing, building, and deployment.

## When to Use

- Automate GitLab-based CI/CD
- Implement multi-stage pipelines
- Configure GitLab Runners
- Deploy to Kubernetes from GitLab
- Implement GitOps workflows

## Basic Pipeline Structure

```yaml
stages:
  - build
  - test
  - deploy

variables:
  DOCKER_DRIVER: overlay2
  DOCKER_TLS_CERTDIR: "/certs"

build:
  stage: build
  image: node:20
  script:
    - npm ci
    - npm run build
  artifacts:
    paths:
      - dist/
    expire_in: 1 hour
  cache:
    key: ${CI_COMMIT_REF_SLUG}
    paths:
      - node_modules/

test:
  stage: test
  image: node:20
  script:
    - npm ci
    - npm run lint
    - npm test
  coverage: '/Lines\s*:\s*(\d+\.\d+)%/'
  artifacts:
    reports:
      coverage_report:
        coverage_format: cobertura
        path: coverage/cobertura-coverage.xml

deploy_staging:
  stage: deploy
  image: alpine/k8s:latest
  script:
    - kubectl apply -f k8s/staging/
  environment:
    name: staging
    url: https://staging.example.com
  only:
    - develop

deploy_production:
  stage: deploy
  image: alpine/k8s:latest
  script:
    - kubectl apply -f k8s/production/
  environment:
    name: production
    url: https://example.com
  only:
    - main
  when: manual
```

## Docker Build Pipeline

```yaml
build_image:
  stage: build
  image: docker:24.0
  services:
    - docker:24.0-dind
  script:
    - docker build -t $CI_REGISTRY_IMAGE:$CI_COMMIT_SHA .
    - docker push $CI_REGISTRY_IMAGE:$CI_COMMIT_SHA
  before_script:
    - docker login -u $CI_REGISTRY_USER -p $CI_REGISTRY_PASSWORD $CI_REGISTRY
```

## Best Practices

1. **Cache dependencies**: Use `cache` for node_modules, pip packages
2. **Use artifacts**: Pass build outputs between stages
3. **Parallel jobs**: Split test suites across parallel runners
4. **Environment protection**: Require manual approval for production
5. **Use variables**: Store secrets in CI/CD settings, not code
6. **Include templates**: Use `include` for shared pipeline configs
7. **Rules over only/except**: Prefer `rules:` syntax for conditions
