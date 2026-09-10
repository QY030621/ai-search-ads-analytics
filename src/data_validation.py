"""Validate the Phase 1 CSV contract, without business diagnosis."""
import csv
import io
import numpy as np
import pandas as pd
from src.metrics import RAW

COLUMNS = ['date', 'campaign_id', 'ad_id', 'currency', *RAW]


class ValidationError(ValueError):
    pass


def read_csv(source):
    try:
        payload = source.read() if hasattr(source, 'read') else source
        text = payload.decode('utf-8-sig') if isinstance(payload, bytes) else payload
        rows = list(csv.reader(io.StringIO(text), strict=True))
        if not rows or len(rows) < 2:
            raise ValidationError('CSV 不能为空，必须包含表头和数据行。')
        if len(set(rows[0])) != len(rows[0]):
            raise ValidationError('CSV 存在重复列名。')
        if any(len(row) != len(rows[0]) for row in rows[1:]):
            raise ValidationError('CSV 行的列数不一致，请检查分隔符或空白行。')
        frame = pd.read_csv(io.StringIO(text), dtype=str, keep_default_na=False)
    except (UnicodeError, csv.Error, pd.errors.ParserError, pd.errors.EmptyDataError, TypeError) as exc:
        raise ValidationError('无法读取 CSV，请使用 UTF-8 编码、逗号分隔的文件。') from exc
    return validate(frame)


def validate(frame):
    missing = sorted(set(COLUMNS) - set(frame.columns))
    if missing:
        raise ValidationError('缺少必需字段：' + ', '.join(missing))
    if frame.empty:
        raise ValidationError('CSV 没有数据行。')
    data = frame[COLUMNS].copy()
    if data.isna().any().any() or data.astype(str).apply(lambda c: c.str.strip().eq('')).any().any():
        raise ValidationError('必需字段不能缺失或为空。')
    for field in ['campaign_id', 'ad_id', 'currency']:
        data[field] = data[field].astype(str).str.strip()
    if not data.currency.eq('USD').all():
        raise ValidationError('currency 仅支持 USD。')
    dates = data.date.astype(str)
    parsed = pd.to_datetime(dates, format='%Y-%m-%d', errors='coerce')
    if not dates.str.fullmatch(r'\d{4}-\d{2}-\d{2}').all() or parsed.isna().any():
        raise ValidationError('date 必须为有效的 YYYY-MM-DD 日期。')
    data['date'] = parsed
    for field in RAW:
        values = pd.to_numeric(data[field], errors='coerce')
        if not np.isfinite(values).all() or values.lt(0).any():
            raise ValidationError(f'{field} 必须为有限的非负数。')
        if field in ['impressions', 'clicks', 'conversions']:
            if values.mod(1).ne(0).any() or values.gt(2**53 - 1).any():
                raise ValidationError(f'{field} 必须为可精确表示的非负整数。')
            values = values.astype('int64')
        elif not np.isclose(values * 100, np.round(values * 100), rtol=0, atol=1e-7).all():
            raise ValidationError(f'{field} 最多保留两位小数。')
        data[field] = values
    if data.clicks.gt(data.impressions).any():
        raise ValidationError('本模拟口径要求 clicks 不超过 impressions。')
    if data.conversions.gt(data.clicks).any():
        raise ValidationError('本模拟口径要求 conversions 不超过 clicks。')
    if (data.conversions.eq(0) & data.conversion_value.gt(0)).any():
        raise ValidationError('线上购买口径下，conversions 为 0 时 conversion_value 必须为 0。')
    if data.duplicated(['date', 'campaign_id', 'ad_id']).any():
        raise ValidationError('存在重复的 date + campaign_id + ad_id，不能重复汇总。')
    if data.groupby('ad_id').campaign_id.nunique().gt(1).any():
        raise ValidationError('同一 ad_id 不能归属于多个 Campaign。')
    return data.sort_values(['date', 'campaign_id', 'ad_id']).reset_index(drop=True)
