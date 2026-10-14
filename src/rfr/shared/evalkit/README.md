# evalkit: private experiment wires and public boundaries

Implemented: separate scorer-only GoldRecord and PublicMethodInput; present/absent/unlabelled labels;
raw machine versus human-effective prediction wires; fixed manifest order/count/group bindings;
explicit stale/error/eligible/answered populations and undefined metric shape; whole-group resampling
policy shape; closed aggregate-projection admission with approved string values and finite numbers.

Copy closure: this directory's Python files, schema.json and README with root MIT LICENSE;
Python3.12/Pydantic2. No receipt, image/OCR, provider, domain-normalizer or workspace runtime imports.
Domain adapters supply all actual label meanings, eligible populations and safe public source payloads.
PublicMethodInput rejects scorer records/extra top-level fields; trusted adapter assembly must also
prevent semantic label leakage inside arbitrary JSON source content. Gold/source references are
private opaque handles, not required URLs or a runtime Pointer dependency.

Human-corrected reference gold can be valid with actual provenance; human-effective predictions stay
separate from machine scoring. Provisional/synthetic fixture references do not create actual human
gold. Never-run rows cannot invent outputs, calls or measured scores; unknown metrics use reasons.

Manifest validation checks supplied schema/order/group consistency. Actual corpus bytes, symlink/
containment lookup, source freshness, complete enrichment, label rights, freeze/seal history and real
human provenance remain caller/engine gates. No runner, scorer, rate/confusion/set/Wilson/bootstrap/
agreement calculation, split generator, report writer or live cost collector is implemented.
ResamplingSpec validation is not a draw or interval result. Safe aggregate admission is not a general
de-identification guarantee; named synthetic examples need separately approved retained references.
