import streamlit as st
import pandas as pd
import sys
import os
import numpy as np

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


def display_battery_params(battery_params):
    """展示所有技术参数"""
    st.sidebar.header("电池技术参数详情")
    param_groups = {
        "额定参数": ['E_rated', 'P_rated'],
        "能量参数": ['E_0', 'E_T_target', 'initial_soc'],
        "效率参数": ['η_charge', 'η_discharge'],
        "SOC参数": ['SOC_min', 'SOC_max'],
        "循环与退化": ['N_cycle_max', 'k'],
        "运维成本": ['C_OM'],
        "功率爬坡": ['R_ramp'],
        "电解液流量": ['Q_flow_min', 'Q_flow_max']
    }

    for group, params in param_groups.items():
        with st.sidebar.expander(group):
            for param in params:
                st.write(f"{param}: {battery_params[param]}")


def display_da_market_params_config():
    """日前市场参数配置界面 - 简化版本"""
    st.header("日前市场参数配置")

    st.info("💡 这些参数直接用于日前市场数学优化模型，影响储能电站的充放电决策")

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("🔄 循环寿命参数")

        N_cycle_max = st.number_input(
            "最大等效循环次数",
            min_value=1, max_value=10, value=3, step=1,
            help="约束条件：Σ(|P_charge| + |P_discharge|) ≤ N_cycle_max × E_rated"
        )

        k = st.number_input(
            "度电退化成本系数",
            min_value=0.0, max_value=1.0, value=0.1, step=0.01,
            help="目标函数成本项：k × Σ(|P_charge| + |P_discharge|) × Δt"
        )

        st.subheader("💰 经济性参数")

        C_OM = st.number_input(
            "固定运维成本 (元/日)",
            min_value=0, max_value=10000, value=1000, step=100,
            help="目标函数固定成本项"
        )

        # 价格阈值参数（用于约束条件）
        min_discharge_price = st.number_input(
            "最低放电价格 (元/MWh)",
            min_value=0.0, max_value=500.0, value=200.0, step=10.0,
            help="约束：P_discharge[t] = 0 if price[t] < min_discharge_price"
        )

        max_charge_price = st.number_input(
            "最高充电价格 (元/MWh)",
            min_value=200.0, max_value=800.0, value=400.0, step=10.0,
            help="约束：P_charge[t] = 0 if price[t] > max_charge_price"
        )

    with col2:
        st.subheader("⚡ 功率约束参数")

        R_ramp = st.number_input(
            "功率爬坡速率 (MW/15min)",
            min_value=0.1, max_value=20.0, value=5.0, step=0.5,
            help="约束：|P[t] - P[t-1]| ≤ R_ramp"
        )

        power_reserve_ratio = st.slider(
            "功率预留比例",
            min_value=0.0, max_value=0.2, value=0.05, step=0.01,
            help="约束：P_max = P_rated × (1 - power_reserve_ratio)"
        )

        st.subheader("🎯 风险管理参数")

        soc_target_weight = st.number_input(
            "SOC目标权重",
            min_value=0.0, max_value=1000.0, value=100.0, step=10.0,
            help="目标函数：soc_target_weight × |SOC_end - SOC_target|²"
        )

        risk_penalty = st.number_input(
            "风险惩罚系数",
            min_value=0.0, max_value=100.0, value=10.0, step=1.0,
            help="目标函数惩罚项系数"
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
    """调频市场参数配置界面 - 基于实际代码使用的参数"""
    st.header("调频市场参数配置")

    st.info("💡 这些参数基于广东调频辅助服务市场实施细则，直接用于调频市场数学模型")

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("📋 市场规则参数")

        verified_cost = st.number_input(
            "核定成本 (元/MWh)",
            min_value=100.0, max_value=500.0, value=200.0, step=10.0,
            help="容量补偿收益 = C_freq × max(0, LMP_DA - verified_cost)"
        )

        measured_regulation_rate = st.number_input(
            "实测调节速率 (MW/min)",
            min_value=0.5, max_value=5.0, value=2.0, step=0.1,
            help="容量上限约束：C_max ≤ measured_regulation_rate × 2"
        )

        control_area_demand = st.number_input(
            "控制区调频需求 (MW)",
            min_value=100, max_value=1000, value=600, step=50,
            help="容量上限约束：C_max ≤ control_area_demand × 0.1 / num_units"
        )

        num_units = st.number_input(
            "参与机组数量",
            min_value=1, max_value=20, value=8, step=1,
            help="用于计算单机容量分配上限"
        )

        performance_index = st.slider(
            "综合调频性能指标",
            min_value=0.5, max_value=1.0, value=0.85, step=0.05,
            help="里程补偿收益 = mileage_distance × mileage_price × performance_index × C_freq"
        )

    with col2:
        st.subheader("💸 成本模型参数")

        alpha_freq = st.slider(
            "调频活动系数",
            min_value=0.05, max_value=0.3, value=0.12, step=0.01,
            help="SOC约束：SOC ± (C_freq × alpha_freq / E_rated)，退化成本系数"
        )

        degradation_rate = st.number_input(
            "退化成本率 (元/MW/h)",
            min_value=0.1, max_value=2.0, value=0.3, step=0.1,
            help="退化成本 = C_freq × alpha_freq × degradation_rate"
        )

        efficiency_loss_rate = st.slider(
            "效率损失率",
            min_value=0.01, max_value=0.1, value=0.015, step=0.005,
            help="效率成本 = C_freq × alpha_freq × efficiency_loss_rate × LMP_DA"
        )

        om_cost_rate = st.number_input(
            "运维成本率 (元/MW/h)",
            min_value=0.1, max_value=2.0, value=0.2, step=0.1,
            help="运维成本 = C_freq × om_cost_rate"
        )

        price_upper_limit = st.number_input(
            "里程报价上限 (元/MW)",
            min_value=20.0, max_value=100.0, value=50.0, step=5.0,
            help="价格预测约束：mileage_price ≤ price_upper_limit"
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
    """数据上传专用界面 - 合并调频数据上传"""
    st.header("📁 数据上传中心")

    st.info("💡 请按需上传相关数据文件，系统将根据上传的数据进行优化计算")

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
            template_data = generate_price_template()
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
            template_data = generate_frequency_template()
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


def generate_price_template():
    """生成电价预测数据模板"""
    # 生成96个15分钟时段的示例电价数据
    time_periods = 96
    base_price = 300

    data = []
    for t in range(time_periods):
        hour = t // 4
        minute = (t % 4) * 15

        # 模拟日内电价波动
        daily_pattern = 100 * np.sin(2 * np.pi * hour / 24)
        random_noise = np.random.normal(0, 20)

        price = base_price + daily_pattern + random_noise
        price = max(50, min(800, price))  # 限制价格范围

        data.append({
            'time_period': t + 1,
            'hour': hour,
            'minute': minute,
            'time_label': f"{hour:02d}:{minute:02d}",
            'price': round(price, 2)
        })

    return pd.DataFrame(data)


def generate_frequency_template():
    """生成调频历史数据模板 - 合并需求和价格"""
    from datetime import datetime, timedelta

    # 生成30天的示例数据
    data = []
    start_date = datetime.now() - timedelta(days=30)

    for day in range(30):
        current_date = start_date + timedelta(days=day)
        for hour in range(24):
            # 调频需求模拟
            base_demand = 100 + 50 * np.sin(2 * np.pi * hour / 24)
            is_weekend = 1 if current_date.weekday() >= 5 else 0
            is_peak = 1 if 8 <= hour <= 22 else 0

            weekend_factor = 0.8 if is_weekend else 1.0
            peak_factor = 1.3 if is_peak else 0.9

            frequency_demand = base_demand * weekend_factor * peak_factor + np.random.normal(0, 10)
            frequency_demand = max(50, frequency_demand)

            # 调频里程价格模拟
            base_price = 20 + 15 * np.sin(2 * np.pi * hour / 24)
            price_volatility = 5 * is_peak - 3 * is_weekend

            frequency_price = base_price + price_volatility + np.random.normal(0, 2)
            frequency_price = max(5, min(50, frequency_price))  # 限制在5-50范围内
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

        # 检查价格合理性
        if df['price'].min() < 0 or df['price'].max() > 2000:
            st.warning("⚠️ 电价数据可能超出合理范围（0-2000元/MWh）")

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

        # 检查数值合理性
        if not df['hour'].between(0, 23).all():
            st.error("❌ 小时值必须在0-23范围内")
            return None

        if not df['frequency_demand'].between(0, 1000).all():
            st.warning("⚠️ 调频需求值可能超出合理范围（0-1000MW）")

        if not df['frequency_price'].between(0, 100).all():
            st.warning("⚠️ 调频价格值可能超出合理范围（0-100元/MW）")

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
    freq_cols[0].metric("🎯 调频净利润", f"{frequency_results.get('net_profit', 0):.2f} 元")
    freq_cols[1].metric("📈 调频总收益", f"{frequency_results.get('total_revenue', 0):.2f} 元")
    freq_cols[2].metric("⚙️ 调频总容量", f"{sum(frequency_results.get('frequency_capacity', [0] * 24)):.2f} MW")
    freq_cols[3].metric("💸 调频总成本", f"{frequency_results.get('total_cost', 0):.2f} 元")

    # 计算利润率
    total_revenue = frequency_results.get('total_revenue', 0)
    net_profit = frequency_results.get('net_profit', 0)
    profit_rate = (net_profit / total_revenue * 100) if total_revenue > 0 else 0
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

    # 详细分析
    if total_profit < 0:
        st.error("⚠️ 联合净利润为负值，请检查以下可能原因：")
        st.write("1. 日前市场电价过低，无法覆盖储能运行成本")
        st.write("2. 调频市场参数设置过于保守")
        st.write("3. 电池退化成本或运维成本设置过高")
        st.write("4. 建议调整核定成本、调频活动系数等参数")


def main():
    st.set_page_config(page_title="液流电池储能电站多市场联合优化", layout="wide")

    st.title("液流电池储能电站多市场联合优化决策系统")

    # 添加市场选择
    st.sidebar.header("🏪 市场参与选择")
    market_mode = st.sidebar.selectbox(
        "选择市场参与模式",
        ["仅日前市场", "多市场联合优化"],
        index=1
    )

    # 创建选项卡 - 重新设计
    if market_mode == "仅日前市场":
        tab1, tab2, tab3, tab4 = st.tabs(["系统配置", "电池参数", "日前市场参数", "数据上传"])
    else:
        tab1, tab2, tab3, tab4, tab5 = st.tabs(["系统配置", "电池参数", "日前市场参数", "调频市场参数", "数据上传"])

    # 获取默认电池参数
    battery_params = get_default_battery_params()

    with tab1:
        st.header("系统总体配置")
        col1, col2 = st.columns(2)
        with col1:
            solver_type = st.selectbox("求解器选择", ["CBC", "IPOPT"])

        with col2:
            time_horizon = st.number_input("优化时间范围(小时)", min_value=1, max_value=48, value=24)
            time_step = st.number_input("时间步长(分钟)", min_value=1, max_value=60, value=15)

    with tab2:
        st.header("电池技术参数")
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("额定参数")
            battery_params['E_rated'] = st.number_input('额定容量 (MWh)', 10, 200, int(battery_params['E_rated']))
            battery_params['P_rated'] = st.number_input('额定功率 (MW)', 1, 50, int(battery_params['P_rated']))

            st.subheader("能量参数")
            battery_params['initial_soc'] = st.slider('初始荷电状态', 0.2, 0.8, battery_params['initial_soc'])
            battery_params['E_0'] = st.number_input('初始能量 (MWh)', 1, 100, int(battery_params['E_0']))
            battery_params['E_T_target'] = st.number_input('目标结束能量 (MWh)', 1, 100,
                                                           int(battery_params['E_T_target']))

            st.subheader("效率参数")
            battery_params['η_charge'] = st.slider('充电效率', 0.7, 1.0, battery_params['η_charge'])
            battery_params['η_discharge'] = st.slider('放电效率', 0.7, 1.0, battery_params['η_discharge'])

        with col2:
            st.subheader("SOC参数")
            battery_params['SOC_min'] = st.slider('最小荷电状态', 0.1, 0.3, battery_params['SOC_min'])
            battery_params['SOC_max'] = st.slider('最大荷电状态', 0.7, 0.9, battery_params['SOC_max'])

            st.subheader("🔋 电解液流量参数")
            battery_params['Q_flow_min'] = st.number_input(
                '最小电解液流量 (L/min)',
                min_value=0, max_value=100, value=int(battery_params['Q_flow_min']), step=5,
                help="约束：Q_flow ≥ Q_flow_min when P > 0"
            )
            battery_params['Q_flow_max'] = st.number_input(
                '最大电解液流量 (L/min)',
                min_value=50, max_value=500, value=int(battery_params['Q_flow_max']), step=10,
                help="约束：Q_flow ≤ Q_flow_max"
            )

            flow_power_ratio = st.number_input(
                "流量功率比 (L/min/MW)",
                min_value=1.0, max_value=20.0, value=5.0, step=0.5,
                help="约束：Q_flow = flow_power_ratio × |P|"
            )
            # 将流量功率比添加到电池参数中
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

    # 侧边栏开发者选项
    st.sidebar.header("⚙️ 开发与调试选项")
    force_qp_mode = st.sidebar.toggle(
        "强制显示'报量报价'模式",
        value=False,
        help="开启此项后，无论RARR决策结果如何，都将为您展示'报量报价'的分段报价表。"
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

                if market_mode == "多市场联合优化":
                    # === 多市场联合优化模式 ===

                    # 第一部分：日前市场结果
                    da_kpis = display_da_market_results(optimal_model, price_forecast, battery_params,
                                                        final_display_mode)

                    st.divider()

                    # 调频市场优化
                    st.write("🔄 正在进行调频市场优化...")

                    # 创建多市场协调器 - 传递价格预测数据
                    coordinator = MultiMarketCoordinator(battery_params)
                    coordinator.set_da_results(optimal_model, solve_results, price_forecast)  # 传递价格数据

                    # 如果用户上传了调频数据，使用用户数据训练价格预测模型
                    if frequency_data is not None:
                        st.info("🔄 使用用户上传的调频数据训练价格预测模型...")
                        # 这里可以扩展使用用户数据的逻辑

                    # 初始化价格预测器
                    with st.spinner('正在训练调频价格预测模型...'):
                        predictor_info = coordinator.initialize_price_predictor(
                            price_upper_limit=frequency_config['price_upper_limit']
                        )

                    # 创建调频市场参数 - 修复参数传递问题
                    frequency_params = create_frequency_market_params(
                        lmp_da_forecast=[price_forecast[i * 4] for i in range(24)],  # 转换为小时数据
                        user_params={
                            'verified_cost': frequency_config['verified_cost'],
                            'measured_regulation_rate': frequency_config['measured_regulation_rate'],
                            'control_area_demand': frequency_config['control_area_demand'],
                            'num_units': frequency_config['num_units'],
                            'performance_index': frequency_config['performance_index']  # 单个浮点数，会被转换为24小时列表
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

                    # 验证参数
                    validate_frequency_params(frequency_params, cost_params)

                    # 优化调频市场
                    with st.spinner('正在求解调频市场最优策略...'):
                        frequency_results = coordinator.optimize_frequency_market(
                            frequency_params, cost_params, frequency_config['price_upper_limit']
                        )

                    # 第二部分：调频市场结果
                    display_frequency_market_results(coordinator, frequency_results)

                    st.divider()

                    # 第三部分：多市场联合分析
                    display_joint_market_results(coordinator, da_kpis, frequency_results, optimal_model, price_forecast,
                                                 battery_params)

                    # 保存结果
                    mode_text = '报量不报价' if final_display_mode == 0 else '报量报价'
                    save_price_forecast(price_forecast, mode=mode_text)

                else:
                    # === 仅日前市场模式 ===
                    da_kpis = display_da_market_results(optimal_model, price_forecast, battery_params,
                                                        final_display_mode)

                    # 保存结果
                    mode_text = '报量不报价' if final_display_mode == 0 else '报量报价'
                    save_price_forecast(price_forecast, mode=mode_text)

            except Exception as e:
                st.error(f"❌ 优化求解过程中出错: {e}")
                st.exception(e)
        else:
            st.warning("⚠️ 请先在数据上传选项卡中上传电价预测文件。")


if __name__ == "__main__":
    main()