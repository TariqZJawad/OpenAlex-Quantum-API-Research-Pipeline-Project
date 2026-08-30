import streamlit as st
import pandas as pd 
import sqlite3
import plotly.express as px
import plotly.graph_objects as go
from wordcloud import WordCloud
import matplotlib.pyplot as plt
from datetime import datetime

st.set_page_config(
    page_title="OpenAlex Quantum Research Dashboard",
    page_icon="🔬",
    layout="wide"
)

def get_db_connection():
    conn = sqlite3.connect('openalex_data.db')
    conn.row_factory = sqlite3.Row
    return conn

@st.cache_data
def load_data():
    conn = get_db_connection()
    works_df = pd.read_sql("SELECT * FROM works", conn)
    concepts_df = pd.read_sql("SELECT * FROM concepts", conn)
    work_concepts_df = pd.read_sql("SELECT * FROM work_concepts", conn)
    institutions_df = pd.read_sql("SELECT * FROM institutions", conn)
    authors_df = pd.read_sql("SELECT * FROM authors", conn)
    work_authors_df = pd.read_sql("SELECT * FROM work_authors", conn)
    work_references_df = pd.read_sql("SELECT * FROM work_references", conn)
    conn.close()
    
    # Helper function to clean and normalize IDs
    def clean_id(series):
        return series.astype(str).apply(lambda x: str(x).split('/')[-1].strip().upper())
        
    for df in [works_df, concepts_df, institutions_df, authors_df]:
        if 'id' in df.columns: df['id'] = clean_id(df['id'])
        
    if 'work_id' in work_concepts_df.columns: work_concepts_df['work_id'] = clean_id(work_concepts_df['work_id'])
    if 'concept_id' in work_concepts_df.columns: work_concepts_df['concept_id'] = clean_id(work_concepts_df['concept_id'])
    
    if 'work_id' in work_authors_df.columns: work_authors_df['work_id'] = clean_id(work_authors_df['work_id'])
    if 'author_id' in work_authors_df.columns: work_authors_df['author_id'] = clean_id(work_authors_df['author_id'])
    if 'ins_id' in work_authors_df.columns: work_authors_df['ins_id'] = clean_id(work_authors_df['ins_id'])
    
    return works_df, work_concepts_df, work_authors_df, work_references_df, authors_df, concepts_df, institutions_df

works_df, work_concepts_df, work_authors_df, work_references_df, authors_df, concepts_df, institutions_df = load_data()

st.title("🔬 OpenAlex Quantum Research Dashboard")
st.markdown("---")

# === Sidebar and Filters ===
st.sidebar.title("Navigation & Filters")
st.sidebar.markdown("---")

# 1. Search Query Multi-select Filter
if 'search_query' in works_df.columns:
    unique_queries = works_df['search_query'].dropna().unique().tolist()
else:
    unique_queries = []

selected_queries = st.sidebar.multiselect(
    "🔎 Filter by Search Query",
    options=["All"] + unique_queries,
    default=["All"]
)

# 2. Concepts Multi-select Filter
if 'name' in concepts_df.columns:
    unique_concepts = concepts_df['name'].dropna().unique().tolist()
else:
    unique_concepts = []

selected_concepts_filter = st.sidebar.multiselect(
    "🏷️ Filter by Concepts",
    options=["All"] + unique_concepts,
    default=["All"]
)

works_df['pub_year'] = pd.to_numeric(works_df['publication_date'].astype(str).str[:4], errors='coerce')
valid_years = works_df['pub_year'].dropna()
if not valid_years.empty:
    min_year = int(valid_years.min())
    max_year = int(valid_years.max())
else:
    min_year, max_year = 1990, datetime.now().year

if min_year == max_year:
    min_year -= 1

st.sidebar.subheader("📆 Publication Year Range")
selected_year_range = st.sidebar.slider(
    "Select Year Range",
    min_value=min_year,
    max_value=max_year,
    value=(min_year, max_year)
)

# Knowledge Tree Search Box with Clear/Exit Option
st.sidebar.markdown("---")
st.sidebar.subheader("🌱 Foundational Knowledge Tree")

# Initialize session state for clearing search input safely
if "knowledge_search" not in st.session_state:
    st.session_state.knowledge_search = ""

def clear_search():
    st.session_state.knowledge_search = ""

col_s1, col_s2 = st.sidebar.columns([3, 1])
with col_s1:
    concept_search_term = st.text_input("Concept or Keyword:", value=st.session_state.knowledge_search, key="knowledge_search_input").strip()
with col_s2:
    st.write("")
    st.write("")
    if st.button("🧹 Clear"):
        st.session_state.knowledge_search = ""
        st.rerun()

# Update search term from session state
concept_search_term = st.session_state.knowledge_search_input.strip()

