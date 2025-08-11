import streamlit as st
import pandas as pd
import sys
import os
import numpy as np
from datetime import datetime  # 数据库集成：导入datetime用于记录时间戳

# 获取项目根目录
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

# 确保data目录存在
data_dir = os.path.join(project_root, 'data')
os.makedirs(data_dir, exist_ok=True)

# 导入原有的日前市场模块
from models.optimization_model import FlowBatteryDayAheadMarketModel, mode_selection_rarr, \
    generate_segmented_bid_table, generate_bid_table, calculate_kpis
from models.parameter_config import get_default_battery_params, validate_battery_params
from utils.data_processor import generate_price_forecast, save_price_forecast, load_price_forecast
from utils.visualization import generate_comprehensive_visualization

# 导入新增的调频市场模块
from models.multi_market_coordinator import MultiMarketCoordinator
from utils.frequency_data_processor import create_frequency_market_params, create_cost_params, validate_frequency_params
from utils.multi_market_visualization import generate_multi_market_visualization, generate_frequency_market_analysis, \
    generate_cost_breakdown_chart, generate_market_comparison_chart, create_kpi_metrics_display

# --- 数据库集成：导入数据库工具函数 ---
# 假设您的 save_decision_record 函数也在此文件中
try:
    from utils.database import init_db, load_station_profile, save_decision_record
except ImportError:
    st.error(
        "无法从 'utils.database' 导入必要的函数。请确保该文件存在且包含 init_db, load_station_profile 和 save_decision_record。")
    st.stop()


def get_realistic_battery_params():
    """获取基于实际液流电池技术的合理参数"""
    return {
        # 额定参数 - 基于实际项目规模
        'E_rated': 100.0,  # 100MWh容量
        'P_rated': 25.0,  # 25MW功率，4小时放电设计（更保守）

        # 能量参数
        'E_0': 50.0,  # 初始能量
        'E_T_target': 50.0,  # 目标能量
        'initial_soc': 0.50,  # 初始SOC

        # 效率参数 - 基于优化后的液流电池性能
        'η_charge': 0.85,  # 85%充电效率（技术优化后水平）
        'η_discharge': 0.88,  # 88%放电效率（技术优化后水平）

        # SOC参数 - 更保守的运行范围
        'SOC_min': 0.10,  # 10%最小SOC
        'SOC_max': 0.90,  # 90%最大SOC

        # 循环与退化 - 基于实际运行经验
        'N_cycle_max': 2.0,  # 2次/日循环（更保守）
        'k': 0.05,  # 0.05退化成本系数（考虑实际退化）

        # 运维成本 - 基于实际运营成本
        'C_OM': 5000,  # 5000元/日运维成本（更现实）

        # 功率爬坡 - 基于优化后的技术能力
        'R_ramp': 15.0,  # 15MW/15min爬坡速率（技术优化后）

        # 电解液流量 - 基于实际系统参数
        'Q_flow_min': 30,  # 30L/min最小流量
        'Q_flow_max': 300,  # 300L/min最大流量
        'flow_power_ratio': 6.0  # 6.0 L/min/MW流量功率比
    }


# --- 数据库集成：新增函数，用于从数据库加载参数并与默认值合并 ---
def load_parameters_from_db_and_defaults():
    """
    首先加载默认参数，然后尝试从数据库加载电站档案，
    并用档案中的值（如E_rated, P_rated）覆盖默认值。
    """
    # 1. 获取一套完整的默认参数
    params = get_realistic_battery_params()

    # 2. 尝试从数据库加载电站档案
    profile = load_station_profile()

    # 3. 如果档案存在，用档案数据更新默认参数
    if profile:
        st.sidebar.info(f"✅ 已加载电站 **{profile.get('station_name', '未知')}** 的档案。")
        params['E_rated'] = float(profile.get('e_rated', params['E_rated']))
        params['P_rated'] = float(profile.get('p_rated', params['P_rated']))
        # 初始能量和目标能量可以设置为SOC 50%
        params['E_0'] = params['E_rated'] * params['initial_soc']
        params['E_T_target'] = params['E_rated'] * params['initial_soc']
    else:
        st.sidebar.warning("⚠️ 未找到电站档案，将使用默认参数。请在“电站档案”页面进行设置。")

    return params


def display_battery_params(battery_params):
    """展示所有技术参数"""
    st.sidebar.header("🔋 储能电站技术参数")

    param_groups = {
        "💡 额定参数": ['E_rated', 'P_rated'],
        "⚡ 能量参数": ['E_0', 'E_T_target', 'initial_soc'],
        "🔄 效率参数": ['η_charge', 'η_discharge'],
        "📊 SOC参数": ['SOC_min', 'SOC_max'],
        "🔧 循环与退化": ['N_cycle_max', 'k'],
        "💰 运维成本": ['C_OM'],
        "⚡ 功率爬坡": ['R_ramp'],
        "🌊 电解液流量": ['Q_flow_min', 'Q_flow_max', 'flow_power_ratio']
    }

    for group, params in param_groups.items():
        with st.sidebar.expander(group):
            for param in params:
                if param in battery_params:
                    value = battery_params[param]
                    if isinstance(value, float):
                        st.write(f"{param}: {value:.3f}")
                    else:
                        st.write(f"{param}: {value}")


