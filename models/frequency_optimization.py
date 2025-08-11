"""
调频市场优化模型
基于日前市场结果，优化调频容量申报策略
"""

import pyomo.environ as pyo
import numpy as np
import pandas as pd

class FrequencyMarketOptimizer:
    def __init__(self, da_results, battery_params, frequency_params, cost_params):
        """
        初始化调频市场优化器

        Args:
            da_results: 日前市场优化结果
            battery_params: 电池技术参数
            frequency_params: 调频市场参数
            cost_params: 成本参数
        """
        self.da_results = da_results
        self.battery_params = battery_params
        self.frequency_params = frequency_params
        self.cost_params = cost_params
        self.model = None
        self.solution = None

        # 调试信息
        print(f"🔧 调频市场优化器初始化")
        print(f"   电池额定功率: {battery_params['P_rated']} MW")
        print(f"   电池额定容量: {battery_params['E_rated']} MWh")
        print(f"   核定成本: {cost_params['verified_cost']} 元/MWh")

    def extract_da_schedule(self):
        """
        从日前市场结果中提取功率计划和SOC状态
        """
        schedule = {
            'charge_power': [],
            'discharge_power': [],
            'net_power': [],
            'soc': [],
            'energy': []
        }

        print("📊 提取日前市场数据...")

        for t in range(24):
            try:
                # 从15分钟时段聚合到小时
                hour_charge = sum(pyo.value(self.da_results.P_charge[t*4 + i]) for i in range(4)) / 4
                hour_discharge = sum(pyo.value(self.da_results.P_discharge[t*4 + i]) for i in range(4)) / 4
                hour_energy = pyo.value(self.da_results.E[t*4])  # 取小时初的能量状态

                schedule['charge_power'].append(hour_charge)
                schedule['discharge_power'].append(hour_discharge)
                schedule['net_power'].append(hour_discharge - hour_charge)
                schedule['energy'].append(hour_energy)
                schedule['soc'].append(hour_energy / self.battery_params['E_rated'])

                # 调试信息（只显示前3小时）
                if t < 3:
                    print(f"   第{t+1}小时: 充电={hour_charge:.2f}MW, 放电={hour_discharge:.2f}MW, 净功率={hour_discharge - hour_charge:.2f}MW, SOC={hour_energy / self.battery_params['E_rated']:.3f}")

            except Exception as e:
                print(f"⚠️ 提取第{t}小时数据时出错: {e}")
                # 使用默认值
                schedule['charge_power'].append(0)
                schedule['discharge_power'].append(0)
                schedule['net_power'].append(0)
                schedule['energy'].append(self.battery_params['E_0'])
                schedule['soc'].append(self.battery_params['initial_soc'])

        return schedule

    def calculate_capacity_limits(self, da_schedule):
        """
        计算调频容量申报的上下限 - 放宽限制条件
        """
        limits = {'min': [], 'max': []}

        # 实测调节速率 (MW/min) - 使用更保守的值
        measured_rate = min(self.frequency_params.get('measured_regulation_rate', 1.5),
                           self.battery_params['P_rated'] * 0.1)  # 不超过额定功率的10%

        # 控制区调频容量需求
        control_area_demand = self.frequency_params.get('control_area_demand', 500)
        num_units = self.frequency_params.get('num_units', 10)

        print(f"📊 计算调频容量限制:")
        print(f"   实测调节速率: {measured_rate} MW/min")
        print(f"   控制区需求: {control_area_demand} MW")

        for t in range(24):
            # 可调节容量 = 额定功率 - |日前净功率| - 安全裕度
            safety_margin = self.battery_params['P_rated'] * 0.05  # 5%安全裕度
            available_capacity = max(0, self.battery_params['P_rated'] - abs(da_schedule['net_power'][t]) - safety_margin)

            # 下限：设为0，允许不参与调频
            c_min = 0

            # 上限：采用更保守的计算方式
            c_max_options = [
                measured_rate * 2,  # 2分钟调节能力（降低要求）
                self.battery_params['P_rated'] * 0.1,  # 10%额定功率（降低要求）
                control_area_demand * 0.1 / num_units,  # 10%控制区需求分摊（降低要求）
                available_capacity * 0.8,  # 80%可用容量（增加安全裕度）
                5.0  # 绝对上限5MW
            ]

            c_max = min([x for x in c_max_options if x > 0])  # 取正值中的最小值

            # 确保上下限合理
            c_min = max(0, c_min)
            c_max = max(c_min + 0.1, c_max)  # 确保至少有0.1MW的可行域

            limits['min'].append(c_min)
            limits['max'].append(c_max)

            # 调试信息（只显示前3小时）
            if t < 3:
                print(f"   第{t+1}小时: 可调节容量={available_capacity:.2f}MW, 容量范围=[{c_min:.2f}, {c_max:.2f}]MW")

        return limits

    def create_optimization_model(self):
        """
        创建调频市场优化模型 - 简化约束条件
        """
        model = pyo.ConcreteModel()

        # 提取日前市场计划
        da_schedule = self.extract_da_schedule()
        capacity_limits = self.calculate_capacity_limits(da_schedule)

        print(f"\n📊 调频市场建模参数:")
        print(f"   日前电价范围: {min(self.frequency_params['lmp_da']):.1f} - {max(self.frequency_params['lmp_da']):.1f} 元/MWh")
        print(f"   里程价格范围: {min(self.frequency_params['mileage_price_forecast']):.1f} - {max(self.frequency_params['mileage_price_forecast']):.1f} 元/MW")
        print(f"   里程距离范围: {min(self.frequency_params['mileage_distance']):.1f} - {max(self.frequency_params['mileage_distance']):.1f} MW")

        # 决策变量：24小时调频容量申报 C_t^freq
        model.C_freq = pyo.Var(
            range(24),
            domain=pyo.NonNegativeReals,
            bounds=lambda model, t: (capacity_limits['min'][t], capacity_limits['max'][t])
        )

        # 目标函数：最大化净收益 - 简化计算
        def objective_rule(model):
            total_objective = 0

            for t in range(24):
                # 技术参数
                LMP_DA = self.frequency_params['lmp_da'][t]
                C_verified = self.cost_params['verified_cost']
                D_t = self.frequency_params['mileage_distance'][t]
                Q_t = self.frequency_params['mileage_price_forecast'][t]
                K_t = self.frequency_params['performance_index'][t]

                # 容量补偿收益: R_t^capacity = C_t^freq × max(0, LMP_DA - C_verified)
                capacity_price_diff = max(0, LMP_DA - C_verified)
                capacity_revenue = model.C_freq[t] * capacity_price_diff

                # 里程补偿收益: 简化计算，使用固定系数
                mileage_revenue = model.C_freq[t] * Q_t * K_t * 0.1  # 简化系数

                # 运行成本 - 简化计算
                total_cost_rate = (
                    self.cost_params['degradation_rate'] * self.cost_params['alpha_freq'] +
                    self.cost_params['om_cost_rate']
                )

                total_cost = model.C_freq[t] * total_cost_rate

                # 小时净收益
                hourly_profit = capacity_revenue + mileage_revenue - total_cost
                total_objective += hourly_profit

            return total_objective

        model.objective = pyo.Objective(rule=objective_rule, sense=pyo.maximize)

        # 约束条件 - 大幅简化

        # 1. 基本功率约束 - 放宽限制
        def power_constraint(model, t):
            net_power = da_schedule['net_power'][t]
            max_additional_power = self.battery_params['P_rated'] * 0.8 - abs(net_power)  # 80%限制
            return model.C_freq[t] <= max(0.1, max_additional_power)  # 至少允许0.1MW

        model.power_limit = pyo.Constraint(range(24), rule=power_constraint)

        # 2. SOC约束 - 大幅放宽
        def soc_constraint(model, t):
            soc_da = da_schedule['soc'][t]
            # 只检查极端情况，给予很大的容忍度
            max_soc_impact = 0.1  # 最大10%的SOC影响
            max_capacity_from_soc = max_soc_impact * self.battery_params['E_rated'] / self.cost_params['alpha_freq']
            return model.C_freq[t] <= max(1.0, max_capacity_from_soc)  # 至少允许1MW

        model.soc_limit = pyo.Constraint(range(24), rule=soc_constraint)

        # 3. 移除爬坡率约束 - 简化模型

        # 4. 移除净收益约束 - 让目标函数自然优化

        self.model = model
        return model

    def solve_model(self):
        """
        求解优化模型
        """
        if self.model is None:
            self.create_optimization_model()

        # 使用CBC求解器
        solver = pyo.SolverFactory('cbc')

        try:
            print("\n🔧 开始求解调频市场优化模型...")
            results = solver.solve(self.model, tee=False)

            print(f"   求解状态: {results.solver.status}")
            print(f"   终止条件: {results.solver.termination_condition}")

            if (results.solver.status == pyo.SolverStatus.ok and
                results.solver.termination_condition == pyo.TerminationCondition.optimal):

                # 提取解
                self.solution = {
                    'frequency_capacity': [pyo.value(self.model.C_freq[t]) for t in range(24)],
                    'objective_value': pyo.value(self.model.objective),
                    'solver_status': 'optimal'
                }

                print(f"✅ 求解成功!")
                print(f"   目标函数值: {self.solution['objective_value']:.2f} 元")
                print(f"   总调频容量: {sum(self.solution['frequency_capacity']):.2f} MW")
                print(f"   最大小时容量: {max(self.solution['frequency_capacity']):.2f} MW")

                # 计算详细的收益和成本分解
                self._calculate_detailed_results()

                return self.solution

            elif results.solver.termination_condition == pyo.TerminationCondition.infeasible:
                print("❌ 模型仍然无可行解，使用启发式解决方案")
                # 生成启发式解决方案
                self.solution = self._generate_heuristic_solution()
                self._calculate_detailed_results()
                return self.solution

            else:
                print(f"❌ 求解失败: {results.solver.termination_condition}")
                # 生成启发式解决方案
                self.solution = self._generate_heuristic_solution()
                self._calculate_detailed_results()
                return self.solution

        except Exception as e:
            print(f"❌ 调频市场求解过程中出现错误: {e}")
            import traceback
            traceback.print_exc()

            # 生成启发式解决方案
            self.solution = self._generate_heuristic_solution()
            self._calculate_detailed_results()
            return self.solution

    def _generate_heuristic_solution(self):
        """
        生成启发式解决方案 - 当优化求解失败时使用
        """
        print("🔧 生成启发式调频容量申报方案...")

        # 提取日前市场计划
        da_schedule = self.extract_da_schedule()
        capacity_limits = self.calculate_capacity_limits(da_schedule)

        frequency_capacity = []

        for t in range(24):
            # 基于经济性的启发式决策
            LMP_DA = self.frequency_params['lmp_da'][t]
            C_verified = self.cost_params['verified_cost']
            Q_t = self.frequency_params['mileage_price_forecast'][t]

            # 计算潜在收益率
            capacity_profit_rate = max(0, LMP_DA - C_verified)
            mileage_profit_rate = Q_t * self.frequency_params['performance_index'][t] * 0.1
            total_profit_rate = capacity_profit_rate + mileage_profit_rate

            # 计算成本率
            cost_rate = (self.cost_params['degradation_rate'] * self.cost_params['alpha_freq'] +
                        self.cost_params['om_cost_rate'])

            # 如果有利可图，申报容量
            if total_profit_rate > cost_rate:
                # 申报容量为上限的50-80%
                capacity_ratio = min(0.8, max(0.3, (total_profit_rate - cost_rate) / cost_rate))
                capacity = capacity_limits['max'][t] * capacity_ratio
            else:
                # 不参与调频
                capacity = 0

            frequency_capacity.append(capacity)

        total_capacity = sum(frequency_capacity)
        print(f"   启发式方案总容量: {total_capacity:.2f} MW")
        print(f"   参与调频时段: {sum(1 for c in frequency_capacity if c > 0)} 小时")

        return {
            'frequency_capacity': frequency_capacity,
            'objective_value': 0,  # 将在详细计算中更新
            'solver_status': 'heuristic'
        }

    def _calculate_detailed_results(self):
        """
        计算详细的收益和成本分解
        """
        if self.solution is None:
            return

        print("\n📊 计算详细收益成本分解...")

        capacity_revenues = []
        mileage_revenues = []
        degradation_costs = []
        efficiency_costs = []
        om_costs = []

        for t in range(24):
            c_freq = self.solution['frequency_capacity'][t]

            # 技术参数
            LMP_DA = self.frequency_params['lmp_da'][t]
            C_verified = self.cost_params['verified_cost']
            D_t = self.frequency_params['mileage_distance'][t]
            Q_t = self.frequency_params['mileage_price_forecast'][t]
            K_t = self.frequency_params['performance_index'][t]

            # 容量补偿收益
            capacity_rev = c_freq * max(0, LMP_DA - C_verified)
            capacity_revenues.append(capacity_rev)

            # 里程补偿收益 - 使用更合理的计算方式
            mileage_rev = c_freq * Q_t * K_t * 0.1  # 简化系数
            mileage_revenues.append(mileage_rev)

            # 成本分解
            deg_cost = c_freq * self.cost_params['alpha_freq'] * self.cost_params['degradation_rate']
            eff_cost = c_freq * self.cost_params['alpha_freq'] * self.cost_params['efficiency_loss_rate'] * LMP_DA * 0.01
            om_cost = c_freq * self.cost_params['om_cost_rate']

            degradation_costs.append(deg_cost)
            efficiency_costs.append(eff_cost)
            om_costs.append(om_cost)

        self.solution.update({
            'capacity_revenues': capacity_revenues,
            'mileage_revenues': mileage_revenues,
            'degradation_costs': degradation_costs,
            'efficiency_costs': efficiency_costs,
            'om_costs': om_costs,
            'total_revenue': sum(capacity_revenues) + sum(mileage_revenues),
            'total_cost': sum(degradation_costs) + sum(efficiency_costs) + sum(om_costs),
            'net_profit': sum(capacity_revenues) + sum(mileage_revenues) -
                         sum(degradation_costs) - sum(efficiency_costs) - sum(om_costs)
        })

        # 添加价格预测到结果中
        self.solution['mileage_price_forecast'] = self.frequency_params['mileage_price_forecast']

        # 更新目标函数值
        if self.solution['solver_status'] == 'heuristic':
            self.solution['objective_value'] = self.solution['net_profit']

        print(f"   总收益: {self.solution['total_revenue']:.2f} 元")
        print(f"   总成本: {self.solution['total_cost']:.2f} 元")
        print(f"   净利润: {self.solution['net_profit']:.2f} 元")
        print(f"   容量补偿: {sum(capacity_revenues):.2f} 元")
        print(f"   里程补偿: {sum(mileage_revenues):.2f} 元")

    def get_solution_summary(self):
        """
        获取求解结果摘要
        """
        if self.solution is None:
            return None

        return {
            'total_frequency_capacity': sum(self.solution['frequency_capacity']),
            'max_hourly_capacity': max(self.solution['frequency_capacity']),
            'min_hourly_capacity': min(self.solution['frequency_capacity']),
            'avg_hourly_capacity': np.mean(self.solution['frequency_capacity']),
            'total_revenue': self.solution['total_revenue'],
            'total_cost': self.solution['total_cost'],
            'net_profit': self.solution['net_profit'],
            'profit_margin': self.solution['net_profit'] / self.solution['total_revenue'] if self.solution['total_revenue'] > 0 else 0,
            'solver_status': self.solution['solver_status']
        }

