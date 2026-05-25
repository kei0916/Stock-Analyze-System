"""Login / logout routes."""
from __future__ import annotations

from fastapi import APIRouter, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse

from stock_analyze_system.web.auth import (
    SESSION_COOKIE,
    SESSION_MAX_AGE,
    SessionSigner,
    get_client_key,
    verify_password,
)
from stock_analyze_system.web.dependencies import render

router = APIRouter()


@router.get("/login", response_class=HTMLResponse)
async def login_form(request: Request, error: str | None = None):
    return render(request, "login.html", {"error": error})


@router.post("/login")
async def login_submit(request: Request, password: str = Form(...)):
    config = request.app.state.app_state.config
    limiter = request.app.state.login_rate_limiter
    client_key = get_client_key(request, "login")
    lease = limiter.try_acquire(client_key)
    if lease is None:
        return render(
            request,
            "login.html",
            {"error": "試行回数が多すぎます。しばらく待ってから再試行してください。"},
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        )
    if not verify_password(password, config.web.password):
        return render(
            request,
            "login.html",
            {"error": "パスワードが違います"},
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
    limiter.release(lease)
    signer: SessionSigner = request.app.state.session_signer
    token = signer.sign("user")
    resp = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    resp.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=SESSION_MAX_AGE,
        httponly=True,
        secure=config.web.secure_cookies,
        samesite="lax",
    )
    return resp


@router.get("/logout")
async def logout():
    resp = RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    resp.delete_cookie(SESSION_COOKIE)
    return resp