def validate_parameters(battery_params, da_config, frequency_config):
    """验证储能电站参数的合理性"""
    warnings = []
    errors = []

    # 基本参数检查
    if battery_params['P_rated'] <= 0:
        errors.append("❌ 额定功率必须大于0")

    if battery_params['E_rated'] <= 0:
        errors.append("❌ 额定容量必须大于0")

    # SOC范围检查
    if battery_params['SOC_max'] <= battery_params['SOC_min']:
        errors.append("❌ 最大SOC必须大于最小SOC")

    # 效率参数检查
    if not (0.5 <= battery_params['η_charge'] <= 1.0):
        warnings.append("⚠️ 充电效率建议在50%-100%范围内")

    if not (0.5 <= battery_params['η_discharge'] <= 1.0):
        warnings.append("⚠️ 放电效率建议在50%-100%范围内")

    return warnings, errors


def display_da_market_params_config():
    """日前市场参数配置界面 - 基于实际市场情况调整"""
    st.header("📈 日前市场参数配置")

    st.info("💡 配置日前市场优化相关参数")

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("🔄 循环寿命参数")

        N_cycle_max = st.number_input(
            "最大等效循环次数 (次/日)",
            min_value=1.0, max_value=3.0, value=2.0, step=0.1,
            help="每日最大等效循环次数限制，基于电池寿命考虑"
        )

        k = st.number_input(
            "度电退化成本系数",
            min_value=0.02, max_value=0.08, value=0.05, step=0.005,
            help="电池退化成本系数，基于实际运行经验"
        )

        st.subheader("💰 经济性参数")

        C_OM = st.number_input(
            "固定运维成本 (元/日)",
            min_value=3000, max_value=8000, value=5000, step=200,
            help="储能电站日固定运维成本，基于实际运营数据"
        )

        min_discharge_price = st.number_input(
            "最低放电价格 (元/MWh)",
            min_value=200.0, max_value=350.0, value=280.0, step=10.0,
            help="低于此价格不进行放电"
        )

        max_charge_price = st.number_input(
            "最高充电价格 (元/MWh)",
            min_value=400.0, max_value=600.0, value=500.0, step=20.0,
            help="高于此价格不进行充电"
        )

    with col2:
        st.subheader("⚡ 功率约束参数")

        R_ramp = st.number_input(
            "功率爬坡速率 (MW/15min)",
            min_value=5.0, max_value=20.0, value=15.0, step=1.0,
            help="功率变化速率限制，基于优化后的技术能力"
        )

        power_reserve_ratio = st.slider(
            "功率预留比例",
            min_value=0.02, max_value=0.08, value=0.05, step=0.005,
            help="功率预留比例，确保系统安全运行"
        )

        st.subheader("🎯 风险管理参数")

        soc_target_weight = st.number_input(
            "SOC目标权重",
            min_value=100.0, max_value=300.0, value=200.0, step=25.0,
            help="SOC目标偏差惩罚权重"
        )

        risk_penalty = st.number_input(
            "风险惩罚系数",
            min_value=10.0, max_value=30.0, value=20.0, step=2.5,
            help="风险控制惩罚系数"
        )

    return {
        'N_cycle_max': N_cycle_max,
        'k': k,
        'C_OM': C_OM,
        'min_discharge_price': min_discharge_price,
        'max_charge_price': max_charge_price,
        'R_ramp': R_ramp,
        'power_reserve_ratio': power_reserve_ratio,
        'soc_target_weight': soc_target_weight,
        'risk_penalty': risk_penalty
    }