# Author Info Section with Custom Links
st.sidebar.markdown("---")
st.sidebar.subheader("🧑‍💻 About the Author")
st.sidebar.markdown("**Tariq Zeyad Jawad**")
st.sidebar.markdown("Map the past, understand the present, and steer the future of scientific evolution.")
st.sidebar.markdown("### 📬 Connect with Me")
st.sidebar.markdown(
    """
    * 💼 **LinkedIn:** [Profile Link](https://www.linkedin.com/in/tariq-jawad?utm_source=share_via&utm_content=profile&utm_medium=member_android)
    * 🐙 **GitHub:** [Repository](https://github.com/TariqZJawad?tab=repositories)
    * ✉️ **Email:** tzyad3763@gmail.com
    """
)

# === Main Filtering Function ===
def get_filtered_data(selected_queries, selected_concepts_filter, year_range, works_df, work_concepts_df, work_authors_df, work_references_df, authors_df, concepts_df, institutions_df):
    f_works = works_df.copy()
    
    if "All" not in selected_queries and len(selected_queries) > 0 and 'search_query' in f_works.columns:
        f_works = f_works[f_works['search_query'].isin(selected_queries)]
        
    f_works = f_works[
        (f_works['pub_year'] >= year_range[0]) & 
        (f_works['pub_year'] <= year_range[1])
    ]
    
    valid_work_ids = f_works['id'].tolist()
    
    f_work_concepts = work_concepts_df[work_concepts_df['work_id'].isin(valid_work_ids)]
    c_df = concepts_df.rename(columns={'id': 'c_id'})
    f_concepts = f_work_concepts.merge(c_df, left_on='concept_id', right_on='c_id', how='inner')
    
    if "All" not in selected_concepts_filter and len(selected_concepts_filter) > 0 and not f_concepts.empty:
        filtered_work_ids = f_concepts[f_concepts['name'].isin(selected_concepts_filter)]['work_id'].tolist()
        f_works = f_works[f_works['id'].isin(filtered_work_ids)]
        valid_work_ids = f_works['id'].tolist()
        f_work_concepts = work_concepts_df[work_concepts_df['work_id'].isin(valid_work_ids)]
        f_concepts = f_work_concepts.merge(c_df, left_on='concept_id', right_on='c_id', how='inner')

    if not f_concepts.empty:
        if 'level' in f_concepts.columns: f_concepts['level'] = pd.to_numeric(f_concepts['level'], errors='coerce').fillna(0)
        if 'score' in f_concepts.columns: f_concepts['score'] = pd.to_numeric(f_concepts['score'], errors='coerce').fillna(0)
    
    f_work_authors = work_authors_df[work_authors_df['work_id'].isin(valid_work_ids)]
    i_df = institutions_df.rename(columns={'id': 'i_id'})
    f_ins = f_work_authors.merge(i_df, left_on='ins_id', right_on='i_id', how='inner')
    
    a_df = authors_df.rename(columns={'id': 'a_id'})
    f_authors = f_work_authors.merge(a_df, left_on='author_id', right_on='a_id', how='inner')
    
    f_work_references = work_references_df[
        work_references_df['parent_work_id'].isin(valid_work_ids) | 
        work_references_df['child_work_id'].isin(valid_work_ids)
    ]
    
    return f_works, f_work_concepts, f_concepts, f_work_authors, f_authors, f_work_references, f_ins

f_works, f_work_concepts, f_concepts, f_work_authors, f_authors, f_work_references, f_ins = get_filtered_data(
    selected_queries, selected_concepts_filter, selected_year_range, works_df, work_concepts_df, work_authors_df, work_references_df, authors_df, concepts_df, institutions_df
)

st.markdown("> *\"Decoding the trajectory of global science is not just about observing trends—it is about positioning yourself at the absolute frontier of discovery.\"*")
st.markdown("---")

total_works_count = len(f_works)
high_concept = f_concepts['name'].value_counts().idxmax() if not f_concepts.empty and 'name' in f_concepts.columns else "N/A"

kpi1, kpi2 = st.columns(2)
with kpi1: st.metric(label="📊 Total Filtered Works", value=f"{total_works_count:,}")
with kpi2: st.metric(label="⭐ High Concept (Top Trend)", value=high_concept)
st.markdown("---")

