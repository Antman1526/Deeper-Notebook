# Research Quality Evaluation

- Corpus: `v1`
- Model: `deterministic`
- Temperature: `0.0`
- Average latency: `0.00 ms`
- Informational macro score: `1.0000`

## Release Metrics

| Metric | Value | Numerator | Denominator | State |
| --- | ---: | ---: | ---: | --- |
| supported_precision | 1.0000 | 12 | 12 | ok |
| supported_recall | 1.0000 | 12 | 12 | ok |
| unsupported_escape_rate | 0.0000 | 0 | 54 | ok |
| citation_location_rate | 1.0000 | 42 | 42 | ok |
| schema_success_rate | 1.0000 | 66 | 66 | ok |

## Per-case diagnostics

| Case | Category | Expected | Predicted | Status | Spans | Schema | Latency |
| --- | --- | --- | --- | --- | --- | --- | ---: |
| ev1-supported_single_source-01 | supported_single_source | supported | supported | pass | 1/1 | pass | 0.00 ms |
| ev1-supported_single_source-02 | supported_single_source | supported | supported | pass | 1/1 | pass | 0.00 ms |
| ev1-supported_single_source-03 | supported_single_source | supported | supported | pass | 1/1 | pass | 0.00 ms |
| ev1-supported_single_source-04 | supported_single_source | supported | supported | pass | 1/1 | pass | 0.00 ms |
| ev1-supported_single_source-05 | supported_single_source | supported | supported | pass | 1/1 | pass | 0.00 ms |
| ev1-supported_single_source-06 | supported_single_source | supported | supported | pass | 1/1 | pass | 0.00 ms |
| ev1-supported_multi_source-01 | supported_multi_source | supported | supported | pass | 2/2 | pass | 0.00 ms |
| ev1-supported_multi_source-02 | supported_multi_source | supported | supported | pass | 2/2 | pass | 0.00 ms |
| ev1-supported_multi_source-03 | supported_multi_source | supported | supported | pass | 2/2 | pass | 0.00 ms |
| ev1-supported_multi_source-04 | supported_multi_source | supported | supported | pass | 2/2 | pass | 0.00 ms |
| ev1-supported_multi_source-05 | supported_multi_source | supported | supported | pass | 2/2 | pass | 0.00 ms |
| ev1-supported_multi_source-06 | supported_multi_source | supported | supported | pass | 2/2 | pass | 0.00 ms |
| ev1-partial_support-01 | partial_support | partial | partial | pass | 1/1 | pass | 0.00 ms |
| ev1-partial_support-02 | partial_support | partial | partial | pass | 1/1 | pass | 0.00 ms |
| ev1-partial_support-03 | partial_support | partial | partial | pass | 1/1 | pass | 0.00 ms |
| ev1-partial_support-04 | partial_support | partial | partial | pass | 1/1 | pass | 0.00 ms |
| ev1-partial_support-05 | partial_support | partial | partial | pass | 1/1 | pass | 0.00 ms |
| ev1-partial_support-06 | partial_support | partial | partial | pass | 1/1 | pass | 0.00 ms |
| ev1-contradiction-01 | contradiction | contradicted | contradicted | pass | 1/1 | pass | 0.00 ms |
| ev1-contradiction-02 | contradiction | contradicted | contradicted | pass | 1/1 | pass | 0.00 ms |
| ev1-contradiction-03 | contradiction | contradicted | contradicted | pass | 1/1 | pass | 0.00 ms |
| ev1-contradiction-04 | contradiction | contradicted | contradicted | pass | 1/1 | pass | 0.00 ms |
| ev1-contradiction-05 | contradiction | contradicted | contradicted | pass | 1/1 | pass | 0.00 ms |
| ev1-contradiction-06 | contradiction | contradicted | contradicted | pass | 1/1 | pass | 0.00 ms |
| ev1-missing_citation-01 | missing_citation | uncited | uncited | pass | 0/0 | pass | 0.00 ms |
| ev1-missing_citation-02 | missing_citation | uncited | uncited | pass | 0/0 | pass | 0.00 ms |
| ev1-missing_citation-03 | missing_citation | uncited | uncited | pass | 0/0 | pass | 0.00 ms |
| ev1-missing_citation-04 | missing_citation | uncited | uncited | pass | 0/0 | pass | 0.00 ms |
| ev1-missing_citation-05 | missing_citation | uncited | uncited | pass | 0/0 | pass | 0.00 ms |
| ev1-missing_citation-06 | missing_citation | uncited | uncited | pass | 0/0 | pass | 0.00 ms |
| ev1-wrong_source-01 | wrong_source | unsupported | unsupported | pass | 0/0 | pass | 0.00 ms |
| ev1-wrong_source-02 | wrong_source | unsupported | unsupported | pass | 0/0 | pass | 0.00 ms |
| ev1-wrong_source-03 | wrong_source | unsupported | unsupported | pass | 0/0 | pass | 0.00 ms |
| ev1-wrong_source-04 | wrong_source | unsupported | unsupported | pass | 0/0 | pass | 0.00 ms |
| ev1-wrong_source-05 | wrong_source | unsupported | unsupported | pass | 0/0 | pass | 0.00 ms |
| ev1-wrong_source-06 | wrong_source | unsupported | unsupported | pass | 0/0 | pass | 0.00 ms |
| ev1-numeric_mismatch-01 | numeric_mismatch | contradicted | contradicted | pass | 1/1 | pass | 0.00 ms |
| ev1-numeric_mismatch-02 | numeric_mismatch | contradicted | contradicted | pass | 1/1 | pass | 0.00 ms |
| ev1-numeric_mismatch-03 | numeric_mismatch | contradicted | contradicted | pass | 1/1 | pass | 0.00 ms |
| ev1-numeric_mismatch-04 | numeric_mismatch | contradicted | contradicted | pass | 1/1 | pass | 0.00 ms |
| ev1-numeric_mismatch-05 | numeric_mismatch | contradicted | contradicted | pass | 1/1 | pass | 0.00 ms |
| ev1-numeric_mismatch-06 | numeric_mismatch | contradicted | contradicted | pass | 1/1 | pass | 0.00 ms |
| ev1-temporal_mismatch-01 | temporal_mismatch | contradicted | contradicted | pass | 1/1 | pass | 0.00 ms |
| ev1-temporal_mismatch-02 | temporal_mismatch | contradicted | contradicted | pass | 1/1 | pass | 0.00 ms |
| ev1-temporal_mismatch-03 | temporal_mismatch | contradicted | contradicted | pass | 1/1 | pass | 0.00 ms |
| ev1-temporal_mismatch-04 | temporal_mismatch | contradicted | contradicted | pass | 1/1 | pass | 0.00 ms |
| ev1-temporal_mismatch-05 | temporal_mismatch | contradicted | contradicted | pass | 1/1 | pass | 0.00 ms |
| ev1-temporal_mismatch-06 | temporal_mismatch | contradicted | contradicted | pass | 1/1 | pass | 0.00 ms |
| ev1-quote_mismatch-01 | quote_mismatch | unsupported | unsupported | pass | 0/0 | pass | 0.00 ms |
| ev1-quote_mismatch-02 | quote_mismatch | unsupported | unsupported | pass | 0/0 | pass | 0.00 ms |
| ev1-quote_mismatch-03 | quote_mismatch | unsupported | unsupported | pass | 0/0 | pass | 0.00 ms |
| ev1-quote_mismatch-04 | quote_mismatch | unsupported | unsupported | pass | 0/0 | pass | 0.00 ms |
| ev1-quote_mismatch-05 | quote_mismatch | unsupported | unsupported | pass | 0/0 | pass | 0.00 ms |
| ev1-quote_mismatch-06 | quote_mismatch | unsupported | unsupported | pass | 0/0 | pass | 0.00 ms |
| ev1-prompt_injection-01 | prompt_injection | unsupported | unsupported | pass | 0/0 | pass | 0.00 ms |
| ev1-prompt_injection-02 | prompt_injection | unsupported | unsupported | pass | 0/0 | pass | 0.00 ms |
| ev1-prompt_injection-03 | prompt_injection | unsupported | unsupported | pass | 0/0 | pass | 0.00 ms |
| ev1-prompt_injection-04 | prompt_injection | unsupported | unsupported | pass | 0/0 | pass | 0.00 ms |
| ev1-prompt_injection-05 | prompt_injection | unsupported | unsupported | pass | 0/0 | pass | 0.00 ms |
| ev1-prompt_injection-06 | prompt_injection | unsupported | unsupported | pass | 0/0 | pass | 0.00 ms |
| ev1-not_in_sources-01 | not_in_sources | unsupported | unsupported | pass | 0/0 | pass | 0.00 ms |
| ev1-not_in_sources-02 | not_in_sources | unsupported | unsupported | pass | 0/0 | pass | 0.00 ms |
| ev1-not_in_sources-03 | not_in_sources | unsupported | unsupported | pass | 0/0 | pass | 0.00 ms |
| ev1-not_in_sources-04 | not_in_sources | unsupported | unsupported | pass | 0/0 | pass | 0.00 ms |
| ev1-not_in_sources-05 | not_in_sources | unsupported | unsupported | pass | 0/0 | pass | 0.00 ms |
| ev1-not_in_sources-06 | not_in_sources | unsupported | unsupported | pass | 0/0 | pass | 0.00 ms |
