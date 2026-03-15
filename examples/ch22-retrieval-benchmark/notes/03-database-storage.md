# Storage Notes

When I wrote about databases, I often meant very different things under one umbrella: PostgreSQL for transactional application data, and RocksDB for embedded storage engines.

The interesting part was not the word "database" itself. It was comparing indexing, write amplification, transaction behavior, and how much operational visibility each option gave me.

Some notes only mention WAL tuning, compaction, or index strategy without repeating the higher-level category name.

