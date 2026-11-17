---
name: polyglot-architecture-synthesizer
description: >-
  Synthesizes production-grade, clean Hexagonal/Clean Architecture target microservice codebases
  supporting Java 21 / Spring Boot 3 or C# / .NET 9 with EF Core, MediatR, and OpenAPI contracts.
---

# Polyglot Architecture Synthesizer (Phase 5 / Code Generation)

## Purpose
Enterprise modernization platforms must be technology-neutral. Depending on the client's corporate cloud strategy, the target microservice must generate cleanly in either:
- **Java 21 / Spring Boot 3** (Spring Data JPA, Hibernate, Resilience4j, Flyway DDL, JUnit 5)
- **C# / .NET 9** (Clean Architecture, ASP.NET Core Minimal APIs, EF Core, MediatR, FluentValidation, xUnit)

The **Polyglot Architecture Synthesizer** takes the reverse-engineered requirements and domain models, dynamically producing an idiomatic repository with complete domain, application, infrastructure, and presentation layers.

## Invocation & CLI Usage
```bash
python -c "
import sys; sys.path.insert(0, 'apps/api')
from app.bedrock_skills import synthesize_target_codebase
scope = {'name': 'Motor Policy Underwriting', 'capabilityId': 'motor'}
# Generate for .NET 9:
csharp_repo = synthesize_target_codebase(scope, target_tech={'language': 'csharp', 'framework': 'dotnet-9'})
# Generate for Java 21:
java_repo = synthesize_target_codebase(scope, target_tech={'language': 'java', 'framework': 'spring-boot-3'})
print('Generated files:', list(csharp_repo.keys()))
"
```

## Architectural Folder Structure (Clean Architecture Pattern)
Regardless of language, the synthesizer adheres to strict **Ports & Adapters (Hexagonal)** separation:
```
src/
├── Domain/              # Entities, Value Objects, Domain Exceptions, Aggregate Roots
├── Application/         # CQRS Commands & Queries, Handlers, Validators, DTOs
├── Infrastructure/      # Database Repositories, Kafka/EventBridge Messaging, External Gateways
└── Presentation/        # REST Controllers / Minimal API Endpoints, OpenAPI Swagger
```
