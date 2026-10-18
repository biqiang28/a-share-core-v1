import datetime as dt
import pandas as pd
import streamlit as st

st.set_page_config(page_title='A股二板成核2.2｜原型',page_icon='📈',layout='wide')
st.title('A股二板成核2.2｜自动筛选原型 V1.0')
st.caption('免费数据 · 盘后研究 · 不接券商、不自动交易、不提供实时买点')

@st.cache_data(ttl=900,show_spinner=False)
def load_pool(day):
    import akshare as ak
    data=ak.stock_zt_pool_em(date=day.strftime('%Y%m%d'))
    if data is None or data.empty:
        raise ValueError('该日期未返回涨停池数据，可能是非交易日、尚未收盘或接口暂时不可用。')
    return data

def numeric(s):
    return pd.to_numeric(s,errors='coerce')

def time_num(s):
    v=str(s).replace(':','').strip().split('.')[0]
    if v.isdigit():
        return int(v.zfill(6))
    return None

def analyze(df):
    required=['代码','名称','连板数']
    absent=[c for c in required if c not in df.columns]
    if absent:
        raise ValueError('数据字段发生变化，缺少：'+ '、'.join(absent))
    pool=df.copy()
    pool['连板数']=numeric(pool['连板数'])
    pool=pool[pool['连板数']==2].copy()
    if pool.empty: return pool
    # 仅使用已获得的量化字段形成可核实的局部评分，绝不假装完整100分。
    pool['已核实局部得分']=0.0
    pool['可评分满分']=0
    if '首次封板时间' in pool:
        t=pool['首次封板时间'].map(time_num)
        # 早封板是参考项，并非绝对越早越好。
        points=t.map(lambda x: 10 if x is not None and x<=100000 else (6 if x is not None and x<=110000 else (3 if x is not None else 0)))
        pool['已核实局部得分']+=points
        pool['可评分满分']+=10
    if '炸板次数' in pool:
        breaks=numeric(pool['炸板次数'])
        pool['已核实局部得分']+=breaks.map(lambda x: 10 if pd.notna(x) and x==0 else (6 if pd.notna(x) and x==1 else (2 if pd.notna(x) and x==2 else 0)))
        pool['可评分满分']+=10
    if '换手率' in pool:
        rate=numeric(pool['换手率'])
        # 换手率仅是信息，不机械地把高换手当作好承接。
        pool['换手率（供人工判断）']=rate
    pool=pool.sort_values(['已核实局部得分','代码'],ascending=[False,True])
    return pool

with st.sidebar:
    st.header('筛选设置')
    day=st.date_input('行情日期（建议已收盘交易日）',value=dt.date.today(),max_value=dt.date.today())
    st.info('免费涨停池数据可能延迟、停用或字段变更。请先核实日期与完整性。')
    run=st.button('🔎 开始自动筛选',type='primary',use_container_width=True)

if not run:
    st.info('选择交易日期后，点击左侧「开始自动筛选」。手机上点击左上角箭头可打开设置。')
    st.subheader('三层确认状态')
    st.write('第一层：主线与梯队 → **待核实**（当前免费接口只提供行业代理信息）')
    st.write('第二层：真正二板候选 → **待运行**；核心100分 → **只显示可验证的局部得分**')
    st.write('第三层：分时放量、缩量分歧、强回封 → **未接入实时分钟数据，不能确认**')
    st.stop()

try:
    with st.spinner('正在获取免费涨停池数据…'):
        raw=load_pool(day)
    st.success(f'获取成功：{day}，涨停池 {len(raw)} 条（接口返回数，非全市场涨停家数保证值）。')
    if day==dt.date.today():
        st.warning('当日数据可能尚未最终更新，尤其盘中不能据此确认连续二板。')
    c1,c2,c3=st.columns(3)
    c1.metric('接口涨停池记录',len(raw))
    boards=numeric(raw['连板数']) if '连板数' in raw else pd.Series(dtype=float)
    c2.metric('连续二板候选',int((boards==2).sum()))
    c3.metric('买点状态','未确认')
    st.subheader('第一层｜板块观察（仅行业代理，不等于真实题材）')
    if '所属行业' in raw:
        sectors=raw.groupby('所属行业',dropna=False).agg(该行业涨停数=('代码','count'),该行业二板数=('连板数',lambda s:int((numeric(s)==2).sum()))).sort_values(['该行业涨停数','该行业二板数'],ascending=False)
        st.dataframe(sectors.head(25),use_container_width=True)
        st.warning('「所属行业」不是低空经济、密码安全等概念板块。当前无法自动核实具体题材、消息催化和同步封板，第一层保持「待核实」。')
    else:
        st.warning('接口未提供所属行业字段，第一层无法自动判断。')
    st.subheader('第二层｜真正2天2板候选')
    candidates=analyze(raw)
    if candidates.empty:
        st.warning('本次数据没有发现连板数=2的记录。若数据不完整，不能据此断言市场没有二板。')
    else:
        preferred=['代码','名称','所属行业','首次封板时间','最后封板时间','炸板次数','换手率','成交额','连板数','已核实局部得分','可评分满分']
        st.dataframe(candidates[[c for c in preferred if c in candidates.columns]],use_container_width=True,hide_index=True)
        st.caption('局部得分仅为封板时间与炸板次数的启发式参考，不是完整100分，也不是上涨概率；不得据此直接选唯一核心。')
        csv=candidates.to_csv(index=False).encode('utf-8-sig')
        st.download_button('下载二板候选CSV',csv,file_name=f'二板候选_{day}.csv',mime='text/csv')
    st.subheader('第三层｜买点确认')
    st.warning('缺少竞价、逐分钟量价、细分题材同步与历史盘口证据：买点未确认。**只观察，不买入。**')
    st.error('最终结论：当前数据不足以确认唯一可交易核心；今天没有已验证的合格买点，空仓。')
    with st.expander('查看原始行情数据与字段'):
        st.write(list(raw.columns))
        st.dataframe(raw,use_container_width=True)
except Exception as exc:
    st.error('免费行情接口未成功返回有效数据。系统不会伪造候选或评分。')
    st.code(f'{type(exc).__name__}: {exc}')
    st.info('可尝试选择最近一个已收盘交易日，或稍后重试。接口故障不代表当天没有机会。')
