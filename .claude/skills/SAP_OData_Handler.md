---
name: SAP_OData_Handler
description: SAP OData integration handler — CSRF token management, retry with circuit breaker, SAP EWM warehouse task orchestration
---

# SAP_OData_Handler

## Trigger
Activate this skill when writing SAP integration code, OData API calls, or SAP-bridge communication logic.

## Core Requirements

### 1. OData V2/V4 Standards Compliance
- Always use proper OData URL conventions: `/EntitySet?$filter=...&$expand=...&$top=...&$skip=...`
- Support both V2 (SAP Gateway) and V4 (modern SAP S/4HANA) protocol versions
- Include proper Content-Type headers:
  - V2: `application/json;odata=verbose` or `application/json;odata=minimalmetadata`
  - V4: `application/json`
- Handle pagination with `__next` links (V2) or `@odata.nextLink` (V4)

### 2. X-CSRF-Token Validation
```python
# Always implement CSRF token fetch-then-use pattern
async def fetch_csrf_token(session, base_url):
    """Fetch X-CSRF-Token from SAP before state-changing operations."""
    async with session.get(
        f"{base_url}/sap/opu/odata/srv",
        headers={
            "X-CSRF-Token": "Fetch",
            "Authorization": "Basic <credentials>"
        }
    ) as response:
        response.raise_for_status()
        return response.headers.get("X-CSRF-Token")

async def create_entity(session, base_url, payload, csrf_token):
    """Use CSRF token in POST/PUT/DELETE operations."""
    async with session.post(
        f"{base_url}/EntitySet",
        json=payload,
        headers={
            "X-CSRF-Token": csrf_token,
            "Content-Type": "application/json"
        }
    ) as response:
        response.raise_for_status()
        return await response.json()
```

### 3. $filter and $expand Query Support
```python
# Build OData queries safely
from urllib.parse import quote

def build_odata_filter(filters: dict) -> str:
    """Convert Python dict to OData $filter string."""
    conditions = []
    for key, value in filters.items():
        if isinstance(value, str):
            conditions.append(f"{key} eq '{value}'")
        elif isinstance(value, list):
            conditions.append(f"{key} in ({','.join(str(v) for v in value)})")
        else:
            conditions.append(f"{key} eq {value}")
    return " and ".join(conditions)

def build_odata_expand(navigation_props: list[str]) -> str:
    """Build $expand parameter for navigation properties."""
    return ",".join(navigation_props)

# Example usage:
# filter_str = build_odata_filter({"Status": "Active", "Priority": 1})
# expand_str = build_odata_expand(["Items", "Partner"])
# url = f"/sap/opu/odata/EntitySet?$filter={filter_str}&$expand={expand_str}"
```

### 4. Exponential Backoff Retry Logic
**MANDATORY** - All SAP HTTP calls must include retry logic:

```python
import asyncio
from aiohttp import ClientSession, ClientError
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=2, max=60),
    retry=retry_if_exception_type((ClientError, asyncio.TimeoutError)),
    before_sleep=lambda retry_state: print(
        f"SAP call failed, retry {retry_state.attempt_number} in {retry_state.next_action.sleep} seconds"
    )
)
async def sap_odata_call(session: ClientSession, url: str, **kwargs):
    """SAP OData call with exponential backoff retry."""
    async with session.get(url, timeout=aiohttp.ClientTimeout(total=30), **kwargs) as response:
        if response.status == 429:  # Rate limit
            raise ClientError("SAP rate limit exceeded")
        response.raise_for_status()
        return await response.json()
```

### 5. Error Handling Patterns
- Parse SAP error responses: `error.message.value` (V2) or `error.message` (V4)
- Log correlation IDs from response headers: `sap-correlation-id`
- Implement circuit breaker pattern for SAP system unavailability
- Handle HTTP 503 (service unavailable) with longer backoff periods

## Anti-Patterns (DENIED)
❌ Synchronous HTTP calls to SAP (must use async/await)
❌ Hardcoded credentials (use environment variables or secret manager)
❌ No retry logic on HTTP calls
❌ Ignoring X-CSRF-Token on state-changing operations
❌ Not handling OData pagination
❌ Swallowing SAP error messages without logging

## References
- SAP OData V2: https://help.sap.com/docs/SAP_NETWEAVER_750/ea72206b834e4ace9cd8ea886550f410/4791d9546e821014e10000000a42189b.html
- SAP OData V4: https://docs.oasis-open.org/odata/odata/v4.01/odata-v4.01-part1-protocol.html
- SAP CSRF Protection: https://help.sap.com/docs/SAP_S4HANA_ON-PREMISE/4791d9546e821014e10000000a42189b/4f9c9c5b6e821014e10000000a42189b.html
