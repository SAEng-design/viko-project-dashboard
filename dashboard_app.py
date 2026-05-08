"""
ViKO Project Library / Dashboard

A central Streamlit app that lists every project saved by the design tools
and lets engineers drill down to members, calculation revisions, and full
input/result payloads.

Read-only with the exception of soft-deleting empty members/projects (deferred
for a future revision).

Run with:
    streamlit run dashboard_app.py
"""

from __future__ import annotations

import json
from datetime import datetime

import pandas as pd
import streamlit as st

from viko_shared import (
    init_db,
    APP_URLS,
    list_projects_with_summary,
    get_project,
    get_project_dashboard,
    get_member,
    list_calculations,
    load_calculation,
    at_risk_calcs,
)

# ---------------------------------------------------------------------------
# Page setup
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="ViKO Project Library",
    page_icon="📚",
    layout="wide",
)

init_db()  # safe if it's already there


# ---------------------------------------------------------------------------
# Cached data accessors (short TTL so saves show up promptly)
# ---------------------------------------------------------------------------

@st.cache_data(ttl=30)
def _cached_projects(include_archived: bool):
    return list_projects_with_summary(include_archived=include_archived)

@st.cache_data(ttl=30)
def _cached_dashboard(project_id: int):
    return get_project_dashboard(project_id)

@st.cache_data(ttl=30)
def _cached_at_risk(threshold: float):
    return at_risk_calcs(util_threshold=threshold)

@st.cache_data(ttl=30)
def _cached_calc_history(member_id: int):
    return list_calculations(member_id)


def refresh_caches():
    _cached_projects.clear()
    _cached_dashboard.clear()
    _cached_at_risk.clear()
    _cached_calc_history.clear()


# ---------------------------------------------------------------------------
# Navigation state
# ---------------------------------------------------------------------------
# view: "projects" | "project" | "member" | "calc"
# selected_project_id, selected_member_id, selected_calc_id

if "view" not in st.session_state:
    st.session_state.view = "projects"
for k in ("selected_project_id", "selected_member_id", "selected_calc_id"):
    if k not in st.session_state:
        st.session_state[k] = None


def go_projects():
    st.session_state.view = "projects"
    st.session_state.selected_project_id = None
    st.session_state.selected_member_id = None
    st.session_state.selected_calc_id = None

def go_project(pid: int):
    st.session_state.view = "project"
    st.session_state.selected_project_id = pid
    st.session_state.selected_member_id = None
    st.session_state.selected_calc_id = None

def go_member(mid: int):
    st.session_state.view = "member"
    st.session_state.selected_member_id = mid
    st.session_state.selected_calc_id = None

def go_calc(cid: int):
    st.session_state.view = "calc"
    st.session_state.selected_calc_id = cid


# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------

header_l, header_r = st.columns([4, 1])
with header_l:
    st.title("📚 ViKO Project Library")
    st.caption("Central register of every member designed using the ViKO design tools.")
with header_r:
    if st.button("🔄 Refresh", use_container_width=True, help="Force a reread of the database"):
        refresh_caches()
        st.rerun()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fmt_util(u):
    """Format utilisation value, with traffic-light emoji."""
    if u is None:
        return "—"
    if u < 0.85:
        icon = "🟢"
    elif u < 1.0:
        icon = "🟡"
    else:
        icon = "🔴"
    return f"{icon} {u:.2f}"


def _fmt_status(status: str | None) -> str:
    if not status:
        return "—"
    return {
        "pass": "✅ Pass",
        "fail": "❌ Fail",
        "warning": "⚠️ Warn",
        "info":  "ℹ️ Info",
    }.get(status, status)


def _fmt_dt(s: str | None) -> str:
    if not s:
        return "—"
    try:
        return datetime.fromisoformat(s).strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return s


def _app_link(app_name: str | None, label: str = "Open in app ↗") -> str | None:
    """Return the deployed URL for a given app_name, or None."""
    if not app_name:
        return None
    return APP_URLS.get(app_name)


