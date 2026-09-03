"""Panel tests, driven through HTTP rather than through the functions.

The interesting failures live in the wiring: a screen reachable without the
password, a decision recorded under nobody's name, an edit that quietly replaces
what the agent wrote. Calling the handlers directly would not see any of that.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from sap_agent_mcp.store import Proposal, ProposalStatus, Store, new_id
from sap_agent_panel.app import create_app

PASSWORD = "test-password"


@pytest.fixture
def store(tmp_path) -> Store:
    return Store(tmp_path / "state.db")


@pytest.fixture
def client(store, tmp_path, monkeypatch) -> TestClient:
    monkeypatch.setenv("REPO_ROOT", str(tmp_path / "repo"))
    for subset in ("open", "sealed"):
        (tmp_path / "repo" / "evals" / "dataset" / subset).mkdir(parents=True)
    (tmp_path / "repo" / "evals" / "reports").mkdir(parents=True)
    app = create_app(
        store,
        {"password": PASSWORD, "state_path": tmp_path / "state.db",
         "analysts": ["lead-analyst", "analyst-1"]},
    )
    return TestClient(app, follow_redirects=False)


@pytest.fixture
def signed_in(client) -> TestClient:
    response = client.post("/login", data={"password": PASSWORD})
    assert response.status_code == 303
    return client


def a_proposal(store: Store, **kwargs) -> Proposal:
    defaults = dict(
        id=new_id("prop"),
        user_id="lead-analyst",
        question="Выручка по странам за второй квартал 2021",
        sql="SELECT SUM(v.netwr) FROM sh.zvbrp v WHERE v.mandt = '100'",
        status=ProposalStatus.PENDING,
        checks=[{"id": "read-only", "title": "Только чтение", "status": "passed",
                 "detail": "Одна инструкция."}],
        tables=["SH.ZVBRP"],
        columns=["SH.ZVBRP.NETWR"],
        row_limit=1000,
        estimated_rows=1,
        plan=["SELECT STATEMENT", "TABLE ACCESS FULL ZVBRP"],
        policy_reason="Оценка 5000 строк, порог 200.",
        data_as_of="2026-09-02T15:45:19",
    )
    return store.add_proposal(Proposal(**{**defaults, **kwargs}))


# --- the password ------------------------------------------------------------

@pytest.mark.parametrize("path", ["/", "/history", "/limits", "/evals", "/queue/rows"])
def test_every_screen_needs_the_password(client, path) -> None:
    response = client.get(path)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_a_wrong_password_does_not_sign_in(client) -> None:
    response = client.post("/login", data={"password": "guess"})
    assert response.headers["location"] == "/login?error=1"
    assert client.get("/").status_code == 303


def test_the_right_password_signs_in(client) -> None:
    client.post("/login", data={"password": PASSWORD})
    assert client.get("/").status_code == 200


def test_logging_out_takes_the_cookie_away(signed_in) -> None:
    signed_in.post("/logout")
    assert signed_in.get("/").status_code == 303


# --- the queue ---------------------------------------------------------------

def test_the_queue_shows_the_question_the_sql_and_why_it_waits(signed_in, store) -> None:
    a_proposal(store)
    body = signed_in.get("/").text
    assert "Выручка по странам" in body
    assert "SELECT SUM" in body
    assert "порог 200" in body
    assert "Только чтение" in body  # the verdict of every check is on the card


def test_an_empty_queue_says_so_rather_than_showing_nothing(signed_in) -> None:
    assert "Очередь пуста" in signed_in.get("/").text


def test_approving_records_who_and_when(signed_in, store) -> None:
    proposal = a_proposal(store)
    response = signed_in.post(
        f"/proposals/{proposal.id}/approve",
        data={"by": "lead-analyst", "note": "период тот, что нужен"},
    )
    assert response.status_code == 303
    stored = store.get_proposal(proposal.id)
    assert stored.status == ProposalStatus.APPROVED
    assert stored.decided_by == "lead-analyst"
    assert stored.decided_at is not None
    assert stored.decision_note == "период тот, что нужен"


def test_rejecting_keeps_the_reason(signed_in, store) -> None:
    proposal = a_proposal(store)
    signed_in.post(
        f"/proposals/{proposal.id}/reject",
        data={"by": "analyst-1", "note": "не тот квартал"},
    )
    stored = store.get_proposal(proposal.id)
    assert stored.status == ProposalStatus.REJECTED
    assert stored.decision_note == "не тот квартал"


def test_editing_keeps_the_original_and_queues_a_new_one(signed_in, store) -> None:
    proposal = a_proposal(store)
    signed_in.post(
        f"/proposals/{proposal.id}/amend",
        data={"sql": "SELECT 1 FROM sh.zvbrp v WHERE v.mandt = '100'",
              "by": "lead-analyst", "note": "добавил год"},
    )
    old = store.get_proposal(proposal.id)
    assert old.status == ProposalStatus.SUPERSEDED
    fresh = [p for p in store.pending() if p.supersedes == proposal.id]
    assert len(fresh) == 1
    assert fresh[0].status == ProposalStatus.PENDING


def test_a_decision_is_journalled_under_the_name_that_made_it(signed_in, store) -> None:
    proposal = a_proposal(store)
    signed_in.post(f"/proposals/{proposal.id}/approve", data={"by": "analyst-1"})
    entries = store.journal(proposal_id=proposal.id)
    assert [(e.tool, e.outcome, e.user_id) for e in entries] == [
        ("panel", "approved", "analyst-1")
    ]


# --- history -----------------------------------------------------------------

def test_history_shows_rejected_proposals_too(signed_in, store) -> None:
    proposal = a_proposal(store)
    signed_in.post(f"/proposals/{proposal.id}/reject", data={"by": "analyst-1"})
    assert "отклонено" in signed_in.get("/history").text


def test_one_proposal_page_shows_the_checks_and_the_journal(signed_in, store) -> None:
    proposal = a_proposal(store)
    store.record(user_id="lead-analyst", tool="propose_query", outcome="ok",
                 proposal_id=proposal.id)
    body = signed_in.get(f"/history/{proposal.id}").text
    assert "propose_query" in body
    assert "Только чтение" in body


def test_a_proposal_that_does_not_exist_is_a_404(signed_in) -> None:
    assert signed_in.get("/history/prop_nothing").status_code == 404


# --- limits ------------------------------------------------------------------

def test_raising_a_limit_without_a_reason_is_refused(signed_in) -> None:
    response = signed_in.post(
        "/limits/grant",
        data={"user_id": "analyst-1", "extra": "50", "by": "lead-analyst", "reason": "  "},
    )
    assert response.status_code == 400


def test_raising_a_limit_with_a_reason_is_recorded(signed_in, store) -> None:
    signed_in.post(
        "/limits/grant",
        data={"user_id": "analyst-1", "extra": "50", "by": "lead-analyst",
              "reason": "закрытие квартала"},
    )
    entries = [e for e in store.journal() if e.tool == "limits"]
    assert entries and entries[0].detail["reason"] == "закрытие квартала"


def test_a_policy_switch_changes_what_runs_without_approval(signed_in, store) -> None:
    signed_in.post(
        "/limits/policy",
        data={"key": "auto_execute", "value": "off", "by": "lead-analyst",
              "reason": "инцидент на реплике"},
    )
    assert store.setting("auto_execute") == "off"


def test_a_policy_change_without_a_reason_is_refused(signed_in, store) -> None:
    response = signed_in.post(
        "/limits/policy",
        data={"key": "auto_max_rows", "value": "5000", "by": "lead-analyst", "reason": ""},
    )
    assert response.status_code == 400
    assert store.setting("auto_max_rows") is None


def test_an_unknown_switch_is_refused(signed_in) -> None:
    response = signed_in.post(
        "/limits/policy",
        data={"key": "disable_guards", "value": "on", "by": "lead-analyst",
              "reason": "очень надо"},
    )
    assert response.status_code == 400


# --- the reference set -------------------------------------------------------

def test_the_evals_screen_hides_the_sealed_questions(signed_in, tmp_path) -> None:
    repo = tmp_path / "repo" / "evals" / "dataset"
    (repo / "open" / "q.yaml").write_text(
        "id: open-01\nquestion: Сколько продали за 2021\ndifficulty: simple\nkind: answerable\n",
        encoding="utf-8",
    )
    (repo / "sealed" / "q.yaml").write_text(
        "id: sealed-01\nquestion: Секретный вопрос\ndifficulty: simple\nkind: answerable\n",
        encoding="utf-8",
    )
    body = signed_in.get("/evals").text
    assert "Сколько продали за 2021" in body
    assert "Секретный вопрос" not in body
    assert "(запечатан)" in body


def test_nominating_a_pair_writes_a_draft_and_does_not_touch_the_set(
    signed_in, store, tmp_path
) -> None:
    proposal = a_proposal(store, status=ProposalStatus.EXECUTED)
    signed_in.post(
        "/evals/candidate", data={"proposal_id": proposal.id, "by": "lead-analyst"}
    )
    drafts = list((tmp_path / "repo" / "evals" / "candidates").glob("*.yaml"))
    assert len(drafts) == 1
    assert "Выручка по странам" in drafts[0].read_text(encoding="utf-8")
    assert not list((tmp_path / "repo" / "evals" / "dataset" / "open").glob("*.yaml"))