def display_frequency_params_config():
    """调频市场参数配置界面 - 基于实际市场情况调整"""
    st.header("⚡ 调频市场参数配置")

    st.info("💡 配置调频辅助服务市场相关参数")

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("📋 市场规则参数")

        verified_cost = st.number_input(
            "核定成本 (元/MWh)",
            min_value=180.0, max_value=250.0, value=220.0, step=5.0,
            help="储能电站核定成本，基于实际成本核算"
        )

        measured_regulation_rate = st.number_input(
            "实测调节速率 (MW/min)",
            min_value=2.0, max_value=5.0, value=3.0, step=0.2,
            help="储能系统实测调节能力，基于实际测试结果"
        )

        control_area_demand = st.number_input(
            "控制区调频需求 (MW)",
            min_value=600, max_value=1000, value=800, step=50,
            help="电网调频需求总量"
        )

        num_units = st.number_input(
            "参与机组数量",
            min_value=8, max_value=15, value=12, step=1,
            help="参与调频的机组总数"
        )

        performance_index = st.slider(
            "综合调频性能指标",
            min_value=0.80, max_value=0.92, value=0.85, step=0.01,
            help="储能系统调频性能指标，基于实际运行表现"
        )

    with col2:
        st.subheader("💸 成本模型参数")

        alpha_freq = st.slider(
            "调频活动系数",
            min_value=0.08, max_value=0.15, value=0.12, step=0.005,
            help="调频对电池的影响系数，基于实际运行数据"
        )

        degradation_rate = st.number_input(
            "退化成本率 (元/MW/h)",
            min_value=0.15, max_value=0.35, value=0.25, step=0.01,
            help="调频导致的电池退化成本，基于实际损耗"
        )

        efficiency_loss_rate = st.slider(
            "效率损失率",
            min_value=0.010, max_value=0.025, value=0.015, step=0.001,
            help="调频过程中的效率损失，基于实际测试"
        )

        om_cost_rate = st.number_input(
            "运维成本率 (元/MW/h)",
            min_value=0.10, max_value=0.25, value=0.18, step=0.01,
            help="调频服务的运维成本，基于实际运营"
        )

        price_upper_limit = st.number_input(
            "里程报价上限 (元/MW)",
            min_value=35.0, max_value=55.0, value=45.0, step=2.5,
            help="调频里程价格上限，基于市场实际水平"
        )

    return {
        'verified_cost': verified_cost,
        'measured_regulation_rate': measured_regulation_rate,
        'control_area_demand': control_area_demand,
        'num_units': num_units,
        'performance_index': performance_index,
        'alpha_freq': alpha_freq,
        'degradation_rate': degradation_rate,
        'efficiency_loss_rate': efficiency_loss_rate,
        'om_cost_rate': om_cost_rate,
        'price_upper_limit': price_upper_limit
    }


def display_data_upload():
    """数据上传专用界面"""
    st.header("📁 数据上传中心")

    st.info("💡 请上传相关数据文件，系统将根据实际数据进行优化计算")

    # 创建两个主要区域
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("📈 电价预测数据")
        st.write("**必需文件** - 日前市场电价预测")

        price_file = st.file_uploader(
            "上传电价预测数据",
            type=['csv', 'xlsx'],
            key="price_forecast",
            help="包含96个15分钟时段的电价预测数据"
        )

        if st.button("📋 下载电价数据模板", key="download_price_template"):
            template_data = generate_realistic_price_template()
            st.download_button(
                label="💾 下载模板文件",
                data=template_data.to_csv(index=False),
                file_name="price_forecast_template.csv",
                mime="text/csv"
            )

        if price_file:
            price_data = validate_price_data_format(price_file)
            if price_data is not None:
                st.success(f"✅ 电价数据验证通过")
                st.write(f"数据量: {len(price_data)} 个时段")
                st.write(f"价格范围: {price_data['price'].min():.1f} - {price_data['price'].max():.1f} 元/MWh")
                st.write(f"平均电价: {price_data['price'].mean():.1f} 元/MWh")
        else:
            price_data = None

    with col2:
        st.subheader("⚡ 调频历史数据")
        st.write("**可选文件** - 调频需求和价格历史数据")

        frequency_file = st.file_uploader(
            "上传调频历史数据",
            type=['csv', 'xlsx'],
            key="frequency_data",
            help="包含调频需求和里程价格的历史数据，用于训练价格预测模型"
        )

        if st.button("📋 下载调频数据模板", key="download_freq_template"):
            template_data = generate_realistic_frequency_template()
            st.download_button(
                label="💾 下载模板文件",
                data=template_data.to_csv(index=False),
                file_name="frequency_data_template.csv",
                mime="text/csv"
            )

        if frequency_file:
            frequency_data = validate_frequency_data_format(frequency_file)
        else:
            frequency_data = None

    # 数据上传状态总览
    st.subheader("📊 数据上传状态")
    status_col1, status_col2 = st.columns(2)

    with status_col1:
        if price_file and price_data is not None:
            st.success("✅ 电价数据已上传")
        else:
            st.error("❌ 电价数据未上传")

    with status_col2:
        if frequency_file and frequency_data is not None:
            st.success("✅ 调频数据已上传")
        else:
            st.info("ℹ️ 调频数据未上传（将使用默认数据）")

    return price_data, frequency_data


def generate_realistic_price_template():
    """生成基于实际市场情况的电价预测数据模板"""
    time_periods = 96
    data = []

    for t in range(time_periods):
        hour = t // 4
        minute = (t % 4) * 15

        # 基于实际电价模式生成更保守的模板
        if 0 <= hour < 6:  # 深夜低谷
            base_price = 250
            variation = 30 * np.sin(2 * np.pi * t / 96) + np.random.normal(0, 10)
        elif 6 <= hour < 10:  # 上午平段
            base_price = 350
            variation = 40 * np.sin(2 * np.pi * t / 96) + np.random.normal(0, 15)
        elif 10 <= hour < 14:  # 午间次高峰
            base_price = 420
            variation = 40 * np.sin(2 * np.pi * t / 96) + np.random.normal(0, 20)
        elif 14 <= hour < 18:  # 下午平段
            base_price = 380
            variation = 40 * np.sin(2 * np.pi * t / 96) + np.random.normal(0, 15)
        elif 18 <= hour < 22:  # 晚高峰
            base_price = 480
            variation = 60 * np.sin(2 * np.pi * t / 96) + np.random.normal(0, 25)
        else:  # 夜间次低谷
            base_price = 320
            variation = 40 * np.sin(2 * np.pi * t / 96) + np.random.normal(0, 15)

        price = base_price + variation
        price = max(200, min(600, price))  # 更保守的价格范围

        data.append({
            'time_period': t + 1,
            'hour': hour,
            'minute': minute,
            'time_label': f"{hour:02d}:{minute:02d}",
            'price': round(price, 2)
        })

    return pd.DataFrame(data)


