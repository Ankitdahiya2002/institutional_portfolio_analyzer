import os
import requests
import streamlit as st
from datetime import datetime

class SupabaseAuth:
    """Handles Supabase Auth (Sign up, Sign in, Session management)"""
    def __init__(self):
        self.url = os.getenv("SUPABASE_URL", "").rstrip("/")
        self.key = os.getenv("SUPABASE_KEY", "")
        self._ok = bool(self.url and self.key)

    @property
    def _headers(self):
        return {
            "apikey": self.key,
            "Content-Type": "application/json"
        }

    def sign_up(self, email, password):
        if not self._ok: return {"error": "Database not configured. Check .env"}
        try:
            # redirect_to must match an allowed URL in Supabase Auth → URL Configuration
            redirect_url = os.getenv("APP_URL", "http://localhost:8502")
            r = requests.post(
                f"{self.url}/auth/v1/signup",
                headers=self._headers,
                json={
                    "email": email,
                    "password": password,
                    "options": {"emailRedirectTo": redirect_url}
                }
            )
            data = r.json()
            if r.status_code == 200:
                # If email confirmation is disabled, user object comes back immediately
                if data.get("user") and data["user"].get("confirmed_at"):
                    return {"user": data["user"], "confirmed": True}
                return {"pending": True, "message": "Check your inbox and click the confirmation link."}
            return {"error": data.get("msg", data.get("error_description", "Signup failed"))}
        except Exception as e:
            return {"error": str(e)}

    def sign_in(self, email, password):
        if not self._ok: return {"error": "Database not configured. Check .env"}
        try:
            r = requests.post(
                f"{self.url}/auth/v1/token?grant_type=password",
                headers=self._headers,
                json={"email": email, "password": password}
            )
            res = r.json()
            if r.status_code == 200:
                return {"user": res.get("user"), "access_token": res.get("access_token")}
            return {"error": res.get("error_description", "Login failed")}
        except Exception as e:
            return {"error": str(e)}

