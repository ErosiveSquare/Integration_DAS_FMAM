import pyomo.environ as pyo
import numpy as np
import pandas as pd


class FlowBatteryDayAheadMarketModel:
    def __init__(self, price_forecast, battery_params):
        self.price_forecast = price_forecast
        self.battery_params = battery_params
        self.hours = 24
        self.steps_per_hour = 4
        self.total_steps = self.hours * self.steps_per_hour

    def diagnose_model(self, model):
        """
        诊断模型中的潜在问题
        """
        print("\n模型诊断:")
        print("决策变量:")

        # 定义要检查的变量列表
        vars_to_check = [
            model.P_discharge,
            model.P_charge,
            model.E,
            model.Q_flow_in,
            model.Q_flow_out,
            model.α,
            model.β
        ]

        for var in vars_to_check:
            print(f"{var.name}:")
            try:
                # 检查变量的基本信息
                print(f"  变量类型: {type(var)}")
                print(f"  索引数量: {len(var)}")

                # 尝试打印一些索引值
                if len(var) > 0:
                    print("  前几个索引值:")
                    for idx in list(var.keys())[:5]:  # 只打印前5个
                        try:
                            value = pyo.value(var[idx])
                            print(f"    {idx}: {value}")
                        except Exception as e:
                            print(f"    {idx}: 无法获取值 - {e}")
            except Exception as e:
                print(f"  无法获取变量信息: {e}")

        print("\n约束条件:")
        constraints_to_check = [
            model.energy_transfer,
            model.final_energy,
            model.soc_lower,
            model.soc_upper,
            model.charging_discharging_mutex,
            model.power_charge_state,
            model.power_discharge_state
        ]

        for con in constraints_to_check:
            print(f"{con.name}:")
            try:
                print(f"  约束类型: {type(con)}")
                print(f"  约束数量: {len(con)}")
            except Exception as e:
                print(f"  无法获取约束信息: {e}")

    def create_optimization_model(self):
        model = pyo.ConcreteModel()

        # 决策变量（添加初始化）
        model.P_discharge = pyo.Var(
            range(self.total_steps),
            domain=pyo.NonNegativeReals,
            initialize=0.0  # 显式初始化为0
        )
        model.P_charge = pyo.Var(
            range(self.total_steps),
            domain=pyo.NonNegativeReals,
            initialize=0.0  # 显式初始化为0
        )
        model.E = pyo.Var(
            range(self.total_steps),
            domain=pyo.NonNegativeReals,
            initialize=lambda model, t: self.battery_params['E_0'] if t == 0 else 0.0
        )
        model.Q_flow_in = pyo.Var(
            range(self.total_steps),
            domain=pyo.NonNegativeReals,
            initialize=0.0
        )
        model.Q_flow_out = pyo.Var(
            range(self.total_steps),
            domain=pyo.NonNegativeReals,
            initialize=0.0
        )

        # 二进制状态变量
        model.α = pyo.Var(
            range(self.hours),
            domain=pyo.Binary,
            initialize=0
        )
        model.β = pyo.Var(
            range(self.hours),
            domain=pyo.Binary,
            initialize=0
        )

        # 目标函数
        def objective_rule(model):
            # 能量套利收益
            energy_revenue = sum(
                model.P_discharge[t] * self.price_forecast[t] * 0.25
                for t in range(self.total_steps)
            ) - sum(
                model.P_charge[t] * self.price_forecast[t] * 0.25
                for t in range(self.total_steps)
            )

            # 退化成本
            degradation_cost = sum(
                self.battery_params['k'] * (
                        model.P_charge[t] / self.battery_params['η_charge'] +
                        model.P_discharge[t] * self.battery_params['η_discharge']
                ) * 0.25
                for t in range(self.total_steps)
            )

            # 固定运维成本
            fixed_cost = self.battery_params['C_OM']

            return energy_revenue - degradation_cost - fixed_cost

        model.objective = pyo.Objective(
            rule=objective_rule,
            sense=pyo.maximize
        )

        # 约束条件
        def energy_transfer_constraint(model, t):
            if t == 0:
                return model.E[t] == self.battery_params['E_0']
            else:
                return model.E[t] == model.E[t - 1] + \
                    model.P_charge[t - 1] * self.battery_params['η_charge'] * 0.25 - \
                    model.P_discharge[t - 1] / self.battery_params['η_discharge'] * 0.25

        def final_energy_constraint(model):
            return model.E[self.total_steps - 1] == self.battery_params['E_T_target']

        def soc_lower_constraint(model, t):
            if t == 0:
                return pyo.Constraint.Skip
            return model.E[t] >= self.battery_params['SOC_min'] * self.battery_params['E_rated']

        def soc_upper_constraint(model, t):
            if t == 0:
                return pyo.Constraint.Skip
            return model.E[t] <= self.battery_params['SOC_max'] * self.battery_params['E_rated']

        def charging_discharging_mutex_constraint(model, h):
            # 小时级充放电互斥
            return model.α[h] + model.β[h] <= 1

        def power_charge_state_constraint(model, t):
            # 将小时级状态映射到15分钟时段
            h = t // 4
            return model.P_charge[t] <= self.battery_params['P_rated'] * model.β[h]

        def power_discharge_state_constraint(model, t):
            # 将小时级状态映射到15分钟时段
            h = t // 4
            return model.P_discharge[t] <= self.battery_params['P_rated'] * model.α[h]

        def flow_in_constraint(model, t):
            return model.Q_flow_in[t] >= self.battery_params['Q_flow_min']

        def flow_out_constraint(model, t):
            return model.Q_flow_out[t] <= self.battery_params['Q_flow_max']

        def ramp_rate_charge_constraint(model, t):
            if t > 0:
                return model.P_charge[t] - model.P_charge[t - 1] <= self.battery_params['R_ramp']
            return pyo.Constraint.Skip

        def ramp_rate_discharge_constraint(model, t):
            if t > 0:
                return model.P_discharge[t] - model.P_discharge[t - 1] <= self.battery_params['R_ramp']
            return pyo.Constraint.Skip

        # 添加约束
        model.energy_transfer = pyo.Constraint(
            range(self.total_steps),
            rule=energy_transfer_constraint
        )
        model.final_energy = pyo.Constraint(rule=final_energy_constraint)
        model.soc_lower = pyo.Constraint(
            range(self.total_steps),
            rule=soc_lower_constraint
        )
        model.soc_upper = pyo.Constraint(
            range(self.total_steps),
            rule=soc_upper_constraint
        )
        model.charging_discharging_mutex = pyo.Constraint(
            range(self.hours),
            rule=charging_discharging_mutex_constraint
        )
        model.power_charge_state = pyo.Constraint(
            range(self.total_steps),
            rule=power_charge_state_constraint
        )
        model.power_discharge_state = pyo.Constraint(
            range(self.total_steps),
            rule=power_discharge_state_constraint
        )
        model.flow_in = pyo.Constraint(
            range(self.total_steps),
            rule=flow_in_constraint
        )
        model.flow_out = pyo.Constraint(
            range(self.total_steps),
            rule=flow_out_constraint
        )
        model.ramp_rate_charge = pyo.Constraint(
            range(self.total_steps),
            rule=ramp_rate_charge_constraint
        )
        model.ramp_rate_discharge = pyo.Constraint(
            range(self.total_steps),
            rule=ramp_rate_discharge_constraint
        )

        return model

    def solve_model(self):
        model = self.create_optimization_model()

        # 诊断模型
        self.diagnose_model(model)

        # 使用CBC求解器
        solver = pyo.SolverFactory('cbc')

        try:
            # 增加详细输出选项
            results = solver.solve(
                model,
                tee=True,  # 显示求解过程
                keepfiles=True,  # 保留中间文件
                options={
                    'maxNodes': 5000,
                    'seconds': 120,  # 增加求解时间
                    'printingOptions': 'all'
                }
            )

            # 详细的求解状态检查
            print("求解器状态:", results.solver.status)
            print("终止条件:", results.solver.termination_condition)

            if (results.solver.status == pyo.SolverStatus.ok) and \
                    (results.solver.termination_condition == pyo.TerminationCondition.optimal):
                return model, results
            elif results.solver.termination_condition == pyo.TerminationCondition.infeasible:
                print("模型无可行解")
                raise ValueError("模型无可行解")
            elif results.solver.termination_condition == pyo.TerminationCondition.unbounded:
                print("模型无界")
                raise ValueError("模型无界")
            else:
                print("求解失败")
                raise ValueError("优化求解未达到最优解")

        except Exception as e:
            print(f"求解过程中出现错误: {e}")
            raise