def generate_realistic_frequency_template():
    """生成基于实际市场情况的调频历史数据模板"""
    from datetime import datetime, timedelta

    # 生成30天的示例数据
    data = []
    start_date = datetime.now() - timedelta(days=30)

    for day in range(30):
        current_date = start_date + timedelta(days=day)
        for hour in range(24):
            # 更保守的调频需求模拟
            base_demand = 80 + 40 * np.sin(2 * np.pi * hour / 24)
            is_weekend = 1 if current_date.weekday() >= 5 else 0
            is_peak = 1 if 8 <= hour <= 22 else 0

            weekend_factor = 0.8 if is_weekend else 1.0
            peak_factor = 1.2 if is_peak else 0.9

            frequency_demand = base_demand * weekend_factor * peak_factor + np.random.normal(0, 8)
            frequency_demand = max(50, min(150, frequency_demand))

            # 更保守的调频里程价格模拟
            base_price = 20 + 12 * np.sin(2 * np.pi * hour / 24)
            price_volatility = 4 * is_peak - 2 * is_weekend

            frequency_price = base_price + price_volatility + np.random.normal(0, 2)
            frequency_price = max(15, min(40, frequency_price))  # 更保守的价格范围
            frequency_price = round(frequency_price, 1)

            data.append({
                'datetime': current_date.replace(hour=hour, minute=0, second=0).strftime('%Y-%m-%d %H:%M:%S'),
                'date': current_date.strftime('%Y-%m-%d'),
                'hour': hour,
                'frequency_demand': round(frequency_demand, 1),
                'frequency_price': frequency_price
            })

    return pd.DataFrame(data)


def validate_price_data_format(file):
    """验证电价预测数据文件格式"""
    try:
        if file.name.endswith('.csv'):
            df = pd.read_csv(file)
        else:
            df = pd.read_excel(file)

        # 检查必要列
        if 'price' not in df.columns:
            st.error("❌ 电价数据缺少'price'列")
            return None

        # 检查数据量
        if len(df) != 96:
            st.error(f"❌ 电价数据应包含96个时段，当前只有{len(df)}个")
            return None

        # 检查数据类型
        try:
            df['price'] = df['price'].astype(float)
        except Exception as e:
            st.error(f"❌ 电价数据格式错误: {e}")
            return None

        # 基本数据合理性检查（不涉及收益导向）
        if df['price'].min() < 0:
            st.error("❌ 电价数据包含负值，请检查数据")
            return None

        if df['price'].max() > 2000:
            st.warning("⚠️ 电价数据包含超高值（>2000元/MWh），请确认数据准确性")

        return df

    except Exception as e:
        st.error(f"❌ 读取电价文件失败: {e}")
        return None


def validate_frequency_data_format(file):
    """验证调频历史数据文件格式"""
    try:
        if file.name.endswith('.csv'):
            df = pd.read_csv(file)
        else:
            df = pd.read_excel(file)

        # 检查必要列
        required_columns = ['datetime', 'date', 'hour', 'frequency_demand', 'frequency_price']
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            st.error(f"❌ 调频数据缺少必要列: {missing_columns}")
            return None

        # 检查数据量
        if len(df) < 24:
            st.error(f"❌ 调频数据量不足，至少需要24小时数据，当前只有{len(df)}条")
            return None

        # 检查数据类型
        try:
            df['datetime'] = pd.to_datetime(df['datetime'])
            df['hour'] = df['hour'].astype(int)
            df['frequency_demand'] = df['frequency_demand'].astype(float)
            df['frequency_price'] = df['frequency_price'].astype(float)
        except Exception as e:
            st.error(f"❌ 调频数据格式错误: {e}")
            return None

        # 基本数据合理性检查
        if not df['hour'].between(0, 23).all():
            st.error("❌ 小时值必须在0-23范围内")
            return None

        if df['frequency_demand'].min() < 0:
            st.error("❌ 调频需求不能为负值")
            return None

        if df['frequency_price'].min() < 0:
            st.error("❌ 调频价格不能为负值")
            return None

        st.success(f"✅ 调频数据格式验证通过，共{len(df)}条记录")
        return df

    except Exception as e:
        st.error(f"❌ 读取调频文件失败: {e}")
        return None


