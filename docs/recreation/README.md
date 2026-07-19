# Open Notebook Plus Reconstruction Pack

This directory is a reconstruction-grade technical record for the
`desktop-app` branch of Open Notebook Plus. It is intended for a senior
engineer or an AI system rebuilding, auditing, or extending the product.

Start with [the current snapshot](00-current-snapshot-2026-07-19.md). It
records the verified July 19 desktop release details and explicitly supersedes
older values in the numbered documents where they conflict.

## Full Reconstruction Set

1. [Project overview and architecture](01-project-overview-architecture.md)
2. [Environment setup and dependencies](02-environment-setup-dependencies.md)
3. [Database schema and data models](03-database-schema-data-models.md)
4. [Backend API specifications](04-backend-api-specifications.md)
5. [Frontend architecture and components](05-frontend-architecture-components.md)
6. [Authentication and authorization](06-authentication-authorization.md)
7. [Business logic and core algorithms](07-business-logic-core-algorithms.md)
8. [Integration points and external services](08-integration-points-external-services.md)
9. [Configuration and environment variables](09-configuration-environment-variables.md)
10. [Testing strategy and test cases](10-testing-strategy-test-cases.md)
11. [Build and deployment pipeline](11-build-deployment-pipeline.md)
12. [Error handling and logging](12-error-handling-logging.md)
13. [Performance optimization and caching](13-performance-optimization-caching.md)
14. [Security implementation](14-security-implementation.md)
15. [File structure and code organization](15-file-structure-code-organization.md)

## AI Review Inputs

- [Technical deep-dive](PROJECT-DEEP-DIVE.md): detailed walkthrough and
  review questions.
- [Technology audit](TECHNOLOGY-AUDIT.md): every meaningful language,
  framework, runtime, library, tool, and external service with its role.
- [Review brief 1](AI-REVIEW-01-project-and-code.md): product, architecture,
  and representative implementation patterns.
- [Review brief 2](AI-REVIEW-02-data-flow-and-dependencies.md): source and
  data flow, integration boundaries, and storage relationships.
- [Review brief 3](AI-REVIEW-03-risks-and-review.md): current technical debt,
  design trade-offs, and exact questions for an external reviewer.

## Safety Notes

The pack intentionally omits `.env` contents, passwords, API keys, database
records, and private notebook content. Configuration examples use placeholders
and documented defaults only.
