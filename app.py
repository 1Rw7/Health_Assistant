import streamlit as st
import pandas as pd
import datetime
import sqlite3
import plotly.express as px
import calendar
import random
from utils import *

# 页面配置
st.set_page_config(page_title="健康助手 Pro Max", layout="wide")

# ================= 1. 数据库初始化（增加密码字段） =================
def init_user_db():
    conn = sqlite3.connect('data/health_data.db')
    c = conn.cursor()
    # 重构用户表，加入 password 字段
    c.execute('''CREATE TABLE IF NOT EXISTS users_auth
                 (username TEXT PRIMARY KEY, password TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS user_profiles
                 (username TEXT PRIMARY KEY, age INT, gender TEXT, height REAL, weight REAL, activity TEXT, goal TEXT)''')
    conn.commit()
    conn.close()

init_user_db()
init_db()  # <--- 补上这一行，用来创建饮食和运动表

# ================= 2. 登录/注册界面拦截 =================
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.username = None

if not st.session_state.logged_in:
    st.title("🥗 欢迎来到健康饮食生活助手")
    st.write("请登录或注册以管理您的专属健康计划")
    st.write("---")
    
    # 居中的登录卡片
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        tab_login, tab_register = st.tabs(["🔒 登录", "📝 注册新账号"])
        
        # --- 登录 Tab ---
        with tab_login:
            login_user = st.text_input("用户名", key="login_user")
            login_pwd = st.text_input("密码", type="password", key="login_pwd")
            if st.button("登录", use_container_width=True):
                conn = sqlite3.connect('data/health_data.db')
                c = conn.cursor()
                c.execute("SELECT password FROM users_auth WHERE username=?", (login_user,))
                res = c.fetchone()
                conn.close()
                
                if res and res[0] == login_pwd:
                    st.session_state.logged_in = True
                    st.session_state.username = login_user
                    st.success("登录成功！")
                    st.rerun()
                else:
                    st.error("用户名或密码错误！")
                    
        # --- 注册 Tab ---
        with tab_register:
            reg_user = st.text_input("设置用户名", key="reg_user")
            reg_pwd = st.text_input("设置密码", type="password", key="reg_pwd")
            reg_pwd2 = st.text_input("确认密码", type="password", key="reg_pwd2")
            
            st.write("*(请填写您的健康基础信息)*")
            col_a, col_b = st.columns(2)
            with col_a:
                reg_age = st.number_input("年龄", 18, 80, 25)
                reg_gender = st.selectbox("性别", ["男", "女"])
                reg_height = st.number_input("身高 (cm)", 140, 220, 175)
            with col_b:
                reg_weight = st.number_input("体重 (kg)", 40, 150, 70)
                reg_activity = st.selectbox("活动量", ["久坐", "轻度", "中度", "高强度"])
                reg_goal = st.selectbox("目标", ["减脂", "增肌", "维持"])
                
            if st.button("注册并登录", use_container_width=True):
                if not reg_user or not reg_pwd:
                    st.warning("用户名和密码不能为空！")
                elif reg_pwd != reg_pwd2:
                    st.warning("两次输入的密码不一致！")
                else:
                    conn = sqlite3.connect('data/health_data.db')
                    c = conn.cursor()
                    try:
                        # 写入账号
                        c.execute("INSERT INTO users_auth VALUES (?, ?)", (reg_user, reg_pwd))
                        # 写入档案
                        c.execute("INSERT INTO user_profiles VALUES (?, ?, ?, ?, ?, ?, ?)", 
                                  (reg_user, reg_age, reg_gender, reg_height, reg_weight, reg_activity, reg_goal))
                        conn.commit()
                        st.session_state.logged_in = True
                        st.session_state.username = reg_user
                        st.success("注册成功！正在进入...")
                        st.rerun()
                    except sqlite3.IntegrityError:
                        st.error("该用户名已被注册，请换一个！")
                    finally:
                        conn.close()
    
    # 如果未登录，强制停止渲染后面的代码
    st.stop()

# ================= 3. 登录成功后的主程序 =================
# 获取当前用户档案
conn = sqlite3.connect('data/health_data.db')
df_profile = pd.read_sql_query(f"SELECT * FROM user_profiles WHERE username='{st.session_state.username}'", conn)
conn.close()

if not df_profile.empty:
    user = df_profile.iloc[0]
    username = user['username']
    age, gender, height, weight = user['age'], user['gender'], user['height'], user['weight']
    activity, goal = user['activity'], user['goal']

# 模型加载
@st.cache_resource
def load_model(): return train_health_model()
model = load_model()

