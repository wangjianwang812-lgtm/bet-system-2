import streamlit as st
import pandas as pd
import re
from collections import Counter, defaultdict

# 全局浅蓝色CSS样式【仅美化UI，业务无改动】
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
    /* 输入框原生保留，仅柔和边框 */
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
    /* 卡片统一圆角柔和阴影 */
    div[data-testid="stHorizontalBlock"] {
        gap:12px;
    }
    /* 统计色块圆角彩色块，恢复原来大小 */
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
    /* 推荐号码红字样式 */
    .pred-num {
        font-size:42px;
        color:#f23c3c;
        font-weight:900;
    }
    /* 表格美化 */
    .stTable table {
        border-radius:12px;
        overflow:hidden;
    }
    .stTable th {
        background:#b8d8fb !important;
    }
    /* 独立行情状态卡片 绿色平稳/红色震荡 右移远离标题 */
    .market-status-card {
        display: inline-block;
        padding: 8px 18px;
        border-radius: 12px;
        color: #fff;
        font-size: 16px;
        font-weight: 900;
        margin: 6px 0 6px 50px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.08);
    }
    .market-status-green {
        background: linear-gradient(135deg, #22b962, #16a34a);
    }
    .market-status-red {
        background: linear-gradient(135deg, #f23c3c, #d13030);
    }
</style>
""", unsafe_allow_html=True)

# 页面基础配置
st.set_page_config(page_title="实时纠错系统 (永久固定5期窗口)", layout="wide")

# 初始化历史存储
if 'history_list' not in st.session_state:
    st.session_state.history_list = []

# 永久固定5期窗口，其余打分逻辑完全沿用原版
def get_recommendation(history):
    window_len = len(history)
    if window_len < 3:
        return "待分析"

    # 统计当前连败数
    curr_miss = 0
    for row in reversed(history):
        if row["pred"] == "待分析":
            continue
        if not row["hit"]:
            curr_miss += 1
        else:
            break

    # 核心：永久固定取最新5期数据计算
    full_window = history[-5:]

    all_digits = []
    period_digits = []
    period_type = []
    for item in full_window:
        num_str = item["data"][-4:]
        digits = [int(c) for c in num_str]
        period_digits.append(digits)
        all_digits.extend(digits)
        # 判断四码形态
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

    # 马尔可夫近2期数字联动
    transfer = defaultdict(Counter)
    for i in range(2, len(period_digits)):
        prev_nums = period_digits[i-2] + period_digits[i-1]
        curr_nums = period_digits[i]
        for p in prev_nums:
            for c in curr_nums:
                transfer[p][c] += 1

    # 阶梯遗漏计分，避免冷号扎堆
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

    # 热度权重随连败动态降低（原版逻辑保留）
    hot_counter = Counter(all_digits)
    hot_weight = 0.2 if curr_miss == 0 else 0.12
    hot_score = {d: hot_counter.get(d, 0) * hot_weight for d in range(10)}

    # 转移矩阵辅助分
    transfer_score = {d: 0 for d in range(10)}
    last2_nums = period_digits[-1] + period_digits[-2]
    for prev_d in last2_nums:
        total = sum(transfer[prev_d].values()) or 1
        for curr_d, cnt in transfer[prev_d].items():
            transfer_score[curr_d] += (cnt / total) * 0.7

    # 主流形态加分
    type_cnt = Counter(period_type)
    main_type = max(type_cnt, key=type_cnt.get)
    type_bonus = {d: 0 for d in range(10)}
    for i in range(len(full_window)):
        if period_type[i] == main_type:
            for d in period_digits[i]:
                type_bonus[d] += 0.2

    # 总分合并
    total_score = {}
    for d in range(10):
        total_score[d] = transfer_score[d] + hot_score[d] + miss_score[d] + type_bonus[d]

    # 分级纠错逻辑（原版完全保留）
    last_item = full_window[-1]
    last_period_digits = period_digits[-1]
    if not last_item["hit"]:
        if curr_miss == 1:
            # 仅错1期：冷2 + 上期残留1个数字
            cold_list = sorted([(d, miss_score[d]) for d in range(10)], key=lambda x: x[1], reverse=True)[:2]
            cold_nums = [x[0] for x in cold_list]
            reserve_num = last_period_digits[0]
            combine = list(set(cold_nums + [reserve_num]))[:3]
            return "".join(sorted([str(x) for x in combine]))
        else:
            # 两连错以上：混合冷热全新组合
            mix_sort = sorted(total_score.items(), key=lambda x: x[1], reverse=True)
            mix_3 = [str(d) for d, s in mix_sort[:3]]
            return "".join(sorted(mix_3))

    # 连对正常输出：2热1冷
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

    res = "".join(sorted([str(d) for d in final[:3]]))
    return res

# 连中连败统计函数（无改动）
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
            max_hit_streak = max(max_hit_streak, curr_hit)
        else:
            curr_miss += 1
            curr_hit = 0
            max_miss_streak = max(max_miss_streak, curr_miss)
    return {
        "curr_hit": curr_hit,
        "curr_miss": curr_miss,
        "max_hit": max_hit_streak,
        "max_miss": max_miss_streak
    }

# 页面布局
st.markdown("<h2 style='margin-top:0; margin-bottom:12px;'>🎯 实时纠错系统 (永久固定5期窗口)</h2>", unsafe_allow_html=True)
col1, col2 = st.columns([0.65, 0.35])
next_pred = get_recommendation(st.session_state.history_list)
streak_data = calc_streak_info(st.session_state.history_list)
curr_miss_global = streak_data["curr_miss"]

# 两连错自动清空重置逻辑
if curr_miss_global >= 2:
    st.session_state.history_list = []
    st.warning("🚨 高危提醒：已出现两连错，系统自动清空全部历史记录并刷新！请重新录入至少3期开奖数据后再分析。")
    st.rerun()

# 左侧统计区域
with col1:
    st.subheader("📈 连中/连败统计")
    s1, s2, s3, s4 = st.columns(4)

    # 恢复原来四个统计色块布局和大小
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

    # 历史复盘标题单独一行
    st.markdown("<h3 style='font-weight:bold; color:#000000; margin-top:-8px; margin-bottom:6px;'>📜 历史复盘 (记录锁定)</h3>", unsafe_allow_html=True)

    # 独立彩色状态卡片，右移50px远离标题，绿色平稳/红色震荡
    if curr_miss_global == 0:
        st.markdown('<div class="market-status-card market-status-green">✅ 当前行情平稳长连</div>', unsafe_allow_html=True)
    else:
        st.markdown('<div class="market-status-card market-status-red">⚠️ 当前行情震荡不平稳</div>', unsafe_allow_html=True)

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

# 右侧预判、录入、清空（带4位数字校验）
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
                digit_raw = nums[-1]
                # 校验长度，不足4位禁止录入
                if len(digit_raw) < 4:
                    st.error("录入失败！请输入完整4位数字，仅1/2位数字会导致冷热统计、推荐号码异常！")
                    st.stop()
                snapshot = {
                    "data": digit_raw[-5:],
                    "pred": next_pred,
                    "hit": any(str(d) in digit_raw[-4:] for d in next_pred) if next_pred != "待分析" else False
                }
                st.session_state.history_list.append(snapshot)
                st.rerun()
    if st.button("手动清空记录"):
        st.session_state.history_list = []
        st.rerun()
