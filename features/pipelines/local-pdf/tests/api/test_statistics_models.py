from local_pdf.api.models.statistics import (
    CapabilityWish,
    CapabilityWishes,
    DiagnosticCounts,
    ExtractStats,
    ProvenienzStats,
    SyntheseStats,
    VoteDistributionRow,
)


def test_extract_stats_round_trip():
    m = ExtractStats(
        slug="doc-a",
        diagnostics=DiagnosticCounts(split=1, no_decomposition=0, clean=10, total=11),
        register_boxes=2,
        total_boxes=20,
        register_rate=0.1,
    )
    assert m.model_dump()["register_rate"] == 0.1


def test_synthese_stats_allows_null_rates():
    m = SyntheseStats(
        slug="doc-a",
        questions_created=0,
        questions_deprecated=0,
        survival_rate=None,
        vote_approved=0,
        vote_rejected=0,
        vote_approval_rate=None,
        vote_distribution=[],
    )
    assert m.survival_rate is None
    assert m.vote_distribution == []


def test_capability_wishes_carries_actor_split():
    w = CapabilityWishes(
        wishes=[
            CapabilityWish(
                name="RegisterLookup",
                count=5,
                by_actor={"human": 1, "agent": 4},
                skill_bucket="register",
            )
        ]
    )
    assert w.wishes[0].by_actor == {"human": 1, "agent": 4}


def test_provenienz_stats_zero_proposals_is_null_rate():
    m = ProvenienzStats(
        slug="doc-a",
        plan_proposals=0,
        expert_overrides=0,
        correction_rate=None,
    )
    assert m.correction_rate is None


def test_vote_distribution_row():
    r = VoteDistributionRow(
        entry_id="q1", text_short="Was ist der Registersatz?", approved=3, rejected=1
    )
    assert r.approved == 3
