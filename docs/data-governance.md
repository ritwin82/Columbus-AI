# Data governance and provider boundaries

## Stable RAG data

Only ingest material whose reuse terms have been reviewed. Each chunk must retain its source URL, publisher, licence, retrieval date, location, and topic. Government publication does not automatically imply unrestricted reuse.

Suitable stable topics include history, cultural context, general accessibility notes, facilities, cuisine, seasonal guidance, and official visitor rules.

## Live data

Weather, traffic, opening status, routes, hotel prices, event status, and closures are live facts. Retrieve them at request time, record their timestamp, and do not silently replace unavailable live data with model-generated claims.

Google Places and Routes content must follow Google Maps Platform caching, display, and attribution rules. The permanent corpus should contain independently sourced knowledge and reusable Place IDs rather than copied Google responses or reviews.

## User data

- Store only preferences needed for personalization.
- Mark inferred preferences separately from explicit preferences.
- Do not store raw conversation text as long-term memory by default.
- Expose preference retrieval and deletion operations.
- Never log secrets, precise live location, or unnecessary personal information.

## Reliability

Recommended source priority:

1. Official venue or responsible authority
2. Government tourism source
3. Licensed structured/open dataset
4. Established secondary source
5. Community content

Unknown facts must remain `unknown`; absence of an accessibility warning is not evidence of accessibility.

## Current corpus policy

The importer labels every file from the external `RAG_DATA` folder as user-provided and unverified. It may support discovery and ranking, but its prices, hours, footfall, and business listings must not be presented as live facts until independently checked.

The official-site collector is deliberately bounded. It checks `robots.txt`, accepts HTML only, limits page size and pages per host, follows only relevant same-domain links, rate-limits requests, stores a content hash, and records every collection or skip decision in `data/sources/crawl_manifest.jsonl`. A successful fetch is not proof of a reuse licence, so site-specific terms still require review before redistribution.