# ---------------------------------------------------------------------------
# Breadcrumbs
# ---------------------------------------------------------------------------

def render_breadcrumbs():
    crumbs = []
    crumbs.append(("All Projects", "projects", None))

    if st.session_state.selected_project_id:
        proj = get_project(st.session_state.selected_project_id)
        if proj:
            crumbs.append((f"{proj['project_number']} — {proj['project_name']}",
                           "project", proj["project_id"]))

    if st.session_state.selected_member_id:
        mem = get_member(st.session_state.selected_member_id)
        if mem:
            crumbs.append((f"{mem['member_mark']} ({mem['member_type']})",
                           "member", mem["member_id"]))

    if st.session_state.selected_calc_id and st.session_state.view == "calc":
        crumbs.append((f"Calc #{st.session_state.selected_calc_id}",
                       "calc", st.session_state.selected_calc_id))

    cols = st.columns(len(crumbs) * 2 - 1) if len(crumbs) > 1 else [st.container()]
    for i, (label, view, _id) in enumerate(crumbs):
        col = cols[i * 2] if len(crumbs) > 1 else cols[0]
        with col:
            is_last = (i == len(crumbs) - 1)
            if is_last:
                st.markdown(f"**{label}**")
            else:
                if st.button(label, key=f"crumb_{i}_{view}", type="tertiary"):
                    if view == "projects":
                        go_projects()
                    elif view == "project":
                        go_project(_id)
                    elif view == "member":
                        go_member(_id)
                    st.rerun()
        if i < len(crumbs) - 1:
            cols[i * 2 + 1].markdown("›")


# ---------------------------------------------------------------------------
# View: All projects
# ---------------------------------------------------------------------------

def view_projects():
    render_breadcrumbs()
    st.divider()

    # At-risk panel
    at_risk = _cached_at_risk(0.95)
    if at_risk:
        with st.container(border=True):
            st.markdown(f"### ⚠️ Needs attention ({len(at_risk)})")
            st.caption("Current calculations with utilisation ≥ 0.95 or status = fail.")
            for r in at_risk[:10]:
                cA, cB, cC, cD, cE = st.columns([2, 2, 2, 1, 1])
                cA.markdown(f"**{r['project_number']}** — {r['project_name']}")
                cB.markdown(f"{r['member_mark']} · *{r.get('app_display_name') or r['member_type']}*")
                cC.markdown(_fmt_util(r["governing_utilisation"]))
                cD.markdown(_fmt_status(r["status"]))
                if cE.button("Open →", key=f"atrisk_{r['calc_id']}"):
                    go_member(r["member_id"])
                    st.rerun()
            if len(at_risk) > 10:
                st.caption(f"…and {len(at_risk) - 10} more.")
        st.write("")

    # Filters
    fc1, fc2, fc3 = st.columns([3, 1, 1])
    search = fc1.text_input("🔎 Search by project number or name", placeholder="e.g. 2026-014 or warehouse")
    include_archived = fc2.checkbox("Include archived", value=False)
    sort_choice = fc3.selectbox("Sort by", ["Newest", "Oldest", "Project number"])

    projects = _cached_projects(include_archived)

    if search:
        s = search.lower()
        projects = [p for p in projects
                    if s in (p["project_number"] or "").lower()
                    or s in (p["project_name"] or "").lower()]

    if sort_choice == "Newest":
        projects.sort(key=lambda p: p["created_at"] or "", reverse=True)
    elif sort_choice == "Oldest":
        projects.sort(key=lambda p: p["created_at"] or "")
    else:
        projects.sort(key=lambda p: p["project_number"] or "")

    st.markdown(f"### {len(projects)} project(s)")

    if not projects:
        st.info("No projects yet. Save a calculation in any design app to get started.")
        return

    # Render as a clickable list
    for p in projects:
        with st.container(border=True):
            cA, cB, cC, cD, cE = st.columns([3, 2, 1.2, 1.2, 1])
            cA.markdown(f"### {p['project_number']}")
            cA.caption(p["project_name"])
            if p.get("client"):
                cA.caption(f"Client: {p['client']}")

            cB.metric("Members", p["member_count"] or 0)
            cC.metric("Calcs", p["calc_count"] or 0)
            cD.markdown("**Worst util.**")
            cD.markdown(_fmt_util(p["max_utilisation"]))
            cE.write("")
            cE.write("")
            if cE.button("Open →", key=f"proj_open_{p['project_id']}", use_container_width=True):
                go_project(p["project_id"])
                st.rerun()

            footer_l, footer_r = st.columns([3, 1])
            footer_l.caption(
                f"Created {_fmt_dt(p['created_at'])} by {p['created_by']} · "
                f"Status: {p['status']}"
            )
            if (p["fail_count"] or 0) > 0:
                footer_r.markdown(f"❌ **{p['fail_count']} failing calc(s)**")


