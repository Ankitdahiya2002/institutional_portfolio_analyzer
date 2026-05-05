import streamlit as st

def apply_custom_css():
    st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800;900&display=swap');
*{font-family:'Inter',sans-serif!important;}
html,body,[data-testid="stAppViewContainer"]{background:var(--background-color)!important;}
[data-testid="stSidebar"]{background:var(--secondary-background-color)!important;border-right:1px solid rgba(150,150,150,0.1);}
.block-container{padding:2rem 2.5rem!important; padding-top: 4rem !important;}
.kc{background:var(--secondary-background-color);border:1px solid rgba(150,150,150,0.2);border-radius:12px;padding:20px 22px;margin-bottom:4px;}
.kl{color:#4b5563;font-size:10px;font-weight:700;letter-spacing:.15em;text-transform:uppercase;margin-bottom:6px;}
.kv{color:var(--text-color);font-size:28px;font-weight:800;}
.ks{font-size:12px;font-weight:600;margin-top:4px;}
.sec{color:#6b7280;font-size:10px;font-weight:800;letter-spacing:.2em;text-transform:uppercase;margin:20px 0 10px;}
.err{background:#160a0a;border:1px solid #7f1d1d;border-radius:12px;padding:24px 28px;margin:16px 0;}
.hdr{color:#fca5a5;font-size:10px;font-weight:800;letter-spacing:.18em;text-transform:uppercase;margin-bottom:8px;}
.etitle{color:var(--text-color);font-size:18px;font-weight:800;margin-bottom:10px;}
.ecause{color:#fca5a5;font-size:13px;line-height:1.6;}
.raw{background:#0c0202;border:1px solid #450a0a;border-radius:8px;padding:10px 14px;font-family:monospace;font-size:11px;color:#ef4444;white-space:pre-wrap;margin-top:10px;}
.hint{color:#6b7280;font-size:11px;margin-top:8px;}
.ai-box{background:#0d1a0d;border:1px solid #14532d;border-radius:12px;padding:24px;color:#86efac;line-height:1.8;font-size:14px;}
.vbox{background:#0a1628;border-left:3px solid #3b82f6;border-radius:0 8px 8px 0;padding:12px 18px;margin-bottom:8px;color:#93c5fd;font-size:13px;}
.rbox{background:#1a1205;border-left:3px solid #f59e0b;border-radius:0 8px 8px 0;padding:12px 18px;margin-bottom:16px;color:#fbbf24;font-size:13px;}
.sig{background:var(--secondary-background-color);border:1px solid rgba(150,150,150,0.2);border-radius:12px;padding:24px 28px;margin-bottom:14px;}
/* Hide the annoying Streamlit 'Running' status widget */
[data-testid="stStatusWidget"] { visibility: hidden; display: none; }

/* Light mode is now handled dynamically via the sidebar toggle below */
@keyframes pulse-live {
  0% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.4; transform: scale(0.96); }
  100% { opacity: 1; transform: scale(1); }
}
.live-badge {
  background: #064e3b; /* Default Dark Mode */
  color: #34d399;
  font-size: 8px;
  font-weight: 900;
  padding: 1px 6px;
  border-radius: 4px;
  border: 1px solid #05966933;
  animation: pulse-live 1.5s infinite;
  display: inline-block;
  letter-spacing: 0.05em;
}

/* Homepage and Utility Classes */
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.6}}
@keyframes slideUp{from{opacity:0;transform:translateY(30px)}to{opacity:1;transform:translateY(0)}}
@keyframes glow{0%,100%{text-shadow:0 0 20px #3b82f660}50%{text-shadow:0 0 40px #3b82f6aa,0 0 80px #6366f155}}
@keyframes ticker{0%{transform:translateX(0)}100%{transform:translateX(-50%)}}
.hero-title{font-size:clamp(36px,5vw,72px);font-weight:900;background:linear-gradient(135deg,#fff 30%,#3b82f6 70%,#8b5cf6 100%);-webkit-background-clip:text;-webkit-text-fill-color:transparent;animation:slideUp .8s ease,glow 3s ease infinite;line-height:1.1;margin-bottom:16px;}
.hero-sub{color:#9ca3af;font-size:18px;line-height:1.7;margin-bottom:32px;animation:slideUp 1s ease;}
.feat-card{background:linear-gradient(135deg,#0f1117,#0d1526);border:1px solid #1e2030;border-radius:16px;padding:24px;transition:all .3s;cursor:default;height:100%;}
.feat-card:hover{border-color:#3b82f6;box-shadow:0 0 30px #3b82f620;transform:translateY(-4px);}
.feat-icon{font-size:32px;margin-bottom:12px;transition:transform 0.3s;}
.feat-card:hover .feat-icon{transform:scale(1.1) rotate(5deg);}
.feat-title{color:#fff;font-size:16px;font-weight:800;margin-bottom:8px;transition:color 0.3s;}
.feat-desc{color:#6b7280;font-size:13px;line-height:1.6;transition:color 0.3s;}
.feat-card:hover .feat-title{color:#93c5fd!important;}
.feat-card:hover .feat-desc{color:#d1d5db!important;}
.broker-chip{background:#0f1117;border:1px solid #1e2030;border-radius:8px;padding:8px 16px;color:#9ca3af;font-size:12px;font-weight:700;text-align:center;transition:all .2s;}
.broker-chip:hover{border-color:#3b82f6;color:#60a5fa;box-shadow:0 0 15px #3b82f630;}
.step-num{width:36px;height:36px;background:linear-gradient(135deg,#1d4ed8,#7c3aed);border-radius:50%;display:flex;align-items:center;justify-content:center;color:#fff;font-weight:900;font-size:14px;margin-bottom:12px;}
.stat-box{background:linear-gradient(135deg,#0d1526,#0f1117);border:1px solid #1e3a5f;border-radius:12px;padding:20px;text-align:center;}
.stat-num{font-size:32px;font-weight:900;background:linear-gradient(135deg,#60a5fa,#a78bfa);-webkit-background-clip:text;-webkit-text-fill-color:transparent;}
.stat-lbl{color:#6b7280;font-size:11px;font-weight:700;letter-spacing:.15em;text-transform:uppercase;margin-top:4px;}
.ticker-wrap{overflow:hidden;background:#090b12;border:1px solid #1e2030;border-radius:10px;padding:10px 0;margin-bottom:28px;}
.ticker-inner{display:flex;gap:48px;animation:ticker 30s linear infinite;white-space:nowrap;width:max-content;}
.tick-item{font-size:12px;font-weight:700;color:#9ca3af;display:flex;gap:10px;align-items:center;}
.tick-up{color:#10b981;}.tick-dn{color:#f43f5e;}
.upload-cta{background:linear-gradient(135deg,#1d4ed820,#7c3aed20);border:2px dashed #3b82f6;border-radius:16px;padding:32px;text-align:center;margin-top:20px;}

/* Completely hide all native Streamlit icons (upload, info, etc) from the file uploader */
[data-testid="stFileUploader"] [data-testid="stIconMaterial"],
[data-testid="stFileUploaderDropzone"] [data-testid="stIconMaterial"],
[data-testid="stFileUploaderDropzone"] button,
[data-testid="stFileUploaderDropzoneInstructions"],
[data-testid="stWidgetLabel"] [data-testid="stTooltipIcon"] { display: none !important; }

/* Completely hide top-right Streamlit menu and Deploy button */
[data-testid="stToolbarActions"],
[data-testid="stAppDeployButton"],
[data-testid="stMainMenu"],
[data-testid="stStatusWidget"],
[data-testid="stElementToolbar"] {
    display: none !important;
}
/* Aggressively hide the technical 'Running...' overlay for fragments */
div[data-testid="stStatusWidget"], .stStatusWidget, div[class*="stFragmentStatus"] {
    display: none !important;
    visibility: hidden !important;
}
</style>""", unsafe_allow_html=True)
