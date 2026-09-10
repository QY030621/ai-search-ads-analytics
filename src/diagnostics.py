"""Phase 1 deterministic rules. No causal inference or optimization actions."""
from datetime import timedelta
import pandas as pd
from src.metrics import aggregate

RULES = {
 'CTR 下滑': '两窗各展示≥1,000、点击≥50，基准CTR>0；CTR相对下降≥30%。',
 'CPC 上升并伴随 CPA 恶化': '两窗各点击≥200、购买≥10，基准CPC/CPA>0；CPC及CPA各上升≥25%，且当前CPA>$25。',
 '有花费但零转化': '当前完整7天：花费≥$50、点击≥50、购买=0；转化已完整回传。',
 '正常对照': '相关规则可评估、无已定义异常，且当前CPA≤$25、ROAS≥2.0×。',
}
UNKNOWN = '无法从汇总数据确认文案、搜索需求、竞价、流量质量、落地页或追踪配置中的具体原因；不证明统计显著性或业务因果。'


def metric_text(value):
    return 'N/A' if pd.isna(value) else f'{value:.2f}'


def windows(end):
    end = pd.Timestamp(end).normalize()
    return (pd.Timestamp(end.date()-timedelta(days=6)), end,
            pd.Timestamp(end.date()-timedelta(days=13)), pd.Timestamp(end.date()-timedelta(days=7)))


def diagnose(data, end, campaigns, complete=True):
    """Input must have passed Phase 2 validation. Coverage uses all known ads."""
    start, end, prior_start, prior_end = windows(end)
    results = []
    scope = data[data.campaign_id.isin(campaigns)]
    groups = [('Campaign', str(key), group) for key, group in scope.groupby('campaign_id')]
    groups += [('Ad', f'{key[0]} / {key[1]}', group) for key, group in scope.groupby(['campaign_id','ad_id'])]
    for level, obj, group in groups:
        current = group[group.date.between(start,end)]
        previous = group[group.date.between(prior_start,prior_end)]
        expected = group.ad_id.nunique()*7
        c, p = aggregate(current).iloc[0], aggregate(previous).iloc[0]
        coverage = len(current)==expected and len(previous)==expected
        records=[]
        def add(name, status, reason, confirmed):
            records.append(dict(rule=name,status=status,sufficient='不足 / 不可评估' if status=='数据不足' else '满足该规则评估条件',
                                trigger=RULES[name], reason=reason, confirmed=confirmed, unknown=UNKNOWN))
        common = f'当前记录{len(current)}/{expected}；对比记录{len(previous)}/{expected}；完整回传：{"已确认" if complete else "未确认"}。'
        if not complete or not coverage or min(c.impressions,p.impressions)<1000 or min(c.clicks,p.clicks)<50 or not p.CTR>0:
            add('CTR 下滑','数据不足',common+' 需要完整双窗口、足够展示/点击及正的基准CTR。','仅能报告已记录数据，不能判断CTR下滑。')
        else:
            # Cross multiplication preserves inclusive decimal threshold boundaries.
            hit = c.clicks*p.impressions*10 <= p.clicks*c.impressions*7
            change=(c.CTR/p.CTR-1)*100
            add('CTR 下滑','触发' if hit else '未触发',common,f'CTR {p.CTR:.2f}% → {c.CTR:.2f}%，相对变化{change:+.2f}%。')
        if not complete or not coverage or min(c.clicks,p.clicks)<200 or min(c.conversions,p.conversions)<10 or not p.CPC>0 or not p.CPA>0:
            add('CPC 上升并伴随 CPA 恶化','数据不足',common+' 需要两窗各≥200点击、≥10购买及正的基准CPC/CPA；零购买不计算CPA变化。','不能判断CPC和CPA是否同时恶化。')
        else:
            hit = (c.cost*p.clicks*4 >= p.cost*c.clicks*5 and c.cost*p.conversions*4 >= p.cost*c.conversions*5 and c.cost>25*c.conversions)
            evidence=f'CPC {p.CPC:.2f} → {c.CPC:.2f} USD（{(c.CPC/p.CPC-1)*100:+.2f}%）；CPA {p.CPA:.2f} → {c.CPA:.2f} USD（{(c.CPA/p.CPA-1)*100:+.2f}%）；CVR {p.CVR:.2f}% → {c.CVR:.2f}%。'
            evidence+=' 这里只确认数值共同变化，未确认业务原因。'
            add('CPC 上升并伴随 CPA 恶化','触发' if hit else '未触发',common,evidence)
        if not complete or len(current)!=expected:
            add('有花费但零转化','数据不足',common+' 此规则仅要求当前窗口完整，对比窗口不作为触发前提。','不能对当前完整窗口作结论。')
        elif c.conversions>0:
            add('有花费但零转化','未触发',common+' 当前有购买，不满足零购买条件。',f'当前已记录{c.conversions:g}次购买。')
        elif c.cost<50 or c.clicks<50:
            add('有花费但零转化','数据不足',common+' 当前花费需≥$50且点击≥50。','仅确认已有花费/点击与零购买记录，不判断效率异常。')
        else:
            add('有花费但零转化','触发',common+' 当前窗口满足最低花费与点击要求；无需完整对比窗口。',f'当前花费${c.cost:.2f}、{c.clicks:g}次点击、{c.conversions:g}次购买；CPA={metric_text(c.CPA)}，ROAS={metric_text(c.ROAS)}。')
        if any(r['status']=='触发' for r in records):
            add('正常对照','不适用','至少一条已定义异常触发。','不能标记正常对照。')
        elif any(r['status']=='数据不足' for r in records):
            add('正常对照','数据不足',common+' 相关规则尚不可评估。','不能把未得到异常结论当作正常。')
        elif c.CPA<=25 and c.ROAS>=2:
            add('正常对照','正常对照',common+' 无已定义异常，CPA及ROAS目标达标。','本窗口未发现已定义异常，目标达标；不等于账户完全健康。')
        else:
            add('正常对照','未满足','规则可评估，但CPA或ROAS未达到项目目标。','未触发已定义异常，但不满足正常对照条件；不新增第五类异常。')
        for r in records:
            if r['status']=='不适用': r['sufficient']='见各规则；正常判断不适用'
        results.append(dict(level=level,object=obj,current_window=f'{start.date()} — {end.date()}',
                            previous_window=f'{prior_start.date()} — {prior_end.date()}',
                            current=c,previous=p,records=records,
                            current_coverage=f'{len(current)}/{expected}', previous_coverage=f'{len(previous)}/{expected}'))
    return results