# ---------------------------------------------------------------------------
# View: One project
# ---------------------------------------------------------------------------

def view_project():
    pid = st.session_state.selected_project_id
    proj = get_project(pid)
    if not proj:
        st.error("Project not found.")
        if st.button("← Back to all projects"):
            go_projects()
            st.rerun()
        return

    render_breadcrumbs()
    st.divider()

    # Project header
    h1, h2, h3 = st.columns([3, 1, 1])
    h1.markdown(f"## {proj['project_number']} — {proj['project_name']}")
    if proj.get("client"):
        h1.caption(f"Client: {proj['client']}")
    h1.caption(f"Created {_fmt_dt(proj['created_at'])} by {proj['created_by']} · "
               f"Status: {proj['status']}")
    if proj.get("notes"):
        h1.markdown(f"> {proj['notes']}")

    members = _cached_dashboard(pid)
    h2.metric("Members", len(members))
    designed_calc_count = sum(1 for m in members if m.get("calc_id"))
    h3.metric("With calcs", designed_calc_count)

    st.write("")

    if not members:
        st.info("No members under this project yet.")
        return

    # Member table — built as a dataframe for sorting/searching, plus a
    # stack of clickable rows beneath for navigation.
    table_rows = []
    for m in members:
        s = m.get("summary") or {}
        table_rows.append({
            "Mark":         m["member_mark"],
            "Type":         m.get("app_display_name") or m["member_type"],
            "Section":      s.get("section") or s.get("designation") or "—",
            "Capacity":     _capacity_str(s),
            "Applied":      _applied_str(s),
            "Util.":        m["governing_utilisation"],
            "Status":       _fmt_status(m.get("status")),
            "Last updated": _fmt_dt(m.get("calc_created_at")),
            "By":           m.get("calc_created_by") or "—",
        })

    df = pd.DataFrame(table_rows)
    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Util.": st.column_config.ProgressColumn(
                "Util.",
                min_value=0.0,
                max_value=1.2,
                format="%.2f",
            ),
        },
    )

    st.markdown("#### Open a member")
    st.caption("Click any member to view its calculation history.")

    for m in members:
        cA, cB, cC, cD, cE = st.columns([1, 2, 2, 1, 1])
        cA.markdown(f"**{m['member_mark']}**")
        cB.markdown(m.get("app_display_name") or m["member_type"])
        cC.markdown(f"{(m.get('summary') or {}).get('section', '')}")
        cD.markdown(_fmt_util(m.get("governing_utilisation")))
        if cE.button("Open →", key=f"mem_open_{m['member_id']}", use_container_width=True):
            go_member(m["member_id"])
            st.rerun()


def _capacity_str(s: dict) -> str:
    """Pull the capacity number out of whatever the app called it."""
    for key in ("Tr_kN", "Cr_kN", "Mr_kNm", "Vr_kN"):
        if s.get(key) is not None:
            unit = "kNm" if key.endswith("_kNm") else "kN"
            return f"{s[key]} {unit}"
    return "—"


