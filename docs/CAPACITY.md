# CycloneReady Capacity Estimate

## Measured corpus

- Current PDF pages: 0
- Extracted text tokens: 0
- Measured tokens per page: Not available (no PDF sample pages measured)
- Current disk usage: 0.00 MB

## Full corpus estimate

- Target pages: 3,000
- Estimated tokens: Not available (collect a representative sample first)
- Estimated 500-token chunks: Not available

The full-corpus estimate is unavailable until a representative sample has been collected and measured. It is not zero.

## Capacity questions

1. Embedding cost: Not calculated. Select an embedding provider and use its current published pricing with the measured token count.
2. PostgreSQL capacity: Not verified. Compare measured text and vector storage against the actual database plan limit.
3. Least certain estimate: Tokens per page. Measure a larger, representative sample, including scanned PDFs and OCR output.
4. At 10x corpus size: Expect approximately 10x the text, embedding and storage requirements, subject to chunk overlap, metadata and index overhead.

## Limitations

- Token counts are approximate, using extracted characters divided by four.
- Scanned pages without OCR may contribute zero tokens.
- Chunk estimates use 500 tokens per chunk and do not account for overlap.
- No embedding provider, vector dimension or database storage cost is assumed.
