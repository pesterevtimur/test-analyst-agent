# SunCache: a multi-tier cache benchmark

SunCache is a fictional caching library that this document is benchmarking against a few alternatives. This document is a test fixture for the `wiki-ingest` skill — it specifically exercises the "tables are data, never prose" contract.

## Setup

The benchmark ran on a single c6i.4xlarge AWS instance with 32 GiB RAM, Ubuntu 24.04, Linux kernel 6.8. All caches were warmed for 60 seconds before measurement. Each cache held one million 1-KiB entries with a hot-set of 100,000 keys.

## Results

The table below shows the median read latency and 99th-percentile read latency across three runs of one minute each, plus the steady-state memory footprint:

| cache       | median_us | p99_us | memory_mib |
|-------------|-----------|--------|------------|
| SunCache    | 1.2       | 4.8    | 1180       |
| MoonLib     | 1.5       | 6.1    | 1140       |
| StarStore   | 2.0       | 9.3    | 1290       |
| RedDB-light | 4.4       | 22.5   | 1050       |

The numbers above are the centerpiece of this document. They must not be paraphrased into prose; they must be extracted as data.

## Interpretation

SunCache wins on both latency metrics but pays for it with higher memory usage compared to RedDB-light. MoonLib places second on latency and is the most memory-efficient of the lower-latency entries.
