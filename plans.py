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
    /* 统计色块圆角彩色块，和你效果图一致 */
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
</style>
""", unsafe_allow_html=True)

# 页面基础配置
st.set_page_config(page_title="实时纠错系统 (位移矩阵版)", layout="wide")

# 初始化历史存储
if 'history_list' not in st.session_state:
    st.session_state.history_list = []

# 升级优化算法：5期窗口固定包含最新一期，原有全部核心逻辑完整保留，新增强制携带当期数字规则
def get_recommendation(history):
    window_len = len(history)
    if window_len < 3:
        return "待分析"

    # 统计当前连败数【原逻辑完全不动】
    curr_miss = 0
    for row in reversed(history):
        if row["pred"] == "待分析":
            continue
        if not row["hit"]:
            curr_miss += 1
        else:
            break

    # 分级窗口：0连错=末尾5期（天然包含最新一期）；1连错=7期；>=2连错=10期【原代码无修改】
    if curr_miss == 0:
        full_window = history[-5:]
    elif curr_miss == 1:
        full_window = history[-7:]
    else:
        full_window = history[-10:]

    all_digits = []
    period_digits = []
    period_type = []
    window_weight_map = []  # 新增：存储每期数字+时间权重，原有提取逻辑不变
    total_window_count = len(full_window)

    for idx, item in enumerate(full_window):
        num_str = item["data"][-4:]
        digits = [int(c) for c in num_str]
        period_digits.append(digits)
        all_digits.extend(digits)

        # =====优化1：时间加权，越新期数权重越高，放大最新一期影响力=====
        reverse_index = total_window_count - 1 - idx
        if reverse_index == 0:
            weight = 0.40
        elif reverse_index == 1:
            weight = 0.25
        elif reverse_index == 2:
            weight = 0.15
        elif reverse_index == 3:
            weight = 0.10
        else:
            weight = 0.10
        window_weight_map.append({"digits": digits, "weight": weight})

        # 判断四码形态【原逻辑完全保留】
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

    # 马尔可夫近2期数字联动【原代码无改动】
    transfer = defaultdict(Counter)
    for i in range(2, len(period_digits)):
        prev_nums = period_digits[i-2] + period_digits[i-1]
        curr_nums = period_digits[i]
        for p in prev_nums:
            for c in curr_nums:
                transfer[p][c] += 1

    # 阶梯遗漏计分【原有公式保留】+ 优化2：遗漏分值封顶，防止无限追冷
    last_occur = {d: -1 for d in range(10)}
    for win_idx, item in enumerate(window_weight_map):
        for d in item["digits"]:
            last_occur[d] = win_idx
    max_idx = len(full_window) - 1
    miss_score = {}
    for d in range(10):
        miss = max_idx - last_occur[d]
        if miss <= 2:
            add = miss * 0.15
        elif miss <= 4:
            add = miss * 0.6
        else:
            # 超过4期后分值封顶，不再持续上涨，规避长期死追冷号
            add = 4 * 0.6
        miss_score[d] = add

    # 热度权重随连败动态降低【原逻辑保留】+ 叠加时间加权修正热度
    hot_counter = Counter()
    for item in window_weight_map:
        w = item["weight"]
        for d in item["digits"]:
            hot_counter[d] += w
    hot_weight = 0.2 if curr_miss == 0 else 0.12
    hot_score = {d: hot_counter.get(d, 0) * hot_weight for d in range(10)}

    # 转移矩阵辅助分【原代码完全不变】
    transfer_score = {d: 0 for d in range(10)}
    last2_nums = period_digits[-1] + period_digits[-2]
    for prev_d in last2_nums:
        total = sum(transfer[prev_d].values()) or 1
        for curr_d, cnt in transfer[prev_d].items():
            transfer_score[curr_d] += (cnt / total) * 0.7

    # 主流形态加分【原逻辑不动】
    type_cnt = Counter(period_type)
    main_type = max(type_cnt, key=type_cnt.get)
    type_bonus = {d: 0 for d in range(10)}
    for i in range(len(full_window)):
        if period_type[i] == main_type:
            for d in period_digits[i]:
                type_bonus[d] += 0.2

    # 总分合并【原有四项相加公式完全不变】
    total_score = {}
    for d in range(10):
        total_score[d] = transfer_score[d] + hot_score[d] + miss_score[d] + type_bonus[d]

    # 分级纠错逻辑【原分支全部保留，仅内部增加连败均衡风控】
    last_item = full_window[-1]
    last_period_digits = period_digits[-1]
    raw_candidate = ""
    # 提取窗口内【最新一期】全部数字（full_window[-1]就是刚录入的最新期，固定存在5期窗口末尾）
    new_period_digits = set([int(c) for c in full_window[-1]["data"][-4:]])

    if not last_item["hit"]:
        if curr_miss == 1:
            # 仅错1期：原冷2+上期残留逻辑不变，小幅压低冷号权重
            cold_list = sorted([(d, miss_score[d]) for d in range(10)], key=lambda x: x[1], reverse=True)[:2]
            cold_nums = [x[0] for x in cold_list]
            reserve_num = last_period_digits[0]
            combine = list(set(cold_nums + [reserve_num]))[:3]
            raw_candidate = "".join(sorted([str(x) for x in combine]))
        else:
            # 两连错以上：强制冷热均衡搭配，避免极端全冷组合
            mix_sort = sorted(total_score.items(), key=lambda x: x[1], reverse=True)
            hot_part = [d for d, s in mix_sort[:4]]
            cold_part = [d for d, s in mix_sort[-3:]]
            combine = [hot_part[0], hot_part[2], cold_part[0]]
            raw_candidate = "".join(sorted([str(x) for x in combine]))
    else:
        # ==========连中平稳段核心改动：原生2热1冷逻辑不变，强制最终号码包含最新一期至少1个数字==========
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
        temp_raw = final[:3]
        # 强制校验：如果初选组合不含最新一期数字，替换一个为当期数字
        temp_set = set(temp_raw)
        cross = temp_set & new_period_digits
        if len(cross) == 0:
            # 替换分数最低的数字为最新一期里总分最高的数字
            new_top = sorted([(d, total_score[d]) for d in new_period_digits], key=lambda x:x[1], reverse=True)[0][0]
            min_idx = temp_raw.index(min(temp_raw, key=lambda x:total_score[x]))
            temp_raw[min_idx] = new_top
        raw_candidate = "".join(sorted([str(d) for d in temp_raw]))

    # =====优化3：极端低概率形态过滤，剔除容易挂号的组合=====
    def is_bad_pattern(num_str):
        nums = [int(c) for c in num_str]
        a,b,c = nums
        # 全大(6-9) / 全小(0-3)
        all_big = all(x >=6 for x in nums)
        all_small = all(x <=3 for x in nums)
        # 全奇 / 全偶
        all_odd = all(x%2 ==1 for x in nums)
        all_even = all(x%2 ==0 for x in nums)
        # 顺子 123 234 345等连续三位
        sort_n = sorted(nums)
        is_seq = (sort_n[1] - sort_n[0] ==1) and (sort_n[2] - sort_n[1] ==1)
        # 双重对子 112、779 类两重重复
        cnt = Counter(nums)
        double_pair = any(v >=2 for v in cnt.values())
        return all_big or all_small or all_odd or all_even or is_seq or double_pair

    final_result = raw_candidate
    # 如果原生号码是差形态，同分数替换次优数字
    if is_bad_pattern(raw_candidate):
        all_rank = sorted(total_score.items(), key=lambda x:x[1], reverse=True)
        pool = [str(d) for d,s in all_rank]
        temp = []
        for num in pool:
            if num not in temp:
                temp.append(num)
            if len(temp)>=3:
                break
        alter = "".join(sorted(temp))
        if not is_bad_pattern(alter):
            final_result = alter

    return final_result

# 连中连败统计函数【无任何改动】
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
        "max_hit": max_hit,
        "max_miss": max_miss
    }

# 页面布局 仅修改统计四块展示样式，其余全部原逻辑不动
st.markdown("<h2 style='margin-top:0; margin-bottom:12px;'>🎯 实时纠错系统 (位移矩阵版)</h2>", unsafe_allow_html=True)
col1, col2 = st.columns([0.65, 0.35])
next_pred = get_recommendation(st.session_state.history_list)

# 左侧统计+历史表格
with col1:
    st.subheader("📈 连中/连败统计")
    streak_data = calc_streak_info(st.session_state.history_list)
    s1, s2, s3, s4 = st.columns(4)

    # 彩色圆角统计块【仅UI渲染改动，数值逻辑不变】
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

# 右侧预判、录入、清空【表单输入框、提交判断、清空逻辑完全原样，无改动】
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
