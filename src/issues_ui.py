"""Presentation only: display frozen diagnosis values and recommendation sections."""
import pandas as pd
import streamlit as st

EXPLANATIONS = {
    'CTR':'有多少次展示带来了点击',
    'CPC':'每次点击多少钱',
    'CVR':'点进去后有多少人买',
    'CPA':'平均每次购买所对应的广告成本',
    'ROAS':'每投入 $1 广告费所带来的销售额（不是利润）',
    'CPM':'每千次展示多少钱',
}
FIELDS = {
    'CTR 下滑':['CTR'],
    'CPC 上升并伴随 CPA 恶化':['CPC','CPA'],
    '有花费但零转化':['cost','conversions'],
}
PLAIN = {
    'CTR 下滑':'展示转成点击的比例下降了，具体原因还需要核查。',
    'CPC 上升并伴随 CPA 恶化':'点击和获取订单都变贵了；共同变化不等于已确认原因。',
    '有花费但零转化':'当前窗口花了广告费，但没有记录到购买。',
}


def display_value(field,value):
    if pd.isna(value): return 'N/A'
    if field in ('CTR','CVR'): return f'{value:.2f}%'
    if field in ('cost','CPC','CPM','CPA','conversion_value'): return f'${value:,.2f}'
    if field=='ROAS': return f'{value:.2f}×'
    return f'{value:,.0f}'


def triggered(diagnostics):
    return [(item,record) for item in diagnostics for record in item['records'] if record['status']=='触发']


def account_health(total,diagnostics,dates):
    st.subheader('Account Health / 账户概览', anchor='overview')
    st.caption('快速了解账户整体表现。')
    alerts=triggered(diagnostics)
    entries=[('Spend',display_value('cost',total.cost),'所选期间内的广告总支出'),
             ('Purchases',display_value('conversions',total.conversions),'所选期间记录的购买次数'),
             ('CPA',display_value('CPA',total.CPA),EXPLANATIONS['CPA']),
             ('ROAS',display_value('ROAS',total.ROAS),EXPLANATIONS['ROAS']),
             ('Rule Alerts',str(len(alerts)),'当前诊断窗口内触发的规则提示数量')]
    for column,(label,value,explanation) in zip(st.columns(5),entries):
        with column.container(border=True, key='health_'+label):
            st.markdown(f'**{label}**')
            st.markdown(f'### {value}')
            st.caption(explanation)
    st.caption(f'Spend / Purchases / CPA / ROAS：所选期间 {dates[0]} — {dates[1]}。仅代表已有数据，不是账户健康评分。')
    if diagnostics:
        st.caption(f"Rule Alerts：当前 {diagnostics[0]['current_window']}，对比 {diagnostics[0]['previous_window']}。含 Campaign 与 Ad 两个层级；父子级提示可能来自同一问题，不能相加理解为独立业务损失。")


def metric_guide():
    with st.expander('指标快速读懂 / Metric guide', expanded=False):
        for metric,meaning in EXPLANATIONS.items():
            st.markdown(f'**{metric}**：{meaning}')
        st.caption('CTR / CVR 是按展示与点击记录计算的比例，不代表去重人数。N/A 表示缺失或分母为零，不能当作真实 0。')


SCENARIOS = [
    ('CTR Decline', ('Ad', 'C02 / C02_A01', 'CTR 下滑')),
    ('CPC Rise + CPA Deterioration', ('Ad', 'C03 / C03_A01', 'CPC 上升并伴随 CPA 恶化')),
    ('Spend but Zero Conversion', ('Ad', 'C03 / C03_A02', '有花费但零转化')),
]


def alert_key(item, record):
    return (item['level'], item['object'], record['rule'])


def select_alert(key, diagnostics, source="card"):
    st.session_state["selection_source"] = source
    st.session_state['selected_alert'] = key
    st.session_state['diagnostic_choice'] = next(
        i for i,item in enumerate(diagnostics) if (item['level'],item['object']) == key[:2])


def sync_selection(diagnostics):
    valid = {alert_key(item,record) for item,record in triggered(diagnostics)}
    key = st.session_state.get('selected_alert')
    if key is not None and key not in valid:
        st.session_state.pop('selected_alert', None)
    choice = st.session_state.get('diagnostic_choice', 0)
    if choice not in range(len(diagnostics)):
        st.session_state['diagnostic_choice'] = 0
    key = st.session_state.get('selected_alert')
    if key is not None:
        st.session_state['diagnostic_choice'] = next(
            i for i,item in enumerate(diagnostics) if (item['level'],item['object']) == key[:2])