def display_da_market_results(optimal_model, price_forecast, battery_params, final_display_mode):
    """第一部分：日前市场结果展示"""
    st.header("🏪 第一部分：日前市场优化结果")

    # 模式显示
    mode_text = '报量不报价' if final_display_mode == 0 else '报量报价'
    st.success(f"📊 日前市场最优模式：**{mode_text}**")

    # 申报策略
    if final_display_mode == 1:  # 报量报价
        st.subheader("📋 日前市场分段报价表")
        segmented_bid_table = generate_segmented_bid_table(optimal_model, price_forecast, battery_params)
        st.dataframe(segmented_bid_table, use_container_width=True)
    else:  # 报量不报价
        st.subheader("📋 日前市场功率申报表")
        simple_bid_table = generate_bid_table(optimal_model, price_forecast, battery_params)
        st.dataframe(simple_bid_table, use_container_width=True)

    # 日前市场KPIs
    da_kpis = calculate_kpis(optimal_model, price_forecast, battery_params)
    st.subheader("📈 日前市场关键性能指标")
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("💰 总净利润", f"{da_kpis['总净利润']:.2f} 元")
    col2.metric("💡 总放电收益", f"{da_kpis['总放电收益']:.2f} 元")
    col3.metric("🔄 等效循环次数", f"{da_kpis['等效循环次数']:.3f} 次")
    col4.metric("⚡ 总能量吞吐", f"{da_kpis['总能量吞吐']:.2f} MWh")
    col5.metric("💡 平均度电利润", f"{da_kpis['平均度电利润']:.2f} 元/MWh")

    # 日前市场可视化
    st.subheader("📊 日前市场优化结果可视化")
    da_fig = generate_comprehensive_visualization(optimal_model, price_forecast, battery_params)
    st.plotly_chart(da_fig, use_container_width=True)

    return da_kpis


def display_frequency_market_results(coordinator, frequency_results):
    """第二部分：调频市场结果展示"""
    st.header("⚡ 第二部分：调频市场优化结果")

    # 价格预测结果
    st.subheader("🤖 调频里程价格预测")
    predictor_info = coordinator.price_predictor.get_model_performance() if coordinator.price_predictor else None
    if predictor_info:
        col1, col2, col3 = st.columns(3)
        col1.metric("模型R²得分", f"{predictor_info['r2_score']:.3f}")
        col2.metric("平均绝对误差", f"{predictor_info['mae']:.2f}")
        col3.metric("预测价格范围",
                    f"{predictor_info['price_range'][0]:.1f}-{predictor_info['price_range'][1]:.1f} 元/MW")

    # 显示预测价格曲线
    if 'mileage_price_forecast' in frequency_results:
        price_data = pd.DataFrame({
            '小时': [f"{h:02d}:00" for h in range(24)],
            '预测价格(元/MW)': frequency_results['mileage_price_forecast']
        })
        st.line_chart(price_data.set_index('小时'))

    # 调频市场求解状态
    solver_status = frequency_results.get('solver_status', 'unknown')
    if solver_status == 'optimal':
        st.success(f"✅ 调频市场求解成功")
    elif solver_status == 'heuristic':
        st.info(f"ℹ️ 调频市场使用启发式解决方案")
    else:
        st.warning(f"⚠️ 调频市场求解状态: {solver_status}")

    # 调频容量申报策略
    st.subheader("📋 调频容量申报策略")
    freq_capacity = frequency_results.get('frequency_capacity', [0] * 24)
    freq_prices = frequency_results.get('mileage_price_forecast', [25] * 24)

    # 生成调频申报表
    freq_strategy_data = []
    for t in range(24):
        hour_str = f"{t:02d}:00-{(t + 1) % 24:02d}:00"

        # 确保所有数据都存在
        capacity = freq_capacity[t] if t < len(freq_capacity) else 0
        price = freq_prices[t] if t < len(freq_prices) else 25
        cap_rev = frequency_results['capacity_revenues'][t] if t < len(frequency_results['capacity_revenues']) else 0
        mil_rev = frequency_results['mileage_revenues'][t] if t < len(frequency_results['mileage_revenues']) else 0
        deg_cost = frequency_results['degradation_costs'][t] if t < len(frequency_results['degradation_costs']) else 0
        eff_cost = frequency_results['efficiency_costs'][t] if t < len(frequency_results['efficiency_costs']) else 0
        om_cost = frequency_results['om_costs'][t] if t < len(frequency_results['om_costs']) else 0

        total_cost = deg_cost + eff_cost + om_cost
        net_profit = cap_rev + mil_rev - total_cost

        freq_strategy_data.append({
            '时间段': hour_str,
            '调频容量申报(MW)': f"{capacity:.2f}",
            '调频里程价格(元/MW)': f"{price:.1f}",
            '容量补偿收益(元)': f"{cap_rev:.2f}",
            '里程补偿收益(元)': f"{mil_rev:.2f}",
            '运行成本(元)': f"{total_cost:.2f}",
            '净收益(元)': f"{net_profit:.2f}"
        })

    freq_strategy_df = pd.DataFrame(freq_strategy_data)
    st.dataframe(freq_strategy_df, use_container_width=True)

    # 调频市场KPIs
    st.subheader("📈 调频市场关键性能指标")
    freq_cols = st.columns(5)
    freq_net_profit = frequency_results.get('net_profit', 0)
    freq_total_revenue = frequency_results.get('total_revenue', 0)
    freq_total_capacity = sum(frequency_results.get('frequency_capacity', [0] * 24))
    freq_total_cost = frequency_results.get('total_cost', 0)

    freq_cols[0].metric("🎯 调频净利润", f"{freq_net_profit:.2f} 元")
    freq_cols[1].metric("📈 调频总收益", f"{freq_total_revenue:.2f} 元")
    freq_cols[2].metric("⚙️ 调频总容量", f"{freq_total_capacity:.2f} MW")
    freq_cols[3].metric("💸 调频总成本", f"{freq_total_cost:.2f} 元")

    # 计算利润率
    profit_rate = (freq_net_profit / freq_total_revenue * 100) if freq_total_revenue > 0 else 0
    freq_cols[4].metric("📊 调频利润率", f"{profit_rate:.1f} %")

    # 调频市场专项分析
    st.subheader("📊 调频市场专项分析")
    freq_fig = generate_frequency_market_analysis(frequency_results)
    if freq_fig:
        st.plotly_chart(freq_fig, use_container_width=True)

    # 成本分解
    st.subheader("💰 调频成本分解")
    cost_fig = generate_cost_breakdown_chart(frequency_results)
    if cost_fig:
        st.plotly_chart(cost_fig, use_container_width=True)