def mode_selection_rarr(optimal_model, price_forecast, battery_params, num_simulations=1000):
    """
    一个计算上可行的、基于RARR的模式选择方法。

    Args:
        optimal_model: 已经求解过的、基于预测电价的优化模型。
        price_forecast: 原始的电价预测序列。
        battery_params: 电池参数。
        num_simulations: 蒙特卡洛模拟的次数。

    Returns:
        int: 0 代表“报量不报价”，1 代表“报量报价”。
    """
    print("正在通过RARR方法进行模式决策...")

    # 1. 从基准计划中提取最优充放电功率
    base_charge_power = [pyo.value(optimal_model.P_charge[t]) for t in range(len(price_forecast))]
    base_discharge_power = [pyo.value(optimal_model.P_discharge[t]) for t in range(len(price_forecast))]

    # 2. 模拟价格不确定性
    # 假设预测误差的标准差是价格的15%
    price_error_std_dev = 0.15
    price_scenarios = []
    for _ in range(num_simulations):
        price_noise = np.random.normal(0, price_error_std_dev, len(price_forecast))
        scenario_prices = price_forecast * (1 + price_noise)
        price_scenarios.append(np.maximum(0, scenario_prices))  # 确保价格不为负

    # 3. 评估两种模式
    qnp_revenues = []  # 报量不报价 (Quantity No Price)
    qp_revenues = []  # 报量报价 (Quantity and Price)

    for scenario_prices in price_scenarios:
        # 计算QNP模式的利润
        qnp_profit = sum(
            (base_discharge_power[t] * scenario_prices[t] - base_charge_power[t] * scenario_prices[t]) * 0.25
            for t in range(len(price_forecast))
        )
        qnp_revenues.append(qnp_profit)

        # 计算QP模式的利润，引入“中标率”风险
        clearing_success_rate = np.random.uniform(0.70, 0.95)  # 假设中标率在70%到95%之间
        qp_profit = sum(
            (base_discharge_power[t] * clearing_success_rate * scenario_prices[t] -
             base_charge_power[t] * clearing_success_rate * scenario_prices[t]) * 0.25
            for t in range(len(price_forecast))
        )
        qp_revenues.append(qp_profit)

    # 4. 计算RARR值
    # 为避免除以零，给标准差加上一个极小值
    epsilon = 1e-9

    qnp_mean = np.mean(qnp_revenues)
    qnp_std = np.std(qnp_revenues)
    rarr_qnp = qnp_mean / (qnp_std + epsilon)

    qp_mean = np.mean(qp_revenues)
    qp_std = np.std(qp_revenues)
    rarr_qp = qp_mean / (qp_std + epsilon)

    print(f"报量不报价 (QNP) -> 预期收益: {qnp_mean:.2f}, 风险(Std): {qnp_std:.2f}, RARR: {rarr_qnp:.3f}")
    print(f"报量报价 (QP)   -> 预期收益: {qp_mean:.2f}, 风险(Std): {qp_std:.2f}, RARR: {rarr_qp:.3f}")

    # 5. 最终决策
    if rarr_qp > rarr_qnp:
        print("决策结果: 选择“报量报价”模式。")
        return 1
    else:
        print("决策结果: 选择“报量不报价”模式。")
        return 0


