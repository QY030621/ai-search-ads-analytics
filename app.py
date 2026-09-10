from pathlib import Path
import pandas as pd
import plotly.express as px
import streamlit as st
from src.data_validation import read_csv, ValidationError
from src.metrics import aggregate, filter_data, daily_trends
from src.diagnostics_ui import collect_diagnostics, render_diagnostics
from src.recommendations_ui import render_recommendations
from src.issues_ui import account_health, issue_cards, metric_guide, sync_selection, EXPLANATIONS

ROOT = Path(__file__).parent
st.set_page_config(page_title='LumaNest | Search Ads Analytics', layout='wide')
st.markdown('<style>' + (ROOT / 'src/visual.css').read_text(encoding='utf-8') + '</style>', unsafe_allow_html=True)
st.title('LumaNest · Search Ads Analytics')
st.caption('Personal Project / Simulated Dataset · 美国 DTC 家居收纳品牌 · Google Search Ads · USD')
st.caption('Target CPA $25.00 · Target ROAS 2.00× — 本项目模拟业务假设，不是行业标准。')

with st.sidebar:
    st.header('Navigation / 页面导航')
    st.markdown('''<nav aria-label="页面导航">
<p><a href="#overview" target="_self">Overview / 账户概览</a></p>
<p><a href="#issues" target="_self">Issues / 异常诊断</a></p>
<p><a href="#scenario-lab" target="_self">Scenario Lab / 模拟情景</a></p>
<p><a href="#performance-explorer" target="_self">Performance Explorer / 趋势与明细</a></p>
</nav>''', unsafe_allow_html=True)
    st.divider()
    st.header('Filters / 数据筛选')
    upload = st.file_uploader('上传模拟广告 CSV', type=['csv'], help='UTF-8；每天 × Campaign × Ad。最大 10 MB。')
    st.caption('未上传文件时使用内置的 168 行模拟数据。')
    st.download_button('下载示例 CSV', (ROOT / 'data/sample_ads.csv').read_bytes(), 'sample_ads.csv', 'text/csv')

try:
    data = read_csv(upload.getvalue() if upload else (ROOT / 'data/sample_ads.csv').read_bytes())
except ValidationError as exc:
    st.error(f'数据校验未通过：{exc}')
    st.info('请修正文件后重新上传。当前文件不会用于指标计算。')
    st.stop()

with st.sidebar:
    st.caption(f'已读取 {len(data):,} 行 · {"上传文件" if upload else "内置示例"}')
    dates = st.date_input('日期范围', (data.date.min().date(), data.date.max().date()),
                          min_value=data.date.min().date(), max_value=data.date.max().date())
    campaigns = st.multiselect('Campaign', sorted(data.campaign_id.unique()), default=sorted(data.campaign_id.unique()))
    st.caption('报告时区：America/Los_Angeles')

if len(dates) != 2:
    st.info('请选择完整的开始与结束日期。')
    st.stop()
selected = filter_data(data, dates[0], dates[1], campaigns)
if selected.empty:
    st.info('当前筛选没有数据，请选择至少一个 Campaign 或调整日期。')
    st.stop()

# Count coverage using the selected Campaigns' known ads, including absent ads.
known = data[data.campaign_id.isin(campaigns)]
expected = len(pd.date_range(*dates)) * known[['campaign_id', 'ad_id']].drop_duplicates().shape[0]
gaps = expected - len(selected)
st.caption(f'{dates[0]} — {dates[1]} · {len(campaigns)} Campaigns · {selected.ad_id.nunique()} Ads · {len(selected)} 行')
if gaps:
    st.warning(f'所选范围缺少 {gaps} 个 Ad 日期记录；以下仅汇总已有数据，未将缺失记录补为零，窗口不完整。')

with st.sidebar:
    diagnostic_results = collect_diagnostics(data, dates[1], campaigns, uploaded=upload is not None)

total = aggregate(selected).iloc[0]
def show(value, kind='number'):
    if pd.isna(value):
        return 'N/A'
    if kind == 'money':
        return f'${value:,.2f}'
    if kind == 'percent':
        return f'{value:.2f}%'
    if kind == 'ratio':
        return f'{value:.2f}×'
    return f'{value:,.0f}'

