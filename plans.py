import streamlit as st
import pandas as pd
import re
from collections import Counter

# 强力CSS样式，强制隐藏右上角头部所有按钮、Deploy文字、三点菜单，压缩顶部空白
st.markdown("""
<style>
    /* 整体内容上移 */
    .block-container {
        padding-top: 0.3rem !important;
        padding-bottom: 0rem !important;
    }
    /* 隐藏整个顶部导航栏区域 */
    header[data-testid="stHeader"] {
        display: none !important;
    }
    /* 备用隐藏规则，防止部分版本兼容问题 */
    .stDeployButton,
    [data-testid="stHeaderActionElements"],
    div[class*="stHeader"] {
        display: none !important;
    }
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

# 统计连中、连败数据函数
def calc_streak_info(history):
    max_hit_streak = 0
    max_miss_streak = 0
    curr_hit = 0
    curr_miss = 0
    for row in history:
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
    # 适配字号：标签12px，数字20px，深蓝色
    style_label = "font-size:12px; color:#002266; margin-bottom:2px;"
    style_value = "font-size:20px; color:#002266; font-weight:500;"
    
    with s1:
        st.markdown(f"<div style='{style_label}'>当前连中</div>", unsafe_allow_html=True)
        st.markdown(f"<div style='{style_value}'>{streak_data['curr_hit']}</div>", unsafe_allow_html=True)
    with s2:
        st.markdown(f"<div style='{style_label}'>当前连败</div>", unsafe_allow_html=True)
        st.markdown(f"<div style='{style_value}'>{streak_data['curr_miss']}</div>", unsafe_allow_html=True)
    with s3:
        st.markdown(f"<div style='{style_label}'>历史最大连中</div>", unsafe_allow_html=True)
        st.markdown(f"<div style='{style_value}'>{streak_data['max_hit']}</div>", unsafe_allow_html=True)
    with s4:
        st.markdown(f"<div style='{style_label}'>历史最大连败</div>", unsafe_allow_html=True)
        st.markdown(f"<div style='{style_value}'>{streak_data['max_miss']}</div>", unsafe_allow_html=True)
    
    st.divider()
    # 历史复盘标题：加粗、加深黑色字体
    st.markdown("<h3 style='font-weight:bold; color:#000000; margin-top:4px;'>📜 历史复盘 (记录锁定)</h3>", unsafe_allow_html=True)
    
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
        st.metric("下一期推荐号码:", next_pred)
    else:
        st.info("💡 录入 3 期数据后开启预判")

    with st.form("input_form", clear_on_submit=True):
        user_input = st.text_input("粘贴本期开奖 (如: 91934):")
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
                st.rerun()

    if st.button("手动清空记录"):
        st.session_state.history_list = []
        st.rerun()