def generate_segmented_bid_table(model, price_forecast, battery_params):
    """
    为“报量报价”模式生成详细的、分时段的分段报价表。

    Args:
        model: 已求解的优化模型。
        price_forecast: 电价预测序列。
        battery_params: 电池参数。

    Returns:
        pandas.DataFrame: 格式化后的分段报价表。
    """
    bid_table_data = []

    # 检查模型是否有效
    if model is None:
        # 如果模型无效，生成所有时间步的静置记录
        for t in range(len(price_forecast)):
            hour = t // 4
            minute = (t % 4) * 15
            end_minute = minute + 15
            end_hour = hour

            if end_minute >= 60:
                end_minute = 0
                end_hour = hour + 1

            time_label = f"{hour:02d}:{minute:02d}-{end_hour:02d}:{end_minute:02d}"

            bid_table_data.append({
                '时间点': time_label,
                '申报类型': '静置',
                '功率段 (MW)': '0.0 ~ 0.0',
                '报价 (元/MWh)': f"{price_forecast[t]:.2f}",
                '备注': '模型求解失败，无充放电操作'
            })

        return pd.DataFrame(bid_table_data)

    # 遍历所有96个时间步
    for t in range(len(price_forecast)):
        try:
            # 从模型中获取该时段的最优充放电功率
            charge_power = pyo.value(model.P_charge[t])
            discharge_power = pyo.value(model.P_discharge[t])

            # 检查是否获取到有效值
            if charge_power is None:
                charge_power = 0
            if discharge_power is None:
                discharge_power = 0

        except Exception as e:
            # 如果模型未求解或变量无值，设为0
            print(f"获取时间步 {t} 的功率值时出错: {e}")
            charge_power = 0
            discharge_power = 0

        # 修正时间标签生成逻辑
        hour = t // 4
        minute = (t % 4) * 15
        end_minute = minute + 15
        end_hour = hour

        # 处理分钟进位
        if end_minute >= 60:
            end_minute = 0
            end_hour = hour + 1

        time_label = f"{hour:02d}:{minute:02d}-{end_hour:02d}:{end_minute:02d}"

        # --- 充电时段的报价逻辑 ---
        if charge_power > 0.01 and discharge_power <= 0.01:
            # 计算充电的边际成本价
            base_price = (price_forecast[t] / battery_params['η_charge']) + battery_params['k']

            # 定义三段式报价策略
            segments = [
                {'power_min': 0, 'power_max': charge_power * 0.5, 'price_adj': 5, 'note': '保守报价，确保基础成交'},
                {'power_min': charge_power * 0.5, 'power_max': charge_power * 0.9, 'price_adj': 15,
                 'note': '核心报价，围绕预测边际价'},
                {'power_min': charge_power * 0.9, 'power_max': charge_power, 'price_adj': 30,
                 'note': '激进报价，仅在电价极低时成交'}
            ]

            for i, segment in enumerate(segments):
                if segment['power_max'] > segment['power_min']:
                    bid_table_data.append({
                        '时间点': time_label,
                        '申报类型': '充电',
                        '功率段 (MW)': f"{-segment['power_max']:.1f} ~ {-segment['power_min']:.1f}",
                        '报价 (元/MWh)': f"{base_price + segment['price_adj']:.2f}",
                        '备注': segment['note']
                    })

        # --- 放电时段的报价逻辑 ---
        elif discharge_power > 0.01 and charge_power <= 0.01:
            # 计算放电的边际收益价
            base_price = (price_forecast[t] - battery_params['k']) * battery_params['η_discharge']

            # 定义三段式报价策略
            segments = [
                {'power_min': 0, 'power_max': discharge_power * 0.5, 'price_adj': -20, 'note': '保守报价，确保基础成交'},
                {'power_min': discharge_power * 0.5, 'power_max': discharge_power * 0.9, 'price_adj': -10,
                 'note': '核心报价，围绕预测边际价'},
                {'power_min': discharge_power * 0.9, 'power_max': discharge_power, 'price_adj': 50,
                 'note': '激进报价，捕捉尖峰价格'}
            ]

            for i, segment in enumerate(segments):
                if segment['power_max'] > segment['power_min']:
                    bid_table_data.append({
                        '时间点': time_label,
                        '申报类型': '放电',
                        '功率段 (MW)': f"{segment['power_min']:.1f} ~ {segment['power_max']:.1f}",
                        '报价 (元/MWh)': f"{max(base_price + segment['price_adj'], 10):.2f}",
                        '备注': segment['note']
                    })

        # --- 静置时段 ---
        else:
            bid_table_data.append({
                '时间点': time_label,
                '申报类型': '静置',
                '功率段 (MW)': '0.0 ~ 0.0',
                '报价 (元/MWh)': f"{price_forecast[t]:.2f}",
                '备注': '无充放电操作'
            })

    # 如果没有生成任何数据，创建一个全静置的申报表
    if not bid_table_data:
        for t in range(len(price_forecast)):
            hour = t // 4
            minute = (t % 4) * 15
            end_minute = minute + 15
            end_hour = hour

            if end_minute >= 60:
                end_minute = 0
                end_hour = hour + 1

            time_label = f"{hour:02d}:{minute:02d}-{end_hour:02d}:{end_minute:02d}"

            bid_table_data.append({
                '时间点': time_label,
                '申报类型': '静置',
                '功率段 (MW)': '0.0 ~ 0.0',
                '报价 (元/MWh)': f"{price_forecast[t]:.2f}",
                '备注': '无任何申报'
            })

    return pd.DataFrame(bid_table_data)


