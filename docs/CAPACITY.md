# CycloneReady Capacity Estimate

## Current measured corpus

- Collected files: 5
- PDF pages: 450
- Approximate extracted text tokens: 4,248,770
- Approximate 500-token chunks: 8,498
- Measured PDF tokens per page: 501.71
- Current disk usage: 66.56 MB

The current corpus contains historical cyclone data and disaster-management reference documents. Token counts are approximate character-based estimates, not exact tokenizer results.

## Planned project knowledge

CycloneReady will include an original solution document developed by the project team.

- Cyclone preparedness and response.
- Urban flood preparedness and response.
- Realistic Tamil Nadu disaster scenarios.
- Evacuation and emergency planning.
- Community awareness and recovery recommendations.

The document has not yet been created or measured. Its storage, token count and chunk count are not included in current measurements.

## Capacity estimates

A full capacity estimate will be prepared after the original solution document and any additional reviewed datasets are available.

- Measure actual text using the selected tokenizer.
- Estimate chunks using the chosen chunk size and overlap.
- Measure embedding storage using the selected embedding model.
- Measure PostgreSQL and vector-index storage using the actual database.

## Capacity questions

1. Embedding cost: Not calculated. Choose an embedding provider and use its published pricing with the measured token count.
2. PostgreSQL capacity: Not fully verified. Measure actual text, metadata and vector storage against the database plan limits.
3. Least certain estimate: Future knowledge-base size and token count. The original solution document and additional evidence sources have not yet been finalized.
4. At 10x corpus size: Text storage and embedding requirements may grow approximately 10x. Actual database usage may be higher due to metadata, indexes and chunk overlap.

## Limitations

- Token counts are approximate, using extracted characters divided by four.
- The current dataset has no PDF pages.
- The current measurements do not include the future solution document.
- No embedding provider, vector dimension or database storage cost is assumed.
- Historical cyclone observations alone do not represent the complete knowledge required for disaster preparedness and response.
