import streamlit as st
import pandas as pd
import re
from collections import Counter, defaultdict

st.markdown("""
<style>
    html, body, .stApp {
        background-color: #eef7ff !important;
        min-height: 100vh !important;
    }
    .block-container {
        background-color: transparent !important;
        padding-top: 12px !important;
        padding-left: 24px;
        padding-right: 24px;
        padding-bottom: 0rem !important;
    }
    header[data-testid="stHeader"] {
        display: none !important;
    }
    .stDeployButton,
    [data-testid="stHeaderActionElements"],
    div[class*="stHeader"] {
        display: none !important;
    }
    .stTextInput > div > div > input {
        border-width: 1px !important;
        border-color: #cbd5e1 !important;
        border-radius: 10px;
        font-size:16px;
    }
    .stat-card {
        border-radius:14px;
        padding:16px 8px;
        text-align:center;
        color:#fff;
    }
    .stat-green {background:#22b962;}
    .stat-orange {background:#ff9527;}
    .stat-orange2 {background:#f78a25;}
    .stat-red {background:#f23c3c;}
    .stat-label {font-size:16px;margin-bottom:6px;}
    .stat-value {font-size:40px;font-weight:900;}
    .pred-num {
        font-size:42px;
        color:#f23c3c;
        font-weight:900;
    }
    .tips-box {
        background: #fff3cd;
        border: 1px solid #ffeeba;
        border-radius: 10px;
        padding: 12px 16px;
        margin: 10px 0;
    }
    .warn-box {
        background: #ffebee;
        border: 1px solid #ef9a9a;
        border-radius: 10px;
        padding: 12px 16px;
        margin: 10px 0;
    }
    .monitor-box {
        background: #e8f5e9;
        border: 1px solid #a5d6a7;
        border-radius: 10px;
        padding: 12px 16px;
        margin: 10px 0;
    }
</style>
""", unsafe_allow_html=True)

st.set_page_config(page_title="固定5周期预测系统", layout="wide")

if 'history_list' not in st.session_state:
    st.session_state.history_list = []

# 修复：统计时跳过待分析，只计算有真实推荐的期数
def calc_streak_info(history):
    max_hit = 0
    max_miss = 0
    curr_hit = 0
    curr_miss = 0
    for row in history:
        pred = row["pred"]
        # 待分析不参与连中连错统计
        if pred == "待分析":
            continue
        if row["hit"]:
            curr_hit += 1
            curr_miss = 0
            max_hit = max(max_hit, curr_hit)
        else:
            curr_miss += 1
            curr_hit = 0
            max_miss = max(max_miss, curr_miss)
    return {
        "curr_hit": curr_hit,
        "curr_miss": curr_miss,
        "max_hit": max_hit,
        "max_miss": max_miss
    }

# 固定取最新5期
def get_calc_window(history):
    return history[-5:] if len(history)>=5 else history

# 修复：冷热统计只取有效运算窗口，过滤无效初期数据
def get_market_tip(window):
    if len(window) < 3:
        return "数据不足，录入至少3期有效开奖后显示冷热分析"
    all_digits = []
    for item in window:
        all_digits.extend([int(c) for c in item["data"]])
    cnt = Counter(all_digits)
    hot = sorted(cnt.items(), key=lambda x:x[1], reverse=True)[:4]
    cold = sorted(cnt.items(), key=lambda x:x[1])[:3]
    hot_str = "、".join(str(x[0]) for x in hot)
    cold_str = "、".join(str(x[0]) for x in cold)
    return f"近5期热号：{hot_str}；冷门数字：{cold_str}"

def get_recommend(history):
    win = get_calc_window(history)
    # 不足3期直接待分析
    if len(win) < 3:
        return "待分析"

    all_digits = []
    period_digits = []
    type_cnt = defaultdict(int)
    for item in win:
        ds = [int(c) for c in item["data"]]
        period_digits.append(ds)
        all_digits.extend(ds)
        c = Counter(ds)
        sort_v = sorted(c.values(), reverse=True)
        if sort_v[0] == 4:
            t = "AAAA"
        elif sort_v[0] == 3:
            t = "AAAB"
        elif sort_v[0]==2 and sort_v[1]==2:
            t = "AABB"
        elif sort_v[0]==2:
            t = "AABC"
        else:
            t = "ABCD"
        type_cnt[t] += 1
    main_type = max(type_cnt.items(), key=lambda x:x[1])[0]

    transfer = defaultdict(Counter)
    for i in range(2, len(period_digits)):
        pre = period_digits[i-2] + period_digits[i-1]
        cur = period_digits[i]
        for p in pre:
            for c in cur:
                transfer[p][c] += 1

    last_occur = {d:-1 for d in range(10)}
    for idx, item in enumerate(win):
        for ch in item["data"]:
            d = int(ch)
            last_occur[d] = idx
    miss_score = {}
    max_idx = len(win)-1
    for d in range(10):
        gap = max_idx - last_occur[d]
        if gap <= 2:
            ms = gap * 0.15
        elif gap <=4:
            ms = gap * 0.6
        else:
            ms = 4*0.6 + (gap-4)*0.25
        miss_score[d] = ms

    hot_cnt = Counter(all_digits)
    hot_score = {d: hot_cnt.get(d,0)*0.2 for d in range(10)}

    trans_score = {d:0 for d in range(10)}
    last2 = period_digits[-1] + period_digits[-2]
    for p in last2:
        total = sum(transfer[p].values()) or 1
        for num, val in transfer[p].items():
            trans_score[num] += (val / total)*0.7

    type_bonus = {d:0 for d in range(10)}
    for idx, item in enumerate(win):
        ds = [int(c) for c in item["data"]]
        c = Counter(ds)
        sort_v = sorted(c.values(), reverse=True)
        if sort_v[0] == 4:
            t = "AAAA"
        elif sort_v[0] == 3:
            t = "AAAB"
        elif sort_v[0]==2 and sort_v[1]==2:
            t = "AABB"
        elif sort_v[0]==2:
            t = "AABC"
        else:
            t = "ABCD"
        if t == main_type:
            for d in ds:
                type_bonus[d] += 0.2

    total = {}
    for d in range(10):
        total[d] = hot_score[d] + trans_score[d] + miss_score[d] + type_bonus[d]

    hot_sort = sorted(total.items(), key=lambda x:x[1], reverse=True)
    cold_sort = sorted(total.items(), key=lambda x:x[1])
    h1, h2 = hot_sort[0][0], hot_sort[1][0]
    c1 = cold_sort[0][0]
    res = sorted([h1, h2, c1])
    return "".join(str(x) for x in res)