def generate_bid_table(model, price_forecast, battery_params):
    """
    为"报量不报价"模式生成完整的功率申报表（包含所有96个时间步）

    Args:
        model: 已求解的优化模型
        price_forecast: 电价预测序列
        battery_params: 电池参数

    Returns:
        pandas.DataFrame: 格式化后的功率申报表
    """
    bid_table_data = []

    # 检查模型是否有效
    if model is None:
        # 如果模型无效，生成所有时间步的静置记录
        for t in range(len(price_forecast)):
            hour = t // 4
            minute = (t % 4) * 15
            end_minute = minute + 15
            end_hour = hour

            if end_minute >= 60:
                end_minute = 0
                end_hour = hour + 1

            time_label = f"{hour:02d}:{minute:02d}-{end_hour:02d}:{end_minute:02d}"

            bid_table_data.append({
                '时间点': time_label,
                '申报类型': '静置',
                '申报功率 (MW)': '0.00',
                '预测电价 (元/MWh)': f"{price_forecast[t]:.2f}",
                '预期收益/成本 (元)': '0.00',
                '备注': '模型求解失败，无充放电操作'
            })

        return pd.DataFrame(bid_table_data)

    for t in range(len(price_forecast)):
        try:
            # 从模型中获取该时段的最优充放电功率
            charge_power = pyo.value(model.P_charge[t])
            discharge_power = pyo.value(model.P_discharge[t])

            # 检查是否获取到有效值
            if charge_power is None:
                charge_power = 0
            if discharge_power is None:
                discharge_power = 0

        except Exception as e:
            # 如果模型未求解或变量无值，设为0
            print(f"获取时间步 {t} 的功率值时出错: {e}")
            charge_power = 0
            discharge_power = 0

        # 修正时间标签生成逻辑
        hour = t // 4
        minute = (t % 4) * 15
        end_minute = minute + 15
        end_hour = hour

        # 处理分钟进位
        if end_minute >= 60:
            end_minute = 0
            end_hour = hour + 1

        time_label = f"{hour:02d}:{minute:02d}-{end_hour:02d}:{end_minute:02d}"

        # 确定申报类型和功率
        if discharge_power > 0.01 and charge_power <= 0.01:
            # 放电时段
            power_type = "放电"
            power_value = discharge_power
            expected_revenue = discharge_power * price_forecast[t] * 0.25
            efficiency_note = f"放电效率: {battery_params['η_discharge']:.1%}"

        elif charge_power > 0.01 and discharge_power <= 0.01:
            # 充电时段
            power_type = "充电"
            power_value = -charge_power  # 显示为负值表示充电
            expected_revenue = -charge_power * price_forecast[t] * 0.25  # 负值表示成本
            efficiency_note = f"充电效率: {battery_params['η_charge']:.1%}"

        else:
            # 静置时段
            power_type = "静置"
            power_value = 0.0
            expected_revenue = 0.0
            efficiency_note = "无充放电操作"

        bid_table_data.append({
            '时间点': time_label,
            '申报类型': power_type,
            '申报功率 (MW)': f"{power_value:.2f}",
            '预测电价 (元/MWh)': f"{price_forecast[t]:.2f}",
            '预期收益/成本 (元)': f"{expected_revenue:.2f}",
            '备注': efficiency_note
        })

    # 如果没有生成任何数据，创建一个全静置的申报表
    if not bid_table_data:
        for t in range(len(price_forecast)):
            hour = t // 4
            minute = (t % 4) * 15
            end_minute = minute + 15
            end_hour = hour

            if end_minute >= 60:
                end_minute = 0
                end_hour = hour + 1

            time_label = f"{hour:02d}:{minute:02d}-{end_hour:02d}:{end_minute:02d}"

            bid_table_data.append({
                '时间点': time_label,
                '申报类型': '静置',
                '申报功率 (MW)': '0.00',
                '预测电价 (元/MWh)': f"{price_forecast[t]:.2f}",
                '预期收益/成本 (元)': '0.00',
                '备注': '无任何申报'
            })

    return pd.DataFrame(bid_table_data)

