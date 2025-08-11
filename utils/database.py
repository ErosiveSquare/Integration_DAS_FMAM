# OpmImprove_Integration_DAS_FMAM/utils/database.py

import sqlite3
import pandas as pd
import json
import os
from datetime import datetime

# --- 关键修复：定义一个绝对且唯一的数据库路径 ---
# 获取当前文件(database.py)所在的目录 (your_project_root/utils)
_CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
# 从当前目录向上移动一级，获取项目根目录 (your_project_root)
_PROJECT_ROOT = os.path.abspath(os.path.join(_CURRENT_DIR, '..'))
# 在项目根目录下创建 'data' 文件夹（如果不存在）
_DATA_DIR = os.path.join(_PROJECT_ROOT, 'data')
os.makedirs(_DATA_DIR, exist_ok=True)
# 定义数据库文件的最终绝对路径
# 这样可以确保项目中的任何文件导入时，都指向这同一个文件
DB_PATH = os.path.join(_DATA_DIR, "station_archive.db")


def get_db_connection():
    """建立并返回数据库连接"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """初始化数据库，创建或更新必要的表"""
    # 每次调用时打印路径，用于调试
    # print(f"DEBUG: Database path is {DB_PATH}")
    conn = get_db_connection()
    cursor = conn.cursor()

    # 创建电站档案表
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS station_profile (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        station_name TEXT NOT NULL DEFAULT '未命名电站',
        location TEXT DEFAULT '未知地点',
        commission_date TEXT,
        e_rated REAL DEFAULT 100.0,
        p_rated REAL DEFAULT 25.0
    )
    ''')

    # 插入默认档案
    cursor.execute('''
    INSERT OR IGNORE INTO station_profile (id, station_name, location, commission_date, e_rated, p_rated)
    VALUES (1, '演示液流电池储能电站', '数字孪生园区', '2023-01-01', 100.0, 25.0)
    ''')

    # 创建历史决策记录表
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS decision_records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_timestamp TEXT NOT NULL,
        station_name TEXT DEFAULT '未知电站',
        market_mode TEXT,
        decision_mode TEXT,
        net_profit REAL,
        da_profit REAL,
        fm_profit REAL,
        total_throughput REAL,
        equivalent_cycles REAL
    )
    ''')

    # 兼容旧数据库的升级逻辑
    cursor.execute("PRAGMA table_info(decision_records)")
    columns = [row['name'] for row in cursor.fetchall()]

    if 'station_name' not in columns:
        cursor.execute("ALTER TABLE decision_records ADD COLUMN station_name TEXT DEFAULT '未知电站'")
    if 'market_mode' not in columns:
        cursor.execute("ALTER TABLE decision_records ADD COLUMN market_mode TEXT")
    if 'da_profit' not in columns:
        cursor.execute("ALTER TABLE decision_records ADD COLUMN da_profit REAL")
    if 'fm_profit' not in columns:
        cursor.execute("ALTER TABLE decision_records ADD COLUMN fm_profit REAL")

    conn.commit()
    conn.close()


# load_station_profile, save_station_profile, save_decision_record, load_decision_records
# 函数保持不变，因为它们已经使用了正确的 DB_PATH。
# 这里为了完整性，再次提供它们
def load_station_profile():
    try:
        conn = get_db_connection()
        profile = conn.execute('SELECT * FROM station_profile WHERE id = 1').fetchone()
        conn.close()
        return dict(profile) if profile else None
    except sqlite3.OperationalError:
        return None


def save_station_profile(profile_data):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
    UPDATE station_profile
    SET station_name = ?, location = ?, commission_date = ?, e_rated = ?, p_rated = ?
    WHERE id = 1
    ''', (
        profile_data['station_name'],
        profile_data['location'],
        profile_data['commission_date'],
        profile_data['e_rated'],
        profile_data['p_rated']
    ))
    conn.commit()
    conn.close()


def save_decision_record(record_data: dict):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
    INSERT INTO decision_records (
        run_timestamp, station_name, market_mode, decision_mode, 
        net_profit, da_profit, fm_profit,
        total_throughput, equivalent_cycles
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        record_data.get('run_timestamp', datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        record_data.get('station_name', '未知电站'),
        record_data.get('market_mode'),
        record_data.get('decision_mode'),
        record_data.get('net_profit', 0),
        record_data.get('da_profit', 0),
        record_data.get('fm_profit', 0),
        record_data.get('total_throughput', 0),
        record_data.get('equivalent_cycles', 0)
    ))
    conn.commit()
    conn.close()


def load_decision_records():
    conn = get_db_connection()
    try:
        query = "SELECT id, run_timestamp, station_name, market_mode, decision_mode, net_profit, da_profit, fm_profit, total_throughput, equivalent_cycles FROM decision_records ORDER BY run_timestamp DESC"
        records_df = pd.read_sql_query(query, conn)
    except (pd.errors.DatabaseError, sqlite3.OperationalError):
        records_df = pd.DataFrame(columns=[
            'id', 'run_timestamp', 'station_name', 'market_mode', 'decision_mode',
            'net_profit', 'da_profit', 'fm_profit',
            'total_throughput', 'equivalent_cycles'
        ])
    finally:
        conn.close()
    return records_df
