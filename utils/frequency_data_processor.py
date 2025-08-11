"""
调频数据处理工具
处理调频市场相关的数据，包括历史数据生成、参数配置等
"""

import os
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

def generate_frequency_demand_history(days=90, save_path=None):
    """
    生成历史调频需求数据

    Args:
        days: 生成天数
        save_path: 保存路径
    """
    np.random.seed(42)

    data = []
    start_date = datetime.now() - timedelta(days=days)

    for day in range(days):
        current_date = start_date + timedelta(days=day)

        for hour in range(24):
            # 基础调频需求模式
            base_demand = 100 + 50 * np.sin(2 * np.pi * hour / 24)  # 日内周期

            # 周末因子
            is_weekend = current_date.weekday() >= 5
            weekend_factor = 0.8 if is_weekend else 1.0

            # 高峰时段因子
            is_peak = 8 <= hour <= 22
            peak_factor = 1.3 if is_peak else 0.9

            # 季节因子
            season_factor = 1.0 + 0.2 * np.sin(2 * np.pi * day / 365)

            # 随机波动
            noise = np.random.normal(0, 10)

            demand = base_demand * weekend_factor * peak_factor * season_factor + noise
            demand = max(50, demand)  # 最小需求50MW

            data.append({
                'datetime': current_date.replace(hour=hour, minute=0, second=0),
                'date': current_date.date(),
                'hour': hour,
                'day_of_week': current_date.weekday(),
                'is_weekend': is_weekend,
                'is_peak': is_peak,
                'frequency_demand': demand,
                'system_load': 20000 + 5000 * np.sin(2 * np.pi * hour / 24) + np.random.normal(0, 500),
                'renewable_penetration': max(0, min(1, 0.25 + 0.15 * np.sin(2 * np.pi * hour / 24) + np.random.normal(0, 0.05)))
            })

    df = pd.DataFrame(data)

    if save_path:
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        df.to_csv(save_path, index=False)
        print(f"历史调频需求数据已保存到: {save_path}")

    return df

def generate_frequency_price_history(demand_df=None, days=90, save_path=None):
    """
    生成历史调频价格数据

    Args:
        demand_df: 调频需求数据
        days: 生成天数
        save_path: 保存路径
    """
    if demand_df is None:
        demand_df = generate_frequency_demand_history(days)

    # 基于需求数据生成价格
    price_data = []

    for _, row in demand_df.iterrows():
        # 基础价格模型
        demand_normalized = (row['frequency_demand'] - 50) / 150  # 归一化到0-1

        base_price = 15 + 20 * demand_normalized  # 基础价格15-35元/MW

        # 可再生能源渗透率影响
        renewable_impact = 5 * row['renewable_penetration']

        # 高峰时段溢价
        peak_premium = 8 if row['is_peak'] else 0

        # 周末折扣
        weekend_discount = -3 if row['is_weekend'] else 0

        # 随机波动
        noise = np.random.normal(0, 2)

        price = base_price + renewable_impact + peak_premium + weekend_discount + noise
        price = max(5, min(50, price))  # 限制在5-50元/MW范围内

        # 应用价格最小单位约束
        price = round(price / 0.1) * 0.1

        price_data.append({
            'datetime': row['datetime'],
            'date': row['date'],
            'hour': row['hour'],
            'frequency_demand': row['frequency_demand'],
            'frequency_price': price,
            'system_load': row['system_load'],
            'renewable_penetration': row['renewable_penetration']
        })

    price_df = pd.DataFrame(price_data)

    if save_path:
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        price_df.to_csv(save_path, index=False)
        print(f"历史调频价格数据已保存到: {save_path}")

    return price_df

def load_frequency_data(data_dir="data"):
    """
    加载调频相关数据

    Args:
        data_dir: 数据目录
    """
    demand_path = os.path.join(data_dir, "frequency_demand_history.csv")
    price_path = os.path.join(data_dir, "frequency_price_history.csv")

    # 检查文件是否存在，不存在则生成
    if not os.path.exists(demand_path):
        print("生成历史调频需求数据...")
        generate_frequency_demand_history(save_path=demand_path)

    if not os.path.exists(price_path):
        print("生成历史调频价格数据...")
        demand_df = pd.read_csv(demand_path)
        generate_frequency_price_history(demand_df, save_path=price_path)

    # 加载数据
    demand_df = pd.read_csv(demand_path)
    price_df = pd.read_csv(price_path)

    return demand_df, price_df

