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

---

## Second session, 26 October 2026: design decisions that had no citation

The first pass filled the Related Work groups. This pass asks a different
question: which decisions does the paper already make that nothing in the
bibliography supports? A Related Work section is strong when every choice has
something behind it, not when it has more papers in it.

Eight were uncited and now are.

| Decision already in the paper | Was supported by | Now cited |
|---|---|---|
| The static hash baseline *is* consistent hashing | nothing | Karger et al. 1997; Weil et al. 2006 (CRUSH); Coluzzi et al. 2023 survey |
| The workload generator is YCSB-shaped | nothing | Cooper et al. 2010 |
| A plain DQN was chosen over its variants | Mnih 2015 only | van Hasselt 2016 (Double); Wang 2015 (Dueling); Schaul 2015 (PER); Hessel 2018 (Rainbow) |
| The environment is a Gymnasium environment | nothing | Towers et al. 2025 |
| 80 to 90% of chosen actions are inapplicable | nothing | Huang and Ontañón 2022; Zahavy et al. 2018 |
| Pre-train in simulation, fine-tune on the cluster | nothing | Tobin et al. 2017 |
| Confidence intervals are percentile bootstrap | nothing | Efron 1979 |

Two of these change what the paper can say. The inapplicable action rate was
written up as an unexplained weakness; Zahavy et al. address exactly it, for a
DQN, with an action-elimination network, so the future-work item becomes a named
technique instead of a wish. And the DQN variants matter because the paper
already proposes n-step returns in future work without citing where that idea
comes from.

### Verification method, and a defect found in it

```
Query: Crossref REST API, 14 bibliographic lookups
Date:  2026-10-26
Opened: 10 resolved to a matching record
Blocked: none. api.crossref.org refuses direct connections from both machines
         (proxy CONNECT 403), so WebFetch was again the only route.
Stopped: no
```

**A defect in the method, recorded because it could have produced wrong
citations.** The `query.bibliographic=` parameter was being silently stripped by
the fetch layer on some calls. Crossref then received no query at all and
returned a default sample of its corpus, which looks like a normal response. Two
early calls came back with unrelated works, one on veterinary dentistry. The
tell is `message.query.search-terms: null` together with a total-results count in
the millions.

The fix was a short undotted `query=` string, with the returned
`search-terms` checked on every call. The first batch of twenty was re-examined
against this: every entry there returned a title matching the one requested,
which a corpus sample cannot do, so those entries stand.

**Four have no Crossref record**, which is expected rather than a failure.
PMLR, ICLR and NeurIPS proceedings do not carry DOIs, so Dueling Networks,
Prioritized Experience Replay and the Zahavy action-elimination paper are cited
by arXiv identifier, each confirmed against its arXiv abstract page. Sutton and
Barto's second edition has no Crossref record either; Crossref holds only
reviews of the 1998 first edition, so **it is not cited** rather than cited from
a record that describes a different edition.

Three dates in the second batch do not match the years these works are usually
cited with, and the Crossref year is used in each case: Huang and Ontañón is
recorded at FLAIRS 2022, Gymnasium at 2025 rather than the 2023 the Farama
release is often given, and Dueling Networks carries its 2015 arXiv year rather
than ICML 2016.

### The supplied Semantic Scholar export

Ten papers were supplied as a BibTeX and Markdown export. The export carried no
DOIs, only Semantic Scholar corpus identifiers, which is not enough for an IEEE
bibliography.

**Five were taken**, each verified against Crossref and each filling a real gap:

- **Atrey et al. 2019**, CLOSER. Treats data placement and replication as one
  joint optimization in geo-distributed clouds, rather than placement followed
  by replication. That is the same joint framing this work uses, arrived at
  without learning, and it is the closest non-learned analogue.
- **Mahmoud et al. 2025**, IJICIS. Q-learning for fragment allocation and
  replication, stated as an MDP. Topically the closest work to this project
  after RLRP. A regional journal, but a real indexed one with a DOI.
