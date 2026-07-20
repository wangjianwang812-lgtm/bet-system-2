import streamlit as st
import pandas as pd
import re
from collections import Counter

# 全局强力CSS，整页全覆盖浅蓝色，消除底部白色空白 + 新增输入框样式 + 统计卡片样式
st.markdown("""
<style>
    html, body, .stApp {
        background-color: #e6f2ff !important;
        min-height: 100vh !important;
    }
    .block-container {
        background-color: transparent !important;
        padding-top: 0.3rem !important;
        padding-bottom: 0rem !important;
    }
    /* 隐藏顶部标题栏 */
    header[data-testid="stHeader"] {
        display: none !important;
    }
    .stDeployButton,
    [data-testid="stHeaderActionElements"],
    div[class*="stHeader"] {
        display: none !important;
    }
    /* 输入框边框加粗醒目 */
    .stTextInput > div > div > input {
        border-width: 2px !important;
        border-color: #3366bb !important;
    }
    /* 输入框上方文字加粗变饱满 */
    .stTextInput label p {
        font-weight: 700 !important;
    }

    /* 统计卡片样式 - 缩小尺寸 */
    .stat-card {
        border-radius: 14px !important;
        padding: 8px 10px !important;
        color: #ffffff !important;
        text-align: center !important;
        box-shadow: none !important;
        border: none !important;
    }
    .stat-card .label {
        font-size: 14px !important;
        margin-bottom: 3px !important;
    }
    .stat-card .value {
        font-size: 22px !important;
        font-weight: bold !important;
    }
    .stat-card-1 { background-color: #10b981 !important; }
    .stat-card-2 { background-color: #f59e0b !important; }
    .stat-card-3 { background-color: #f59e0b !important; }
    .stat-card-4 { background-color: #ec4899 !important; }
</style>
""", unsafe_allow_html=True)

# --- 1. 页面配置 ---
st.set_page_config(page_title="实时纠错系统 (位移矩阵版)", layout="wide")

# 初始化存储
if 'history_list' not in st.session_state:
    st.session_state.history_list = []

# --- 2. 核心算法：位移矩阵 + 连挂纠错模型 ---
def get_recommendation(history):
    # 自动滑窗：只取最近 15 期作为分析窗口
    active_history = history[-15:]
    if len(active_history) < 3: return "待分析"

    # 频率分析：最近 5 期赋予高权重 (1.5)，15 期赋予基准权重
    recent_5 = "".join([item['data'][-4:] for item in active_history[-5:]])
    freq = Counter(recent_5)
    scores = {str(d): float(freq.get(str(d), 0)) * 1.5 for d in range(10)}

    # 顺位惯性：上期号码的相邻位有极大概率出现
    last_digit = int(active_history[-1]['data'][-1])
    for offset in [-1, 0, 1]:
        target = str((last_digit + offset) % 10)
        scores[target] += 2.0

    # 连挂纠错机制：如果连续挂了 2 期，对当前的 top3 评分进行打折 (逼迫换号)
    if len(active_history) >= 2:
        if not active_history[-1]['hit'] and not active_history[-2]['hit']:
            for d in scores:
                scores[d] *= 0.8

    # 取前三名作为结果
    top3 = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:3]
    result = "".join(sorted([item[0] for item in top3]))

    return result

# 统计连中、连败数据函数，仅增加跳过待分析判断，其余统计逻辑完全原样
def calc_streak_info(history):
    max_hit_streak = 0
    max_miss_streak = 0
    curr_hit = 0
    curr_miss = 0
    for row in history:
        # 仅新增：待分析记录直接跳过，不参与任何连中/连败计数
        if row["pred"] == "待分析":
            continue
        # 下面原有统计逻辑完全不动，一丝未改
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

# --- 3. 界面布局 ---
# 小号紧凑主标题
st.markdown("<h2 style='margin-top:0; margin-bottom:6px;'>🎯 实时纠错系统 (位移矩阵版)</h2>", unsafe_allow_html=True)
col1, col2 = st.columns([0.65, 0.35])

# 计算下期推荐
next_pred = get_recommendation(st.session_state.history_list)

# ========== 左侧栏：先放连中连败统计，再放历史复盘 ==========
with col1:
    st.subheader("📈 连中/连败统计")
    streak_data = calc_streak_info(st.session_state.history_list)
    s1, s2, s3, s4 = st.columns(4)

    with s1:
        st.markdown(f"""
        <div class="stat-card stat-card-1">
            <div class="label">当前连中</div>
            <div class="value">{streak_data['curr_hit']}</div>
        </div>
        """, unsafe_allow_html=True)

    with s2:
        st.markdown(f"""
        <div class="stat-card stat-card-2">
            <div class="label">当前连败</div>
            <div class="value">{streak_data['curr_miss']}</div>
        </div>
        """, unsafe_allow_html=True)

    with s3:
        st.markdown(f"""
        <div class="stat-card stat-card-3">
            <div class="label">历史最大连中</div>
            <div class="value">{streak_data['max_hit']}</div>
        </div>
        """, unsafe_allow_html=True)

    with s4:
        st.markdown(f"""
        <div class="stat-card stat-card-4">
            <div class="label">历史最大连败</div>
            <div class="value">{streak_data['max_miss']}</div>
        </div>
        """, unsafe_allow_html=True)

    st.divider()
    # 历史复盘标题：margin-top设为负数，紧贴上方分隔横线，紧凑布局
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

# ========== 右侧栏：只保留预判、录入、清空按钮 ==========
with col2:
    st.subheader("💡 实时预判")
    if next_pred != "待分析":
        # 文字保持深色，推荐号码改为红色加粗，布局间距和原metric一致
        st.markdown(f"""
        <div style="font-size: 18px; color:#222222; margin-bottom:4px;">下一期推荐号码:</div>
        <div style="font-size:42px; color:#ff0000; font-weight:bold;">{next_pred}</div>
        """, unsafe_allow_html=True)
    else:
        st.info("💡 录入 3 期数据后开启预判")

    with st.form("input_form", clear_on_submit=True):
        user_input = st.text_input("请输入本期开奖 (如: 91934):")
        submitted = st.form_submit_button("确认录入本期结果")

        if submitted and user_input:
            nums = re.findall(r'\d+', user_input)
            if nums:
                # 快照存储：录入瞬间锁定推荐码和结果
                snapshot = {
                    "data": nums[-1][-5:],
                    "pred": next_pred,
                    "hit": any(d in nums[-1][-4:] for d in next_pred) if next_pred != "待分析" else False
                }
                st.session_state.history_list.append(snapshot)

                # 自动滑窗：保持最近 20 期，防止历史干扰
                if len(st.session_state.history_list) > 20:
                    st.session_state.history_list.pop(0)

                # 新增逻辑：连续2次不中自动清空全部记录
                full_history = st.session_state.history_list
                valid_records = [r for r in full_history if r["pred"] != "待分析"]
                if len(valid_records) >= 2:
                    last1 = valid_records[-1]
                    last2 = valid_records[-2]
                    if (not last1["hit"]) and (not last2["hit"]):
                        st.warning("⚠️ 已连续预判错误2期，系统自动清空全部记录，重新开始统计！")
                        st.session_state.history_list = []

                st.rerun()

    if st.button("手动清空记录"):
        st.session_state.history_list = []
        st.rerun()