# --- 侧边栏 ---
with st.sidebar:
    st.title(f"👤 {username}")
    if st.button("🚪 退出登录"):
        st.session_state.logged_in = False
        st.session_state.username = None
        st.rerun()
        
    st.write("---")
    st.header("📅 当前日期")
    selected_date = st.date_input("选择日期", datetime.date.today())
    current_date_str = selected_date.strftime("%Y-%m-%d") 
    
    bmr, tdee, target_cal = calc_targets(age, gender, weight, height, activity, goal)
    bmi = weight / ((height/100) ** 2)
    st.info(f"📊 **BMI**: {bmi:.1f}")
    st.success(f"🎯 目标热量：**{target_cal} kcal**")
    
    st.write("---")
    st.header("🤖 AI 助手")
    api_key = st.text_input("智谱 API Key", type="password")

# 加载食物和动作库
food_df = pd.read_csv('data/food_db.csv')
workout_dict = {
    "无氧 (力量训练)": {"胸": ["卧推", "哑铃飞鸟", "俯卧撑", "绳索夹胸"], "背": ["引体向上", "高位下拉", "杠铃划船", "硬拉"], "肩": ["哑铃推举", "侧平举", "面拉"], "腿": ["深蹲", "腿举", "弓步蹲", "罗马尼亚硬拉"], "二头/三头": ["二头弯举", "三头下压", "窄距卧推"], "腹肌": ["卷腹", "平板支撑", "悬垂举腿"]},
    "有氧 (心肺训练)": {"全身": ["慢跑", "快走", "骑车", "跳绳", "游泳", "椭圆机"]}
}

tab1, tab2, tab3, tab4 = st.tabs(["📝 饮食运动记录", "📊 数据看板", "💡 智能排课与打卡", "🧠 AI 教练深度分析"])

# ================= Tab 1: 记录 =================
with tab1:
    st.subheader(f"📝 记录 {current_date_str} 的数据")
    col_left, col_right = st.columns([1, 1])
    with col_left:
        st.markdown("### 🍽️ 饮食批量录入")
        selected_foods = st.multiselect("选择食物（可多选）", food_df['食物名称'].tolist())
        food_weights = {}
        if selected_foods:
            for food in selected_foods: food_weights[food] = st.number_input(f"【{food}】的重量 (克)", 10, 1000, 100, key=f"w_{food}")
        if st.button("✅ 批量记录饮食"):
            if selected_foods:
                for food in selected_foods:
                    w = food_weights[food]
                    row = food_df[food_df['食物名称'] == food].iloc[0]
                    add_diet_record(username, current_date_str, food, w, (row['热量(kcal/100g)']*w)/100, (row['蛋白质(g/100g)']*w)/100, (row['碳水(g/100g)']*w)/100, (row['脂肪(g/100g)']*w)/100)
                st.toast("饮食录入成功！"); st.rerun()

    with col_right:
        st.markdown("### 🏃 运动联动录入")
        ex_category = st.radio("运动类别", list(workout_dict.keys()), horizontal=True)
        target_area = st.selectbox("选择锻炼部位", list(workout_dict[ex_category].keys())) if ex_category == "无氧 (力量训练)" else "全身"
        selected_actions = st.multiselect("选择具体动作（可多选）", workout_dict[ex_category][target_area])
        action_minutes = {}
        if selected_actions:
            for action in selected_actions: action_minutes[action] = st.number_input(f"【{action}】时长 (分钟)", 5, 180, 30, key=f"m_{action}")
        if st.button("✅ 批量记录运动"):
            if selected_actions:
                for action in selected_actions:
                    db_type = "无氧" if "无氧" in ex_category else "有氧"
                    add_exercise_record(username, current_date_str, db_type, action, action_minutes[action])
                st.toast("运动录入成功！"); st.rerun()

    df_diet, df_ex = get_today_data(username, current_date_str)
    st.write("---")
    col_d1, col_d2 = st.columns(2)
    with col_d1:
        st.write("📋 **当日饮食明细**")
        if not df_diet.empty: st.dataframe(df_diet[['food', 'weight', 'cal', 'protein']], use_container_width=True)
        else: st.caption("暂无记录")
    with col_d2:
        st.write("🏃 **当日运动明细**")
        if not df_ex.empty: st.dataframe(df_ex[['type', 'target', 'duration']], use_container_width=True)
        else: st.caption("暂无记录")