def create_frequency_market_params(lmp_da_forecast=None, user_params=None):
    """
    创建调频市场参数 - 修复参数类型问题

    Args:
        lmp_da_forecast: 日前市场电价预测（24小时）
        user_params: 用户自定义参数
    """
    # 默认参数 - 优化以提高可行性
    default_params = {
        'lmp_da': lmp_da_forecast if lmp_da_forecast else [350 + 150 * np.sin(2 * np.pi * t / 24) for t in range(24)],  # 提高电价
        'mileage_distance': [60 + 30 * np.sin(2 * np.pi * t / 24) + np.random.normal(0, 5) for t in range(24)],  # 增加里程
        'performance_index': [0.85 + 0.05 * np.sin(2 * np.pi * t / 24) for t in range(24)],  # 时变性能指标
        'measured_regulation_rate': 2.0,  # MW/min，提高调节能力
        'control_area_demand': 600,  # MW，增加需求
        'num_units': 8,  # 减少机组数，增加单机容量分配
        'verified_cost': 200,  # 元/MWh，降低核定成本
        'mileage_price_forecast': [30 + 15 * np.sin(2 * np.pi * t / 24) for t in range(24)]  # 提高里程价格
    }

    # 应用用户自定义参数
    if user_params:
        for key, value in user_params.items():
            if key == 'performance_index':
                # 特殊处理 performance_index 参数
                if isinstance(value, (int, float)):
                    # 如果是单个数值，扩展为24小时的列表
                    default_params[key] = [float(value)] * 24
                elif isinstance(value, (list, tuple)) and len(value) == 24:
                    # 如果是24小时的列表，直接使用
                    default_params[key] = list(value)
                else:
                    # 其他情况，使用默认值
                    print(f"⚠️ performance_index 参数格式不正确，使用默认值")
            else:
                # 其他参数直接更新
                default_params[key] = value

    # 确保里程距离为正值且合理
    default_params['mileage_distance'] = [max(40, min(100, d)) for d in default_params['mileage_distance']]

    # 确保性能指标在合理范围内 - 修复类型检查
    if isinstance(default_params['performance_index'], list):
        default_params['performance_index'] = [max(0.7, min(1.0, p)) for p in default_params['performance_index']]
    else:
        # 如果不是列表，转换为列表
        pi_value = max(0.7, min(1.0, float(default_params['performance_index'])))
        default_params['performance_index'] = [pi_value] * 24

    # 确保电价合理
    if lmp_da_forecast:
        # 如果电价过低，进行调整
        min_price = min(lmp_da_forecast)
        if min_price < 250:
            adjustment = 250 - min_price
            default_params['lmp_da'] = [p + adjustment for p in lmp_da_forecast]

    print(f"📊 调频市场参数创建完成:")
    print(f"   日前电价范围: {min(default_params['lmp_da']):.1f} - {max(default_params['lmp_da']):.1f} 元/MWh")
    print(f"   里程价格范围: {min(default_params['mileage_price_forecast']):.1f} - {max(default_params['mileage_price_forecast']):.1f} 元/MW")
    print(f"   性能指标范围: {min(default_params['performance_index']):.3f} - {max(default_params['performance_index']):.3f}")
    print(f"   核定成本: {default_params['verified_cost']} 元/MWh")

    return default_params