- **Adnan et al. 2025**, Journal of Grid Computing. Network-aware placement
  across geo-distributed clouds.
- **Liao et al. 2019**, IEEE Access. Deep learning for placement against a
  latency objective.
- **Niu et al. 2026**, arXiv. A current instance of the classical allocation
  formulation. Cited as a preprint and labelled as not peer reviewed.

**Five were left out, and the reason matters more than the omission.**

| Left out | Reason |
|---|---|
| Sirimalla 2021, *Intelligent Workload Placement and Sharding...* | The venue shows several markers associated with predatory publishing, and the title is set in full capitals in the record itself. Citing it invites a question about how the bibliography was assembled |
| *An Adaptive Data Placement Architecture in Multicloud Environments*, Scientific Programming 2020 | That journal was discontinued by its publisher following research-integrity concerns |
| Shankar and Chitra 2022, *Computer Systems Science and Engineering* | The journal was removed from the major indexes in 2023 |
| *Cloud-Based Replication Models Using AI Techniques*, IJACSA 2026 | Weak venue, and the abstract does not describe anything this paper's argument needs |
| Danach et al. 2024, *Applied Sciences* | Legitimate venue, but the method is a support vector machine with a genetic allocator rather than a learned policy, and geography does not enter it. It would pad the related work without strengthening it |

A bibliography is judged on its weakest entry as much as its strongest. Adding a
paper from a discontinued or delisted venue costs more credibility than the
citation gains, and a reader who recognizes one of them will wonder what else
was added without being checked.

---

## Recency: the cutoff was applied and then reversed, 26 October 2026

A rule of "nothing older than 2015" was applied, removing fourteen entries, and
then reversed when it turned out to govern the **base papers** rather than every
citation. The base papers, Lion 2024 and GeoTP 2025, satisfy it comfortably.

The reversal is the right call and the reasoning is worth keeping, because the
removal made clear what the foundational work is doing in this bibliography.

**Schism, E-Store and the Pavlo partitioner are the direct ancestors of this
project.** The premise this paper argues from, that placement should follow the
workload rather than be fixed at design time, is theirs. Removing them left a
Related Work section that described graph-cut repartitioning as though it had no
origin, which a reader in this field would notice immediately and read as either
ignorance of the area or evasion of it. Neither is a good look, and the
alternative on offer was a sentence explaining that a publication window
excluded them, which reads oddly in a conference paper.

**Consistent hashing has the same problem in miniature.** The static baseline in
this paper *is* consistent hashing. Citing a 2023 survey for what the baseline
is, rather than the 1997 paper that defined it, is a weaker citation for a
stronger claim.

Three entries found while the cutoff was in force were kept, because they are
good additions in their own right rather than substitutes:

- **Nashat and Amer 2018**, ACM Computing Surveys. A taxonomy of the
  fragmentation and allocation techniques that followed the classical papers.
  It now sits alongside them rather than in place of them.
- **Amer et al. 2017**, Heliyon. Fragmentation and allocation solved together.
- **Kamal et al. 2016**, Future Generation Computer Systems. The incremental
  form of workload-driven repartitioning, which fills the gap between Schism's
  one-shot cut and Clay's block migration.

The bibliography now spans 1979 to 2026, 47 entries.

### A near miss worth recording

One entry added during this pass, Amer et al. 2017, was first written with an
author list reconstructed from memory rather than copied: "Ali A. Amer and
Hassan I. Abdalla". The Crossref record gives **Ali A. Amer, Adel A. Sewisy and
Taha M. A. Elgendy**. The DOI was right and the authors were wrong.

That is the harder error to catch, because a reader checking the DOI lands on
the correct paper and has no reason to look at the names. It was caught by
verifying rather than by proofreading, and it breaks the rule about
reconstructing fields rather than copying them.
