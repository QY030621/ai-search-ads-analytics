"""Small, evidence-first Phase 3 UI."""
import pandas as pd
import streamlit as st
from src.diagnostics import diagnose


def collect_diagnostics(data, end, campaigns, uploaded=False):
    """Existing confirmation and diagnostic call, shared by the UI sections."""
    complete = st.checkbox('确认上传数据已完整回传（7天点击归因）', value=False) if uploaded else True
    if not uploaded:
        st.caption('内置模拟数据已按项目假设完整回传。')
    return diagnose(data,end,campaigns,complete)


def clear_card_selection():
    st.session_state.pop("selected_alert", None)


def render_diagnostics(data, end, campaigns, uploaded=False, results=None):
    st.subheader('Diagnostics / 异常诊断')
    st.caption('阈值均为项目规则假设，不是行业标准；最低数据量不代表统计显著性。Campaign 与 Ad 分别诊断，父子级提示不累计为独立业务问题。')
    st.caption('以日期筛选的结束日为当前窗口末日，取连续7天，对比之前7天；读取原始数据中的对比记录，不受筛选开始日裁剪。')
    if results is None:
        results=collect_diagnostics(data,end,campaigns,uploaded)
    summary=[]
    for item in results:
        alerts=[r['rule'] for r in item['records'] if r['status']=='触发']
        normal=item['records'][-1]
        summary.append({'层级':item['level'],'对象':item['object'],
                        '当前窗口':item['current_window'],'对比窗口':item['previous_window'],
                        '结果':'；'.join(alerts) if alerts else normal['status'],
                        '数据不足规则':'；'.join(r['rule'] for r in item['records'][:3] if r['status']=='数据不足') or '无'})
    st.dataframe(pd.DataFrame(summary),hide_index=True,width='stretch')
    choice=st.selectbox('查看诊断证据',range(len(results)),key='diagnostic_choice',on_change=clear_card_selection,format_func=lambda i:f"{results[i]['level']} · {results[i]['object']}")
    item=results[choice]
    st.write(f"对象：{item['level']} · {item['object']}")
    st.caption(f"当前窗口：{item['current_window']} ｜ 对比窗口：{item['previous_window']}")
    st.caption(f"记录完整性：当前 {item['current_coverage']}；对比 {item['previous_coverage']}。整窗缺失显示 N/A，部分记录仅为已知数据。")
    evidence=pd.DataFrame([item['previous'],item['current']],index=['对比窗口','当前窗口'])
    display_evidence = evidence.map(lambda value: 'N/A' if pd.isna(value) else f'{value:,.2f}')
    st.dataframe(display_evidence,width='stretch')
    st.caption('cost / conversion_value / CPC / CPM / CPA 单位为 USD；CTR / CVR 为百分比；ROAS 为倍数。缺失日期只展示已有记录汇总，不补零。')
    for record in item['records']:
        with st.expander(f"{record['rule']} · {record['status']}",expanded=record['status']=='触发'):
            st.write('触发规则：'+record['trigger'])
            st.write('数据量是否充足：'+record['sufficient'])
            st.write('评估依据：'+record['reason'])
            st.write('当前可以确认：'+record['confirmed'])
            st.write('当前不能确认：'+record['unknown'])

    return results