# === Knowledge Tree with Chronological Search and Expandable Cards ===
def build_knowledge_tree(search_term, works_df, concepts_df, work_concepts_df, work_authors_df, authors_df, institutions_df):
    if not search_term:
        return
    
    st.subheader(f"🌱 Foundational Knowledge Tree / Literature Search: *{search_term}*")
    st.caption("Chronological literature sorting based on keyword matching (Concepts or Abstract Text).")
    
    w_merged = works_df.copy()
    w_merged['pub_year'] = pd.to_numeric(w_merged['publication_date'].astype(str).str[:4], errors='coerce').fillna(9999)
    
    mask = w_merged['abstract_text'].str.contains(search_term, case=False, na=False) | w_merged['title'].str.contains(search_term, case=False, na=False)
    
    c_renamed = concepts_df.rename(columns={'id': 'c_id', 'name': 'c_name', 'level': 'c_level'})
    wc_merged = work_concepts_df.merge(c_renamed, left_on='concept_id', right_on='c_id', how='inner')
    concept_matched_works = wc_merged[wc_merged['c_name'].str.contains(search_term, case=False, na=False)]['work_id'].tolist()
    
    w_filtered = w_merged[mask | w_merged['id'].isin(concept_matched_works)]
    
    if w_filtered.empty:
        st.warning(f"No literature found matching '{search_term}'.")
        return
        
    tree_df = w_filtered.sort_values(by=['pub_year'], ascending=True)
    
    st.info(f"Found {len(tree_df)} matching works. Displaying chronologically:")
    
    for i, (idx, row) in enumerate(tree_df.iterrows()):
        wid = row['id']
        
        wa = work_authors_df[work_authors_df['work_id'] == wid]
        if not wa.empty:
            auths = wa.merge(authors_df.rename(columns={'id': 'a_id', 'name': 'a_name'}), left_on='author_id', right_on='a_id', how='inner')
            insts = wa.merge(institutions_df.rename(columns={'id': 'i_id', 'name': 'i_name', 'country': 'i_country'}), left_on='ins_id', right_on='i_id', how='inner')
            author_list = " • ".join(auths['a_name'].dropna().unique())
            inst_list = " • ".join((insts['i_name'] + " (" + insts['i_country'].fillna('N/A') + ")").dropna().unique())
        else:
            author_list, inst_list = "Unknown", "Unknown"
            
        abstract = row.get('abstract_text', '')
        if pd.isna(abstract) or abstract == "":
            abstract = "Abstract text not available in database."
            
        with st.expander(f"📖 [{int(row['pub_year']) if row['pub_year'] != 9999 else 'N/A'}] {row['title']}", expanded=(i < 3)):
            st.markdown(f"**👥 Authors:** {author_list}")
            st.markdown(f"**🏛️ Institutions:** {inst_list}")
            st.markdown(f"**📑 Abstract:** *{abstract}*")
            
        if i < len(tree_df) - 1:
            st.markdown("<div style='text-align: center; font-size: 20px; color: #ff4b4b; margin: 2px;'>⬇️</div>", unsafe_allow_html=True)
            
    st.markdown("---")

if concept_search_term:
    build_knowledge_tree(concept_search_term, works_df, concepts_df, work_concepts_df, work_authors_df, authors_df, institutions_df)

# === Plotting Functions with Custom Color Theme (Electric / Custom Gradient from Image) ===
def plot_concept_trends(f_concepts, f_works):
    if f_concepts.empty or f_works.empty or 'name' not in f_concepts.columns:
        return px.line(title="No data available for the selected filters.")
    trend_data = f_concepts.merge(f_works[['id', 'pub_year']], left_on='work_id', right_on='id')
    if trend_data.empty: return px.line(title="No temporal concept data found.")
    
    top_concepts = trend_data['name'].value_counts().nlargest(6).index.tolist()
    trend_f = trend_data[trend_data['name'].isin(top_concepts)]
    trend_counts = trend_f.groupby(['pub_year', 'name']).size().reset_index(name='count')
    
    fig = px.area(
        trend_counts, x='pub_year', y='count', color='name', markers=True,
        title="<b>1. Evolution of Top Concepts Over Years</b>",
        color_discrete_sequence=px.colors.sequential.Electric,
        labels={'pub_year': 'Publication Year', 'count': 'Concept Frequency', 'name': 'Concept'}
    )
    fig.update_traces(opacity=0.7)
    fig.update_layout(template="plotly_dark", hovermode="x unified")
    return fig