streak_data = calc_streak_info(st.session_state.history_list)
curr_miss = streak_data["curr_miss"]

# 两连错自动清空刷新
if curr_miss >= 2:
    st.session_state.history_list = []
    st.warning("🚨 高危提醒：已出现两连错，系统自动清空全部数据并重置！请重新录入至少3期开奖号码后才能正常分析。")
    st.rerun()

next_num = get_recommend(st.session_state.history_list)
calc_win = get_calc_window(st.session_state.history_list)
tip_text = get_market_tip(calc_win)

st.markdown("<h2>🎯 固定5周期预测系统（两连错自动重置）</h2>", unsafe_allow_html=True)
col1, col2 = st.columns([0.65, 0.35])

with col1:
    s1,s2,s3,s4 = st.columns(4)
    with s1:
        st.markdown(f'<div class="stat-card stat-green"><div class="stat-label">当前连中</div><div class="stat-value">{streak_data["curr_hit"]}</div></div>', unsafe_allow_html=True)
    with s2:
        st.markdown(f'<div class="stat-card stat-orange"><div class="stat-label">当前连错</div><div class="stat-value">{streak_data["curr_miss"]}</div></div>', unsafe_allow_html=True)
    with s3:
        st.markdown(f'<div class="stat-card stat-orange2"><div class="stat-label">最大连中</div><div class="stat-value">{streak_data["max_hit"]}</div></div>', unsafe_allow_html=True)
    with s4:
        st.markdown(f'<div class="stat-card stat-red"><div class="stat-label">最大连错</div><div class="stat-value">{streak_data["max_miss"]}</div></div>', unsafe_allow_html=True)

    if curr_miss == 0:
        st.markdown(f'<div class="monitor-box"><strong>✅ 平稳周期，使用最新5期数据运算</strong><br>{tip_text}</div>', unsafe_allow_html=True)
    elif curr_miss == 1:
        st.markdown(f'<div class="tips-box"><strong>⚠️ 已断1期，若再错1期将自动清空全部数据重置</strong><br>{tip_text}</div>', unsafe_allow_html=True)

    st.divider()
    st.subheader("📜 历史复盘记录")
    if st.session_state.history_list:
        table_data = []
        total_len = len(st.session_state.history_list)
        for i, item in enumerate(reversed(st.session_state.history_list)):
            idx = total_len - i
            hit_txt = "✅" if item["hit"] else "❌"
            table_data.append({
                "期数": idx,
                "开奖号": item["data"],
                "当时推荐": item["pred"],
                "结果": hit_txt
            })
        st.table(pd.DataFrame(table_data))
    else:
        st.info("暂无历史数据，请在右侧录入开奖号")

with col2:
    st.subheader("💡 实时推荐号码")
    if next_num == "待分析":
        st.markdown('<div style="font-size:44px; font-weight:bold; color:#888;">待分析</div>', unsafe_allow_html=True)
        st.markdown('<div class="warn-box">提示：需要录入至少3期开奖号码才能生成推荐</div>', unsafe_allow_html=True)
    else:
        st.markdown(f'<div style="font-size:44px; font-weight:bold; color:#d32f2f;">{next_num}</div>', unsafe_allow_html=True)

    st.divider()
    form = st.form("input_form", clear_on_submit=True)
    user_input = form.text_input("输入本期开奖（示例：91934）")
    submit_btn = form.form_submit_button("确认录入本期结果")
    if submit_btn and user_input.strip():
        digit_str = re.search(r"\d+", user_input.strip()).group()
        # 待分析期数命中默认false
        hit_flag = False
        if next_num != "待分析":
            hit_flag = any(str(d) in digit_str for d in next_num)
        new_row = {
            "data": digit_str,
            "pred": next_num,
            "hit": hit_flag
        }
        st.session_state.history_list.append(new_row)
        st.rerun()

    if st.button("手动清空全部记录重置"):
        st.session_state.history_list = []
        st.rerun()
