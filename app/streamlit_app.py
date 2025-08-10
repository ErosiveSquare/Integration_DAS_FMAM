import streamlit as st
import pandas as pd
import sys
import os

# 获取项目根目录
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

from models.optimization_model import FlowBatteryDayAheadMarketModel, mode_selection_rarr, generate_bid_table, generate_segmented_bid_table, calculate_kpis
from models.parameter_config import get_default_battery_params, validate_battery_params
from utils.data_processor import generate_price_forecast, save_price_forecast, load_price_forecast
from utils.visualization import generate_comprehensive_visualization


def display_battery_params(battery_params):
    """
    展示所有技术参数
    """
    st.sidebar.header("电池技术参数详情")

    # 分组展示参数
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


def main():
    st.set_page_config(page_title="液流电池储能电站日前市场优化", layout="wide")

    st.title("液流电池储能电站日前市场优化决策系统")

    # 创建选项卡
    tab1, tab2, tab3 = st.tabs(["系统配置", "电池参数", "市场参数"])

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
            # 额定参数
            battery_params['E_rated'] = st.number_input('额定容量 (MWh)', 10, 200, int(battery_params['E_rated']))
            battery_params['P_rated'] = st.number_input('额定功率 (MW)', 1, 50, int(battery_params['P_rated']))

            # 能量参数
            battery_params['initial_soc'] = st.slider('初始荷电状态', 0.2, 0.8, battery_params['initial_soc'])
            battery_params['E_0'] = st.number_input('初始能量 (MWh)', 1, 100, int(battery_params['E_0']))
            battery_params['E_T_target'] = st.number_input('目标结束能量 (MWh)', 1, 100,
                                                           int(battery_params['E_T_target']))

        with col2:
            # 效率参数
            battery_params['η_charge'] = st.slider('充电效率', 0.7, 1.0, battery_params['η_charge'])
            battery_params['η_discharge'] = st.slider('放电效率', 0.7, 1.0, battery_params['η_discharge'])

            # SOC参数
            battery_params['SOC_min'] = st.slider('最小荷电状态', 0.1, 0.3, battery_params['SOC_min'])
            battery_params['SOC_max'] = st.slider('最大荷电状态', 0.7, 0.9, battery_params['SOC_max'])

    with tab3:
        st.header("市场交易参数")
        col1, col2 = st.columns(2)
        with col1:
            # 循环与退化参数
            battery_params['N_cycle_max'] = st.number_input('最大等效循环次数', 1, 10,
                                                            int(battery_params['N_cycle_max']))
            battery_params['k'] = st.number_input('度电退化成本系数', 0.0, 0.5, battery_params['k'])

            # 功率爬坡
            battery_params['R_ramp'] = st.number_input('功率爬坡速率 (MW/15min)', min_value=float(0.1),
                                                       max_value=float(10.0), value=float(battery_params['R_ramp']))

        with col2:
            # 运维成本
            battery_params['C_OM'] = st.number_input('固定运维成本', 0, 5000, int(battery_params['C_OM']))

            # 电解液流量
            battery_params['Q_flow_min'] = st.number_input('最小电解液流量', 0, 50, int(battery_params['Q_flow_min']))
            battery_params['Q_flow_max'] = st.number_input('最大电解液流量', 50, 200, int(battery_params['Q_flow_max']))

    # 展示所有参数
    display_battery_params(battery_params)

    # 上传电价预测数据
    uploaded_file = st.file_uploader("上传电价预测数据", type=['csv', 'xlsx'])

    # 求解按钮
    solve_button = st.button("开始优化求解")

    if solve_button:
        if uploaded_file is not None:
            try:
                # 读取电价数据
                price_forecast = pd.read_csv(uploaded_file)['price'].values

                # 验证电池参数
                battery_params = validate_battery_params(battery_params)

                # --- 三阶段核心逻辑 ---
                # 1. 运行一次优化，得到基准计划
                st.write("第一阶段：正在求解最优充放电基准计划...")
                market_model = FlowBatteryDayAheadMarketModel(price_forecast, battery_params)
                optimal_model, solve_results = market_model.solve_model()
                st.success("基准计划求解完成！")

                # 2. 基于基准计划和蒙特卡洛模拟进行模式选择
                st.write("第二阶段：正在通过RARR方法进行模式决策...")
                with st.spinner('正在进行蒙特卡洛模拟以评估风险...'):
                    optimal_mode = mode_selection_rarr(optimal_model, price_forecast, battery_params)
                mode_text = '报量不报价' if optimal_mode == 0 else '报量报价'
                st.success(f"模式决策完成！最优模式为: **{mode_text}**")

                # 3. 根据决策结果生成申报策略
                st.write("第三阶段：正在生成最终申报策略...")
                if optimal_mode == 1:  # 报量报价
                    st.subheader("分段报价表")
                    segmented_bid_table = generate_segmented_bid_table(optimal_model, price_forecast, battery_params)
                    st.dataframe(segmented_bid_table)
                else:  # 报量不报价
                    st.subheader("功率申报表")
                    simple_bid_table = generate_bid_table(optimal_model, price_forecast, battery_params)  # 假设您有这个函数
                    st.dataframe(simple_bid_table)
                st.success("申报策略生成完毕！")

                # 计算并展示KPIs
                kpis = calculate_kpis(optimal_model, price_forecast, battery_params)
                # KPIs展示
                st.header("关键性能指标")
                col1, col2, col3, col4, col5 = st.columns(5)
                col1.metric("💰 总净利润", f"{kpis['总净利润']:.2f} 元")
                col2.metric("💡 总放电收益", f"{kpis['总放电收益']:.2f} 元")
                col3.metric("🔄 等效循环次数", f"{kpis['等效循环次数']:.3f} 次")
                col4.metric("⚡ 总能量吞吐", f"{kpis['总能量吞吐']:.2f} MWh")
                col5.metric("💡 平均度电利润", f"{kpis['平均度电利润']:.2f} 元/MWh")

                # 可视化
                fig = generate_comprehensive_visualization(optimal_model, price_forecast, battery_params)
                st.plotly_chart(fig, use_container_width=True)

            except Exception as e:
                st.error(f"优化求解或决策过程中出错: {e}")
        else:
            st.warning("请先上传电价预测文件。")
if __name__ == "__main__":
    main()