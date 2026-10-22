import datetime as dt
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

st.set_page_config(page_title='二板次日统计｜原型', page_icon='📊', layout='wide')
st.title('二板次日表现统计｜原型 V0.1')
st.caption('免费数据 · 仅统计历史表现 · 不输出买入结论')


@st.cache_data(ttl=86400, show_spinner=False)
def fetch_zt(day_str):
    import akshare as ak
    return ak.stock_zt_pool_em(date=day_str)


@st.cache_data(ttl=86400, show_spinner=False)
def fetch_prev(day_str):
    import akshare as ak
    return ak.stock_zt_pool_previous_em(date=day_str)


def pick_col(df, candidates):
    """在候选字段名中找到实际存在的第一个，找不到返回 None。"""
    for c in candidates:
        if c in df.columns:
            return c
    return None


def build_pairs(zt_df, prev_df):
    """把第 T 日二板与第 T+1 日的次日表现按代码匹配。"""
    code_col = pick_col(zt_df, ['代码'])
    board_col = pick_col(zt_df, ['连板数'])
    if code_col is None or board_col is None:
        raise ValueError('第 T 日涨停池缺少「代码」或「连板数」字段')

    boards = zt_df[zt_df[board_col].apply(pd.to_numeric, errors='coerce') == 2]
    two = boards[[code_col]].rename(columns={code_col: '代码'}).copy()
    two['代码'] = two['代码'].astype(str).str.zfill(6)

    p_code = pick_col(prev_df, ['代码'])
    p_chg = pick_col(prev_df, ['涨跌幅'])
    p_zb = pick_col(prev_df, ['是否炸板', '昨日炸板', '炸板次数'])
    if p_code is None or p_chg is None:
        raise ValueError(f'昨日涨停池缺少必要字段，实际字段：{list(prev_df.columns)}')

    nxt = prev_df[[c for c in [p_code, p_chg, p_zb] if c is not None]].copy()
    nxt = nxt.rename(columns={p_code: '代码', p_chg: '次日涨跌幅'})
    nxt['代码'] = nxt['代码'].astype(str).str.zfill(6)
    nxt['次日涨跌幅'] = pd.to_numeric(nxt['次日涨跌幅'], errors='coerce')

    merged = two.merge(nxt, on='代码', how='left', indicator=True)
    merged['匹配'] = merged['_merge'].eq('both')
    merged = merged.drop(columns='_merge')
    return merged


def summarize(merged):
    matched = merged[merged['匹配']]
    n = len(matched)
    total = len(merged)
    if n == 0:
        return {'二板总数': total, '匹配样本': 0}

    chg = matched['次日涨跌幅']
    return {
        '二板总数': total,
        '匹配样本': n,
        '未匹配样本': total - n,
        '次日平均涨跌幅(%)': round(chg.mean(), 2),
        '次日中位数涨跌幅(%)': round(chg.median(), 2),
        '次日上涨比例(%)': round((chg > 0).mean() * 100, 1),
        '次日涨停(≥9.8%)比例(%)': round((chg >= 9.8).mean() * 100, 1),
        '次日跌超5%比例(%)': round((chg <= -5).mean() * 100, 1),
    }


with st.sidebar:
    st.header('统计设置')
    day = st.date_input('第 T 日（二板日）', value=dt.date.today() - dt.timedelta(days=1),
                        max_value=dt.date.today())
    st.caption('次日 T+1 自动取下一个交易日的「昨日涨停股池」，需要 T+1 已收盘。')
    run = st.button('📊 开始统计', type='primary', use_container_width=True)

if not run:
    st.info('选择第 T 日后点击「开始统计」。需确保 T+1 日已收盘，否则次日数据不完整。')
    st.stop()

day_str = day.strftime('%Y%m%d')
try:
    with st.spinner('正在获取涨停池数据…'):
        zt = fetch_zt(day_str)
        # T+1 的昨日涨停股池：传入 T+1 日期，返回的是 T 日涨停股在 T+1 的表现
        next_day = day + dt.timedelta(days=1)
        prev = fetch_prev(next_day.strftime('%Y%m%d'))

    if zt is None or zt.empty:
        raise ValueError('第 T 日未返回涨停池数据（可能是非交易日或接口异常）')
    if prev is None or prev.empty:
        raise ValueError('T+1 日未返回昨日涨停股池（可能尚未收盘或非交易日）')

    st.caption(f'接口返回字段（昨日涨停池）：{list(prev.columns)}')

    merged = build_pairs(zt, prev)
    s = summarize(merged)

    st.subheader('统计结果')
    cols = st.columns(3)
    keys = list(s.keys())
    for i, k in enumerate(keys):
        cols[i % 3].metric(k, s[k])

    if s.get('匹配样本', 0) < 30:
        st.warning('匹配样本少于 30，统计结果波动很大，不建议据此判断规律。')
    if s.get('未匹配样本', 0) > 0:
        st.info(f"有 {s['未匹配样本']} 只二板在次日表现中未匹配，请检查是否为接口缺失或代码格式问题。")

    st.subheader('明细')
    st.dataframe(merged, use_container_width=True, hide_index=True)
    st.download_button(
        '下载明细CSV',
        merged.to_csv(index=False).encode('utf-8-sig'),
        file_name=f'二板次日_{day_str}.csv',
        mime='text/csv',
    )
    st.caption('仅为历史统计，不代表未来表现，不构成投资建议。')

except Exception as exc:
    st.error('统计失败，未生成结果。')
    st.code(f'{type(exc).__name__}: {exc}')