def create_default_frequency_params():
    """
    创建默认的调频市场参数
    """
    return {
        'lmp_da': [300 + 100 * np.sin(2 * np.pi * t / 24) for t in range(24)],  # 日前电价
        'mileage_distance': [50 + 20 * np.sin(2 * np.pi * t / 24) for t in range(24)],  # 调频里程
        'mileage_price_forecast': [25 + 10 * np.sin(2 * np.pi * t / 24) for t in range(24)],  # 里程价格预测
        'performance_index': [0.85] * 24,  # 综合调频性能指标
        'measured_regulation_rate': 1.5,  # 实测调节速率 MW/min
        'control_area_demand': 500,  # 控制区调频需求 MW
        'num_units': 10  # 参与机组数
    }

def create_default_cost_params():
    """
    创建默认的成本参数
    """
    return {
        'verified_cost': 250,  # 核定成本 元/MWh
        'degradation_rate': 0.5,  # 退化成本率 元/MW/h，降低成本
        'efficiency_loss_rate': 0.02,  # 效率损失率
        'om_cost_rate': 0.3,  # 运维成本率 元/MW/h，降低成本
        'alpha_freq': 0.15,  # 调频活动系数，降低影响
        'ramp_rate_limit': 0.3,  # 爬坡率限制
        'min_profit_rate': 0.02  # 最小利润率，降低要求
    }

if __name__ == "__main__":
    print("调频市场优化模型测试")