def calculate_kpis(model, price_forecast, battery_params):
    """
    计算关键性能指标 (KPIs)。

    Args:
        model: 已求解的优化模型。
        price_forecast: 电价预测序列。
        battery_params: 电池参数。

    Returns:
        dict: 包含各项KPIs的字典。
    """
    try:
        # --- 从模型中提取结果 ---
        charge_power = [pyo.value(model.P_charge[t]) for t in range(len(price_forecast))]
        discharge_power = [pyo.value(model.P_discharge[t]) for t in range(len(price_forecast))]

        # --- 计算经济指标 ---
        # 计算总的充、放电成本和收益
        total_charge_cost = sum(charge_power[t] * price_forecast[t] * 0.25 for t in range(len(price_forecast)))
        total_discharge_revenue = sum(discharge_power[t] * price_forecast[t] * 0.25 for t in range(len(price_forecast)))

        # 计算总的退化成本
        total_degradation_cost = sum(
            battery_params['k'] * (
                    charge_power[t] / battery_params['η_charge'] +
                    discharge_power[t] * battery_params['η_discharge']
            ) * 0.25
            for t in range(len(price_forecast))
        )

        # 总净利润 = 放电收益 - 充电成本 - 退化成本 - 固定运维成本
        total_net_profit = total_discharge_revenue - total_charge_cost - total_degradation_cost - battery_params['C_OM']

        # --- 计算技术指标 ---
        # 总能量吞吐 (MWh)
        total_energy_throughput = sum((charge_power[t] + discharge_power[t]) * 0.25 for t in range(len(price_forecast)))

        # 等效循环次数 (一个完整循环 = 充一次额定容量 + 放一次额定容量)
        # 避免除以零的错误
        if battery_params['E_rated'] > 0:
            equivalent_cycles = total_energy_throughput / (2 * battery_params['E_rated'])
        else:
            equivalent_cycles = 0

        # 平均度电利润 (元/MWh)
        # 避免除以零的错误
        if total_energy_throughput > 0:
            avg_profit_per_mwh = total_net_profit / total_energy_throughput
        else:
            avg_profit_per_mwh = 0

        return {
            '总净利润': total_net_profit,
            '总放电收益': total_discharge_revenue,
            '等效循环次数': equivalent_cycles,
            '总能量吞吐': total_energy_throughput,
            '平均度电利润': avg_profit_per_mwh
        }
    except Exception as e:
        # 如果计算出错，返回一组默认值
        print(f"KPIs计算过程中出现错误: {e}")
        return {
            '总净利润': 0,
            '总放电收益': 0,
            '等效循环次数': 0,
            '总能量吞吐': 0,
            '平均度电利润': 0
        }