def plot_top_ins(f_ins, f_concepts):
    if f_ins.empty or 'i_id' not in f_ins.columns:
        return px.bar(title="No data available for institutions.")
    
    inst_counts = f_ins.groupby(['i_id', 'name', 'country'])['work_id'].nunique().reset_index(name='works_count')
    top_15_inst = inst_counts.sort_values(by='works_count', ascending=False).head(15).copy()
    
    top_15_inst['short_name'] = top_15_inst['name'].apply(lambda x: x[:28] + '...' if len(x) > 28 else x)
    
    valid_concepts = f_concepts[f_concepts['level'] != 0].copy() if not f_concepts.empty else pd.DataFrame()
    if not valid_concepts.empty:
        m_ic = f_ins[['work_id', 'i_id', 'name', 'country']].merge(
            valid_concepts[['work_id', 'level']], on='work_id', how='inner'
        )
        avg_level_df = m_ic.groupby('i_id')['level'].mean().reset_index(name='avg_concept_level')
        final_inst_df = top_15_inst.merge(avg_level_df, on='i_id', how='left').fillna({'avg_concept_level': 0})
    else:
        top_15_inst['avg_concept_level'] = 0
        final_inst_df = top_15_inst
        
    final_inst_df = final_inst_df.sort_values(by='works_count', ascending=True)
    
    fig = px.bar(
        final_inst_df, x='works_count', y='short_name', orientation='h',
        color='avg_concept_level', color_continuous_scale='Electric',
        hover_data=['name', 'country', 'avg_concept_level'],
        title="<b>2. Top 15 Active Institutions</b>",
        labels={'works_count': 'Publications', 'short_name': 'Institution', 'avg_concept_level': 'Avg Level'}
    )
    fig.update_layout(template="plotly_dark", height=600, yaxis=dict(tickfont=dict(size=10)))
    return fig

def plot_concepts_wordcloud(f_concepts):
    if f_concepts.empty or 'name' not in f_concepts.columns:
        fig, ax = plt.subplots(figsize=(10, 5)); ax.axis('off')
        fig.patch.set_facecolor('#0e1117'); ax.set_facecolor('#0e1117')
        return fig
        
    concept_counts = f_concepts['name'].value_counts().to_dict()
    if not concept_counts:
        fig, ax = plt.subplots(figsize=(10, 5)); ax.axis('off')
        fig.patch.set_facecolor('#0e1117'); ax.set_facecolor('#0e1117')
        return fig

    wordcloud = WordCloud(width=1000, height=500, background_color='#0e1117', colormap='plasma', max_words=100).generate_from_frequencies(concept_counts)
    
    fig, ax = plt.subplots(figsize=(12, 6))
    ax.imshow(wordcloud, interpolation='bilinear'); ax.axis('off')
    fig.patch.set_facecolor('#0e1117'); ax.set_facecolor('#0e1117')
    plt.tight_layout(pad=0)
    return fig

def plot_ins_cons_heatmap(f_ins, f_concepts):
    if f_ins.empty or f_concepts.empty:
        fig = go.Figure(); fig.update_layout(title="No data available", template="plotly_dark")
        return fig
        
    valid_concepts = f_concepts[f_concepts['score'] != 0].copy()
    if valid_concepts.empty:
        fig = go.Figure(); fig.update_layout(title="No valid concepts", template="plotly_dark")
        return fig
        
    merged_data = f_ins[['work_id', 'name', 'country']].merge(
        valid_concepts[['work_id', 'name', 'score']], on='work_id', suffixes=('_inst', '_concept')
    )
    if merged_data.empty: return go.Figure(layout=dict(title="No overlapping data", template="plotly_dark"))
        
    top_insts = merged_data['name_inst'].value_counts().nlargest(10).index.tolist()
    top_concepts = merged_data['name_concept'].value_counts().nlargest(10).index.tolist()
    heatmap_filtered = merged_data[merged_data['name_inst'].isin(top_insts) & merged_data['name_concept'].isin(top_concepts)]
    
    if heatmap_filtered.empty:
        fig = go.Figure(); fig.update_layout(title="Insufficient data for heatmap", template="plotly_dark")
        return fig

    pivot_df = heatmap_filtered.pivot_table(index='name_inst', columns='name_concept', values='score', aggfunc='mean').fillna(0)
    pivot_df.index = [x[:20] + '...' if len(x) > 20 else x for x in pivot_df.index]
    
    fig = go.Figure(data=go.Heatmap(
        z=pivot_df.values, x=pivot_df.columns.tolist(), y=pivot_df.index.tolist(),
        colorscale='Electric', colorbar=dict(title="Score")
    ))
    fig.update_layout(xaxis_title="Concepts", yaxis_title="Institutions", template="plotly_dark", height=550, xaxis=dict(tickangle=-45))
    return fig

# === Layout and Rendering of Visualizations ===
col1, col2 = st.columns(2)
with col1: st.plotly_chart(plot_concept_trends(f_concepts, f_works), use_container_width=True)
with col2: st.plotly_chart(plot_top_ins(f_ins, f_concepts), use_container_width=True)

col3, col4 = st.columns(2)
with col3:
    st.subheader("3. ☁️ Concepts Word Cloud")
    st.pyplot(plot_concepts_wordcloud(f_concepts))
with col4:
    st.subheader("4. 🗺️ Institutions vs Concepts Heatmap")
    st.plotly_chart(plot_ins_cons_heatmap(f_ins, f_concepts), use_container_width=True)
