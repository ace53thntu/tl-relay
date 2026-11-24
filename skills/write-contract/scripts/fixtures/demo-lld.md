# Demo: LLD

## 1. Component use cases and technical scenarios

### 1.1 Scenarios

None.

## 4. Interface contracts and API specifications

The [demo API](demo-lld/interface-contracts.md) page holds the common errors.

| # | Route | Caller · tenancy | Page | Replay |
| --- | --- | --- | --- | --- |
| 4.1 | [`GET /things`](demo-lld/api/4-1-get-things.md) | Admin | `page`, `pageSize` | none |
| 4.2 | [`POST /things`](demo-lld/api/4-2-post-things.md) | Admin | none | none |
| 4.3 | [`GET /things/{id}`](demo-lld/api/4-3-get-things-id.md) | Admin | none | none |

## 5. Concurrency control and execution logic

None.