def display_joint_market_results(coordinator, da_kpis, frequency_results, optimal_model, price_forecast,
                                 battery_params):
    """第三部分：多市场联合优化分析"""
    st.header("🏆 第三部分：多市场联合优化分析")

    # 联合申报策略
    st.subheader("📊 多市场联合申报策略")
    joint_strategy = coordinator.generate_joint_bidding_strategy()
    st.dataframe(joint_strategy, use_container_width=True)

    # 多市场KPIs对比
    multi_kpis = coordinator.calculate_multi_market_kpis()
    kpi_display = create_kpi_metrics_display(multi_kpis)

    st.subheader("📈 多市场KPIs对比分析")

    # 联合市场总体KPIs
    st.subheader("🏆 联合市场总体指标")
    joint_cols = st.columns(4)
    for i, (key, value) in enumerate(kpi_display['joint_market'].items()):
        if i < 4:  # 只显示前4个指标
            joint_cols[i].metric(key, value)

    # 市场收益对比
    st.subheader("📊 市场收益对比分析")
    comparison_fig = generate_market_comparison_chart(
        multi_kpis['da_market'], multi_kpis['frequency_market']
    )
    if comparison_fig:
        st.plotly_chart(comparison_fig, use_container_width=True)

    # 多市场联合可视化
    st.subheader("📊 多市场联合优化综合分析")
    main_fig = generate_multi_market_visualization(
        optimal_model, frequency_results, price_forecast, battery_params
    )
    st.plotly_chart(main_fig, use_container_width=True)

    # 收益增量分析
    st.subheader("💹 收益增量分析")
    da_profit = da_kpis['总净利润']
    freq_profit = frequency_results.get('net_profit', 0)
    total_profit = da_profit + freq_profit

    col1, col2, col3 = st.columns(3)
    col1.metric("日前市场收益", f"{da_profit:.2f} 元",
                f"{da_profit / total_profit * 100:.1f}%" if total_profit > 0 else "0%")
    col2.metric("调频市场收益", f"{freq_profit:.2f} 元",
                f"{freq_profit / total_profit * 100:.1f}%" if total_profit > 0 else "0%")

    # 计算增量百分比
    if da_profit > 0:
        increment_pct = freq_profit / da_profit * 100
        increment_text = f"+{increment_pct:.1f}%"
    else:
        increment_text = "N/A"

    col3.metric("总收益", f"{total_profit:.2f} 元", increment_text)

    # 储能电站收益评估
    st.subheader("🎯 储能电站收益评估")

    annual_profit = total_profit * 365
    capacity_mwh = battery_params['E_rated']

    eval_col1, eval_col2, eval_col3, eval_col4 = st.columns(4)
    eval_col1.metric("年净利润", f"{annual_profit / 1e4:.0f} 万元")
    eval_col2.metric("单位容量年收益", f"{annual_profit / capacity_mwh / 1e4:.1f} 万元/MWh")
    eval_col3.metric("日均收益", f"{total_profit:.0f} 元/日")
    eval_col4.metric("度电收益", f"{total_profit / (capacity_mwh * da_kpis['等效循环次数']):.2f} 元/kWh")


