"""Tests for the agent data supervisor audit loop (Track H / H6).

All network is mocked via in-memory fake adapters / fake httpx clients so these
tests are deterministic and fast. They cover the behavioral guarantees from the
plan: no silent overwrite, provenance tagging, confidence gating, resume via
checkpoint, and graceful degradation when a source raises.
"""

import json

import pytest

from src.backend.etl.agent_data_supervisor import (
    DISP_ACCEPTED,
    DISP_CONFLICT,
    DISP_ERROR,
    DISP_LOW_CONFIDENCE,
    DISP_NO_CHANGE,
    DISP_UNRESOLVED,
    AgentDataSupervisor,
    ChemblAtcAdapter,
    ChemblMechanismAdapter,
    FieldProposal,
    OpenFDAApprovalAdapter,
    Provenance,
    build_disease_drug_edges,
    load_checkpoint,
    needs_enrichment,
    save_checkpoint,
    utcnow_iso,
)


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------
class FakeAdapter:
    """A deterministic adapter that returns a fixed proposal (or None/raise)."""

    def __init__(self, field, value, confidence, *, source="fake",
                 url="https://example.test", behavior="value"):
        self.name = f"fake_{field}"
        self.field = field
        self._value = value
        self._confidence = confidence
        self._source = source
        self._url = url
        self._behavior = behavior  # "value" | "none" | "raise" | "hang"
        self.calls = []

    async def propose(self, drug):
        self.calls.append(drug["id"])
        if self._behavior == "none":
            return None
        if self._behavior == "raise":
            raise RuntimeError("simulated upstream failure")
        return FieldProposal(
            drug_id=drug["id"],
            field=self.field,
            value=self._value,
            provenance=Provenance(
                source=self._source,
                url=self._url,
                fetched_at=utcnow_iso(),
                confidence=self._confidence,
            ),
        )


def _drug(drug_id, **overrides):
    base = {
        "id": drug_id,
        "name": drug_id.title(),
        "atc_code": "C10AA05",
        "atc_category": "C",
        "year_approved": None,
        "company": None,
        "targets": [],
        "class": None,
        "chembl_id": f"CHEMBL_{drug_id}",
    }
    base.update(overrides)
    return base


@pytest.fixture
def drugs_file(tmp_path):
    def _make(drugs):
        path = tmp_path / "drugs.json"
        path.write_text(json.dumps({"drugs": drugs}, indent=2), encoding="utf-8")
        return path

    return _make