# ================= Tab 2: 看板 =================
with tab2:
    st.subheader(f"📈 {current_date_str} 数据看板")
    df_diet, df_ex = get_today_data(username, current_date_str)
    if not df_diet.empty or not df_ex.empty:
        total_cal, total_protein = df_diet['cal'].sum(), df_diet['protein'].sum()
        total_carb, total_fat = df_diet['carb'].sum(), df_diet['fat'].sum()
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("当日热量", f"{total_cal:.0f} kcal", f"目标 {target_cal}", delta_color="inverse")
        col2.metric("蛋白质", f"{total_protein:.1f}g", f"缺口 {max(0, 1.6*weight - total_protein):.1f}g", delta_color="inverse")
        col3.metric("碳脂比", f"{total_carb:.0f}g / {total_fat:.0f}g")
        ex_anaerobic = df_ex[df_ex['type'] == '无氧']['duration'].sum() if not df_ex.empty else 0
        ex_aerobic = df_ex[df_ex['type'] == '有氧']['duration'].sum() if not df_ex.empty else 0
        col4.metric("运动(无氧/有氧)", f"{ex_anaerobic} / {ex_aerobic} min")
        st.write("---")
        col_chart1, col_chart2 = st.columns(2)
        with col_chart1:
            fig1 = px.pie(values=[total_protein*4, total_carb*4, total_fat*9], names=['蛋白质', '碳水', '脂肪'], title="三大营养素供能占比")
            st.plotly_chart(fig1, use_container_width=True)
        with col_chart2:
            df_history = get_last_7_days_data(username)
            if not df_history.empty:
                fig2 = px.line(df_history, x='date', y='total_cal', markers=True, title="近7日热量摄入趋势")
                fig2.add_hline(y=target_cal, line_dash="dash", line_color="red", annotation_text="目标线")
                st.plotly_chart(fig2, use_container_width=True)
        csv = df_diet.to_csv(index=False).encode('utf-8')
        st.download_button("📥 导出今日饮食记录 (CSV)", csv, "diet_log.csv", "text/csv")
    else: st.info(f"{current_date_str} 暂无数据。")

# ================= Tab 3: 排课 =================
with tab3:
    st.subheader(f"🎯 智能动态排课")
    col_set1, col_set2 = st.columns(2)
    with col_set1: days_per_week = st.slider("你每周计划练几天？", 2, 6, 4)
    with col_set2:
        if st.button("🔄 换一批计划"): st.session_state.seed = random.randint(1, 1000)
    if 'seed' not in st.session_state: st.session_state.seed = random.randint(1, 1000)
    random.seed(st.session_state.seed)
    strength_pool = ["胸 + 三头", "背 + 二头", "腿 + 核心", "肩 + 腹肌"]
    cardio_pool = ["有氧 (慢跑) 40min", "有氧 (跳绳) 30min", "有氧 (游泳) 40min"]
    selected_plan = []
    if goal == "增肌":
        selected_plan = random.sample(strength_pool, min(days_per_week, len(strength_pool)))
        if days_per_week > len(strength_pool): selected_plan += ["低强度有氧 20min"] * (days_per_week - len(strength_pool))
    elif goal == "减脂":
        num_strength = days_per_week // 2; num_cardio = days_per_week - num_strength
        selected_plan = random.sample(strength_pool, num_strength) + random.sample(cardio_pool, min(num_cardio, len(cardio_pool)))
    else: selected_plan = random.sample(strength_pool + cardio_pool, days_per_week)
    week_indices = list(range(7)); training_days = sorted(random.sample(week_indices, days_per_week))
    final_schedule = ["休息 / 拉伸"] * 7
    for i, day_idx in enumerate(training_days):
        if i < len(selected_plan): final_schedule[day_idx] = selected_plan[i]
    today_weekday = datetime.datetime.today().weekday()
    week_names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    today_task = final_schedule[today_weekday]
    st.markdown("### 🔥 今日任务")
    if "休息" in today_task: st.success(f"今天是**{week_names[today_weekday]}**，你的任务是：**{today_task}**。")
    else: st.info(f"今天是**{week_names[today_weekday]}**，你的任务是：**{today_task}**。")
    if st.button("✅ 一键完成打卡", use_container_width=True):
        db_type = "有氧" if "有氧" in today_task else ("无氧" if "休息" not in today_task else "休息")
        if db_type != "休息": add_exercise_record(username, current_date_str, db_type, today_task, 40)
        mark_workout_done(username, current_date_str, today_task)
        st.success("打卡成功！"); st.balloons()
    st.write("---"); st.markdown("### 📅 本周动态课表")
    cols = st.columns(7)
    for i in range(7):
        with cols[i]:
            if i == today_weekday: st.markdown(f"""<div style='background-color: #ffe6e6; border: 2px solid #ff4b4b; border-radius: 10px; padding: 10px; text-align: center; height: 120px;'><b style='color: #ff4b4b;'>{week_names[i]} (今天)</b><br><br><span style='font-size: 14px;'>{final_schedule[i]}</span></div>""", unsafe_allow_html=True)
            else: st.markdown(f"""<div style='background-color: #f0f2f6; border-radius: 10px; padding: 10px; text-align: center; height: 120px;'><b>{week_names[i]}</b><br><br><span style='font-size: 14px; color: #555;'>{final_schedule[i]}</span></div>""", unsafe_allow_html=True)