def _applied_str(s: dict) -> str:
    for key in ("Tf_kN", "Cf_kN", "Mf_kNm", "Vf_kN"):
        if s.get(key) is not None:
            unit = "kNm" if key.endswith("_kNm") else "kN"
            return f"{s[key]} {unit}"
    return "—"


# ---------------------------------------------------------------------------
# View: One member
# ---------------------------------------------------------------------------

def view_member():
    mid = st.session_state.selected_member_id
    mem = get_member(mid)
    if not mem:
        st.error("Member not found.")
        if st.button("← Back"):
            go_projects()
            st.rerun()
        return

    render_breadcrumbs()
    st.divider()

    h1, h2 = st.columns([3, 1])
    h1.markdown(f"## {mem['member_mark']}")
    h1.caption(f"Project {mem['project_number']} — {mem['project_name']}")
    h1.markdown(f"**Type:** `{mem['member_type']}`")
    if mem.get("description"):
        h1.markdown(f"*{mem['description']}*")

    url = _app_link(mem["member_type"])
    if url:
        h2.link_button("↗ Open source app", url, use_container_width=True)

    st.write("")
    st.markdown("### Calculation history")

    calcs = _cached_calc_history(mid)
    if not calcs:
        st.info("This member has no saved calculations.")
        return

    for c in calcs:
        is_current = c["is_current"] == 1
        border_label = "🟢 CURRENT" if is_current else "📜 history"
        with st.container(border=True):
            cA, cB, cC, cD, cE = st.columns([1, 3, 1.5, 1.5, 1])
            cA.markdown(f"**#{c['calc_id']}**")
            cA.caption(border_label)
            cB.markdown(f"**{c['calc_label'] or '(no label)'}**")
            cB.caption(f"v{c['app_version']} · "
                       f"{_fmt_dt(c['created_at'])} · {c['created_by']}")
            cC.markdown(_fmt_util(c["governing_utilisation"]))
            cD.markdown(_fmt_status(c["status"]))
            if cE.button("View →", key=f"calc_open_{c['calc_id']}",
                         use_container_width=True):
                go_calc(c["calc_id"])
                st.rerun()


# ---------------------------------------------------------------------------
# View: One calculation
# ---------------------------------------------------------------------------

def view_calc():
    cid = st.session_state.selected_calc_id
    try:
        calc = load_calculation(cid)
    except ValueError:
        st.error("Calculation not found.")
        if st.button("← Back"):
            go_projects()
            st.rerun()
        return

    render_breadcrumbs()
    st.divider()

    st.markdown(f"## Calculation #{cid}")
    st.caption(
        f"{calc['project_number']} — {calc['project_name']} · "
        f"Member **{calc['member_mark']}** ({calc['member_type']})"
    )

    h1, h2, h3, h4 = st.columns(4)
    h1.metric("Status", _fmt_status(calc["status"]))
    h2.metric("Utilisation",
              f"{calc['governing_utilisation']:.3f}" if calc["governing_utilisation"] is not None else "—")
    h3.metric("App version", calc["app_version"])
    h4.metric("Saved", _fmt_dt(calc["created_at"]))

    if calc.get("calc_label"):
        st.markdown(f"**Label:** {calc['calc_label']}")
    st.caption(f"Saved by {calc['created_by']}")

    url = _app_link(calc["app_name"])
    if url:
        st.link_button(f"↗ Open in {calc['app_name']}", url)

    st.write("")
    tab_summary, tab_inputs, tab_results = st.tabs(["Summary", "Inputs", "Results"])

    with tab_summary:
        if calc["summary"]:
            st.json(calc["summary"])
        else:
            st.info("No summary stored.")

    with tab_inputs:
        st.json(calc["inputs"])

    with tab_results:
        st.json(calc["results"])


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

view = st.session_state.view
if view == "projects":
    view_projects()
elif view == "project":
    view_project()
elif view == "member":
    view_member()
elif view == "calc":
    view_calc()
else:
    st.error(f"Unknown view: {view}")
    if st.button("Reset"):
        go_projects()
        st.rerun()