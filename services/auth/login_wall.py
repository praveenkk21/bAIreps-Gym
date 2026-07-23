import os
import streamlit as st
from urllib.parse import urlencode
import httpx
from dotenv import load_dotenv

from services.persistence.exercise_repository import (
    create_user,
    get_user,
    verify_user,
    get_or_create_google_user,
)

load_dotenv()

_GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
_GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"


def _google_client_id() -> str:
    v = os.environ.get("GOOGLE_CLIENT_ID", "")
    if not v and hasattr(st, "secrets") and "GOOGLE_CLIENT_ID" in st.secrets:
        v = st.secrets["GOOGLE_CLIENT_ID"]
    return v


def _google_client_secret() -> str:
    v = os.environ.get("GOOGLE_CLIENT_SECRET", "")
    if not v and hasattr(st, "secrets") and "GOOGLE_CLIENT_SECRET" in st.secrets:
        v = st.secrets["GOOGLE_CLIENT_SECRET"]
    return v


def _redirect_uri() -> str:
    v = os.environ.get("GOOGLE_REDIRECT_URI", "")
    if not v and hasattr(st, "secrets") and "GOOGLE_REDIRECT_URI" in st.secrets:
        v = st.secrets["GOOGLE_REDIRECT_URI"]
    if v:
        return v
    try:
        headers = st.context.headers
        host = (
            headers.get("x-forwarded-host")
            or headers.get("host")
            or "localhost:8501"
        )
        proto = headers.get("x-forwarded-proto") or ("https" if "localhost" not in host else "http")
        return f"{proto}://{host}"
    except Exception:
        pass
    try:
        from urllib.parse import urlparse
        parsed = urlparse(st.context.url)
        return f"{parsed.scheme}://{parsed.netloc}"
    except Exception:
        return "http://localhost:8501"


def _build_google_auth_url() -> str:
    params = {
        "client_id": _google_client_id(),
        "redirect_uri": _redirect_uri(),
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
        "prompt": "select_account",
    }
    return f"{_GOOGLE_AUTH_URL}?{urlencode(params)}"


def _google_button() -> None:
    auth_url = _build_google_auth_url()
    st.markdown(
        f"""
        <a href="{auth_url}" target="_self" style="
            display: block;
            width: 100%;
            padding: 0.5rem 1rem;
            background-color: #181D2A;
            border: 1px solid rgba(255,255,255,0.08);
            color: #fff;
            text-align: center;
            text-decoration: none;
            font-family: 'AdobeClean', sans-serif;
            font-size: 0.95rem;
            box-sizing: border-box;
        ">Continue with Google</a>
        """,
        unsafe_allow_html=True,
    )


def _exchange_code_for_user(code: str) -> dict | None:
    redirect = _redirect_uri()
    try:
        resp = httpx.post(
            _GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": _google_client_id(),
                "client_secret": _google_client_secret(),
                "redirect_uri": redirect,
                "grant_type": "authorization_code",
            },
            timeout=10,
        )
        if not resp.is_success:
            st.error(f"Google token exchange failed ({resp.status_code}). redirect_uri used: `{redirect}`")
            return None
        access_token = resp.json().get("access_token")
        info = httpx.get(
            _GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )
        info.raise_for_status()
        return info.json()
    except Exception as e:
        st.error(f"Google sign-in failed: {e}. redirect_uri used: `{redirect}`")
        return None


def _handle_oauth_callback() -> bool:
    code = st.query_params.get("code")
    if not code:
        return False

    userinfo = _exchange_code_for_user(code)
    st.query_params.clear()

    if userinfo is None:
        return False

    google_id = userinfo.get("sub")
    email = userinfo.get("email", "")
    name = userinfo.get("name", email.split("@")[0])

    user = get_or_create_google_user(google_id, email, name)
    st.session_state["username"] = user["username"]
    st.session_state["user_id"] = user["id"]
    return True


def render_footer():
    st.markdown(
        """
        <style>
        .aigym-footer {
            position: fixed;
            bottom: 0;
            left: 0;
            width: 100%;
            background: #0A0D14;
            border-top: 1px solid rgba(255,255,255,0.07);
            padding: 10px 0;
            text-align: center;
            font-size: 13px;
            color: rgba(255,255,255,0.4);
            z-index: 9999;
            font-family: 'AdobeClean', sans-serif;
        }
        .aigym-footer a {
            color: rgba(255,255,255,0.65);
            text-decoration: none;
            font-weight: 500;
        }
        .aigym-footer a:hover { color: #fff; }
        </style>
        <div class="aigym-footer">
            Created by <a href="https://www.linkedin.com/in/praveenkk21" target="_blank">Praveen</a>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_login_wall() -> bool:
    if st.session_state.get("user_id") is not None:
        return True

    if _handle_oauth_callback():
        st.rerun()

    google_configured = bool(_google_client_id() and _google_client_secret())

    st.markdown(
        """
        <style>
        .login-hero {
            text-align: center;
            padding: 2.5rem 0 1.5rem;
        }
        .login-hero .logo { font-size: 3rem; line-height: 1; }
        .login-hero h1 {
            font-size: 2rem !important;
            font-weight: 700 !important;
            margin: 0.4rem 0 0.25rem !important;
            letter-spacing: -0.5px;
        }
        .login-hero p {
            color: rgba(255,255,255,0.45);
            font-size: 0.95rem;
            margin: 0;
        }
        .login-divider {
            display: flex;
            align-items: center;
            gap: 10px;
            margin: 1.2rem 0;
            color: rgba(255,255,255,0.25);
            font-size: 12px;
        }
        .login-divider::before,
        .login-divider::after {
            content: '';
            flex: 1;
            border-top: 1px solid rgba(255,255,255,0.1);
        }
        </style>
        <div class="login-hero">
            <div class="logo">💪</div>
            <h1>bAIreps</h1>
            <p>AI-powered gym coach — track every rep, perfect every set</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    login_tab, register_tab = st.tabs(["Log In", "Register"])

    with login_tab:
        with st.form("login_form", clear_on_submit=False):
            username = st.text_input("Username", placeholder="Your username")
            password = st.text_input("Password", type="password", placeholder="Your password")
            submit = st.form_submit_button("Log In", use_container_width=True)

        if submit:
            if not username or not password:
                st.error("Username and password are required.")
                return False
            user = verify_user(username, password)
            if user is None:
                st.error("Invalid username or password.")
                return False
            st.session_state["username"] = user["username"]
            st.session_state["user_id"] = user["id"]
            st.rerun()

        if google_configured:
            st.markdown('<div class="login-divider">or</div>', unsafe_allow_html=True)
            _google_button()

    with register_tab:
        with st.form("register_form", clear_on_submit=False):
            new_username = st.text_input("Choose a username", placeholder="Unique username")
            new_password = st.text_input("Choose a password", type="password", placeholder="At least 6 characters")
            confirm_password = st.text_input("Confirm password", type="password", placeholder="Repeat password")
            register = st.form_submit_button("Create Account", use_container_width=True)

        if register:
            if not new_username or not new_password:
                st.error("Username and password are required.")
                return False
            if len(new_password) < 6:
                st.error("Password must be at least 6 characters.")
                return False
            if new_password != confirm_password:
                st.error("Passwords do not match.")
                return False
            if get_user(new_username) is not None:
                st.error("That username is already taken.")
                return False
            user = create_user(new_username, new_password)
            st.session_state["username"] = user["username"]
            st.session_state["user_id"] = user["id"]
            st.rerun()

        if google_configured:
            st.markdown('<div class="login-divider">or</div>', unsafe_allow_html=True)
            _google_button()

    render_footer()
    return False
