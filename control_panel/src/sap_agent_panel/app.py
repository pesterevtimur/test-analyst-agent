"""The analyst's panel: approve, look back, hold the limits, see the set.

Four screens, one password, bound to the loopback and reached through an ssh
tunnel. It is a second process over the same SQLite file the MCP server writes,
which is why the store speaks WAL: the panel reads the queue while the server
appends to it.

What is deliberately not here: anything OpenClaw's own panel already does
(sessions, live task page, per-call tool view, spend). Duplicating that would
mean two places to look and two places to be wrong.

The approval is the point. Everything else on these screens exists to make the
approval an informed one: the question, the SQL, the plan, the volume estimate,
and the verdict of every check, on one card.
"""

from __future__ import annotations

import os
import secrets
from pathlib import Path
from typing import Any

from fastapi import Cookie, Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from sap_agent_mcp.store import ProposalStatus, Store

HERE = Path(__file__).resolve().parent
STATIC = HERE.parent.parent / "static"

# Session cookies are signed with a per-process secret: a restart logs everyone
# out, which is the right trade for a panel with one password and no user store.
SESSION_SECRET = secrets.token_urlsafe(32)
COOKIE = "sap_panel"


def settings() -> dict[str, Any]:
    password = os.environ.get("PANEL_PASSWORD")
    if not password:
        raise RuntimeError(
            "PANEL_PASSWORD is not set. The panel refuses to start rather than "
            "run without a password: it approves database queries."
        )
    return {
        "password": password,
        "state_path": Path(os.environ.get("STATE_PATH", "state/sap-agent.db")),
        # Who is approving. No user store, no real authentication: the list is
        # configuration and the choice is recorded with the decision. Named in
        # docs/limits.md and docs/not-done.md, not glossed over.
        "analysts": [
            name.strip()
            for name in os.environ.get(
                "PANEL_ANALYSTS", "lead-analyst,analyst-1,analyst-2"
            ).split(",")
            if name.strip()
        ],
    }