sync_selection(diagnostic_results)
account_health(total, diagnostic_results, dates)
st.divider()
issues_area = st.container()
st.divider()
metric_guide()
st.subheader('Performance Explorer / 趋势与明细', anchor='performance-explorer')
st.caption('深入查看趋势与 Campaign / Ad 明细。')
with st.expander('全部指标 / All metrics'):
    top = [('cost', 'Spend', 'money'), ('conversion_value', 'Conversion value', 'money'),
           ('conversions', 'Purchases', 'number'), ('CPA', 'CPA', 'money'), ('ROAS', 'ROAS', 'ratio')]
    for col, (field, label, kind) in zip(st.columns(5), top):
        col.metric(label, show(total[field], kind), help=EXPLANATIONS.get(field))
    secondary = [('impressions', 'Impressions', 'number'), ('clicks', 'Clicks', 'number'),
                 ('CTR', 'CTR', 'percent'), ('CPC', 'CPC', 'money'), ('CPM', 'CPM', 'money'), ('CVR', 'CVR', 'percent')]
    for col, (field, label, kind) in zip(st.columns(6), secondary):
        col.metric(label, show(total[field], kind), help=EXPLANATIONS.get(field))
        if field in EXPLANATIONS:
            col.caption(EXPLANATIONS[field])

st.subheader('每日趋势')
metric = st.selectbox('趋势指标', ['cost', 'conversions', 'CPA', 'ROAS', 'CTR', 'CPC', 'CPM', 'CVR'],
                      format_func=lambda x: {'cost': 'Spend (USD)', 'conversions': 'Purchases'}.get(x, x))
daily = daily_trends(data, dates[0], dates[1], campaigns)
if daily.coverage.ne('完整').any():
    st.caption('趋势中的部分数据或缺失日期已断开，不表示真实下降或零投放。')
unit = 'USD' if metric in ['cost', 'CPA', 'CPC', 'CPM'] else '%' if metric in ['CTR', 'CVR'] else '×' if metric == 'ROAS' else '次'
fig = px.line(daily, x='date', y=metric, color='campaign_id', markers=True,
              labels={'date': '', metric: f'{metric} ({unit})', 'campaign_id': 'Campaign'},
              color_discrete_sequence=['#1E40AF', '#0F766E', '#B45309'], template='plotly_white')
fig.update_traces(connectgaps=False)
fig.update_layout(height=245, margin=dict(l=10, r=10, t=15, b=10), legend=dict(orientation='h', y=1.15))
st.plotly_chart(fig, width='stretch')

def table(frame):
    ids = [c for c in ['campaign_id', 'ad_id'] if c in frame.columns]
    frame = frame[ids + ['cost', 'conversions', 'CPA', 'ROAS', 'CTR', 'CPC', 'CPM', 'CVR', 'impressions', 'clicks', 'conversion_value']]
    formats = {field: (lambda v: show(v)) for field in ['impressions', 'clicks', 'conversions']}
    for field in ['cost', 'conversion_value', 'CPA', 'CPC', 'CPM']:
        formats[field] = lambda v: show(v, 'money')
    for field in ['CTR', 'CVR']:
        formats[field] = lambda v: show(v, 'percent')
    formats['ROAS'] = lambda v: show(v, 'ratio')
    st.dataframe(frame.style.format(formats, na_rep='N/A'), hide_index=True, width='stretch', row_height=30)

st.subheader('Campaign 汇总')
table(aggregate(selected, ['campaign_id']))
st.subheader('Ad 表现')
table(aggregate(selected, ['campaign_id', 'ad_id']))
with st.expander('指标口径与模拟数据说明'):
    st.markdown('''**所有汇总先累加原始值，再计算比率；分母为零显示 N/A。**

CTR = 点击 / 展示；CPC = 花费 / 点击；CPM = 花费 / 展示 × 1,000；
CVR = 购买 / 点击；CPA = 花费 / 购买；ROAS = 转化价值 / 花费。

转化价值是购买金额，不是利润。零购买且有花费时，CPA 为 N/A，ROAS 为 0。
示例每次购买固定 $50；7 天点击归因、按点击日期记录，2026-09-05 冻结，假设已完整回传。
上传数据须遵循相同归因和完整回传假设；系统无法从汇总 CSV 验证归因是否正确。
数据全部为模拟数据，不代表真实账户或经营成果。''')

with st.expander('Advanced details / 完整诊断记录 · 含正常对照与数据不足'):
    render_diagnostics(data, dates[1], campaigns, uploaded=upload is not None, results=diagnostic_results)

with issues_area:
    st.subheader('Issues Detected / 异常诊断', anchor='issues')
    st.write('查看已触发的异常及证据。')
    with st.expander('AI Recommendations / AI 优化建议 · 生成与状态'):
        recommendation_result = render_recommendations(diagnostic_results, show_details=False)
    st.caption('卡片中的建议来源：'+recommendation_result['source']+'。生成或重试后，各卡片会同步更新。')
    issue_cards(diagnostic_results, recommendation_result, is_sample=upload is None)
