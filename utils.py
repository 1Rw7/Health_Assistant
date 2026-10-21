import pandas as pd
import numpy as np
import sqlite3
from zhipuai import ZhipuAI
from sklearn.ensemble import RandomForestClassifier

# ================= 1. 基础计算模块 =================
def calc_targets(age, gender, weight, height, activity, goal):
    if gender == '男':
        bmr = 10 * weight + 6.25 * height - 5 * age + 5
    else:
        bmr = 10 * weight + 6.25 * height - 5 * age - 161
    activity_factors = {'久坐': 1.2, '轻度': 1.375, '中度': 1.55, '高强度': 1.725}
    tdee = bmr * activity_factors.get(activity, 1.2)
    if goal == '减脂': target_cal = tdee - 400
    elif goal == '增肌': target_cal = tdee + 300
    else: target_cal = tdee
    return round(bmr), round(tdee), round(target_cal)

# ================= 2. 机器学习模型模块 =================
def train_health_model():
    np.random.seed(42)
    df = pd.DataFrame({
        'calorie_diff': np.random.randint(-600, 600, 1000),
        'protein_ratio': np.random.uniform(0.1, 0.4, 1000), 
        'sleep_hours': np.random.uniform(4, 10, 1000),
        'exercise_min': np.random.randint(0, 90, 1000)
    })
    labels = []
    for _, row in df.iterrows():
        if row['sleep_hours'] > 7 and row['exercise_min'] > 30 and abs(row['calorie_diff']) < 500 and row['protein_ratio'] > 0.15:
            labels.append(2)
        elif row['sleep_hours'] < 5 or abs(row['calorie_diff']) > 800:
            labels.append(0)
        else:
            labels.append(1)
    df['label'] = labels
    X = df[['calorie_diff', 'protein_ratio', 'sleep_hours', 'exercise_min']]
    y = df['label']
    model = RandomForestClassifier(random_state=42)
    model.fit(X, y)
    return model

# ================= 3. 数据库与用户模块 =================
def init_db():
    conn = sqlite3.connect('data/health_data.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (username TEXT PRIMARY KEY, age INT, gender TEXT, height REAL, weight REAL, activity TEXT, goal TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS diet_log
                 (username TEXT, date TEXT, food TEXT, weight REAL, cal REAL, protein REAL, carb REAL, fat REAL)''')
    c.execute('''CREATE TABLE IF NOT EXISTS exercise_log
                 (username TEXT, date TEXT, type TEXT, target TEXT, duration INTEGER)''')
    c.execute('''CREATE TABLE IF NOT EXISTS workout_log
                 (username TEXT, date TEXT, workout_name TEXT)''')
    conn.commit()
    conn.close()

def register_user(username, age, gender, height, weight, activity, goal):
    conn = sqlite3.connect('data/health_data.db')
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO users VALUES (?, ?, ?, ?, ?, ?, ?)", (username, age, gender, height, weight, activity, goal))
    conn.commit()
    conn.close()

def get_user_profile(username):
    conn = sqlite3.connect('data/health_data.db')
    df = pd.read_sql_query(f"SELECT * FROM users WHERE username='{username}'", conn)
    conn.close()
    if not df.empty:
        return df.iloc[0].to_dict()
    return None

# ================= 4. 饮食与运动操作 =================
def add_diet_record(username, date, food, weight, cal, protein, carb, fat):
    conn = sqlite3.connect('data/health_data.db')
    c = conn.cursor()
    c.execute("INSERT INTO diet_log VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (username, date, food, weight, cal, protein, carb, fat))
    conn.commit()
    conn.close()

def add_exercise_record(username, date, ex_type, target, duration):
    conn = sqlite3.connect('data/health_data.db')
    c = conn.cursor()
    c.execute("INSERT INTO exercise_log VALUES (?, ?, ?, ?, ?)", (username, date, ex_type, target, duration))
    conn.commit()
    conn.close()

def get_today_data(username, date):
    conn = sqlite3.connect('data/health_data.db')
    df_diet = pd.read_sql_query(f"SELECT * FROM diet_log WHERE username='{username}' AND date='{date}'", conn)
    df_ex = pd.read_sql_query(f"SELECT * FROM exercise_log WHERE username='{username}' AND date='{date}'", conn)
    conn.close()
    return df_diet, df_ex

def get_last_7_days_data(username):
    conn = sqlite3.connect('data/health_data.db')
    query = f"SELECT date, SUM(cal) as total_cal, SUM(protein) as total_protein FROM diet_log WHERE username='{username}' GROUP BY date ORDER BY date DESC LIMIT 7"
    df_diet = pd.read_sql_query(query, conn)
    query_ex = f"SELECT date, SUM(duration) as total_exercise FROM exercise_log WHERE username='{username}' GROUP BY date ORDER BY date DESC LIMIT 7"
    df_ex = pd.read_sql_query(query_ex, conn)
    conn.close()
    if df_diet.empty: return pd.DataFrame()
    df_merged = pd.merge(df_diet, df_ex, on='date', how='outer').fillna(0)
    return df_merged.sort_values(by='date')

# ================= 5. 打卡与日历 =================
def mark_workout_done(username, date_str, workout_name):
    conn = sqlite3.connect('data/health_data.db')
    c = conn.cursor()
    c.execute("SELECT * FROM workout_log WHERE username=? AND date=? AND workout_name=?", (username, date_str, workout_name))
    if not c.fetchone():
        c.execute("INSERT INTO workout_log VALUES (?, ?, ?)", (username, date_str, workout_name))
        conn.commit()
    conn.close()

def get_month_workout_logs(username, year, month):
    conn = sqlite3.connect('data/health_data.db')
    c = conn.cursor()
    start_date = f"{year}-{month:02d}-01"
    end_date = f"{year+1}-01-01" if month == 12 else f"{year}-{month+1:02d}-01"
    c.execute("SELECT date FROM workout_log WHERE username=? AND date >= ? AND date < ?", (username, start_date, end_date))
    rows = c.fetchall()
    conn.close()
    return [row[0] for row in rows]

# ================= 6. 大模型 =================
def generate_llm_report(api_key, diet_data, exercise_data, goal):
    try:
        client = ZhipuAI(api_key=api_key)
        prompt = f"你是私人教练。学员目标：{goal}，饮食：{diet_data['total_cal']} kcal，蛋白质：{diet_data['total_protein']}g，运动：{exercise_data}。请给出200字内的口语化建议，有鼓励性。"
        response = client.chat.completions.create(model="glm-4-flash-250414", messages=[{"role": "user", "content": prompt}], temperature=0.7)
        return response.choices[0].message.content
    except Exception as e:
        return f"AI 教练暂时休息了。错误信息：{e}"