def main():
    st.set_page_config(page_title="液流电池储能电站多市场联合优化", layout="wide")

    # --- 数据库集成：在应用启动时初始化数据库 ---
    init_db()

    st.title("🔋 液流电池储能电站多市场联合优化决策系统")
    st.caption("基于数学优化的储能电站市场参与决策支持平台")

    # 添加市场选择
    st.sidebar.header("🏪 市场参与选择")
    market_mode = st.sidebar.selectbox(
        "选择市场参与模式",
        ["仅日前市场", "多市场联合优化"],
        index=1,
        help="建议选择多市场联合优化以获得更好收益"
    )

    # --- 数据库集成：从数据库加载参数 ---
    # 此函数会用数据库中的 E_rated 和 P_rated 覆盖默认值
    battery_params = load_parameters_from_db_and_defaults()
    station_profile = load_station_profile()  # 再次加载以获取电站名称等信息用于保存

    # 创建选项卡
    if market_mode == "仅日前市场":
        tab1, tab2, tab3, tab4 = st.tabs(["🔧 系统配置", "🔋 电池参数", "📈 日前市场参数", "📁 数据上传"])
    else:
        tab1, tab2, tab3, tab4, tab5 = st.tabs(
            ["🔧 系统配置", "🔋 电池参数", "📈 日前市场参数", "⚡ 调频市场参数", "📁 数据上传"])

    with tab1:
        st.header("🔧 系统总体配置")

        col1, col2 = st.columns(2)
        with col1:
            solver_type = st.selectbox("求解器选择", ["CBC", "IPOPT"], help="建议使用CBC求解器")

        with col2:
            time_horizon = st.number_input("优化时间范围(小时)", min_value=1, max_value=48, value=24)
            time_step = st.number_input("时间步长(分钟)", min_value=1, max_value=60, value=15)

    with tab2:
        st.header("🔋 电池技术参数")

        col1, col2 = st.columns(2)
        with col1:
            st.subheader("💡 额定参数")
            # --- 数据库集成：UI输入框的值默认为从数据库加载的 battery_params ---
            battery_params['E_rated'] = st.number_input('额定容量 (MWh)', 10, 200, int(battery_params['E_rated']),
                                                        help="该值默认从电站档案加载，可在此处临时修改。")
            battery_params['P_rated'] = st.number_input('额定功率 (MW)', 5, 100, int(battery_params['P_rated']),
                                                        help="该值默认从电站档案加载，可在此处临时修改。")

            st.subheader("⚡ 能量参数")
            battery_params['initial_soc'] = st.slider('初始荷电状态', 0.2, 0.8, battery_params['initial_soc'])
            # 动态更新初始能量和目标能量
            battery_params['E_0'] = battery_params['E_rated'] * battery_params['initial_soc']
            battery_params['E_T_target'] = battery_params['E_rated'] * battery_params['initial_soc']
            st.write(
                f"根据当前设置，初始能量为 **{battery_params['E_0']:.2f} MWh**，目标结束能量为 **{battery_params['E_T_target']:.2f} MWh**。")

            st.subheader("🔄 效率参数")
            battery_params['η_charge'] = st.slider('充电效率', 0.70, 0.95, battery_params['η_charge'], step=0.01)
            battery_params['η_discharge'] = st.slider('放电效率', 0.70, 0.95, battery_params['η_discharge'], step=0.01)

        with col2:
            st.subheader("📊 SOC参数")
            battery_params['SOC_min'] = st.slider('最小荷电状态', 0.05, 0.20, battery_params['SOC_min'], step=0.01)
            battery_params['SOC_max'] = st.slider('最大荷电状态', 0.80, 0.95, battery_params['SOC_max'], step=0.01)

            st.subheader("🌊 电解液流量参数")
            battery_params['Q_flow_min'] = st.number_input('最小电解液流量 (L/min)', 10, 100,
                                                           int(battery_params['Q_flow_min']), step=5)
            battery_params['Q_flow_max'] = st.number_input('最大电解液流量 (L/min)', 100, 500,
                                                           int(battery_params['Q_flow_max']), step=25)

            flow_power_ratio = st.number_input("流量功率比 (L/min/MW)", 3.0, 10.0,
                                               battery_params['flow_power_ratio'], step=0.5)
            battery_params['flow_power_ratio'] = flow_power_ratio

    with tab3:
        da_market_config = display_da_market_params_config()
        # 将日前市场参数更新到battery_params中
        battery_params.update({
            'N_cycle_max': da_market_config['N_cycle_max'],
            'k': da_market_config['k'],
            'C_OM': da_market_config['C_OM'],
            'R_ramp': da_market_config['R_ramp']
        })

    # 调频市场参数配置
    frequency_config = None
    if market_mode == "多市场联合优化":
        with tab4:
            frequency_config = display_frequency_params_config()

    # 数据上传选项卡
    data_tab_index = 4 if market_mode == "仅日前市场" else 5
    with (tab4 if market_mode == "仅日前市场" else tab5):
        price_data, frequency_data = display_data_upload()

    # 展示所有参数
    display_battery_params(battery_params)

    # 参数验证
    if market_mode == "多市场联合优化" and frequency_config:
        warnings, errors = validate_parameters(battery_params, da_market_config, frequency_config)

        if warnings:
            st.sidebar.header("⚠️ 参数建议")
            for warning in warnings:
                st.sidebar.warning(warning)

        if errors:
            st.sidebar.header("❌ 参数错误")
            for error in errors:
                st.sidebar.error(error)

    # 侧边栏开发者选项
    st.sidebar.header("⚙️ 开发与调试选项")
    force_qp_mode = st.sidebar.toggle(
        "强制显示'报量报价'模式",
        value=False,
        help="开启此项后，无论RARR决策结果如何，都将为您展示'报量报价'下的分段报价表。"
    )

    # 求解按钮
    if st.button("🚀 开始优化求解", type="primary"):
        if price_data is not None:
            try:
                # 提取电价数据
                price_forecast = price_data['price'].values

                # 验证电池参数
                battery_params = validate_battery_params(battery_params)

                # === 日前市场优化 ===
                st.write("🔄 正在进行日前市场优化...")
                with st.spinner('正在求解日前市场最优策略...'):
                    market_model = FlowBatteryDayAheadMarketModel(price_forecast, battery_params)
                    optimal_model, solve_results = market_model.solve_model()

                # 模式选择
                optimal_mode = mode_selection_rarr(optimal_model, price_forecast, battery_params)

                # 检查开发者开关
                if force_qp_mode:
                    final_display_mode = 1
                    st.warning("⚠️ **强制预览模式已开启**")
                else:
                    final_display_mode = optimal_mode

                mode_text = '报量不报价' if final_display_mode == 0 else '报量报价'

                # 初始化用于保存到数据库的变量
                da_kpis = {}
                frequency_results = {}
                total_profit = 0
                da_profit = 0
                fm_profit = 0

                if market_mode == "多市场联合优化":
                    # === 多市场联合优化模式 ===

                    # 第一部分：日前市场结果
                    da_kpis = display_da_market_results(optimal_model, price_forecast, battery_params,
                                                        final_display_mode)

                    st.divider()

                    # 调频市场优化
                    st.write("🔄 正在进行调频市场优化...")

                    coordinator = MultiMarketCoordinator(battery_params)
                    coordinator.set_da_results(optimal_model, solve_results, price_forecast)
                    if frequency_data is not None:
                        st.info("🔄 使用用户上传的调频数据训练价格预测模型...")

                    with st.spinner('正在训练调频价格预测模型...'):
                        predictor_info = coordinator.initialize_price_predictor(
                            price_upper_limit=frequency_config['price_upper_limit']
                        )

                    # --- 已修复 ---
                    frequency_params = create_frequency_market_params(
                        lmp_da_forecast=[price_forecast[i * 4] for i in range(24)],
                        user_params={
                            'verified_cost': frequency_config['verified_cost'],
                            'measured_regulation_rate': frequency_config['measured_regulation_rate'],
                            'control_area_demand': frequency_config['control_area_demand'],
                            'num_units': frequency_config['num_units'],
                            'performance_index': frequency_config['performance_index']
                        }
                    )

                    cost_params = create_cost_params(
                        battery_params,
                        user_params={
                            'verified_cost': frequency_config['verified_cost'],
                            'alpha_freq': frequency_config['alpha_freq'],
                            'degradation_rate': frequency_config['degradation_rate'],
                            'efficiency_loss_rate': frequency_config['efficiency_loss_rate'],
                            'om_cost_rate': frequency_config['om_cost_rate']
                        }
                    )

                    validate_frequency_params(frequency_params, cost_params)

                    with st.spinner('正在求解调频市场最优策略...'):
                        # --- 已修复 ---
                        frequency_results = coordinator.optimize_frequency_market(
                            frequency_params, cost_params, frequency_config['price_upper_limit']
                        )

                    display_frequency_market_results(coordinator, frequency_results)
                    st.divider()
                    display_joint_market_results(coordinator, da_kpis, frequency_results, optimal_model, price_forecast,
                                                 battery_params)

                    # 计算总利润用于保存
                    da_profit = da_kpis.get('总净利润', 0)
                    fm_profit = frequency_results.get('net_profit', 0)
                    total_profit = da_profit + fm_profit

                else:
                    # === 仅日前市场模式 ===
                    da_kpis = display_da_market_results(optimal_model, price_forecast, battery_params,
                                                        final_display_mode)
                    total_profit = da_kpis.get('总净利润', 0)
                    da_profit = total_profit
                    fm_profit = 0

                # --- 数据库集成：准备数据并保存决策记录 ---
                st.info("💾 正在保存本次决策结果到历史档案...")
                try:
                    decision_data = {
                        'run_timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        'station_name': station_profile.get('station_name',
                                                            '默认电站') if station_profile else '默认电站',
                        'market_mode': market_mode,
                        'decision_mode': mode_text,
                        'net_profit': total_profit,
                        'da_profit': da_profit,
                        'fm_profit': fm_profit,
                        'total_throughput': da_kpis.get('总能量吞吐', 0),
                        'equivalent_cycles': da_kpis.get('等效循环次数', 0)
                    }
                    save_decision_record(decision_data)
                    st.success("✅ 优化决策已成功记录到数据库！")
                except Exception as db_e:
                    st.error(f"❌ 保存决策到数据库时发生错误: {db_e}")
                    st.exception(db_e)

            except Exception as e:
                st.error(f"❌ 优化求解过程中出错: {e}")
                st.exception(e)
        else:
            st.warning("⚠️ 请先在数据上传选项卡中上传电价预测文件。")


if __name__ == "__main__":
    main()

