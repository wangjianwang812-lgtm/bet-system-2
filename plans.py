import streamlit as st
import pandas as pd
import re
from collections import Counter, defaultdict

# 页面样式CSS
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
    .tips-box {
        background: #fff3cd;
        border: 1px solid #ffeeba;
        border-radius: 10px;
        padding: 12px 16px;
        margin: 10px 0;
    }
</style>
""", unsafe_allow_html=True)

st.set_page_config(page_title="实时纠错系统 (位移矩阵版)", layout="wide")

if 'history_list' not in st.session_state:
    st.session_state.history_list = []

# 行情规律分析函数（新增）
def get_market_tips(history, curr_miss):
    if len(history) < 5:
        return "暂无足够历史数据，录入更多期数后显示行情规律"
    win = history[-10:] if len(history)>=10 else history
    all_digits = []
    for item in win:
        ds = [int(c) for c in item["data"]]
        all_digits.extend(ds)
    cnt = Counter(all_digits)
    hot = sorted(cnt.items(), key=lambda x:x[1], reverse=True)[:4]
    hot_nums = "、".join([str(i[0]) for i in hot])
    cold = sorted(cnt.items(), key=lambda x:x[1])[:3]
    cold_nums = "、".join([str(i[0]) for i in cold])
    total = len(all_digits)
    hot_total = sum([i[1] for i in hot])
    hot_ratio = hot_total / total

    # 判断行情状态
    if curr_miss == 0:
        status = "【平稳热循环行情】当前无连败，短期热号持续延续，优先抓核心活跃数字，适合长连中"
        tip = "规律提示：连续多期无挂单时，核心热号3-8区间占比高，每3-4期会小幅穿插冷门数字回调"
    else:
        if curr_miss >=2:
            status = "【震荡反转行情】当前存在2连连败，原有热区间过热回调，注意均衡冷热搭配，避免死守旧热号"
            tip = "规律提示：连续两期挂单代表热区间行情断裂，下期会加大冷门数字权重，优先选取长期遗漏数字"
        else:
            status = "【小幅回调行情】单次挂单，仅短期区间切换，大概率保留上期1个数字延续，很快回归核心热池"
            tip = "规律提示：单挂属于正常周期波动，不会彻底抛弃主流热号，10期窗口均衡修正后命中率回升"
    ratio_text = f"近10期高频热号：{hot_nums}；低频冷号：{cold_nums}；核心热号总出现占比：{hot_ratio:.1%}"
    full_tip = f"{status}\n{ratio_text}\n{tip}"
    return full_tip

# 对齐截图系统逻辑算法
def get_recommendation(history):
    window_len = len(history)
    if window_len < 3:
        return "待分析"

    curr_miss = 0
    last_miss_digits = set()
    for idx, row in enumerate(reversed(history)):
        if row["pred"] == "待分析":
            continue
        if not row["hit"]:
            curr_miss += 1
            pred_digits = [int(c) for c in row["pred"]]
            if curr_miss == 1:
                for d in pred_digits:
                    last_miss_digits.add(d)
        else:
            break

    # 窗口规则：无挂单用5期，只要挂单≥1直接10期
    if curr_miss == 0:
        full_window = history[-5:]
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
        if curr_miss >= 1:
            add *= 1.15
        miss_score[d] = add

    hot_counter = Counter(all_digits)
    hot_base_weight = 0.2
    if curr_miss >= 1:
        hot_base_weight *= 0.85
    hot_score = {d: hot_counter.get(d, 0) * hot_base_weight for d in range(10)}

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
        base = transfer_score[d] + hot_score[d] + miss_score[d] + type_bonus[d]
        if d in last_miss_digits:
            base *= 0.75
        total_score[d] = base

    last_item = full_window[-1]
    last_period_digits = period_digits[-1]
    raw_candidate = ""
    if curr_miss >= 1:
        hot_sort = sorted(total_score.items(), key=lambda x: x[1], reverse=True)
        cold_sort = sorted(total_score.items(), key=lambda x: x[1])
        hot1, hot2 = hot_sort[0][0], hot_sort[1][0]
        cold1 = cold_sort[0][0]
        mix_3 = sorted([hot1, hot2, cold1])
        raw_candidate = "".join([str(i) for i in mix_3])
    else:
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
    return raw_candidate

# 统计函数
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

# 页面布局
st.markdown("<h2 style='margin-top:0; margin-bottom:12px;'>🎯 实时纠错系统 (位移矩阵版)</h2>", unsafe_allow_html=True)
col1, col2 = st.columns([0.65, 0.35])
next_pred = get_recommendation(st.session_state.history_list)
streak_data = calc_streak_info(st.session_state.history_list)
curr_miss_val = streak_data["curr_miss"]
market_tip = get_market_tips(st.session_state.history_list, curr_miss_val)

with col1:
    st.subheader("📈 连中/连败统计")
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

    # 新增行情规律提醒框
    st.markdown(f'<div class="tips-box"><strong>📊 行情规律实时提醒</strong><br>{market_tip}</div>', unsafe_allow_html=True)
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
                    "hit": any(str(d) in next_pred for d in nums[-1][-4:]) if next_pred != "待分析" else False
                }
                st.session_state.history_list.append(snapshot)
                st.rerun()
    if st.button("手动清空记录"):
        st.session_state.history_list = []
        st.rerun()
