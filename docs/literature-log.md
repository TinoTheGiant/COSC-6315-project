# Literature search log

Kept because a search that is not recorded cannot be relied on later, and
because "I did not find it" means nothing unless the sources that failed to
load are named. Format follows the research-integrity protocol: every row
states the query, what was opened, what was blocked, and a conclusion that
stays inside what was opened.

---

## Session, 26 October 2026

**Goal.** Find related work in three groups the Related Work section sets up:
fragmentation and allocation as a classical optimization, systems that adapt
placement to a moving workload, and learned database administration.

### Searches

```
Query: "reinforcement learning data placement replica placement distributed storage systems"
Date:  2026-10-26   Index: Consensus (Semantic Scholar, OpenAlex, PubMed)
Opened: 9 abstract records
Blocked: none
Stopped: no
Conclusion: Four records relevant to RL for placement, of which Sibyl (ISCA 2022)
and Harmonia (ICS) are the closest in method to this project.
```

```
Query: "data partitioning and allocation problem distributed database design cost model"
Date:  2026-10-26   Index: Consensus
Opened: 10 abstract records
Blocked: none
Stopped: no
Conclusion: Five classical treatments located, spanning 1982 to 1995, which is
the group the Related Work section had marked as a gap.
```

```
Query: "learned database administration index selection knob tuning reinforcement learning query optimizer"
Date:  2026-10-26   Index: Consensus
Opened: 10 abstract records
Blocked: none
Stopped: no
Conclusion: Five records covering knob tuning, query optimization and index
selection, including a 2023 survey.
```

```
Query: "workload-driven dynamic repartitioning elastic data migration OLTP distributed transactions skew"
Date:  2026-10-26   Index: Consensus
Opened: 10 abstract records
Blocked: none
Stopped: no
Conclusion: Schism, Clay, E-Store and the Pavlo skew-aware partitioner located.
These are the direct ancestors of this project and were absent from the
bibliography before today.
```

### Verification

```
Query: Crossref REST API, 23 bibliographic lookups
Date:  2026-10-26
Opened: 21 of 23 resolved to a matching Crossref work record
Blocked: api.crossref.org refuses direct connections from both this session's
         cloud container and the linked computer (HTTP 403 at the egress
         proxy). All lookups went through the WebFetch channel instead, one at
         a time, because parallel requests are rate-limited by Crossref.
Stopped: no
Conclusion: Every DOI, year, volume and page range in references.bib is copied
from a Crossref record retrieved on this date.
```

**Two did not resolve, and are recorded as such rather than filled in.**

- **Stable-Baselines3 (Raffin et al.).** No Crossref record. JMLR does not
  register Crossref DOIs. The entry carries the JMLR landing page and no DOI.
- **Principles of Distributed Database Systems (Özsu and Valduriez).** The
  bibliographic query returned a different work by the same authors, a 1991
  *Computer* article. The monograph record did not surface. The entry keeps the
  Springer book DOI, marked as not confirmed against a Crossref work record.

**Two dates were corrected against Crossref.**

- Saccà and Wiederhold is **1985**, TODS 10(1), not 1983 as the search index
  reported.
- Harmonia is dated **2026** by Crossref and 2025 by the search index. The
  Crossref year is used and the discrepancy is noted in the entry.

### How far each source was read

**Abstract only, through the Consensus index**, for all twenty new entries.
None was opened in full, and none was downloaded. The base papers `lion2024`
and `geotp2025` were read from their PDFs earlier in the project.

That limit governs what may be written about them. A sentence summarizing a
paper's abstract is supportable. A sentence about its method, its baselines or
its failure modes is not, unless the paper is opened first. Sentences added to
the Related Work section on 26 October stay inside the abstracts.

### What this search does not establish

It does not establish that this project's combination is new. No novelty claim
is made anywhere in the paper on the strength of these searches. What can be
said, and is said, is narrower: the four indexes above returned no paper that
learns fragmentation and geographic placement jointly for transactional
workloads. IEEE Xplore and the ACM Digital Library were not searched directly,
only through aggregators, and api.crossref.org was reachable only through one
channel.