def create_app(store: Store | None = None, config: dict[str, Any] | None = None) -> FastAPI:
    config = config or settings()
    store = store or Store(config["state_path"])

    app = FastAPI(title="Панель аналитика", docs_url=None, redoc_url=None)
    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    templates = Jinja2Templates(directory=str(HERE / "templates"))
    app.state.store = store
    app.state.config = config

    def signed_in(session: str | None = Cookie(default=None, alias=COOKIE)) -> bool:
        if session != SESSION_SECRET:
            raise HTTPException(status_code=303, headers={"Location": "/login"})
        return True

    def page(request: Request, name: str, **context: Any) -> HTMLResponse:
        return templates.TemplateResponse(
            request, name, {"analysts": config["analysts"], **context}
        )

    # -- one password ---------------------------------------------------------

    @app.get("/login", response_class=HTMLResponse)
    def login_form(request: Request) -> HTMLResponse:
        return page(request, "login.html", error=None)

    @app.post("/login")
    def login(password: str = Form(...)) -> RedirectResponse:
        # Constant time: the password is short and the panel is on a loopback,
        # but a comparison that leaks length teaches the wrong habit.
        if not secrets.compare_digest(password, config["password"]):
            return RedirectResponse("/login?error=1", status_code=303)
        response = RedirectResponse("/", status_code=303)
        response.set_cookie(
            COOKIE, SESSION_SECRET, httponly=True, samesite="strict", path="/"
        )
        return response

    @app.post("/logout")
    def logout() -> RedirectResponse:
        response = RedirectResponse("/login", status_code=303)
        response.delete_cookie(COOKIE, path="/")
        return response

    # -- 1. the queue ---------------------------------------------------------

    @app.get("/", response_class=HTMLResponse)
    def queue(request: Request, _: bool = Depends(signed_in)) -> HTMLResponse:
        return page(request, "queue.html", proposals=store.pending())

    @app.get("/queue/rows", response_class=HTMLResponse)
    def queue_rows(request: Request, _: bool = Depends(signed_in)) -> HTMLResponse:
        """The list alone, polled by htmx so a new proposal appears by itself."""
        return page(request, "_queue_rows.html", proposals=store.pending())

    @app.post("/proposals/{proposal_id}/approve")
    def approve(
        proposal_id: str,
        by: str = Form(...),
        note: str = Form(""),
        _: bool = Depends(signed_in),
    ) -> RedirectResponse:
        store.decide(proposal_id, status=ProposalStatus.APPROVED, by=by, note=note)
        store.record(
            user_id=by, tool="panel", outcome="approved",
            proposal_id=proposal_id, note=note,
        )
        return RedirectResponse("/", status_code=303)

    @app.post("/proposals/{proposal_id}/reject")
    def reject(
        proposal_id: str,
        by: str = Form(...),
        note: str = Form(""),
        _: bool = Depends(signed_in),
    ) -> RedirectResponse:
        store.decide(proposal_id, status=ProposalStatus.REJECTED, by=by, note=note)
        store.record(
            user_id=by, tool="panel", outcome="rejected",
            proposal_id=proposal_id, note=note,
        )
        return RedirectResponse("/", status_code=303)

    @app.post("/proposals/{proposal_id}/amend")
    def amend(
        proposal_id: str,
        sql: str = Form(...),
        by: str = Form(...),
        note: str = Form(""),
        _: bool = Depends(signed_in),
    ) -> RedirectResponse:
        old, fresh = store.amend(proposal_id, sql=sql, by=by, note=note)
        store.record(
            user_id=by, tool="panel", outcome="amended",
            proposal_id=old.id, replacement=fresh.id, note=note,
        )
        return RedirectResponse("/", status_code=303)

    # -- 2. history -----------------------------------------------------------

    @app.get("/history", response_class=HTMLResponse)
    def history(request: Request, _: bool = Depends(signed_in)) -> HTMLResponse:
        proposals = store.history()
        return page(
            request, "history.html",
            proposals=proposals,
            results={p.id: store.result_for(p.id) for p in proposals},
        )

    @app.get("/history/{proposal_id}", response_class=HTMLResponse)
    def one(request: Request, proposal_id: str, _: bool = Depends(signed_in)) -> HTMLResponse:
        proposal = store.get_proposal(proposal_id)
        if proposal is None:
            raise HTTPException(status_code=404, detail="нет такого предложения")
        return page(
            request, "proposal.html",
            proposal=proposal,
            result=store.result_for(proposal_id),
            journal=store.journal(proposal_id=proposal_id),
        )

    # -- 3. limits ------------------------------------------------------------

    @app.get("/limits", response_class=HTMLResponse)
    def limits(request: Request, _: bool = Depends(signed_in)) -> HTMLResponse:
        return page(
            request, "limits.html",
            states=store.rate_states(),
            policy={
                "auto_execute": store.setting("auto_execute", "on"),
                "auto_max_rows": store.setting("auto_max_rows", "200"),
                "auto_max_tables": store.setting("auto_max_tables", "3"),
            },
        )

    @app.post("/limits/grant")
    def grant(
        user_id: str = Form(...),
        extra: int = Form(...),
        by: str = Form(...),
        reason: str = Form(...),
        _: bool = Depends(signed_in),
    ) -> RedirectResponse:
        try:
            store.grant_bonus(user_id, extra=extra, by=by, reason=reason)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return RedirectResponse("/limits", status_code=303)

    @app.post("/limits/policy")
    def policy(
        key: str = Form(...),
        value: str = Form(...),
        by: str = Form(...),
        # Empty on purpose rather than required by the form: a missing reason
        # must come back as the sentence explaining why it is missing, not as a
        # framework's validation blob.
        reason: str = Form(""),
        _: bool = Depends(signed_in),
    ) -> RedirectResponse:
        if key not in {"auto_execute", "auto_max_rows", "auto_max_tables"}:
            raise HTTPException(status_code=400, detail=f"неизвестный переключатель {key}")
        try:
            store.set_setting(key, value, by=by, reason=reason)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return RedirectResponse("/limits", status_code=303)

    # -- 4. the reference set -------------------------------------------------

    @app.get("/evals", response_class=HTMLResponse)
    def evals(request: Request, _: bool = Depends(signed_in)) -> HTMLResponse:
        from .reference import last_report, load_questions

        return page(
            request, "evals.html",
            questions=load_questions(),
            report=last_report(),
            candidates=store.history(limit=200),
        )

    @app.post("/evals/candidate")
    def candidate(
        proposal_id: str = Form(...),
        by: str = Form(...),
        _: bool = Depends(signed_in),
    ) -> RedirectResponse:
        """Nominate an approved pair for the reference set.

        It is a nomination, not an addition. The set lives in git (ADR-011) and
        grows by commit: a set that grows automatically with what the agent
        already got right raises its own score.
        """
        from .reference import nominate

        proposal = store.get_proposal(proposal_id)
        if proposal is None:
            raise HTTPException(status_code=404, detail="нет такого предложения")
        path = nominate(proposal, by=by)
        store.record(
            user_id=by, tool="panel", outcome="nominated",
            proposal_id=proposal_id, path=str(path),
        )
        return RedirectResponse("/evals", status_code=303)

    return app


app = None  # built by __main__ so importing the module never demands a password


def main() -> None:
    import uvicorn

    uvicorn.run(
        create_app(),
        host=os.environ.get("PANEL_HOST", "127.0.0.1"),
        port=int(os.environ.get("PANEL_PORT", "8081")),
        log_level="info",
    )


if __name__ == "__main__":
    main()
