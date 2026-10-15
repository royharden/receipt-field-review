# fieldextract: candidate-bound proposal engine

Implemented: generic FieldSpec/Candidate/FieldValue/ScoreComponents and native-distribution wires.
False values, nullable confidence and raw proposals remain distinct from human-effective outcomes.
Hard flags require review; a human-effective shape needs provenance, without claiming authenticated
human evidence. Native quality multiplication is named policy, not generated OCR confidence.

Copy closure: this directory plus the complete declared docio directory, with their
generated schemas/READMEs and root MIT LICENSE. Python3.12/Pydantic2 are required. Relative imports
allow moving this pair under another consumer namespace. No receipt, provider SDK or UI imports.

Extension evidence carries an explicit consumer profile and JSON payload, to be checked by the
injected consumer validator. This is not a second Pointer union or a resolver. Candidate generators,
actual evidence resolvers, domain checks and funded judgment transports remain consumer ports.

`engine.extract_field` validates the complete candidate/question/answer/verifier bindings and resolves
all candidate evidence before judgment. It accepts at most63 candidates plus an explicit none option.
Selection can choose only an existing ID; a none answer or tie abstains without asserting printed
absence. A configured existing JudgmentPort supplies one binary verifier question; independent hazards
use separate bound ports/distributions. Mismatched, incomplete or promoted-origin responses refuse.
Callback arguments are detached copies so a port cannot mutate an existing candidate into a new value.

The diagnostic score is `min(s*q, 1-v)`: B0 uses declared .9/.6/.3/0 priors; J1 uses the actual selection
probability; V2 uses .5 only after independently measured OCR anchoring. `q` is the minimum measured
word confidence, zero if missing, one for a validated named native-text structural policy, zero for
model-claimed/absent geometry. Native text confidence remains null. `v` is the largest actual relevant
binary violation probability; no verifier retains unknown metadata and an explicit not-run issue.

High scores do not establish calibration. The default policy always requires review. Only an actual
trusted caller's admitted known-stratum calibration can route a machine proposal; a bool/version or
synthetic test policy is not proof. Hard flags override routing. Review rows leave the visible value
blank and preserve the selected normalized proposal. The caller must retain the original raw candidate
bank/source artifacts alongside results. This engine never writes a human-effective outcome.

`apply_domain_checks` applies consumer issues to machine fields, blanks hard/review failures without
erasing proposals, rejects foreign fields and leaves human-effective projection to the rulings policy.
Actual receipt arithmetic/locale/row semantics, sources/screens, calibration, provider/ledger full-fanout
reservation, deadline/retry/cost authority and actual transport are not implemented here. Ordinary tests
use tiny literal synthetic ports, including fake native PDF evidence and the complete moved closure;
they do not prove genuine native OCR, Jev probabilities, real calibration or receipt accuracy.