def create_cost_params(battery_params, user_params=None):
    """
    创建成本参数 - 优化以提高经济性

    Args:
        battery_params: 电池技术参数
        user_params: 用户自定义参数
    """
    # 基于电池参数计算默认成本参数
    battery_cost_per_kwh = 1200  # 元/kWh，降低电池成本
    design_life_cycles = 10000  # 增加设计寿命

    default_params = {
        'verified_cost': 200,  # 核定成本 元/MWh，降低
        'degradation_rate': 0.3,  # 退化成本率 元/MW/h，大幅降低
        'efficiency_loss_rate': 0.015,  # 效率损失率，降低
        'om_cost_rate': 0.2,  # 运维成本率 元/MW/h，降低
        'alpha_freq': 0.12,  # 调频活动系数，降低
        'ramp_rate_limit': 0.4,  # 爬坡率限制，放宽
        'min_profit_rate': 0.02,  # 最小利润率，降低要求
        'battery_initial_cost': battery_cost_per_kwh * battery_params['E_rated'] * 1000,  # 总电池成本
        'design_cycle_life': design_life_cycles
    }

    # 应用用户自定义参数
    if user_params:
        default_params.update(user_params)

    print(f"📊 成本参数创建完成:")
    print(f"   核定成本: {default_params['verified_cost']} 元/MWh")
    print(f"   调频活动系数: {default_params['alpha_freq']}")
    print(f"   退化成本率: {default_params['degradation_rate']} 元/MW/h")

    return default_params

def validate_frequency_params(frequency_params, cost_params):
    """
    验证调频市场参数的有效性

    Args:
        frequency_params: 调频市场参数
        cost_params: 成本参数
    """
    errors = []
    warnings = []

    # 检查必要参数
    required_freq_params = ['lmp_da', 'mileage_distance', 'performance_index', 'mileage_price_forecast']
    for param in required_freq_params:
        if param not in frequency_params:
            errors.append(f"缺少调频市场参数: {param}")
        elif isinstance(frequency_params[param], list) and len(frequency_params[param]) != 24:
            errors.append(f"调频市场参数 {param} 必须包含24个小时的数据")

    required_cost_params = ['verified_cost', 'degradation_rate', 'alpha_freq']
    for param in required_cost_params:
        if param not in cost_params:
            errors.append(f"缺少成本参数: {param}")

    # 检查参数范围
    if 'performance_index' in frequency_params:
        if isinstance(frequency_params['performance_index'], list):
            for i, pi in enumerate(frequency_params['performance_index']):
                if not (0.5 <= pi <= 1.0):
                    warnings.append(f"第{i+1}小时的性能指标 {pi:.3f} 可能超出合理范围 [0.5, 1.0]")
        else:
            pi = frequency_params['performance_index']
            if not (0.5 <= pi <= 1.0):
                warnings.append(f"性能指标 {pi:.3f} 可能超出合理范围 [0.5, 1.0]")

    if 'alpha_freq' in cost_params:
        if not (0.05 <= cost_params['alpha_freq'] <= 0.3):
            warnings.append(f"调频活动系数 {cost_params['alpha_freq']} 可能超出合理范围 [0.05, 0.3]")

    # 检查经济性参数 - 放宽要求
    if 'lmp_da' in frequency_params and 'verified_cost' in cost_params:
        profitable_hours = sum(1 for lmp in frequency_params['lmp_da'] if lmp > cost_params['verified_cost'])
        if profitable_hours < 8:  # 降低要求
            warnings.append(f"只有 {profitable_hours} 小时的日前电价高于核定成本，可能影响调频市场收益")

    # 检查里程补偿潜力
    if 'mileage_price_forecast' in frequency_params:
        avg_mileage_price = np.mean(frequency_params['mileage_price_forecast'])
        if avg_mileage_price < 15:
            warnings.append(f"平均里程价格 {avg_mileage_price:.1f} 元/MW 较低，可能影响调频收益")

    # 输出验证结果
    if errors:
        raise ValueError("参数验证失败:\n" + "\n".join(errors))

    if warnings:
        print("📋 参数验证警告:")
        for warning in warnings:
            print(f"  ⚠️  {warning}")
    else:
        print("✅ 参数验证通过")

    return True

