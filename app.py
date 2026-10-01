import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from sqlalchemy import create_engine, text
from datetime import datetime
import io

# Page configuration
st.set_page_config(
    page_title="NWF Metrics",
    page_icon="🌲",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for better styling
st.markdown("""
<style>
    .main > div {
        padding-top: 2rem;
    }
    .stMetric {
        background-color: #f0f2f6;
        padding: 10px;
        border-radius: 5px;
    }
    h1 {
        color: #2C5F2D;
    }
    h2 {
        color: #2C5F2D;
    }
    .stButton>button {
        background-color: #2C5F2D;
        color: white;
    }
</style>
""", unsafe_allow_html=True)

# Database connection with better error handling
@st.cache_resource
def get_database_connection():
    """Create database connection using Streamlit secrets"""
    try:
        db_password = st.secrets["database"]["password"]
        db_host = st.secrets["database"]["host"]
        db_name = st.secrets["database"]["name"]
        db_user = st.secrets["database"]["user"]
        db_port = st.secrets["database"]["port"]
        
        connection_string = f"postgresql+psycopg2://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
        engine = create_engine(
            connection_string,
            pool_pre_ping=True,  # Test connections before using them
            pool_recycle=3600,   # Recycle connections after 1 hour
            echo=False            # Set to True to see SQL queries in console
        )
        
        # Test the connection
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        
        return engine
    except KeyError as e:
        st.error(f"Database configuration missing: {str(e)}")
        st.stop()
    except Exception as e:
        st.error(f"Database connection failed: {str(e)}")
        st.error("Please check your database credentials in .streamlit/secrets.toml")
        st.stop()

# Initialize database tables with error handling
def init_database():
    """Create tables if they don't exist"""
    engine = get_database_connection()
    if engine is None:
        return
    
    try:
        with engine.connect() as conn:
            # Projects table
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS projects (
                    project_id SERIAL PRIMARY KEY,
                    project_name TEXT NOT NULL,
                    state_affiliate TEXT NOT NULL,
                    grant_number TEXT,
                    start_date DATE,
                    end_date DATE,
                    project_status TEXT,
                    grant_amount NUMERIC,
                    match_contributions NUMERIC,
                    created_date DATE,
                    notes TEXT
                )
            """))
            
            # Reporting periods table
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS reporting_periods (
                    period_id SERIAL PRIMARY KEY,
                    project_id INTEGER REFERENCES projects(project_id) ON DELETE CASCADE,
                    reporting_year INTEGER,
                    report_date DATE,
                    amount_spent NUMERIC,
                    created_date DATE
                )
            """))
            
            # Metrics table
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS metrics (
                    metric_id SERIAL PRIMARY KEY,
                    period_id INTEGER REFERENCES reporting_periods(period_id) ON DELETE CASCADE,
                    metric_name TEXT NOT NULL,
                    metric_value NUMERIC,
                    metric_unit TEXT,
                    notes TEXT
                )
            """))
            
            conn.commit()
            
    except Exception as e:
        st.error(f"Database initialization failed: {str(e)}")
        st.stop()


# Sidebar navigation
st.sidebar.title("🌲 NWF Metrics")
page = st.sidebar.radio(
    "Navigation",
    ["Dashboard", "Projects", "Enter Metrics", "View Data", "Reports", "Help"]
)

# ============================================================================
# DASHBOARD PAGE
# ============================================================================
if page == "Dashboard":
    st.title("📊 Dashboard")
    
    engine = get_database_connection()
    if engine:
        # Get summary statistics
        with engine.connect() as conn:
            total_projects = pd.read_sql(text("SELECT COUNT(*) as count FROM projects"), conn).iloc[0]['count']
            active_projects = pd.read_sql(text("SELECT COUNT(*) as count FROM projects WHERE project_status = 'Active'"), conn).iloc[0]['count']
            total_funding = pd.read_sql(text("SELECT SUM(grant_amount) as total FROM projects"), conn).iloc[0]['total']
            if pd.isna(total_funding):
                total_funding = 0
        
        # Display metrics
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Total Projects", int(total_projects))
        with col2:
            st.metric("Active Projects", int(active_projects))
        with col3:
            st.metric("Total Funding", f"${total_funding:,.0f}")
        
        # Charts
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("Projects by State Affiliate")
            with engine.connect() as conn:
                state_data = pd.read_sql(text("""
                    SELECT state_affiliate, COUNT(*) as count
                    FROM projects
                    GROUP BY state_affiliate
                    ORDER BY count DESC
                """), conn)
            
            if not state_data.empty:
                fig = px.bar(state_data, x='count', y='state_affiliate', 
                            orientation='h',
                            labels={'count': 'Number of Projects', 'state_affiliate': 'State'},
                            color_discrete_sequence=['#2C5F2D'])
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("No projects yet")
        
        with col2:
            st.subheader("Project Status Overview")
            with engine.connect() as conn:
                status_data = pd.read_sql(text("""
                    SELECT project_status, COUNT(*) as count
                    FROM projects
                    GROUP BY project_status
                """), conn)
            
            if not status_data.empty:
                fig = px.pie(status_data, values='count', names='project_status',
                            color_discrete_map={'Planning': '#FDB462', 'Active': '#97BC62', 'Completed': '#2C5F2D'})
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("No projects yet")
        
        # Recent activity
        st.subheader("Recent Activity")
        with engine.connect() as conn:
            recent_activity = pd.read_sql(text("""
                SELECT 
                    p.project_name,
                    p.state_affiliate,
                    rp.reporting_year,
                    rp.report_date,
                    COUNT(m.metric_id) as metrics_count
                FROM reporting_periods rp
                JOIN projects p ON rp.project_id = p.project_id
                LEFT JOIN metrics m ON rp.period_id = m.period_id
                GROUP BY rp.period_id, p.project_name, p.state_affiliate, rp.reporting_year, rp.report_date
                ORDER BY rp.created_date DESC
                LIMIT 10
            """), conn)
        
        if not recent_activity.empty:
            st.dataframe(recent_activity, use_container_width=True)
        else:
            st.info("No activity yet")

# ============================================================================
# PROJECTS PAGE
# ============================================================================
elif page == "Projects":
    st.title("📁 Projects")
    
    tab1, tab2, tab3 = st.tabs(["Add New Project", "View Projects", "Manage Projects"])
    
    with tab1:
        st.subheader("Add New Project")
        
        with st.form("add_project_form", clear_on_submit=True):
            col1, col2 = st.columns(2)
            
            with col1:
                proj_name = st.text_input("Project Name*")
                proj_state = st.selectbox("State Affiliate*", 
                    ["", "NCWF", "GWF", "AWF", "FWF", "SCWF", "TNWF"])
                proj_grant = st.text_input("Grant Number")
                proj_start = st.date_input("Start Date")
                proj_end = st.date_input("End Date")
            
            with col2:
                proj_status = st.selectbox("Project Status", 
                    ["Planning", "Active", "Completed"])
                proj_grant_amt = st.number_input("Grant Amount ($)", min_value=0.0, step=1000.0)
                proj_match = st.number_input("Match Contributions ($)", min_value=0.0, step=1000.0)
            
            proj_notes = st.text_area("Notes")
            
            submitted = st.form_submit_button("Save Project", type="primary")
            
            if submitted:
                if not proj_name or not proj_state:
                    st.error("⚠️ Please fill in required fields: Project Name and State Affiliate")
                else:
                    engine = get_database_connection()
                    if engine:
                        try:
                            with engine.begin() as conn:
                                conn.execute(text("""
                                    INSERT INTO projects 
                                    (project_name, state_affiliate, grant_number, start_date, 
                                     end_date, project_status, grant_amount, match_contributions, 
                                     created_date, notes)
                                    VALUES (:name, :state, :grant, :start, :end, :status, :amount, :match, :created, :notes)
                                """), {
                                    'name': proj_name,
                                    'state': proj_state,
                                    'grant': proj_grant if proj_grant else None,
                                    'start': proj_start,
                                    'end': proj_end,
                                    'status': proj_status,
                                    'amount': proj_grant_amt,
                                    'match': proj_match,
                                    'created': datetime.now().date(),
                                    'notes': proj_notes if proj_notes else None
                                })
                            st.success("✅ Project saved successfully!")
                            st.balloons()
                            import time
                            time.sleep(1)
                            st.rerun()
                        except Exception as e:
                            st.error(f"❌ Error saving project: {str(e)}")
                            with st.expander("🔍 Show detailed error"):
                                import traceback
                                st.code(traceback.format_exc())
    
    with tab2:
        st.subheader("Existing Projects")
        
        engine = get_database_connection()
        if engine:
            try:
                with engine.connect() as conn:
                    projects = pd.read_sql(text("""
                        SELECT 
                            project_id,
                            project_name,
                            state_affiliate,
                            grant_number,
                            start_date,
                            end_date,
                            project_status,
                            grant_amount,
                            match_contributions
                        FROM projects
                        ORDER BY created_date DESC
                    """), conn)
                
                if not projects.empty:
                    # Format currency columns
                    display_projects = projects.copy()
                    display_projects['grant_amount'] = display_projects['grant_amount'].apply(
                        lambda x: f"${x:,.0f}" if pd.notna(x) else "$0"
                    )
                    display_projects['match_contributions'] = display_projects['match_contributions'].apply(
                        lambda x: f"${x:,.0f}" if pd.notna(x) else "$0"
                    )
                    
                    # Hide project_id from display
                    display_df = display_projects.drop('project_id', axis=1)
                    
                    st.dataframe(display_df, use_container_width=True, hide_index=True)
                    
                    # Download button
                    csv = display_df.to_csv(index=False)
                    st.download_button(
                        label="📥 Download Projects as CSV",
                        data=csv,
                        file_name=f"nwf_projects_{datetime.now().strftime('%Y%m%d')}.csv",
                        mime="text/csv"
                    )
                else:
                    st.info("📭 No projects yet. Add one in the 'Add New Project' tab!")
                    
            except Exception as e:
                st.error(f"❌ Error loading projects: {str(e)}")
                with st.expander("🔍 Show detailed error"):
                    import traceback
                    st.code(traceback.format_exc())
    
    with tab3:
        st.subheader("🗑️ Manage & Delete Projects")
        st.warning("⚠️ **Warning:** Deleting a project will permanently delete all associated reporting periods and metrics!")
        
        engine = get_database_connection()
        if engine:
            try:
                with engine.connect() as conn:
                    projects = pd.read_sql(text("""
                        SELECT 
                            p.project_id,
                            p.project_name,
                            p.state_affiliate,
                            p.project_status,
                            COUNT(DISTINCT rp.period_id) as reporting_periods,
                            COUNT(m.metric_id) as total_metrics
                        FROM projects p
                        LEFT JOIN reporting_periods rp ON p.project_id = rp.project_id
                        LEFT JOIN metrics m ON rp.period_id = m.period_id
                        GROUP BY p.project_id, p.project_name, p.state_affiliate, p.project_status
                        ORDER BY p.project_name
                    """), conn)
                
                if not projects.empty:
                    for idx, project in projects.iterrows():
                        with st.expander(f"📁 {project['project_name']} ({project['state_affiliate']})"):
                            col1, col2, col3 = st.columns(3)
                            
                            with col1:
                                st.write(f"**Status:** {project['project_status']}")
                            with col2:
                                st.write(f"**Reporting Periods:** {project['reporting_periods']}")
                            with col3:
                                st.write(f"**Total Metrics:** {project['total_metrics']}")
                            
                            st.divider()
                            
                            # Confirmation checkbox
                            confirm_delete = st.checkbox(
                                f"I understand this will delete all data for '{project['project_name']}'",
                                key=f"confirm_delete_{project['project_id']}"
                            )
                            
                            col_delete, col_spacer = st.columns([1, 3])
                            
                            with col_delete:
                                if st.button(
                                    "🗑️ Delete Project",
                                    key=f"delete_project_{project['project_id']}",
                                    type="primary",
                                    disabled=not confirm_delete
                                ):
                                    try:
                                        with engine.begin() as conn:
                                            # Delete project (cascade will handle periods and metrics)
                                            conn.execute(text("""
                                                DELETE FROM projects WHERE project_id = :pid
                                            """), {'pid': project['project_id']})
                                        
                                        st.success(f"✅ Project '{project['project_name']}' deleted successfully!")
                                        import time
                                        time.sleep(1)
                                        st.rerun()
                                        
                                    except Exception as e:
                                        st.error(f"❌ Error deleting project: {str(e)}")
                                        with st.expander("🔍 Show detailed error"):
                                            import traceback
                                            st.code(traceback.format_exc())
                else:
                    st.info("📭 No projects to manage")
                    
            except Exception as e:
                st.error(f"❌ Error loading projects: {str(e)}")
                with st.expander("🔍 Show detailed error"):
                    import traceback
                    st.code(traceback.format_exc())
                    # Add this as a 4th tab in View Data
        tab1, tab2, tab3, tab4 = st.tabs(["📋 Project Summary", "📊 Cumulative Metrics", "📈 Visualizations", "🗑️ Manage Data"])
        
              
        # ============================================================================
        # TAB 4: MANAGE DATA (DELETE REPORTING PERIODS)
        # ============================================================================
        with tab4:
            st.subheader("🗑️ Manage Reporting Periods & Metrics")
            st.warning("⚠️ **Warning:** Deleting a reporting period will permanently delete all associated metrics!")
            
            try:
                # Select project
                with engine.connect() as conn:
                    projects = pd.read_sql(text("SELECT project_id, project_name FROM projects ORDER BY project_name"), conn)
                
                if not projects.empty:
                    project_dict = dict(zip(projects['project_name'], projects['project_id']))
                    selected_project_name = st.selectbox(
                        "Select Project to Manage", 
                        list(project_dict.keys()),
                        key="manage_project_select"
                    )
                    selected_project_id = project_dict[selected_project_name]
                    
                    # Get reporting periods for this project
                    with engine.connect() as conn:
                        periods = pd.read_sql(text("""
                            SELECT 
                                rp.period_id,
                                rp.reporting_year,
                                rp.report_date,
                                rp.amount_spent,
                                COUNT(m.metric_id) as metric_count
                            FROM reporting_periods rp
                            LEFT JOIN metrics m ON rp.period_id = m.period_id
                            WHERE rp.project_id = :pid
                            GROUP BY rp.period_id, rp.reporting_year, rp.report_date, rp.amount_spent
                            ORDER BY rp.reporting_year DESC
                        """), conn, params={'pid': selected_project_id})
                    
                    if not periods.empty:
                        st.write(f"**Reporting periods for {selected_project_name}:**")
                        
                        for idx, period in periods.iterrows():
                            with st.expander(f"📅 Year {period['reporting_year']} - {period['metric_count']} metrics"):
                                col1, col2, col3 = st.columns(3)
                                
                                with col1:
                                    st.write(f"**Report Date:** {period['report_date']}")
                                with col2:
                                    st.write(f"**Amount Spent:** ${period['amount_spent']:,.2f}")
                                with col3:
                                    st.write(f"**Metrics:** {period['metric_count']}")
                                
                                # Show metrics in this period
                                with engine.connect() as conn:
                                    metrics = pd.read_sql(text("""
                                        SELECT metric_id, metric_name, metric_value, metric_unit, notes
                                        FROM metrics
                                        WHERE period_id = :pid
                                        ORDER BY metric_name
                                    """), conn, params={'pid': period['period_id']})
                                
                                if not metrics.empty:
                                    st.write("**Metrics in this period:**")
                                    
                                    # Display metrics with individual delete buttons
                                    for m_idx, metric in metrics.iterrows():
                                        col_metric, col_delete = st.columns([5, 1])
                                        
                                        with col_metric:
                                            st.text(f"• {metric['metric_name']}: {metric['metric_value']} {metric['metric_unit']}")
                                        
                                        with col_delete:
                                            if st.button("❌", key=f"delete_metric_{metric['metric_id']}", help="Delete this metric"):
                                                try:
                                                    with engine.begin() as conn:
                                                        conn.execute(text("""
                                                            DELETE FROM metrics WHERE metric_id = :mid
                                                        """), {'mid': metric['metric_id']})
                                                    st.success("✅ Metric deleted!")
                                                    import time
                                                    time.sleep(0.5)
                                                    st.rerun()
                                                except Exception as e:
                                                    st.error(f"❌ Error: {str(e)}")
                                
                                st.divider()
                                
                                # Delete entire reporting period
                                confirm_period_delete = st.checkbox(
                                    f"I understand this will delete the entire {period['reporting_year']} reporting period",
                                    key=f"confirm_period_{period['period_id']}"
                                )
                                
                                if st.button(
                                    "🗑️ Delete Entire Reporting Period",
                                    key=f"delete_period_{period['period_id']}",
                                    type="primary",
                                    disabled=not confirm_period_delete
                                ):
                                    try:
                                        with engine.begin() as conn:
                                            # Delete reporting period (cascade will handle metrics)
                                            conn.execute(text("""
                                                DELETE FROM reporting_periods WHERE period_id = :pid
                                            """), {'pid': period['period_id']})
                                        
                                        st.success(f"✅ Reporting period {period['reporting_year']} deleted!")
                                        import time
                                        time.sleep(1)
                                        st.rerun()
                                        
                                    except Exception as e:
                                        st.error(f"❌ Error deleting period: {str(e)}")
                    else:
                        st.info(f"📭 No reporting periods found for {selected_project_name}")
                else:
                    st.info("📭 No projects available")
                    
            except Exception as e:
                st.error(f"❌ Error loading data management: {str(e)}")
                with st.expander("🔍 Show detailed error"):
                    import traceback
                    st.code(traceback.format_exc())

# ============================================================================
# ENTER METRICS PAGE
# ============================================================================
elif page == "Enter Metrics":
    st.title("📝 Enter Metrics")
    
    # Define standard metrics
    STANDARD_METRICS = {
        "Longleaf Pine Metrics": [
            "Longleaf acres planted",
            "Longleaf acres restored through silvicultural manipulation",
            "Longleaf acres improved management (private)",
            "Longleaf acres burned (prescribed fire)",
            "Longleaf trees planted (number of seedlings)",
            "Longleaf acres invasive species removed"
        ],
        "Bottomland Hardwood Metrics": [
            "Bottomland hardwoods acres improved",
            "Bottomland hardwoods acres invasive species removed",
            "Bottomland hardwoods acres planted"
        ],
        "Species Metrics": [
            "Red-cockaded woodpecker habitat acres",
            "Gopher tortoise habitat acres",
            "Northern bobwhite habitat acres",
            "Bachman's sparrow habitat acres"
        ],
        "Outreach & Education Metrics": [
            "Number of people reached",
            "Number of people targeted",
            "Number of people with changed behavior",
            "Number of landowners engaged",
            "Number of landowners with management plans",
            "Number of workshops/events held"
        ],
        "Technical Assistance Metrics": [
            "Acres receiving technical assistance",
            "Number of management plans developed",
            "Number of landowners enrolled in Farm Bill programs"
        ]
    }
    
    # Flatten for dropdown
    all_metrics = []
    for category, metrics in STANDARD_METRICS.items():
        all_metrics.extend(metrics)
    all_metrics.append("Other (specify)")
    
    engine = get_database_connection()
    if not engine:
        st.error("❌ Cannot connect to database. Please check your connection.")
        st.stop()
    
    try:
        # Get list of projects
        with engine.connect() as conn:
            projects = pd.read_sql(text("SELECT project_id, project_name FROM projects ORDER BY project_name"), conn)
        
        if projects.empty:
            st.warning("⚠️ No projects available. Please add a project first!")
            if st.button("➕ Go to Projects Page"):
                st.switch_page("Projects")
        else:
            # Initialize session state for current metrics
            if 'current_metrics' not in st.session_state:
                st.session_state.current_metrics = []
            
            col1, col2 = st.columns([1, 2])
            
            with col1:
                st.subheader("Reporting Period")
                
                project_dict = dict(zip(projects['project_name'], projects['project_id']))
                selected_project_name = st.selectbox("Select Project*", list(project_dict.keys()), key="metric_project_select")
                selected_project_id = project_dict[selected_project_name]
                
                reporting_year = st.number_input("Reporting Year*", 
                    min_value=2020, max_value=2050, value=datetime.now().year, step=1, key="reporting_year_input")
                report_date = st.date_input("Report Date", value=datetime.now().date(), key="report_date_input")
                amount_spent = st.number_input("Amount Spent This Period ($)", min_value=0.0, step=100.0, key="amount_spent_input")
                
                st.divider()
                st.subheader("Add Metric")
                
                # Metric dropdown with categories
                metric_selected = st.selectbox("Select Metric*", all_metrics, key="metric_dropdown")
                
                # Show custom text input only if "Other" is selected
                if metric_selected == "Other (specify)":
                    metric_name = st.text_input("Specify Metric Name*", 
                        placeholder="e.g., Custom metric name",
                        key="custom_metric_name")
                    if not metric_name:
                        st.info("👆 Please specify a custom metric name above")
                else:
                    metric_name = metric_selected
                
                metric_value = st.number_input("Value*", min_value=0.0, step=0.01, format="%.2f", key="metric_value_input")
                
                # Auto-suggest units based on metric type
                suggested_unit = ""
                if metric_name:
                    if "acres" in metric_name.lower():
                        suggested_unit = "acres"
                    elif "trees" in metric_name.lower() or "seedlings" in metric_name.lower():
                        suggested_unit = "trees"
                    elif "people" in metric_name.lower() or "landowners" in metric_name.lower():
                        suggested_unit = "people"
                    elif "workshops" in metric_name.lower() or "events" in metric_name.lower():
                        suggested_unit = "events"
                    elif "plans" in metric_name.lower():
                        suggested_unit = "plans"
                    elif "number" in metric_name.lower():
                        suggested_unit = "count"
                
                metric_unit = st.text_input("Unit", 
                    value=suggested_unit,
                    placeholder="e.g., acres, trees, people",
                    key="metric_unit_input")
                metric_notes = st.text_area("Notes", height=100, key="metric_notes_input", 
                    placeholder="Optional: Add any notes about this metric")
                
                # Validation for add button
                add_button_disabled = False
                error_message = None
                
                if metric_selected == "Other (specify)" and not metric_name:
                    add_button_disabled = True
                    error_message = "Please specify the custom metric name"
                elif not metric_name:
                    add_button_disabled = True
                    error_message = "Please select or enter a metric name"
                elif metric_value == 0:
                    st.info("💡 Tip: Enter a value greater than 0")
                
                if error_message:
                    st.warning(error_message)
                
                if st.button("➕ Add Metric", type="secondary", disabled=add_button_disabled, key="add_metric_button"):
                    if metric_name and metric_value is not None:
                        try:
                            # Validate metric_value is a number
                            metric_value_float = float(metric_value)
                            
                            new_metric = {
                                'metric_name': str(metric_name).strip(),
                                'metric_value': metric_value_float,
                                'metric_unit': str(metric_unit).strip() if metric_unit else "",
                                'notes': str(metric_notes).strip() if metric_notes else ""
                            }
                            
                            st.session_state.current_metrics.append(new_metric)
                            st.success(f"✅ Metric '{metric_name}' added!")
                            
                            # Clear the form by rerunning
                            st.rerun()
                            
                        except ValueError as e:
                            st.error(f"❌ Invalid value: {str(e)}")
                        except Exception as e:
                            st.error(f"❌ Error adding metric: {str(e)}")
                    else:
                        st.error("⚠️ Please enter both metric name and value")
            
            with col2:
                st.subheader("Current Period Metrics")
                
                if st.session_state.current_metrics:
                    # Display metrics in a nice formatted table
                    metrics_df = pd.DataFrame(st.session_state.current_metrics)
                    
                    # Format the display
                    display_df = metrics_df.copy()
                    display_df['metric_value'] = display_df['metric_value'].apply(lambda x: f"{x:,.2f}")
                    
                    st.dataframe(
                        display_df,
                        use_container_width=True,
                        hide_index=True,
                        column_config={
                            "metric_name": st.column_config.TextColumn("Metric", width="medium"),
                            "metric_value": st.column_config.TextColumn("Value", width="small"),
                            "metric_unit": st.column_config.TextColumn("Unit", width="small"),
                            "notes": st.column_config.TextColumn("Notes", width="large")
                        }
                    )
                    
                    # Summary
                    st.info(f"📊 Total metrics to save: **{len(st.session_state.current_metrics)}**")
                    
                    col_a, col_b = st.columns(2)
                    
                    with col_a:
                        if st.button("💾 Save Reporting Period", type="primary", key="save_period_button"):
                            try:
                                # Validate we have data
                                if not st.session_state.current_metrics:
                                    st.error("⚠️ No metrics to save. Please add at least one metric.")
                                else:
                                    # Show progress
                                    with st.spinner("Saving to database..."):
                                        # Save to database
                                        with engine.begin() as conn:  # Use begin() for auto-commit
                                            # Insert reporting period
                                            result = conn.execute(text("""
                                                INSERT INTO reporting_periods 
                                                (project_id, reporting_year, report_date, amount_spent, created_date)
                                                VALUES (:pid, :year, :date, :spent, :created)
                                                RETURNING period_id
                                            """), {
                                                'pid': int(selected_project_id),
                                                'year': int(reporting_year),
                                                'date': report_date,
                                                'spent': float(amount_spent),
                                                'created': datetime.now().date()
                                            })
                                            period_id = result.fetchone()[0]
                                            
                                            # Insert metrics one by one
                                            metrics_saved = 0
                                            for idx, metric in enumerate(st.session_state.current_metrics):
                                                try:
                                                    conn.execute(text("""
                                                        INSERT INTO metrics 
                                                        (period_id, metric_name, metric_value, metric_unit, notes)
                                                        VALUES (:pid, :name, :value, :unit, :notes)
                                                    """), {
                                                        'pid': period_id,
                                                        'name': str(metric['metric_name']),
                                                        'value': float(metric['metric_value']),
                                                        'unit': str(metric['metric_unit']) if metric['metric_unit'] else None,
                                                        'notes': str(metric['notes']) if metric['notes'] else None
                                                    })
                                                    metrics_saved += 1
                                                except Exception as metric_error:
                                                    st.warning(f"⚠️ Could not save metric #{idx+1} ({metric['metric_name']}): {str(metric_error)}")
                                    
                                    # Success message
                                    st.success(f"✅ Reporting period saved successfully!\n\n**{metrics_saved}** of **{len(st.session_state.current_metrics)}** metrics recorded for **{selected_project_name}** ({reporting_year}).")
                                    st.balloons()
                                    
                                    # Clear the metrics
                                    st.session_state.current_metrics = []
                                    
                                    # Small delay to show success message
                                    import time
                                    time.sleep(1.5)
                                    st.rerun()
                                    
                            except Exception as e:
                                st.error(f"❌ Error saving reporting period: {str(e)}")
                                with st.expander("🔍 Show detailed error (for debugging)"):
                                    import traceback
                                    st.code(traceback.format_exc())
                                st.warning("💡 Your metrics are still in the table above. Fix the error and try saving again.")
                    
                    with col_b:
                        if st.button("🗑️ Clear All Metrics", type="secondary", key="clear_metrics_button"):
                            st.session_state.current_metrics = []
                            st.success("🗑️ All metrics cleared")
                            st.rerun()
                    
                    # Option to remove individual metrics
                    st.divider()
                    with st.expander("✏️ Remove Individual Metrics"):
                        for idx, metric in enumerate(st.session_state.current_metrics):
                            col_metric, col_remove = st.columns([4, 1])
                            with col_metric:
                                st.text(f"{metric['metric_name']}: {metric['metric_value']} {metric['metric_unit']}")
                            with col_remove:
                                if st.button("❌", key=f"remove_{idx}", help="Remove this metric"):
                                    st.session_state.current_metrics.pop(idx)
                                    st.rerun()
                
                else:
                    st.info("📭 No metrics added yet. Use the form on the left to add metrics.")
                    
                    # Show helpful hint
                    with st.expander("💡 Available Metric Categories", expanded=True):
                        for category, metrics in STANDARD_METRICS.items():
                            st.markdown(f"**{category}:**")
                            for metric in metrics:
                                st.markdown(f"  • {metric}")
                            st.markdown("")  # Add space between categories
                    
                    st.markdown("---")
                    st.markdown("**How to use this page:**")
                    st.markdown("1. Select your project and reporting year")
                    st.markdown("2. Choose a metric from the dropdown (or select 'Other' for custom)")
                    st.markdown("3. Enter the value and unit")
                    st.markdown("4. Click 'Add Metric' to add it to the list")
                    st.markdown("5. Repeat for all metrics, then click 'Save Reporting Period'")
    
    except Exception as e:
        st.error(f"❌ Error loading Enter Metrics page: {str(e)}")
        with st.expander("🔍 Show detailed error"):
            import traceback
            st.code(traceback.format_exc())


# ============================================================================
# VIEW DATA PAGE
# ============================================================================
elif page == "View Data":
    st.title("📈 View Data")
    
    engine = get_database_connection()
    if not engine:
        st.error("❌ Cannot connect to database")
        st.stop()
    
    try:
        # Filters
        with st.expander("🔍 Filters", expanded=True):
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                filter_state = st.selectbox("State Affiliate", 
                    ["All", "NCWF", "GWF", "AWF", "FWF", "SCWF", "TNWF"],
                    key="filter_state")
            
            with col2:
                try:
                    with engine.connect() as conn:
                        projects = pd.read_sql(text("SELECT DISTINCT project_name FROM projects ORDER BY project_name"), conn)
                    project_names = ["All"] + projects['project_name'].tolist() if not projects.empty else ["All"]
                except Exception as e:
                    st.warning(f"Could not load projects: {str(e)}")
                    project_names = ["All"]
                
                filter_project = st.selectbox("Project", project_names, key="filter_project")
            
            with col3:
                filter_status = st.selectbox("Status", 
                    ["All", "Planning", "Active", "Completed"],
                    key="filter_status")
            
            with col4:
                filter_year_start = st.number_input("Start Year", 
                    min_value=2020, max_value=2050, value=2020, step=1,
                    key="filter_year_start")
                filter_year_end = st.number_input("End Year", 
                    min_value=2020, max_value=2050, value=datetime.now().year, step=1,
                    key="filter_year_end")
        
        # Build query based on filters
        where_clauses = []
        if filter_state != "All":
            where_clauses.append(f"p.state_affiliate = '{filter_state}'")
        if filter_project != "All":
            # Escape single quotes in project name
            safe_project_name = filter_project.replace("'", "''")
            where_clauses.append(f"p.project_name = '{safe_project_name}'")
        if filter_status != "All":
            where_clauses.append(f"p.project_status = '{filter_status}'")
        
        where_sql = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""
        
        # Add year filter for reporting periods
        year_filter = f"AND rp.reporting_year BETWEEN {filter_year_start} AND {filter_year_end}" if where_clauses else f"WHERE rp.reporting_year BETWEEN {filter_year_start} AND {filter_year_end}"
        
        # Tabs for different views
        tab1, tab2, tab3 = st.tabs(["📋 Project Summary", "📊 Cumulative Metrics", "📈 Visualizations"])
        
        # ============================================================================
        # TAB 1: PROJECT SUMMARY
        # ============================================================================
        with tab1:
            st.subheader("Project Summary")
            
            try:
                with engine.connect() as conn:
                    summary_query = f"""
                        SELECT 
                            p.project_name,
                            p.state_affiliate,
                            p.project_status,
                            p.grant_amount,
                            p.match_contributions,
                            p.start_date,
                            p.end_date,
                            COUNT(DISTINCT rp.period_id) as reporting_periods,
                            COUNT(m.metric_id) as total_metrics,
                            SUM(rp.amount_spent) as total_spent
                        FROM projects p
                        LEFT JOIN reporting_periods rp ON p.project_id = rp.project_id
                        LEFT JOIN metrics m ON rp.period_id = m.period_id
                        {where_sql}
                        GROUP BY p.project_id, p.project_name, p.state_affiliate, 
                                 p.project_status, p.grant_amount, p.match_contributions,
                                 p.start_date, p.end_date
                        ORDER BY p.project_name
                    """
                    summary = pd.read_sql(text(summary_query), conn)
                
                if not summary.empty:
                    # Format currency columns
                    summary['grant_amount'] = summary['grant_amount'].apply(
                        lambda x: f"${x:,.0f}" if pd.notna(x) else "$0"
                    )
                    summary['match_contributions'] = summary['match_contributions'].apply(
                        lambda x: f"${x:,.0f}" if pd.notna(x) else "$0"
                    )
                    summary['total_spent'] = summary['total_spent'].apply(
                        lambda x: f"${x:,.0f}" if pd.notna(x) else "$0"
                    )
                    
                    # Rename columns for display
                    summary.columns = [
                        'Project Name', 'State', 'Status', 'Grant Amount', 
                        'Match', 'Start Date', 'End Date', 
                        'Reporting Periods', 'Total Metrics', 'Total Spent'
                    ]
                    
                    st.dataframe(summary, use_container_width=True, hide_index=True)
                    
                    # Download button
                    csv = summary.to_csv(index=False)
                    st.download_button(
                        label="📥 Download Summary as CSV",
                        data=csv,
                        file_name=f"nwf_project_summary_{datetime.now().strftime('%Y%m%d')}.csv",
                        mime="text/csv"
                    )
                else:
                    st.info("📭 No data matches the selected filters")
                    
            except Exception as e:
                st.error(f"❌ Error loading project summary: {str(e)}")
                with st.expander("🔍 Show detailed error"):
                    import traceback
                    st.code(traceback.format_exc())
        
        # ============================================================================
        # TAB 2: CUMULATIVE METRICS
        # ============================================================================
        with tab2:
            st.subheader("Cumulative Metrics by Project")
            
            try:
                with engine.connect() as conn:
                    cumulative_query = f"""
                        SELECT 
                            p.project_name,
                            p.state_affiliate,
                            m.metric_name,
                            m.metric_unit,
                            SUM(m.metric_value) as total_value,
                            COUNT(m.metric_id) as entry_count,
                            MIN(rp.reporting_year) as first_year,
                            MAX(rp.reporting_year) as last_year
                        FROM projects p
                        JOIN reporting_periods rp ON p.project_id = rp.project_id
                        JOIN metrics m ON rp.period_id = m.period_id
                        {where_sql}
                        {year_filter}
                        GROUP BY p.project_name, p.state_affiliate, m.metric_name, m.metric_unit
                        ORDER BY p.project_name, m.metric_name
                    """
                    cumulative = pd.read_sql(text(cumulative_query), conn)
                
                if not cumulative.empty:
                    # Format the total_value column
                    cumulative['total_value'] = cumulative['total_value'].apply(lambda x: f"{x:,.2f}")
                    
                    # Rename columns
                    cumulative.columns = [
                        'Project', 'State', 'Metric', 'Unit', 
                        'Total Value', 'Entries', 'First Year', 'Last Year'
                    ]
                    
                    st.dataframe(cumulative, use_container_width=True, hide_index=True)
                    
                    # Summary stats
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("Total Unique Metrics", len(cumulative['Metric'].unique()))
                    with col2:
                        st.metric("Total Projects", len(cumulative['Project'].unique()))
                    with col3:
                        st.metric("Total Entries", cumulative['Entries'].sum())
                    
                    # Download button
                    csv = cumulative.to_csv(index=False)
                    st.download_button(
                        label="📥 Download Metrics as CSV",
                        data=csv,
                        file_name=f"nwf_cumulative_metrics_{datetime.now().strftime('%Y%m%d')}.csv",
                        mime="text/csv"
                    )
                else:
                    st.info("📭 No metrics data available for the selected filters")
                    
            except Exception as e:
                st.error(f"❌ Error loading cumulative metrics: {str(e)}")
                with st.expander("🔍 Show detailed error"):
                    import traceback
                    st.code(traceback.format_exc())
        
        # ============================================================================
        # TAB 3: VISUALIZATIONS
        # ============================================================================
        with tab3:
            st.subheader("Data Visualizations")
            
            try:
                # Get available metrics for dropdown
                with engine.connect() as conn:
                    metrics_query = f"""
                        SELECT DISTINCT m.metric_name 
                        FROM metrics m
                        JOIN reporting_periods rp ON m.period_id = rp.period_id
                        JOIN projects p ON rp.project_id = p.project_id
                        {where_sql}
                        ORDER BY m.metric_name
                    """
                    available_metrics = pd.read_sql(text(metrics_query), conn)
                
                if not available_metrics.empty:
                    selected_metric = st.selectbox(
                        "Select Metric to Visualize", 
                        available_metrics['metric_name'].tolist(),
                        key="viz_metric_select"
                    )
                    
                    viz_type = st.radio(
                        "Visualization Type", 
                        ["📈 Time Series by Year", "🗺️ State Comparison", "📊 Project Comparison"],
                        key="viz_type_radio",
                        horizontal=True
                    )
                    
                    # TIME SERIES VISUALIZATION
                    if viz_type == "📈 Time Series by Year":
                        try:
                            with engine.connect() as conn:
                                timeseries_query = f"""
                                    SELECT 
                                        rp.reporting_year,
                                        SUM(m.metric_value) as total_value,
                                        COUNT(DISTINCT p.project_id) as project_count
                                    FROM reporting_periods rp
                                    JOIN metrics m ON rp.period_id = m.period_id
                                    JOIN projects p ON rp.project_id = p.project_id
                                    WHERE m.metric_name = :metric 
                                    {' AND ' + ' AND '.join(where_clauses) if where_clauses else ''}
                                    AND rp.reporting_year BETWEEN :start_year AND :end_year
                                    GROUP BY rp.reporting_year
                                    ORDER BY rp.reporting_year
                                """
                                timeseries_data = pd.read_sql(
                                    text(timeseries_query), 
                                    conn, 
                                    params={
                                        'metric': selected_metric,
                                        'start_year': filter_year_start,
                                        'end_year': filter_year_end
                                    }
                                )
                            
                            if not timeseries_data.empty:
                                fig = px.line(
                                    timeseries_data, 
                                    x='reporting_year', 
                                    y='total_value',
                                    labels={
                                        'reporting_year': 'Year', 
                                        'total_value': selected_metric
                                    },
                                    markers=True,
                                    title=f"{selected_metric} Over Time"
                                )
                                fig.update_traces(
                                    line_color='#2C5F2D', 
                                    marker=dict(size=10, color='#97BC62')
                                )
                                fig.update_layout(hovermode='x unified')
                                st.plotly_chart(fig, use_container_width=True)
                                
                                # Show data table below chart
                                with st.expander("📊 View Data Table"):
                                    timeseries_data['total_value'] = timeseries_data['total_value'].apply(
                                        lambda x: f"{x:,.2f}"
                                    )
                                    st.dataframe(timeseries_data, use_container_width=True, hide_index=True)
                            else:
                                st.info("📭 No data available for this metric and time period")
                                
                        except Exception as e:
                            st.error(f"❌ Error creating time series: {str(e)}")
                            with st.expander("🔍 Show detailed error"):
                                import traceback
                                st.code(traceback.format_exc())
                    
                    # STATE COMPARISON VISUALIZATION
                    elif viz_type == "🗺️ State Comparison":
                        try:
                            with engine.connect() as conn:
                                state_query = f"""
                                    SELECT 
                                        p.state_affiliate,
                                        SUM(m.metric_value) as total_value,
                                        COUNT(DISTINCT p.project_id) as project_count,
                                        COUNT(m.metric_id) as metric_entries
                                    FROM projects p
                                    JOIN reporting_periods rp ON p.project_id = rp.project_id
                                    JOIN metrics m ON rp.period_id = m.period_id
                                    WHERE m.metric_name = :metric
                                    AND rp.reporting_year BETWEEN :start_year AND :end_year
                                    GROUP BY p.state_affiliate
                                    ORDER BY total_value DESC
                                """
                                state_data = pd.read_sql(
                                    text(state_query), 
                                    conn, 
                                    params={
                                        'metric': selected_metric,
                                        'start_year': filter_year_start,
                                        'end_year': filter_year_end
                                    }
                                )
                            
                            if not state_data.empty:
                                fig = px.bar(
                                    state_data, 
                                    x='state_affiliate', 
                                    y='total_value',
                                    labels={
                                        'state_affiliate': 'State Affiliate', 
                                        'total_value': selected_metric
                                    },
                                    color='total_value',
                                    color_continuous_scale=['#97BC62', '#2C5F2D'],
                                    title=f"{selected_metric} by State"
                                )
                                fig.update_layout(showlegend=False)
                                st.plotly_chart(fig, use_container_width=True)
                                
                                # Show data table
                                with st.expander("📊 View Data Table"):
                                    display_state = state_data.copy()
                                    display_state['total_value'] = display_state['total_value'].apply(
                                        lambda x: f"{x:,.2f}"
                                    )
                                    display_state.columns = ['State', 'Total Value', 'Projects', 'Entries']
                                    st.dataframe(display_state, use_container_width=True, hide_index=True)
                            else:
                                st.info("📭 No data available for this metric")
                                
                        except Exception as e:
                            st.error(f"❌ Error creating state comparison: {str(e)}")
                            with st.expander("🔍 Show detailed error"):
                                import traceback
                                st.code(traceback.format_exc())
                    
                    # PROJECT COMPARISON VISUALIZATION
                    else:  # Project Comparison
                        try:
                            with engine.connect() as conn:
                                project_query = f"""
                                    SELECT 
                                        p.project_name,
                                        p.state_affiliate,
                                        SUM(m.metric_value) as total_value,
                                        COUNT(m.metric_id) as metric_entries
                                    FROM projects p
                                    JOIN reporting_periods rp ON p.project_id = rp.project_id
                                    JOIN metrics m ON rp.period_id = m.period_id
                                    WHERE m.metric_name = :metric 
                                    {' AND ' + ' AND '.join(where_clauses) if where_clauses else ''}
                                    AND rp.reporting_year BETWEEN :start_year AND :end_year
                                    GROUP BY p.project_name, p.state_affiliate
                                    ORDER BY total_value DESC
                                """
                                project_data = pd.read_sql(
                                    text(project_query), 
                                    conn, 
                                    params={
                                        'metric': selected_metric,
                                        'start_year': filter_year_start,
                                        'end_year': filter_year_end
                                    }
                                )
                            
                            if not project_data.empty:
                                # Limit to top 15 projects for readability
                                if len(project_data) > 15:
                                    st.info(f"📊 Showing top 15 of {len(project_data)} projects")
                                    project_data = project_data.head(15)
                                
                                fig = px.bar(
                                    project_data, 
                                    x='project_name', 
                                    y='total_value',
                                    color='state_affiliate',
                                    labels={
                                        'project_name': 'Project', 
                                        'total_value': selected_metric,
                                        'state_affiliate': 'State'
                                    },
                                    title=f"{selected_metric} by Project",
                                    color_discrete_sequence=px.colors.qualitative.Set2
                                )
                                fig.update_layout(xaxis_tickangle=-45, showlegend=True)
                                st.plotly_chart(fig, use_container_width=True)
                                
                                # Show data table
                                with st.expander("📊 View Data Table"):
                                    display_project = project_data.copy()
                                    display_project['total_value'] = display_project['total_value'].apply(
                                        lambda x: f"{x:,.2f}"
                                    )
                                    display_project.columns = ['Project', 'State', 'Total Value', 'Entries']
                                    st.dataframe(display_project, use_container_width=True, hide_index=True)
                            else:
                                st.info("📭 No data available for this metric and filters")
                                
                        except Exception as e:
                            st.error(f"❌ Error creating project comparison: {str(e)}")
                            with st.expander("🔍 Show detailed error"):
                                import traceback
                                st.code(traceback.format_exc())
                else:
                    st.info("📭 No metrics data available yet. Enter some metrics to see visualizations!")
                    if st.button("➕ Go to Enter Metrics"):
                        st.switch_page("Enter Metrics")
                        
            except Exception as e:
                st.error(f"❌ Error loading visualizations: {str(e)}")
                with st.expander("🔍 Show detailed error"):
                    import traceback
                    st.code(traceback.format_exc())
    
    except Exception as e:
        st.error(f"❌ Error loading View Data page: {str(e)}")
        with st.expander("🔍 Show detailed error"):
            import traceback
            st.code(traceback.format_exc())


# ============================================================================
# REPORTS PAGE
# ============================================================================
elif page == "Reports":
    st.title("📄 Reports")
    
    engine = get_database_connection()
    if engine:
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("📊 Excel Report")
            
            # Get projects for dropdown
            with engine.connect() as conn:
                projects = pd.read_sql(text("SELECT project_id, project_name FROM projects ORDER BY project_name"), conn)
            
            if not projects.empty:
                project_dict = dict(zip(projects['project_name'], projects['project_id']))
                selected_project = st.selectbox("Select Project", ["All Projects"] + list(project_dict.keys()))
                
                report_format = st.selectbox("Report Format", 
                    ["Summary by Year", "Detailed Metrics", "NFWF Format"])
                
                if st.button("📥 Generate Excel Report", type="primary"):
                    # Generate Excel report
                    output = io.BytesIO()
                    
                    with pd.ExcelWriter(output, engine='openpyxl') as writer:
                        if selected_project == "All Projects":
                            # All projects summary
                            with engine.connect() as conn:
                                projects_data = pd.read_sql(text("""
                                    SELECT * FROM projects ORDER BY project_name
                                """), conn)
                                projects_data.to_excel(writer, sheet_name='Projects', index=False)
                                
                                metrics_data = pd.read_sql(text("""
                                    SELECT 
                                        p.project_name,
                                        p.state_affiliate,
                                        rp.reporting_year,
                                        m.metric_name,
                                        m.metric_value,
                                        m.metric_unit
                                    FROM metrics m
                                    JOIN reporting_periods rp ON m.period_id = rp.period_id
                                    JOIN projects p ON rp.project_id = p.project_id
                                    ORDER BY p.project_name, rp.reporting_year, m.metric_name
                                """), conn)
                                metrics_data.to_excel(writer, sheet_name='All Metrics', index=False)
                        else:
                            # Single project report
                            project_id = project_dict[selected_project]
                            
                            with engine.connect() as conn:
                                # Project details
                                project_info = pd.read_sql(text("""
                                    SELECT * FROM projects WHERE project_id = :pid
                                """), conn, params={'pid': project_id})
                                project_info.to_excel(writer, sheet_name='Project Info', index=False)
                                
                                # Metrics by year
                                metrics_by_year = pd.read_sql(text("""
                                    SELECT 
                                        rp.reporting_year,
                                        m.metric_name,
                                        m.metric_value,
                                        m.metric_unit,
                                        m.notes
                                    FROM metrics m
                                    JOIN reporting_periods rp ON m.period_id = rp.period_id
                                    WHERE rp.project_id = :pid
                                    ORDER BY rp.reporting_year, m.metric_name
                                """), conn, params={'pid': project_id})
                                metrics_by_year.to_excel(writer, sheet_name='Metrics', index=False)
                                
                                # Cumulative summary
                                cumulative = pd.read_sql(text("""
                                    SELECT 
                                        m.metric_name,
                                        m.metric_unit,
                                        SUM(m.metric_value) as total_value,
                                        COUNT(m.metric_id) as entry_count
                                    FROM metrics m
                                    JOIN reporting_periods rp ON m.period_id = rp.period_id
                                    WHERE rp.project_id = :pid
                                    GROUP BY m.metric_name, m.metric_unit
                                    ORDER BY m.metric_name
                                """), conn, params={'pid': project_id})
                                cumulative.to_excel(writer, sheet_name='Cumulative Totals', index=False)
                    
                    output.seek(0)
                    
                    st.download_button(
                        label="💾 Download Excel Report",
                        data=output,
                        file_name=f"nwf_metrics_{selected_project.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d')}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
            else:
                st.info("No projects available to generate reports")
        
        with col2:
            st.subheader("📑 Quick Export")
            st.write("Export all data for backup or external analysis")
            
            if st.button("📥 Download All Data", type="secondary"):
                output = io.BytesIO()
                
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    with engine.connect() as conn:
                        # Export all tables
                        projects_data = pd.read_sql(text("SELECT * FROM projects"), conn)
                        projects_data.to_excel(writer, sheet_name='Projects', index=False)
                        
                        periods_data = pd.read_sql(text("SELECT * FROM reporting_periods"), conn)
                        periods_data.to_excel(writer, sheet_name='Reporting Periods', index=False)
                        
                        metrics_data = pd.read_sql(text("SELECT * FROM metrics"), conn)
                        metrics_data.to_excel(writer, sheet_name='Metrics', index=False)
                
                output.seek(0)
                
                st.download_button(
                    label="💾 Download Backup",
                    data=output,
                    file_name=f"nwf_metrics_backup_{datetime.now().strftime('%Y%m%d')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )

# ============================================================================
# HELP PAGE
# ============================================================================
elif page == "Help":
    st.title("❓ Help")
    
    st.markdown("""
    ## How to Use NWF Metrics
    
    ### 1. 📁 Add a New Project
    - Go to the **Projects** tab
    - Fill out the form with project details
    - Required fields: Project Name and State Affiliate
    - Click "Save Project"
    
    ### 2. 📝 Enter Metrics
    - Go to **Enter Metrics** tab
    - Select your project and reporting year
    - Add individual metrics one at a time
    - Click "Add Metric" for each one
    - When done, click "Save Reporting Period"
    
    ### 3. 📈 View Progress
    - Use the **View Data** tab
    - Apply filters to narrow down results
    - View cumulative totals, time series, and comparisons
    
    ### 4. 📄 Generate Reports
    - Go to **Reports** tab
    - Select a project or export all data
    - Download Excel reports with your metrics
    
    ### 5. 📊 Dashboard
    - The **Dashboard** shows a quick overview
    - See total projects, funding, and recent activity
    - View charts by state and status
    
    ---
    
    ## Data Storage
    
    All data is stored securely in a PostgreSQL cloud database (Supabase).  
    Your data persists forever and is accessible from anywhere!
    
    ---
    
    ## Tips & Best Practices
    
    - **Mobile-Friendly**: This app works great on phones and tablets
    - **Annual Reporting**: Enter NEW metrics for each reporting period (the app calculates cumulative totals automatically)
    - **Cumulative Totals**: View cumulative metrics in the "View Data" tab
    - **Backup Regularly**: Use the "Download All Data" button in Reports to create backups
    - **Free-Form Metrics**: You can create any metric name you need - they're not restricted to a predefined list
    - **Units Matter**: Always include units (acres, trees, people, etc.) for clarity
    
    ---
    
    ## State Affiliates
    
    This system tracks projects from six southeastern state affiliates:
    
    - **NCWF** - North Carolina Wildlife Federation
    - **GWF** - Georgia Wildlife Federation
    - **AWF** - Alabama Wildlife Federation
    - **FWF** - Florida Wildlife Federation
    - **SCWF** - South Carolina Wildlife Federation
    - **TNWF** - Tennessee Wildlife Federation
    
    ---
    
    ## Common Metrics Examples
    
    Here are some common metrics you might track (but you can create any metric you need):
    
    **Habitat Metrics:**
    - Longleaf acres planted
    - Longleaf acres restored through silvicultural manipulation
    - Acres improved management (private)
    - Prescribed burn acres (private land)
    - Bottomland hardwoods improved
    - Invasive species acres removed
    
    **Species Metrics:**
    - Red-cockaded woodpecker monitoring
    - Gopher tortoise habitat acres
    - Northern bobwhite habitat acres
    - Bachman's sparrow habitat acres
    
    **Planting Metrics:**
    - Number of trees planted (longleaf seedlings)
    - Number of landowners engaged
    - Acres receiving technical assistance
    
    **Outreach Metrics:**
    - Number of people reached
    - Number of people targeted
    - Number of people with changed behavior
    - Number of landowners with management plans
    
    ---
    
    ## Reporting Periods
    
    - Reports are typically **annual** (one entry per project per year)
    - Enter the **new accomplishments** for that reporting period
    - The system automatically calculates cumulative totals across all years
    - You can enter metrics for multiple years for the same project
    
    ---
    
    ## Troubleshooting
    
    **Can't connect to database?**
    - Check your internet connection
    - Verify your Supabase credentials in `.streamlit/secrets.toml`
    - Contact your administrator
    
    **Data not showing up?**
    - Make sure you clicked "Save Reporting Period" after adding metrics
    - Try refreshing the page
    - Check the filters on the "View Data" page
    
    **Excel download not working?**
    - Ensure you have data entered for the selected project
    - Try a different browser
    - Check that you have the latest version of the app
    
    ---
    
    ## Need Help?
    
    Contact your NWF administrator if you have questions or issues.
    
    **Technical Support:**  
    For technical issues with the app, database connection problems, or feature requests, contact your IT department or the app developer.
    
    **Data Entry Questions:**  
    For questions about what metrics to track or how to enter specific project data, contact your project manager or NFWF grant coordinator.
    """)
    
    # Display app version and info
    st.divider()
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("App Version", "1.0")
    with col2:
        st.metric("Database", "PostgreSQL/Supabase")
    with col3:
        st.metric("Platform", "Streamlit")

# Footer for all pages
st.sidebar.markdown("---")
st.sidebar.info("🌲 **NWF Metrics Tracker**\nVersion 1.0\n\nBuilt for National Wildlife Federation\nand State Affiliates")
st.sidebar.markdown("📧 Need help? Contact your administrator")