# ================= Tab 4: AI分析 =================
with tab4:
    st.subheader("🧠 AI 健康日历与深度报告")
    if 'selected_date' not in st.session_state: st.session_state.selected_date = current_date_str
    if 'current_cal_month' not in st.session_state: st.session_state.current_cal_month = datetime.date.today().month
    if 'current_cal_year' not in st.session_state: st.session_state.current_cal_year = datetime.date.today().year
    col_prev, col_title, col_next = st.columns([1, 2, 1])
    with col_prev:
        if st.button("⬅️ 上个月", use_container_width=True):
            if st.session_state.current_cal_month == 1: st.session_state.current_cal_month = 12; st.session_state.current_cal_year -= 1
            else: st.session_state.current_cal_month -= 1
            st.rerun()
    with col_title: st.markdown(f"<h3 style='text-align: center;'>{st.session_state.current_cal_year}年 {st.session_state.current_cal_month}月</h3>", unsafe_allow_html=True)
    with col_next:
        if st.button("下个月 ➡️", use_container_width=True):
            if st.session_state.current_cal_month == 12: st.session_state.current_cal_month = 1; st.session_state.current_cal_year += 1
            else: st.session_state.current_cal_month += 1
            st.rerun()
    year = st.session_state.current_cal_year; month = st.session_state.current_cal_month
    num_days = calendar.monthrange(year, month)[1]; first_weekday = calendar.monthrange(year, month)[0]
    checked_dates = get_month_workout_logs(username, year, month)
    cols = st.columns(7); week_headers = ["一", "二", "三", "四", "五", "六", "日"]
    for i, wd in enumerate(week_headers): cols[i].write(f"<div style='text-align:center; color:gray;'>{wd}</div>", unsafe_allow_html=True)
    day_count = 1
    for _ in range(first_weekday): cols[_].write("")
    while day_count <= num_days:
        date_str = f"{year}-{month:02d}-{day_count:02d}"; has_workout = date_str in checked_dates
        col_idx = (first_weekday + day_count - 1) % 7
        with cols[col_idx]:
            btn_label = f"{day_count} 🏃" if has_workout else f"{day_count}"
            is_selected = (st.session_state.selected_date == date_str)
            if st.button(btn_label, key=f"cal_{date_str}", type="primary" if is_selected else "secondary", use_container_width=True):
                st.session_state.selected_date = date_str; st.rerun()
        day_count += 1
        if col_idx == 6 and day_count <= num_days: cols = st.columns(7)
    st.write("---"); target_date = st.session_state.selected_date
    st.markdown(f"### 📋 {target_date} 的健康诊断")
    df_selected_diet = pd.read_sql_query(f"SELECT * FROM diet_log WHERE username='{username}' AND date='{target_date}'", sqlite3.connect('data/health_data.db'))
    df_selected_ex = pd.read_sql_query(f"SELECT * FROM exercise_log WHERE username='{username}' AND date='{target_date}'", sqlite3.connect('data/health_data.db'))
    if not df_selected_diet.empty or not df_selected_ex.empty:
        sel_cal = df_selected_diet['cal'].sum(); sel_protein = df_selected_diet['protein'].sum()
        sel_exercise = df_selected_ex['duration'].sum() if not df_selected_ex.empty else 0
        score = 0
        if abs(sel_cal - target_cal) < (target_cal * 0.15): score += 20
        if sel_protein >= 1.5 * weight: score += 20
        if sel_exercise > 0: score += 20
        if not df_selected_ex.empty and "无氧" in df_selected_ex['type'].values: score += 20
        score += 10 
        if score >= 80: st.success(f"🌟 **得分：{score} / 100（优秀）** - 完美的一天！")
        elif score >= 60: st.warning(f"⭐ **得分：{score} / 100（中等）** - 有进步空间。")
        else: st.error(f"⚠️ **得分：{score} / 100（需改进）** - 健康亮红灯。")
        st.write("---"); st.markdown("#### 🤖 大模型私教点评")
        if api_key:
            if st.button("让 AI 教练分析一下今天的数据"):
                with st.spinner("教练正在思考中..."):
                    diet_data = {'total_cal': sel_cal, 'total_protein': sel_protein}
                    ex_data = f"{sel_exercise}分钟" if sel_exercise > 0 else "无运动"
                    report = generate_llm_report(api_key, diet_data, ex_data, goal)
                    st.info(report)
        else: st.warning("⚠️ 请在左侧边栏输入你的智谱 API Key。")
    else: st.info(f"{target_date} 暂无数据记录，快去补录吧！")