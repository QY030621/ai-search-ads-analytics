"""Ratios are calculated only after additive measures have been summed."""
import pandas as pd

RAW = ['impressions', 'clicks', 'cost', 'conversions', 'conversion_value']
RATIOS = {'CTR': ('clicks', 'impressions', 100),
          'CPC': ('cost', 'clicks', 1), 'CPM': ('cost', 'impressions', 1000),
          'CVR': ('conversions', 'clicks', 100), 'CPA': ('cost', 'conversions', 1),
          'ROAS': ('conversion_value', 'cost', 1)}


def aggregate(data, by=None):
    if by:
        result = data.groupby(by, as_index=False, sort=True)[RAW].sum()
    else:
        result = data[RAW].sum(min_count=1).to_frame().T
    for name, (numerator, denominator, scale) in RATIOS.items():
        result[name] = result[numerator].div(result[denominator].where(result[denominator].ne(0))) * scale
    return result


def filter_data(data, start, end, campaigns):
    return data.loc[data.date.between(pd.Timestamp(start), pd.Timestamp(end))
                    & data.campaign_id.isin(campaigns)].copy()


def missing_days(data, start, end):
    """Coverage only; missing rows are never imputed as zero delivery."""
    expected = pd.date_range(start, end)
    return sum(len(expected.difference(group.date))
               for _, group in data.groupby(['campaign_id', 'ad_id']))


def daily_trends(data, start, end, campaigns):
    """Break lines when any known Ad-day is missing; never plot partial totals."""
    selected = filter_data(data, start, end, campaigns)
    daily = aggregate(selected, ['date', 'campaign_id'])
    index = pd.MultiIndex.from_product([pd.date_range(start, end), campaigns], names=['date', 'campaign_id'])
    daily = daily.set_index(['date', 'campaign_id']).reindex(index)
    observed = selected.groupby(['date', 'campaign_id']).size().reindex(index, fill_value=0)
    expected = data[data.campaign_id.isin(campaigns)].groupby('campaign_id').ad_id.nunique()
    required = pd.Series(index.get_level_values('campaign_id').map(expected).to_numpy(), index=index)
    daily['coverage'] = '完整'
    daily.loc[observed.eq(0), 'coverage'] = '缺失'
    daily.loc[observed.gt(0) & observed.lt(required), 'coverage'] = '部分数据'
    daily.loc[observed.lt(required), RAW + list(RATIOS)] = float('nan')
    return daily.reset_index()
