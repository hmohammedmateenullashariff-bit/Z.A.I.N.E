---
name: github-reverse-engineering
description: Reverse engineer GitHub repositories, reconstruct undocumented API contracts, analyze network schemas, and decompile commit histories. Use when dissecting repositories, discovering internal API routes, generating client SDKs, or analyzing protocol specifications.
---

# GitHub Reverse Engineering & API Analysis

Specialized engineering capability for autonomous repository dissection, undocumented endpoint reconstruction, commit graph analysis, and API specification synthesis.

## Core Capabilities

1. **Repository Architecture Deconstruction**:
   - Parse ASTs to extract all exported interfaces, models, functions, and router endpoints.
   - Detect routing frameworks (FastAPI, Express, Flask, Gin, Spring Boot, Actix, Axum).
   - Trace dependency injection patterns, middleware chains, and security boundaries.

2. **API Contract & Schema Extraction**:
   - Map undocumented HTTP endpoints, query parameters, path variables, request bodies, and headers.
   - Extract validation schemas (Pydantic, Zod, Joi, Marshmallow, Serde).
   - Synthesize valid OpenAPI / Swagger 3.1 JSON schemas and cURL execution commands.

3. **Authentication & Session Analysis**:
   - Reverse engineer token issuance, JWT claims, HMAC request signatures, nonce generation, and OAuth2/OIDC exchange flows.
   - Identify header requirements (`Authorization`, `X-CSRF-Token`, custom fingerprints).

4. **Commit Graph Forensics**:
   - Trace historical diffs to locate sensitive configuration leaks, deprecation cycles, and internal endpoint evolution.
   - Extract bug-fix patterns to predict software vulnerabilities or integration gotchas.

## Methodology

When reverse engineering a target:
1. **Catalog entry points**: Check `package.json`, `setup.py`, `pyproject.toml`, `Cargo.toml`, or `go.mod`.
2. **Scan routing tables**: Identify all endpoints (`@app.get`, `router.post`, etc.).
3. **Map data schemas**: Reconstruct inputs and response structures.
4. **Generate Typed Client**: Produce a robust Python `httpx` or TypeScript client wrapper with error handling.