def render_auth_ui():
    """Renders the Login/Signup form in the Streamlit Sidebar"""
    if "user" not in st.session_state:
        st.session_state.user = None

    if st.session_state.user:
        with st.sidebar:
            st.markdown(f"### 👤 Welcome, {st.session_state.user.get('email')}")
            if st.button("🚪 Logout", use_container_width=True):
                if "current_session_id" in st.session_state:
                    from services.database import SupabaseService
                    db = SupabaseService()
                    db.track_logout(st.session_state.current_session_id, st.session_state.user["id"])
                
                st.session_state.user = None
                if "current_session_id" in st.session_state:
                    del st.session_state.current_session_id
                st.rerun()
        return True

    auth = SupabaseAuth()
    
    st.markdown("""
    <style>
    /* Full page background */
    [data-testid="stAppViewContainer"] {
        background-color: #fdfbf7 !important;
    }
    
    /* Center column styling */
    div[data-testid="column"] {
        background: #ffffff;
        padding: 40px;
        border-radius: 20px;
        box-shadow: 0 10px 40px -10px rgba(0,0,0,0.08);
        border: 1px solid #f1f5f9;
        margin-top: 40px;
    }

    /* Titles */
    .login-title {
        font-family: 'Inter', sans-serif;
        font-size: 32px;
        font-weight: 800;
        color: #0f172a;
        text-align: center;
        margin-bottom: 8px;
    }
    .login-sub {
        font-family: 'Inter', sans-serif;
        font-size: 15px;
        color: #64748b;
        text-align: center;
        margin-bottom: 32px;
    }

    /* Input Labels */
    .stTextInput label p {
        color: #475569 !important;
        font-weight: 600 !important;
        font-size: 13px !important;
    }
    
    /* Input Fields */
    .stTextInput input {
        background-color: #ffffff !important;
        border: 1px solid #cbd5e1 !important;
        border-radius: 12px !important;
        padding: 12px 16px !important;
        color: #1e293b !important;
        font-size: 14px !important;
    }
    .stTextInput input:focus {
        border-color: #3b82f6 !important;
        box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.2) !important;
    }
    
    /* Primary Button */
    .stButton button[kind="primary"] {
        background-color: #1d4ed8 !important;
        color: white !important;
        border-radius: 12px !important;
        padding: 12px !important;
        font-weight: 600 !important;
        font-size: 15px !important;
        width: 100% !important;
        border: none !important;
        margin-top: 10px !important;
    }
    .stButton button[kind="primary"]:hover {
        background-color: #1e40af !important;
    }
    
    /* Hide sidebar when logged out */
    [data-testid="stSidebar"] {
        display: none !important;
    }
    
    /* Fix Tab Colors */
    button[data-baseweb="tab"] p {
        color: #64748b !important;
        font-weight: 600 !important;
    }
    button[data-baseweb="tab"][aria-selected="true"] p {
        color: #1d4ed8 !important;
    }
    
    /* Action Link (tertiary button) */
    .stButton button[kind="tertiary"] {
        color: #1d4ed8 !important;
        font-weight: 700 !important;
        padding: 0 !important;
        background: transparent !important;
        border: none !important;
    }
    .stButton button[kind="tertiary"]:hover {
        text-decoration: underline !important;
    }
    
    .link-text {
        text-align: center;
        margin-top: 20px;
        font-size: 14px;
        color: #64748b;
    }
    </style>
    """, unsafe_allow_html=True)
    
    if "auth_mode" not in st.session_state:
        st.session_state.auth_mode = "login"
        
    auth_container = st.container()
    with auth_container:
        _, col2, _ = st.columns([1, 1.2, 1])
        
        with col2:
            if st.session_state.auth_mode == "login":
                st.markdown("<div class='login-title'>Welcome back</div>", unsafe_allow_html=True)
                st.markdown("<div class='login-sub'>Enter your credentials to access your dashboard</div>", unsafe_allow_html=True)
                
                t1, t2 = st.tabs(["User", "Admin"])
                with t1:
                    st.write("") # spacing
                    l_email = st.text_input("Username or Email", placeholder="name@company.com", key="l_email")
                    l_pass = st.text_input("Password", type="password", placeholder="••••••••", key="l_pass")
                    
                    if st.button("Continue", use_container_width=True, type="primary"):
                        res = auth.sign_in(l_email, l_pass)
                        if "error" in res:
                            st.error(res["error"])
                        else:
                            st.session_state.user = res["user"]
                            st.rerun()
                    
                    st.markdown("<div class='link-text'>Don't have an account?</div>", unsafe_allow_html=True)
                    if st.button("Create Account", type="tertiary", use_container_width=True, key="to_signup"):
                        st.session_state.auth_mode = "signup"
                        st.rerun()
                            
                with t2:
                    st.info("Admin login is restricted to corporate network only.")
                    
            else:
                st.markdown("<div class='login-title'>Create Account</div>", unsafe_allow_html=True)
                st.markdown("<div class='login-sub'>Join the secure portal network.</div>", unsafe_allow_html=True)
                
                st.write("")
                s_name = st.text_input("Full Name", placeholder="John Doe", key="s_name")
                s_email = st.text_input("Email Address", placeholder="name@company.com", key="s_email")
                
                c_dob, c_gen = st.columns(2)
                with c_dob:
                    s_dob = st.date_input("Date of Birth", key="s_dob")
                with c_gen:
                    s_gen = st.selectbox("Gender", ["-- Select --", "Male", "Female", "Other", "Prefer not to say"], key="s_gen")
                    
                s_pass = st.text_input("Password", type="password", placeholder="••••••••", key="s_pass")
                s_conf = st.text_input("Confirm Password", type="password", placeholder="••••••••", key="s_conf")
                
                if st.button("Create Account", use_container_width=True, type="primary", key="do_signup"):
                    if s_pass != s_conf:
                        st.error("Passwords do not match!")
                    elif len(s_pass) < 6:
                        st.error("Password must be at least 6 characters.")
                    else:
                        res = auth.sign_up(s_email, s_pass)
                        if "error" in res:
                            st.error(res["error"])
                        else:
                            st.success("Verification email sent! Please check your inbox.")
                            
                st.markdown("<div class='link-text'>Already have an account?</div>", unsafe_allow_html=True)
                if st.button("Sign In", type="tertiary", use_container_width=True, key="to_login"):
                    st.session_state.auth_mode = "login"
                    st.rerun()
                
    return False