def export_frequency_data_template(save_path="data/frequency_data_template.xlsx"):
    """
    导出调频数据模板文件
    """
    # 创建模板数据
    template_data = {
        '调频市场参数': pd.DataFrame({
            '小时': list(range(1, 25)),
            '日前电价(元/MWh)': [350 + 150 * np.sin(2 * np.pi * t / 24) for t in range(24)],
            '调频里程(MW)': [60 + 30 * np.sin(2 * np.pi * t / 24) for t in range(24)],
            '性能指标': [0.85 + 0.05 * np.sin(2 * np.pi * t / 24) for t in range(24)],
            '里程价格预测(元/MW)': [30 + 15 * np.sin(2 * np.pi * t / 24) for t in range(24)]
        }),
        '成本参数': pd.DataFrame({
            '参数名称': ['核定成本', '退化成本率', '效率损失率', '运维成本率', '调频活动系数', '爬坡率限制', '最小利润率'],
            '参数值': [200, 0.3, 0.015, 0.2, 0.12, 0.4, 0.02],
            '单位': ['元/MWh', '元/MW/h', '比例', '元/MW/h', '比例', '比例', '比例'],
            '说明': ['储能电站核定成本', '电池退化成本', '调频效率损失', '运维成本增量', '调频活动强度', '容量变化限制', '最小收益要求']
        })
    }

    # 保存到Excel文件
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    with pd.ExcelWriter(save_path, engine='openpyxl') as writer:
        for sheet_name, df in template_data.items():
            df.to_excel(writer, sheet_name=sheet_name, index=False)

    print(f"调频数据模板已保存到: {save_path}")
    return save_path

def calculate_economic_feasibility(frequency_params, cost_params, battery_params):
    """
    计算调频市场经济可行性
    """
    print("\n📊 调频市场经济可行性分析:")

    total_capacity_revenue = 0
    total_mileage_revenue = 0
    total_cost = 0

    for t in range(24):
        # 假设申报1MW容量
        test_capacity = 1.0

        # 容量补偿
        lmp_da = frequency_params['lmp_da'][t]
        verified_cost = cost_params['verified_cost']
        capacity_rev = test_capacity * max(0, lmp_da - verified_cost)

        # 里程补偿 - 处理性能指标可能是单个值的情况
        if isinstance(frequency_params['performance_index'], list):
            performance_index = frequency_params['performance_index'][t]
        else:
            performance_index = frequency_params['performance_index']

        mileage_rev = (test_capacity *
                      frequency_params['mileage_price_forecast'][t] *
                      performance_index * 0.1)

        # 成本
        cost = test_capacity * (cost_params['degradation_rate'] * cost_params['alpha_freq'] +
                               cost_params['om_cost_rate'])

        total_capacity_revenue += capacity_rev
        total_mileage_revenue += mileage_rev
        total_cost += cost

    total_revenue = total_capacity_revenue + total_mileage_revenue
    net_profit = total_revenue - total_cost

    print(f"   单位容量(1MW)日收益分析:")
    print(f"   容量补偿收益: {total_capacity_revenue:.2f} 元")
    print(f"   里程补偿收益: {total_mileage_revenue:.2f} 元")
    print(f"   总收益: {total_revenue:.2f} 元")
    print(f"   总成本: {total_cost:.2f} 元")
    print(f"   净利润: {net_profit:.2f} 元")
    print(f"   利润率: {net_profit/total_revenue*100 if total_revenue > 0 else 0:.1f}%")

    if net_profit > 0:
        print("   ✅ 调频市场参与具有经济可行性")
    else:
        print("   ⚠️ 调频市场参与经济性较差，建议调整参数")

    return {
        'feasible': net_profit > 0,
        'net_profit_per_mw': net_profit,
        'profit_margin': net_profit/total_revenue if total_revenue > 0 else 0
    }

if __name__ == "__main__":
    # 测试代码
    print("生成调频市场测试数据...")
    
    # 生成历史数据
    demand_df = generate_frequency_demand_history(days=30)
    price_df = generate_frequency_price_history(demand_df)
    
    print(f"生成了 {len(demand_df)} 条调频需求记录")
    print(f"生成了 {len(price_df)} 条调频价格记录")
    
    # 导出模板
    export_frequency_data_template()
    
    print("调频数据处理工具测试完成")