def _supervisor(tmp_path, adapters, drugs_path, **kwargs):
    return AgentDataSupervisor(
        adapters,
        drugs_file=drugs_path,
        reports_dir=tmp_path / "reports",
        changes_dir=tmp_path / "changes",
        checkpoint_file=tmp_path / "checkpoints" / "ckpt.json",
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Confidence gating + provenance
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_fills_empty_field_with_provenance_when_confident(tmp_path, drugs_file):
    path = drugs_file([_drug("aspirin", year_approved=None)])
    adapter = FakeAdapter("year_approved", 1899, confidence=0.8)
    sup = _supervisor(tmp_path, [adapter], path)

    report = await sup.run()

    outcomes = [o for o in sup.outcomes if o.field == "year_approved"]
    assert len(outcomes) == 1
    assert outcomes[0].disposition == DISP_ACCEPTED
    assert outcomes[0].proposed_value == 1899
    # Provenance carries source/url/fetched_at/confidence
    prov = outcomes[0].provenance
    assert prov["source"] == "fake"
    assert prov["url"] == "https://example.test"
    assert prov["confidence"] == 0.8
    assert "fetched_at" in prov and prov["fetched_at"]
    assert report["accepted_changes_count"] == 1


@pytest.mark.asyncio
async def test_low_confidence_proposal_is_queued_not_accepted(tmp_path, drugs_file):
    path = drugs_file([_drug("aspirin", year_approved=None)])
    adapter = FakeAdapter("year_approved", 1899, confidence=0.3)  # below 0.6
    sup = _supervisor(tmp_path, [adapter], path)

    await sup.run()

    o = [o for o in sup.outcomes if o.field == "year_approved"][0]
    assert o.disposition == DISP_LOW_CONFIDENCE
    assert len(sup.review_queue) == 1
    assert sup.accepted_changes == []


# ---------------------------------------------------------------------------
# No silent overwrite
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_no_silent_overwrite_of_existing_value(tmp_path, drugs_file):
    # Existing non-empty company; a high-confidence different proposal must NOT
    # overwrite — it must surface as a conflict for human review.
    path = drugs_file([_drug("lisinopril", company="Originator Pharma")])
    adapter = FakeAdapter("company", "Azurity Pharmaceuticals", confidence=0.95)
    sup = _supervisor(tmp_path, [adapter], path, apply_to_canonical=True)

    await sup.run()

    o = [o for o in sup.outcomes if o.field == "company"][0]
    assert o.disposition == DISP_CONFLICT
    assert o.existing_value == "Originator Pharma"
    assert o.proposed_value == "Azurity Pharmaceuticals"
    assert any(item["field"] == "company" for item in sup.review_queue)
    # No change record was emitted for a conflict.
    assert sup.accepted_changes == []
    # Canonical data on disk is untouched for the conflicting field.
    on_disk = json.loads(path.read_text())["drugs"][0]
    assert on_disk["company"] == "Originator Pharma"


@pytest.mark.asyncio
async def test_matching_value_is_no_change(tmp_path, drugs_file):
    path = drugs_file([_drug("aspirin", year_approved=1899)])
    adapter = FakeAdapter("year_approved", 1899, confidence=0.9)
    # year_approved is populated; with verify_existing=False the adapter is
    # skipped entirely -> no outcome for that field.
    sup = _supervisor(tmp_path, [adapter], path, verify_existing=False)
    await sup.run()
    assert [o for o in sup.outcomes if o.field == "year_approved"] == []

    # With verify_existing=True (the default), the same matching value is
    # surfaced as a verified no-change rather than skipped. Use a fresh
    # checkpoint so resume does not skip the drug.
    path2 = drugs_file([_drug("aspirin", year_approved=1899)])
    adapter2 = FakeAdapter("year_approved", 1899, confidence=0.9)
    sup2 = AgentDataSupervisor(
        [adapter2],
        drugs_file=path2,
        reports_dir=tmp_path / "reports2",
        changes_dir=tmp_path / "changes2",
        checkpoint_file=tmp_path / "checkpoints2" / "ckpt.json",
        verify_existing=True,
    )
    await sup2.run()
    verified = [o for o in sup2.outcomes if o.field == "year_approved"]
    assert len(verified) == 1
    assert verified[0].disposition == DISP_NO_CHANGE

    # If we force the field to look empty-ish but pass the same value via a list
    # field, the "no change" branch is exercised directly through _gate.
    drug = _drug("x", targets=["A", "B"])
    proposal = FieldProposal(
        "x", "targets", ["B", "A"],
        Provenance("fake", "u", utcnow_iso(), 0.9),
    )
    outcome = sup._gate(drug, proposal)
    assert outcome.disposition == DISP_NO_CHANGE


# ---------------------------------------------------------------------------
# Graceful degradation
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_adapter_raise_is_recorded_and_loop_continues(tmp_path, drugs_file):
    path = drugs_file([_drug("aspirin"), _drug("ibuprofen")])
    raising = FakeAdapter("year_approved", None, 0.0, behavior="raise")
    working = FakeAdapter("company", "Good Pharma", confidence=0.9)
    sup = _supervisor(tmp_path, [raising, working], path)

    report = await sup.run()

    errors = [o for o in sup.outcomes if o.disposition == DISP_ERROR]
    assert len(errors) == 2  # one per drug for the raising adapter
    assert all("simulated upstream failure" in e.note for e in errors)
    # The working adapter still produced accepted company fills for both drugs.
    accepted = [o for o in sup.outcomes if o.disposition == DISP_ACCEPTED]
    assert len(accepted) == 2
    assert report["errors"] and report["errors"][0]["error"]


@pytest.mark.asyncio
async def test_adapter_returning_none_is_unresolved(tmp_path, drugs_file):
    path = drugs_file([_drug("aspirin")])
    adapter = FakeAdapter("year_approved", None, 0.0, behavior="none")
    sup = _supervisor(tmp_path, [adapter], path)
    await sup.run()
    o = [o for o in sup.outcomes if o.field == "year_approved"][0]
    assert o.disposition == DISP_UNRESOLVED


@pytest.mark.asyncio
async def test_adapter_timeout_is_recorded(tmp_path, drugs_file):
    import asyncio

    class HangingAdapter:
        name = "hang"
        field = "year_approved"

        async def propose(self, drug):
            await asyncio.sleep(5)

    path = drugs_file([_drug("aspirin")])
    sup = _supervisor(tmp_path, [HangingAdapter()], path, per_adapter_timeout=0.05)
    await sup.run()
    o = [o for o in sup.outcomes if o.field == "year_approved"][0]
    assert o.disposition == DISP_ERROR
    assert "timed out" in o.note


# ---------------------------------------------------------------------------
# Resume / checkpoint
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_resume_skips_already_processed(tmp_path, drugs_file):
    path = drugs_file([_drug("a"), _drug("b"), _drug("c")])
    adapter = FakeAdapter("year_approved", 2000, confidence=0.9)
    sup1 = _supervisor(tmp_path, [adapter], path, max_records=2)
    await sup1.run()
    assert sorted(adapter.calls) == ["a", "b"]

    ckpt = load_checkpoint(tmp_path / "checkpoints" / "ckpt.json")
    assert set(ckpt["processed_ids"]) == {"a", "b"}

    # Second run resumes — only the remaining drug is processed.
    adapter2 = FakeAdapter("year_approved", 2000, confidence=0.9)
    sup2 = _supervisor(tmp_path, [adapter2], path)
    await sup2.run()
    assert adapter2.calls == ["c"]


@pytest.mark.asyncio
async def test_checkpoint_written_per_batch(tmp_path, drugs_file):
    path = drugs_file([_drug(str(i)) for i in range(5)])
    adapter = FakeAdapter("year_approved", 2000, confidence=0.9)
    sup = _supervisor(tmp_path, [adapter], path, batch_size=2)
    await sup.run()
    ckpt = load_checkpoint(tmp_path / "checkpoints" / "ckpt.json")
    assert len(ckpt["processed_ids"]) == 5


def test_corrupt_checkpoint_starts_fresh(tmp_path):
    p = tmp_path / "ckpt.json"
    p.write_text("not valid json{", encoding="utf-8")
    ckpt = load_checkpoint(p)
    assert ckpt["processed_ids"] == []


# ---------------------------------------------------------------------------
# Report + change record format
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_report_and_change_record_written(tmp_path, drugs_file):
    path = drugs_file([_drug("aspirin", year_approved=None)])
    adapter = FakeAdapter("year_approved", 1899, confidence=0.9)
    sup = _supervisor(tmp_path, [adapter], path)
    report = await sup.run()

    # Report file exists and is valid JSON with the expected top-level keys.
    report_path = tmp_path / "reports"
    files = list(report_path.glob("agent_supervisor_report_*.json"))
    assert len(files) == 1
    data = json.loads(files[0].read_text())
    assert data["stage"] == "agent_data_supervisor"
    assert "summary" in data and "review_queue" in data
    assert data["totals"]["total_drugs"] == 1

    # Change record matches the existing DrugChange schema + carries provenance.
    change_files = list((tmp_path / "changes").glob("*.json"))
    assert len(change_files) == 1
    change = json.loads(change_files[0].read_text())
    for key in ("change_id", "drug_id", "change_type", "field_changes",
                "old_snapshot", "new_snapshot", "source"):
        assert key in change
    assert change["change_type"] == "updated"
    assert change["field_changes"][0]["field_name"] == "year_approved"
    assert change["field_changes"][0]["new_value"] == 1899
    assert change["provenance"]["source"] == "fake"
    assert change["source"].startswith("agent_data_supervisor:")


# ---------------------------------------------------------------------------
# needs_enrichment / ATC placeholder handling
# ---------------------------------------------------------------------------
def test_needs_enrichment_atc_placeholder():
    assert needs_enrichment({"atc_code": "C99XX99"}, "atc_code") is True
    assert needs_enrichment({"atc_code": None}, "atc_code") is True
    assert needs_enrichment({"atc_code": "C10AA05"}, "atc_code") is False


def test_needs_enrichment_empty_collections():
    assert needs_enrichment({"targets": []}, "targets") is True
    assert needs_enrichment({"targets": ["X"]}, "targets") is False
    assert needs_enrichment({"company": ""}, "company") is True


@pytest.mark.asyncio
async def test_atc_adapter_only_skips_specific_codes(tmp_path, drugs_file):
    # Drug with a placeholder ATC should be processed; one with a specific code
    # is skipped entirely.
    path = drugs_file([
        _drug("placeholder_drug", atc_code="C99XX99"),
        _drug("specific_drug", atc_code="C10AA05"),
    ])
    adapter = FakeAdapter("atc_code", "C09AA03", confidence=0.9)
    sup = _supervisor(tmp_path, [adapter], path, verify_existing=False)
    await sup.run()
    assert adapter.calls == ["placeholder_drug"]
    o = [o for o in sup.outcomes if o.field == "atc_code"][0]
    assert o.disposition == DISP_ACCEPTED
    assert o.proposed_value == "C09AA03"


# ---------------------------------------------------------------------------
# Real adapters against a fake httpx client (no network)
# ---------------------------------------------------------------------------
class _FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


class _FakeHttpClient:
    """Minimal httpx.AsyncClient stand-in keyed by URL substring."""

    def __init__(self, routes):
        self._routes = routes  # list[(substr, _FakeResponse)]
        self.requests = []

    async def get(self, url, params=None):
        self.requests.append((url, params))
        for substr, resp in self._routes:
            if substr in url:
                return resp
        return _FakeResponse(404, {})


@pytest.mark.asyncio
async def test_chembl_atc_adapter_with_fake_http():
    drug = _drug("aspirin", atc_code="C99XX99", chembl_id="CHEMBL25")
    fake = _FakeHttpClient([
        ("molecule/CHEMBL25.json", _FakeResponse(200, {
            "molecule_chembl_id": "CHEMBL25",
            "atc_classifications": ["N02BA01"],
        })),
    ])
    adapter = ChemblAtcAdapter(fake)
    proposal = await adapter.propose(drug)
    assert proposal is not None
    assert proposal.value == "N02BA01"
    assert proposal.provenance.source.startswith("ChEMBL")
    assert proposal.provenance.confidence >= 0.85


@pytest.mark.asyncio
async def test_chembl_atc_adapter_rejects_non_specific_code():
    drug = _drug("x", atc_code="C99XX99", chembl_id="CHEMBL1")
    fake = _FakeHttpClient([
        ("molecule/CHEMBL1.json", _FakeResponse(200, {
            "molecule_chembl_id": "CHEMBL1",
            "atc_classifications": ["BOGUS"],  # not a valid specific code
        })),
    ])
    adapter = ChemblAtcAdapter(fake)
    assert await adapter.propose(drug) is None


@pytest.mark.asyncio
async def test_chembl_atc_adapter_degrades_on_http_error():
    drug = _drug("x", atc_code="C99XX99", chembl_id="CHEMBL1")

    class _Boom:
        async def get(self, url, params=None):
            raise RuntimeError("network down")

    adapter = ChemblAtcAdapter(_Boom())
    assert await adapter.propose(drug) is None  # no raise, just None


@pytest.mark.asyncio
async def test_chembl_mechanism_adapter_targets_and_class():
    drug = _drug("aspirin", targets=[], chembl_id="CHEMBL25")
    mech_payload = {
        "mechanisms": [
            {"mechanism_of_action": "Cyclooxygenase inhibitor",
             "target_pref_name": "Cyclooxygenase-1"},
            {"mechanism_of_action": "Cyclooxygenase inhibitor",
             "target_pref_name": "Cyclooxygenase-2"},
        ]
    }
    fake = _FakeHttpClient([("mechanism.json", _FakeResponse(200, mech_payload))])

    targets_adapter = ChemblMechanismAdapter(fake, target_field="targets")
    p_targets = await targets_adapter.propose(drug)
    assert p_targets.value == ["Cyclooxygenase-1", "Cyclooxygenase-2"]

    class_adapter = ChemblMechanismAdapter(fake, target_field="class")
    p_class = await class_adapter.propose(_drug("aspirin", **{"class": None},
                                               chembl_id="CHEMBL25"))
    assert p_class.value == "Cyclooxygenase inhibitor"


@pytest.mark.asyncio
async def test_openfda_adapter_with_fake_client():
    class _FakeFDA:
        async def get_drug_approvals(self, name):
            return [{
                "application_number": "NDA021436",
                "approval_date": "20170928",
                "sponsor": "Eli Lilly and Company",
            }]

    drug = _drug("abemaciclib", year_approved=None)
    year_adapter = OpenFDAApprovalAdapter(_FakeFDA())
    p = await year_adapter.propose(drug)
    assert p.value == 2017
    assert p.field == "year_approved"
    assert "openFDA" in p.provenance.source


# ---------------------------------------------------------------------------
# H3 disease-drug edge builder
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_build_disease_drug_edges_appends_and_flags(tmp_path):
    diseases = {"diseases": [
        {"id": "hypertension", "canonical_name": "Hypertension",
         "synonyms": ["high blood pressure"]},
        {"id": "rare_orphan", "canonical_name": "Rare Orphan Disease",
         "synonyms": []},
    ]}
    drugs = {"drugs": [
        {"id": "lisinopril", "name": "Lisinopril", "chembl_id": "CHEMBL1431"},
    ]}
    edges = {"edges": [
        {"disease_id": "hypertension", "drug_id": "amlodipine",
         "indication_type": "primary", "evidence_source": "curated_seed",
         "evidence_level": "approved"},
    ], "metadata": {"seed_edge_count": 1}}

    d_path = tmp_path / "diseases.json"
    dr_path = tmp_path / "drugs.json"
    e_path = tmp_path / "disease_drug_edges.json"
    d_path.write_text(json.dumps(diseases))
    dr_path.write_text(json.dumps(drugs))
    e_path.write_text(json.dumps(edges))

    class _FakeIndications:
        async def indications_for_drug(self, chembl_id):
            return [{"disease_id": "D006973", "disease_name": "Hypertension"}]

    out = await build_disease_drug_edges(
        indication_provider=_FakeIndications(),
        diseases_file=d_path,
        drugs_file=dr_path,
        edges_file=e_path,
        reports_dir=tmp_path / "reports",
    )

    # Existing curated edge preserved; one new sourced edge appended.
    keys = {(e["disease_id"], e["drug_id"]) for e in out["edges"]}
    assert ("hypertension", "amlodipine") in keys
    assert ("hypertension", "lisinopril") in keys
    new_edge = [e for e in out["edges"] if e["drug_id"] == "lisinopril"][0]
    assert new_edge["evidence_source"] == "chembl_indication"
    assert new_edge["provenance"]["source"] == "ChEMBL:drug_indication"

    # The disease with no resolved drug is flagged explicitly.
    flags = {f["disease_id"] for f in out["no_drug_flags"]}
    assert "rare_orphan" in flags
    assert out["metadata"]["new_edge_count"] == 1


@pytest.mark.asyncio
async def test_build_disease_drug_edges_syncs_approved_drug_count(tmp_path):
    # Writing new edges must keep diseases.json approved_drug_count consistent
    # with the edge file (the test_disease_edge_consistency invariant).
    diseases = {"diseases": [
        {"id": "hypertension", "canonical_name": "Hypertension",
         "synonyms": [], "approved_drug_count": 1},
    ]}
    drugs = {"drugs": [
        {"id": "lisinopril", "name": "Lisinopril", "chembl_id": "CHEMBL1431"},
    ]}
    edges = {"edges": [
        {"disease_id": "hypertension", "drug_id": "amlodipine",
         "indication_type": "primary", "evidence_source": "curated_seed",
         "evidence_level": "approved"},
    ], "metadata": {}}
    d_path = tmp_path / "diseases.json"
    dr_path = tmp_path / "drugs.json"
    e_path = tmp_path / "edges.json"
    d_path.write_text(json.dumps(diseases))
    dr_path.write_text(json.dumps(drugs))
    e_path.write_text(json.dumps(edges))

    class _FakeIndications:
        async def indications_for_drug(self, chembl_id):
            return [{"disease_id": "D006973", "disease_name": "Hypertension"}]

    await build_disease_drug_edges(
        indication_provider=_FakeIndications(),
        diseases_file=d_path,
        drugs_file=dr_path,
        edges_file=e_path,
        reports_dir=tmp_path / "reports",
    )
    # 2 edges now point at hypertension -> approved_drug_count must be 2.
    updated = json.loads(d_path.read_text())["diseases"][0]
    assert updated["approved_drug_count"] == 2
    written_edges = json.loads(e_path.read_text())["edges"]
    counts = sum(1 for e in written_edges if e["disease_id"] == "hypertension")
    assert counts == updated["approved_drug_count"]


@pytest.mark.asyncio
async def test_build_disease_drug_edges_degrades_on_provider_error(tmp_path):
    d_path = tmp_path / "diseases.json"
    dr_path = tmp_path / "drugs.json"
    d_path.write_text(json.dumps({"diseases": [
        {"id": "hypertension", "canonical_name": "Hypertension", "synonyms": []}]}))
    dr_path.write_text(json.dumps({"drugs": [
        {"id": "lisinopril", "name": "Lisinopril", "chembl_id": "CHEMBL1431"}]}))

    class _BoomProvider:
        async def indications_for_drug(self, chembl_id):
            raise RuntimeError("ChEMBL down")

    out = await build_disease_drug_edges(
        indication_provider=_BoomProvider(),
        diseases_file=d_path,
        drugs_file=dr_path,
        edges_file=tmp_path / "edges.json",
        reports_dir=tmp_path / "reports",
        write=False,
    )
    # No crash; error captured; disease flagged as no-approved-drug.
    assert out["metadata"]["errors"] == 1
    assert out["metadata"]["new_edge_count"] == 0
