# Roadmap and release gates

At 6–8 hours/week the learning plan estimates 30 weeks plus 4–6 weeks of revision time.
AI-assisted implementation does not replace that learning time.

| Phase | Weeks | Local deliverable | Remaining learning/live gate |
|---|---:|---|---|
| 0 | 1 | Environment and repeatable setup | Explain interpreter, environment, and packages |
| 1 | 3 | PDF API and frontend | Teach back the lifecycle; add a metadata field |
| 2 | 4 | Structured fixtures and corrections | Add a business field; measure live extraction |
| 3 | 4 | Matching and deterministic reports | Hand-calculate a report and explain ambiguity |
| 4 | 4 | Retrieval and confirmed rules | Experiment with chunking; measure semantic retrieval |
| 5 | 4 | Approval, audit, simulated outbox | Explain idempotency and uncertain delivery |
| 6 | 7 | Cloud code and recovery tooling | Agree budget; deploy and verify live integrations |
| 7 | 3 | Corpus, evaluator, demo | Held-out live benchmarks and customer walkthrough |

The synthetic corpus contains 60 business documents, 20 scanned variants, five policies, and
adversarial inputs. The last five examples per type use a held-out template. Originals and scans
stay in the same split. This corpus does not represent all supplier layouts.

Release targets: 95% critical-field accuracy on held-out digital examples, 90% policy recall@5,
zero incorrect automatic benchmark matches, valid citations, and passing workflow safety tests.
Live outputs must establish these targets; fixture scores do not satisfy them.

Extensions: cumulative partial invoicing, richer tax conventions, quotation ranking, agreement
interpretation, public authentication, tenant isolation, and real-customer hardening.
