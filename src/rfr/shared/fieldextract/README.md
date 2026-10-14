# fieldextract: proposal wires and ports

Implemented: generic FieldSpec/Candidate/FieldValue/ScoreComponents and native-distribution wires.
False values, nullable confidence and raw proposals remain distinct from human-effective outcomes.
Hard flags require review; a human-effective shape needs provenance, without claiming authenticated
human evidence. Native quality multiplication is named policy, not generated OCR confidence.

Copy closure: this directory plus the complete docio model/identity/interface directory, with their
generated schemas/READMEs and root MIT LICENSE. Python3.12/Pydantic2 are required. Relative imports
allow moving this pair under another consumer namespace. No receipt, provider SDK or UI imports.

Extension evidence carries an explicit consumer profile and JSON payload, to be checked by the
injected consumer validator. This is not a second Pointer union or a resolver. Domain checks,
candidate generators, funded judgment transport, selectors/verifiers and score computation are ports
only; no such engine or receipt arithmetic/plugin is implemented in this slice.
