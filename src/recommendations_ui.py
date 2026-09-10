from src.api_config import load_api_config
import streamlit as st
from src.recommendations import prepare,generate,fingerprint


def render_recommendations(diagnostics, show_details=True):
    st.subheader('AI Recommendations / AI 优化建议')
    st.caption('Personal Project / Simulated Dataset · 仅使用结构化诊断；数字直接引用，不重新计算。父子级异常可能反映同一问题，不重复执行实验。')
    payload=prepare(diagnostics)
    model,key,base_url,config_error=load_api_config()
    if config_error:
        st.caption(config_error)
    token=fingerprint(payload,model,base_url)
    if st.session_state.get('recommendation_token')!=token:
        st.session_state['recommendation_token']=token
        st.session_state['recommendation_result']=generate(payload)
    if payload['events']:
        st.caption('点击后仅将已触发异常的诊断发送至配置的 AI 服务商；不发送原始CSV。AI在受约束的假设、检查和实验组合中选择，不自由改写数字。')
        if not key or not model:
            st.caption('尚未配置API，仍可查看下方规则备用建议。配置说明见 README。')
        if st.button('生成 / 重试 AI 建议'):
            with st.spinner('正在生成建议…'):
                st.session_state['recommendation_result']=generate(payload,model,key,True,base_url=base_url)
        result=st.session_state['recommendation_result']
        st.write(result['source'])
        st.caption(result['message'])
        for rec in result['recommendations'] if show_details else []:
            event=rec['event']
            with st.expander(f"{event['level']} · {event['object']} · {event['rule']}"):
                st.caption(f"当前窗口：{event['current_window']} ｜ 对比窗口：{event['previous_window']}")
                for heading,value in rec['sections'].items():
                    st.markdown(f'**{heading}**')
                    st.text(value)
    else:
        st.caption('没有已触发异常，不强行生成优化问题。')
    if payload['checks']:
        with st.expander('数据不足：仅查看检查建议'):
            for item in payload['checks']:
                st.text(f"{item['level']} · {item['object']} · {item['rule']}\n{item['reason']}")
            st.text('请补齐相应窗口记录、核对完整回传状态，并等待规则要求的数据量。当前不生成原因判断或投放实验结论。')
    return st.session_state['recommendation_result']
