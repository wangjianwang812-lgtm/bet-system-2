import streamlit as st
import pandas as pd
import re
from collections import Counter, defaultdict

# 全局浅蓝色CSS样式
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
    .stTextInput label p {
        font-weight: 600 !important;
        font-size:16px;
    }
    div[data-testid="stHorizontalBlock"] {
        gap:12px;
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
    .stTable table {
        border-radius:12px;
        overflow:hidden;
    }
    .stTable th {
        background:#b8d8fb !important;
    }
</style>
""", unsafe_allow_html=True)

st.set_page_config(page_title="实时纠错系统 (位移矩阵版)", layout="wide")

if 'history_list' not in st.session_state:
    st.session_state.history_list = []

# 初代原版核心不变，连败场景新增规避上期错误号码逻辑
def get_recommendation(history):
    window_len = len(history)
    if window_len < 3:
        return "待分析"

    curr_miss = 0
    miss_pred_set = set()
    # 统计连败，同时收集最近2次挂单的推荐数字，后续规避
    for idx, row in enumerate(reversed(history)):
        if row["pred"] == "待分析":
            continue
        if not row["hit"]:
            curr_miss += 1
            # 仅记录最近两次错误推荐数字
            if curr_miss <= 2:
                for c in row["pred"]:
                    miss_pred_set.add(int(c))
        else:
            break

    # 分级窗口不变
    if curr_miss == 0:
        full_window = history[-5:]
    elif curr_miss == 1:
        full_window = history[-7:]
    else:
        full_window = history[-10:]

    all_digits = []
    period_digits = []
    period_type = []
    for item in full_window:
        num_str = item["data"][-4:]
        digits = [int(c) for c in num_str]
        period_digits.append(digits)
        all_digits.extend(digits)
        cnt = Counter(digits)
        sort_cnt = sorted(cnt.values(), reverse=True)
        if sort_cnt[0] == 4:
            t = "AAAA"
        elif sort_cnt[0] == 3:
            t = "AAAB"
        elif sort_cnt[0] == 2 and sort_cnt[1] == 2:
            t = "AABB"
        elif sort_cnt[0] == 2:
            t = "AABC"
        else:
            t = "ABCD"
        period_type.append(t)

    transfer = defaultdict(Counter)
    for i in range(2, len(period_digits)):
        prev_nums = period_digits[i-2] + period_digits[i-1]
        curr_nums = period_digits[i]
        for p in prev_nums:
            for c in curr_nums:
                transfer[p][c] += 1

    last_occur = {d: -1 for d in range(10)}
    for idx, item in enumerate(full_window):
        for c in item["data"][-4:]:
            d = int(c)
            last_occur[d] = idx
    max_idx = len(full_window) - 1
    miss_score = {}
    for d in range(10):
        miss = max_idx - last_occur[d]
        if miss <= 2:
            add = miss * 0.15
        elif miss <= 4:
            add = miss * 0.6
        else:
            add = 4 * 0.6 + (miss - 4) * 0.25
        miss_score[d] = add

    hot_counter = Counter(all_digits)
    hot_weight = 0.2 if curr_miss == 0 else 0.12
    hot_score = {d: hot_counter.get(d, 0) * hot_weight for d in range(10)}

    transfer_score = {d: 0 for d in range(10)}
    last2_nums = period_digits[-1] + period_digits[-2]
    for prev_d in last2_nums:
        total = sum(transfer[prev_d].values()) or 1
        for curr_d, cnt in transfer[prev_d].items():
            transfer_score[curr_d] += (cnt / total) * 0.7

    type_cnt = Counter(period_type)
    main_type = max(type_cnt, key=type_cnt.get)
    type_bonus = {d: 0 for d in range(10)}
    for i in range(len(full_window)):
        if period_type[i] == main_type:
            for d in period_digits[i]:
                type_bonus[d] += 0.2

    total_score = {}
    for d in range(10):
        total_score[d] = transfer_score[d] + hot_score[d] + miss_score[d] + type_bonus[d]

    last_item = full_window[-1]
    last_period_digits = period_digits[-1]
    raw_candidate = ""
    if not last_item["hit"]:
        if curr_miss == 1:
            # 单挂1期原版逻辑
            cold_list = sorted([(d, miss_score[d]) for d in range(10)], key=lambda x: x[1], reverse=True)[:2]
            cold_nums = [x[0] for x in cold_list]
            reserve_num = last_period_digits[0]
            combine = list(set(cold_nums + [reserve_num]))[:3]
            raw_candidate = "".join(sorted([str(x) for x in combine]))
        else:
            # 两连及以上连败：2热1冷，同时剔除近2期错误数字
            hot_sort = sorted([(d,s) for d,s in total_score.items() if d not in miss_pred_set], key=lambda x:x[1], reverse=True)
            cold_sort = sorted([(d,s) for d,s in total_score.items() if d not in miss_pred_set], key=lambda x:x[1])
            hot1, hot2 = hot_sort[0][0], hot_sort[1][0]
            cold1 = cold_sort[0][0]
            mix_3 = sorted([hot1, hot2, cold1])
            raw_candidate = "".join([str(i) for i in mix_3])
    else:
        # 连中平稳段【完全原版2热1冷逻辑，无任何改动】
        hot_pool = sorted([(d, s) for d, s in total_score.items()], key=lambda x: x[1], reverse=True)[:4]
        miss_pool = sorted([(d, miss_score[d]) for d in range(10)], key=lambda x: x[1], reverse=True)[:4]
        hot_digits = set([x[0] for x in hot_pool])
        cold_digits = set([x[0] for x in miss_pool])

        all_sorted = sorted(total_score.items(), key=lambda x: x[1], reverse=True)
        top_raw = [d for d, s in all_sorted]

        hot_count = 0
        cold_count = 0
        final = []
        for num in top_raw:
            if num in hot_digits and hot_count < 2:
                final.append(num)
                hot_count += 1
            elif num in cold_digits and cold_count < 1:
                final.append(num)
                cold_count += 1
            if len(final) >= 3:
                break
        while len(final) < 3:
            for d, _ in all_sorted:
                if d not in final:
                    final.append(d)
                    break
        raw_candidate = "".join(sorted([str(d) for d in final[:3]]))
    # 无形态过滤，原生结果直接返回
    return raw_candidate

# 统计函数不变
def calc_streak_info(history):
    max_hit_streak = 0
    max_miss_streak = 0
    curr_hit = 0
    curr_miss = 0
    for row in history:
        if row["pred"] == "待分析":
            continue
        if row["hit"]:
            curr_hit += 1
            curr_miss = 0
            if curr_hit > max_hit_streak:
                max_hit_streak = curr_hit
        else:
            curr_miss += 1
            curr_hit = 0
            if curr_miss > max_miss_streak:
                max_miss_streak = curr_miss
    return {
        "curr_hit": curr_hit,
        "curr_miss": curr_miss,
        "max_hit": max_hit_streak,
        "max_miss": max_miss_streak
    }

# 页面布局完全不变
st.markdown("<h2 style='margin-top:0; margin-bottom:12px;'>🎯 实时纠错系统 (位移矩阵版)</h2>", unsafe_allow_html=True)
col1, col2 = st.columns([0.65, 0.35])
next_pred = get_recommendation(st.session_state.history_list)

with col1:
    st.subheader("📈 连中/连败统计")
    streak_data = calc_streak_info(st.session_state.history_list)
    s1, s2, s3, s4 = st.columns(4)
    with s1:
        st.markdown(f"""
        <div class="stat-card stat-green">
            <div class="stat-label">当前连中</div>
            <div class="stat-value">{streak_data['curr_hit']}</div>
        </div>
        """, unsafe_allow_html=True)
    with s2:
        st.markdown(f"""
        <div class="stat-card stat-orange">
            <div class="stat-label">当前连败</div>
            <div class="stat-value">{streak_data['curr_miss']}</div>
        </div>
        """, unsafe_allow_html=True)
    with s3:
        st.markdown(f"""
        <div class="stat-card stat-orange2">
            <div class="stat-label">历史最大连中</div>
            <div class="stat-value">{streak_data['max_hit']}</div>
        </div>
        """, unsafe_allow_html=True)
    with s4:
        st.markdown(f"""
        <div class="stat-card stat-red">
            <div class="stat-label">历史最大连败</div>
            <div class="stat-value">{streak_data['max_miss']}</div>
        </div>
        """, unsafe_allow_html=True)
    st.divider()
    st.markdown("<h3 style='font-weight:bold; color:#000000; margin-top:-8px; margin-bottom:6px;'>📜 历史复盘 (记录锁定)</h3>", unsafe_allow_html=True)
    if st.session_state.history_list:
        data = []
        for i, item in enumerate(reversed(st.session_state.history_list)):
            data.append({
                "期数": len(st.session_state.history_list) - i,
                "开奖号": item['data'][-4:],
                "当时推荐": item['pred'],
                "结果": "✅" if item['hit'] else "❌"
            })
        st.table(pd.DataFrame(data))
    else:
        st.info("暂无数据，请在右侧录入...")

with col2:
    st.subheader("💡 实时预判")
    if next_pred != "待分析":
        st.markdown(f"""
        <div style="font-size: 18px; color:#222222; margin-bottom:4px;">下一期推荐号码:</div>
        <div class="pred-num">{next_pred}</div>
        """, unsafe_allow_html=True)
    else:
        st.info("💡 录入 3 期数据后开启预判")
    with st.form("input_form", clear_on_submit=True):
        user_input = st.text_input("请输入本期开奖 (如: 91934):")
        submitted = st.form_submit_button("确认录入本期结果")
        if submitted and user_input:
            nums = re.findall(r'\d+', user_input)
            if nums:
                snapshot = {
                    "data": nums[-1][-5:],
                    "pred": next_pred,
                    "hit": any(d in nums[-1][-4:] for d in next_pred) if next_pred != "待分析" else False
                }
                st.session_state.history_list.append(snapshot)
                st.rerun()
    if st.button("手动清空记录"):
        st.session_state.history_list = []
        st.rerun()