def scenario_lab(diagnostics, is_sample):
    st.markdown('#### Scenario Lab / 模拟情景区')
    st.caption('快速演示典型广告异常场景。用于快速演示典型异常分析流程，不会修改原始数据。')
    valid = {alert_key(item,record) for item,record in triggered(diagnostics)}
    for column,(label,key) in zip(st.columns(3),SCENARIOS):
        with column:
            st.button(label, key='scenario_'+key[2], on_click=select_alert,
                      args=(key,diagnostics,"scenario"), disabled=not is_sample or key not in valid,
                      width='stretch')
            st.caption(key[1])
    if not is_sample:
        st.caption('上传文件模式：模拟案例入口不可用；仍可查看上传数据自己的异常卡片。')
    elif any(key not in valid for _,key in SCENARIOS):
        st.caption('灰色入口：对应对象不在当前筛选中，或该窗口未触发此规则。查看全部案例可选择全部 Campaign，并将结束日设为 2026-08-28。')


def issue_cards(diagnostics,recommendations,is_sample=True):
    alerts=triggered(diagnostics)
    scenario_lab(diagnostics,is_sample)
    lookup={(rec['event']['level'],rec['event']['object'],rec['event']['rule']):rec
            for rec in recommendations['recommendations']}
    selected=st.session_state.get('selected_alert')
    for item,record in alerts:
        if alert_key(item,record)==selected and st.session_state.get("selection_source")=="scenario":
            st.markdown('#### View evidence / 查看证据')
            st.text(f"当前对象：{item['level']} · {item['object']} · {record['rule']}")
            render_issue_detail(item,record,recommendations,lookup)
    if not alerts:
        st.write('当前没有已触发的规则提示。数据不足或未满足正常对照条件，不等于账户完全正常；请查看下方完整规则记录。')
        return
    for item,record in alerts:
        key=alert_key(item,record)
        with st.container(border=True, key='issue_'+'|'.join(key)):
            st.text(f"{item['level']} · {item['object']}")
            st.caption('Rule type / 规则类型：'+record['rule'])
            st.markdown(f"#### {record['rule']}")
            st.caption('Previous → Current / 对比窗口 → 当前窗口')
            for field in FIELDS[record['rule']]:
                label={'cost':'Spend','conversions':'Purchases'}.get(field,field)
                st.text(f"{label}　{display_value(field,item['previous'][field])} → {display_value(field,item['current'][field])}")
            st.write(PLAIN[record['rule']])
            st.button(f"View evidence / 查看证据 · {item['level']} {item['object']}",
                      key='evidence_'+'|'.join(key),on_click=select_alert,args=(key,diagnostics))
            if key==selected:
                st.caption('已选中：Advanced details 已同步到此对象。')
                if st.session_state.get('selection_source')!='scenario':
                    render_issue_detail(item,record,recommendations,lookup)


def render_issue_detail(item,record,recommendations,lookup):
    fields=FIELDS[record['rule']]
    with st.container(border=True, key='observed_fact'):
        st.markdown('**Observed Fact / 数据事实**')
        st.markdown('##### Previous → Current / 发生了什么与变化幅度')
        st.text(record['confirmed'])
        if record['rule']=='有花费但零转化':
            for field in fields:
                p,c=item['previous'][field],item['current'][field]
                if pd.isna(p) or pd.isna(c):
                    st.text(f'{field} 变化幅度：N/A（缺少可比记录）')
                else:
                    st.text(f'{field} 绝对变化：{display_value(field,c-p)}（仅展示窗口差值，不参与规则判断）')
        st.markdown('##### Evidence / 数据证据')
        st.caption(f"当前窗口：{item['current_window']}\n\n对比窗口：{item['previous_window']}")
        evidence_fields=list(dict.fromkeys(fields+['impressions','clicks','cost','conversions','CPA','ROAS']))
        rows=['| 指标 | Previous | Current |','| :--- | ---: | ---: |']
        for field in evidence_fields:
            previous=display_value(field,item['previous'][field]).replace('$',r'\$')
            current=display_value(field,item['current'][field]).replace('$',r'\$')
            rows.append(f"| {field} | {previous} | {current} |")
        st.markdown('\n'.join(rows))
        st.text('为什么被标记：'+record['trigger'])
        st.text('数据量是否充足：'+record['sufficient'])
        st.text(record['reason'])
        st.caption('阈值来自已冻结的项目规则假设，不是行业标准。')
        st.markdown('##### What we know / 可以确定的事实')
        st.text(record['confirmed'])
        st.markdown('##### What we cannot conclude / 目前不能下的结论')
        st.text(record['unknown'])
    with st.container(border=True, key='possible_cause'):
        st.markdown('**Possible Cause / 可能原因 · 待验证**')
        st.caption('以下用于安排检查，不是已经证实的归因。')
        st.caption(recommendations['source'])
        rec=lookup.get((item['level'],item['object'],record['rule']))
        if rec is None:
            st.write('当前没有对应建议，请先查看数据证据与完整规则记录。')
        else:
            sections=rec['sections']
            for heading,key in [('Possible causes / 可能原因','可能原因'),
                                ('What to check / 建议检查','还需要检查什么'),
                                ('Suggested experiment / 建议实验','建议做什么实验')]:
                st.markdown('##### '+heading)
                st.text(sections[key])
            st.markdown('**实验后看什么 / 验证指标**')
            st.text(sections['验证指标'])
            st.caption(sections['判断边界'])
