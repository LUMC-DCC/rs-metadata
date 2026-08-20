# Where this came from

rs-metadata implements a decision made by a working group on software metadata
standards for the life sciences and health domain.
Organizations involved: LUMC, AUMC, DReaMS, and ELIXIR-NL.

## The problem

Research software in the domain is frequently undocumented, hard to discover,
and not reusable outside the context it was written in. That undermines
reproducibility, duplicates effort, and leaves institutions unable to account
for the software their funding produces.

Structured metadata is an important part of addressing these challenges.
Several schemas already existed but the agreement on a minimal common standard,
that works for everything from a large bioinformatics infrastructure project to a
single-purpose analysis script, was missing.

## Choosing schema

The group defined a weighted rubric of eight criteria and applied it to five
candidate schemas. The priority ordering behind the weights was **citability <
discoverability < reuse**. Gathering and evaluating information on each
schema resulted in the overall scoring:

| Criterion | Weight | CodeMeta 3.1 | CITATION.cff 1.2.0 | Bioschemas CT 1.0 | biotoolsSchema 3.3.0 | maSMP 2.1.0 |
|---|---|---|---|---|---|---|
| Coverage of must-haves | 1.0 | 85% | 70% | 95% | 95% | 85% |
| Governance & sustainability | 0.9 | 100% | 67% | 100% | 100% | 33% |
| Adoption in the domain | 0.7 | 67% | 67% | 100% | 100% | 33% |
| Interoperability (crosswalks) | 0.5 | 67% | 29% | 19% | 19% | 11% |
| Automation maturity | 0.4 | 88% | 75% | 75% | 88% | 25% |
| Ease of use | 0.4 | 70% | 100% | 50% | 60% | 40% |
| Adoption in registries | 0.3 | 40% | 50% | 0% | 25% | 0% |
| Coverage of nice-to-haves | 0.3 | 65% | 28% | 53% | 60% | 55% |
| **Weighted score** | | **77.7%** | 63.2% | 73.4% | **77.5%** | 41.4% |
| **Rank** | | **1** | 4 | 3 | **2** | 5 |

Three things are noteworthy about that result.

- **The top two are effectively tied.** CodeMeta and biotoolsSchema differ by 0.2
percentage points, and the ranking is sensitive to the weights. CodeMeta leads
on interoperability and registry breadth; biotoolsSchema leads on domain
adoption and has native EDAM operations.
- **Bioschemas ComputationalTool scored well but is a web markup profile**, not a
stand-alone file format, which limits it as a repository metadata file.
- **maSMP describes a software management plan**, not a software record, so its
low score partly reflects a mismatch with a rubric aimed at descriptive
metadata.

## Decisions

**A CodeMeta 3.1 subset is the primary record.** CodeMeta covers the full
must-have set with one extension, is the de facto exchange standard,
has the broadest crosswalks, and applies to every size of software.

**`CITATION.cff` sits alongside it.** GitHub renders it as a "Cite this
repository" button and Zenodo uses it when archiving a release. It is
citation-scoped and does not replace `codemeta.json`.

**Validation happens in CI.** Both files live in the repository root and are checked
automatically for validity and consistency
with each other. rs-metadata is that checker.

## Fields

Ten fields are mandatory: `name`, `description`, `version`, `identifier`,
`author`, `license`, `codeRepository`, `programmingLanguage`,
`applicationCategory`, and `schema:featureList`. Fifteen more are recommended
and reported as a single warning rather than enforced.

The [field reference](using/profile.md) covers all of them.
