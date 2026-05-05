import streamlit as st

def kpi(label, value, sub="", color="#10b981"):
    st.markdown(f'''
    <div class="kc">
        <div class="kl">{label}</div>
        <div class="kv">{value}</div>
        <div class="ks" style="color:{color}">{sub}</div>
    </div>
    ''', unsafe_allow_html=True)

def fmt(v, p="", s=""):
    return f"{p}{v:,.2f}{s}" if isinstance(v, (int, float)) else str(v)

def show_err(title, cause, raw="", hint=""):
    html = f'''
    <div class="err">
        <div class="hdr">🚨 Error</div>
        <div class="etitle">{title}</div>
        <div class="ecause">{cause}</div>
    '''
    if raw: html += f'<div class="raw">{raw}</div>'
    if hint: html += f'<div class="hint">💡 <b>Hint:</b> {hint}</div>'
    html += '</div>'
    st.markdown(html, unsafe_allow_html=True)
