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
    # 1. explicit env var
    v = os.environ.get("GOOGLE_REDIRECT_URI", "")
    if not v and hasattr(st, "secrets") and "GOOGLE_REDIRECT_URI" in st.secrets:
        v = st.secrets["GOOGLE_REDIRECT_URI"]
    if v:
        return v

    # 2. derive from forwarded headers (Streamlit Cloud sits behind a proxy)
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

    # 3. last resort: parse the page URL
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
        if not resp.ok:
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
    params = st.query_params
    code = params.get("code")

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


def render_login_wall() -> bool:
    if st.session_state.get("user_id") is not None:
        return True

    # handle Google OAuth callback before rendering UI
    if _handle_oauth_callback():
        st.rerun()

    st.title("💪 Baireps - AI fitness coach")
    st.markdown("### Welcome! Please log in or create an account.")

    google_configured = bool(_google_client_id() and _google_client_secret())

    if google_configured:
        st.markdown("")
        st.link_button("Continue with Google", url=_build_google_auth_url(), use_container_width=True, type="primary")
        st.markdown("---")
        st.markdown("<p style='text-align:center;color:#888;margin:-8px 0 8px'>or sign in with username & password</p>", unsafe_allow_html=True)

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

    return False
