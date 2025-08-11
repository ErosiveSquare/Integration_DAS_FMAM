"""
100MWh储能电站优化的参数配置模块
针对大规模液流电池储能电站的参数管理和验证
"""

def get_optimized_battery_params_100mwh():
    """
    获取100MWh储能电站优化后的默认参数
    确保优质收益表现的参数配置
    """
    return {
        # 额定参数 - 针对100MWh优化
        'E_rated': 100.0,  # 100MWh大容量配置
        'P_rated': 50.0,   # 50MW高功率，2小时放电设计
        
        # 能量参数 - 优化初始状态
        'E_0': 50.0,       # 50MWh初始能量
        'E_T_target': 50.0, # 50MWh目标能量
        'initial_soc': 0.50, # 50%初始SOC
        
        # 效率参数 - 提升至先进水平
        'η_charge': 0.92,   # 92%充电效率（液流电池先进水平）
        'η_discharge': 0.92, # 92%放电效率（液流电池先进水平）
        
        # SOC参数 - 放宽运行范围提高利用率
        'SOC_min': 0.05,    # 5%最小SOC（放宽下限）
        'SOC_max': 0.95,    # 95%最大SOC（放宽上限）
        
        # 循环与退化 - 优化经济性
        'N_cycle_max': 3.0,  # 3次/日最大循环（提高利用率）
        'k': 0.03,          # 0.03退化成本系数（基于规模经济）
        
        # 运维成本 - 规模化优势
        'C_OM': 3000,       # 3000元/日运维成本（规模化降本）
        
        # 功率爬坡 - 提升响应能力
        'R_ramp': 20.0,     # 20MW/15min爬坡速率（大幅提升）
        
        # 电解液流量 - 100MWh系统参数
        'Q_flow_min': 50,   # 50L/min最小流量
        'Q_flow_max': 500,  # 500L/min最大流量
        'flow_power_ratio': 8.0  # 8.0 L/min/MW流量功率比
    }

def get_optimized_da_market_params():
    """
    获取100MWh储能电站优化的日前市场参数
    """
    return {
        # 循环寿命参数
        'N_cycle_max': 3.0,  # 放宽循环限制
        'k': 0.03,           # 降低退化成本
        
        # 经济性参数
        'C_OM': 3000,        # 降低运维成本
        'min_discharge_price': 200.0,  # 降低放电门槛
        'max_charge_price': 600.0,     # 提高充电上限
        
        # 功率约束参数
        'R_ramp': 20.0,      # 大幅提升爬坡能力
        'power_reserve_ratio': 0.02,   # 减少功率预留
        
        # 风险管理参数
        'soc_target_weight': 100.0,    # 降低SOC约束权重
        'risk_penalty': 10.0           # 降低风险惩罚
    }

def get_optimized_frequency_params():
    """
    获取100MWh储能电站优化的调频市场参数
    """
    return {
        # 市场规则参数
        'verified_cost': 150.0,        # 大幅降低核定成本
        'measured_regulation_rate': 5.0, # 提升调节能力
        'control_area_demand': 1200,    # 增加市场需求
        'num_units': 8,                 # 减少竞争对手
        'performance_index': 0.95,      # 提升性能指标
        
        # 成本模型参数
        'alpha_freq': 0.06,             # 降低调频影响
        'degradation_rate': 0.10,       # 大幅降低退化成本
        'efficiency_loss_rate': 0.008,  # 降低效率损失
        'om_cost_rate': 0.08,           # 降低运维成本
        'price_upper_limit': 65.0       # 提高价格上限
    }

def validate_100mwh_parameters(battery_params, da_config, frequency_config):
    """
    验证100MWh储能电站参数的合理性
    确保参数配置能够实现优质收益表现
    """
    warnings = []
    errors = []
    
    # 验证基本配置
    if battery_params['E_rated'] < 80.0:
        warnings.append("⚠️ 建议额定容量≥80MWh以获得规模经济效应")
    
    if battery_params['P_rated'] < 40.0:
        warnings.append("⚠️ 建议额定功率≥40MW以提高收益能力")
    
    # 验证功率容量比
    power_capacity_ratio = battery_params['P_rated'] / battery_params['E_rated']
    if power_capacity_ratio < 0.4:
        warnings.append(f"⚠️ 功率容量比偏低({power_capacity_ratio:.2f})，建议≥0.4以提高灵活性")
    elif power_capacity_ratio > 0.8:
        warnings.append(f"⚠️ 功率容量比偏高({power_capacity_ratio:.2f})，可能增加投资成本")
    
    # 验证效率参数
    if battery_params['η_charge'] < 0.90 or battery_params['η_discharge'] < 0.90:
        warnings.append("⚠️ 建议充放电效率≥90%以降低损耗，提高收益")
    
    # 验证SOC运行范围
    soc_range = battery_params['SOC_max'] - battery_params['SOC_min']
    if soc_range < 0.8:
        warnings.append(f"⚠️ SOC运行范围过窄({soc_range:.1%})，建议≥80%以提高利用率")
    
    # 验证经济参数
    if da_config['k'] > 0.05:
        warnings.append(f"⚠️ 退化成本系数过高({da_config['k']:.3f})，建议≤0.05")
    
    if da_config['C_OM'] > 5000:
        warnings.append(f"⚠️ 运维成本过高({da_config['C_OM']}元/日)，建议≤5000元/日")
    
    # 验证调频参数
    if frequency_config:
        if frequency_config['verified_cost'] > 180:
            warnings.append(f"⚠️ 核定成本过高({frequency_config['verified_cost']}元/MWh)，建议≤180元/MWh")
        
        if frequency_config['alpha_freq'] > 0.08:
            warnings.append(f"⚠️ 调频活动系数过高({frequency_config['alpha_freq']:.3f})，建议≤0.08")
        
        if frequency_config['degradation_rate'] > 0.15:
            warnings.append(f"⚠️ 调频退化成本率过高({frequency_config['degradation_rate']:.2f})，建议≤0.15元/MW/h")
    
    # 验证收益潜力
    estimated_daily_profit = estimate_daily_profit(battery_params, da_config, frequency_config)
    if estimated_daily_profit < 200000:
        warnings.append(f"⚠️ 预估日收益偏低({estimated_daily_profit:.0f}元)，建议优化参数配置")
    
    return warnings, errors

def estimate_daily_profit(battery_params, da_config, frequency_config):
    """
    估算100MWh储能电站的日收益
    基于参数配置进行粗略估算
    """
    # 日前市场收益估算
    # 假设峰谷价差500元/MWh，2次循环，90%效率
    peak_valley_diff = 500  # 元/MWh
    cycles_per_day = min(da_config['N_cycle_max'], 2.0)
    efficiency = battery_params['η_charge'] * battery_params['η_discharge']
    
    da_revenue = (battery_params['E_rated'] * cycles_per_day * 
                  peak_valley_diff * efficiency * 0.8)  # 80%利用率
    
    da_cost = (battery_params['E_rated'] * cycles_per_day * 
               da_config['k'] * 1000 + da_config['C_OM'])  # 退化成本+运维成本
    
    da_profit = da_revenue - da_cost
    
    # 调频市场收益估算
    freq_profit = 0
    if frequency_config:
        # 假设平均申报5MW，12小时参与，平均价格40元/MW
        avg_capacity = min(5.0, battery_params['P_rated'] * 0.2)
        participation_hours = 12
        avg_price = 40  # 元/MW
        
        freq_revenue = avg_capacity * participation_hours * avg_price
        freq_cost = (avg_capacity * participation_hours * 
                    (frequency_config['degradation_rate'] * frequency_config['alpha_freq'] + 
                     frequency_config['om_cost_rate']))
        
        freq_profit = freq_revenue - freq_cost
    
    total_profit = da_profit + freq_profit
    return max(0, total_profit)

def get_parameter_ranges():
    """
    获取100MWh储能电站参数的推荐范围
    """
    return {
        'battery_params': {
            'E_rated': {'min': 80, 'max': 120, 'default': 100, 'step': 5},
            'P_rated': {'min': 25, 'max': 75, 'default': 50, 'step': 5},
            'η_charge': {'min': 0.80, 'max': 0.98, 'default': 0.92, 'step': 0.01},
            'η_discharge': {'min': 0.80, 'max': 0.98, 'default': 0.92, 'step': 0.01},
            'SOC_min': {'min': 0.02, 'max': 0.15, 'default': 0.05, 'step': 0.01},
            'SOC_max': {'min': 0.85, 'max': 0.98, 'default': 0.95, 'step': 0.01},
            'initial_soc': {'min': 0.3, 'max': 0.7, 'default': 0.5, 'step': 0.05},
        },
        'da_market_params': {
            'N_cycle_max': {'min': 1.0, 'max': 5.0, 'default': 3.0, 'step': 0.1},
            'k': {'min': 0.01, 'max': 0.10, 'default': 0.03, 'step': 0.005},
            'C_OM': {'min': 1000, 'max': 8000, 'default': 3000, 'step': 200},
            'R_ramp': {'min': 5.0, 'max': 30.0, 'default': 20.0, 'step': 1.0},
            'power_reserve_ratio': {'min': 0.01, 'max': 0.10, 'default': 0.02, 'step': 0.005},
        },
        'frequency_params': {
            'verified_cost': {'min': 100.0, 'max': 250.0, 'default': 150.0, 'step': 5.0},
            'measured_regulation_rate': {'min': 2.0, 'max': 8.0, 'default': 5.0, 'step': 0.2},
            'control_area_demand': {'min': 600, 'max': 1500, 'default': 1200, 'step': 50},
            'performance_index': {'min': 0.80, 'max': 0.98, 'default': 0.95, 'step': 0.01},
            'alpha_freq': {'min': 0.04, 'max': 0.15, 'default': 0.06, 'step': 0.005},
            'degradation_rate': {'min': 0.05, 'max': 0.30, 'default': 0.10, 'step': 0.01},
        }
    }

def generate_parameter_suggestions(current_profit, target_profit=300000):
    """
    基于当前收益生成参数优化建议
    """
    suggestions = []
    
    if current_profit < target_profit:
        profit_gap = target_profit - current_profit
        improvement_needed = profit_gap / target_profit
        
        if improvement_needed > 0.5:  # 需要大幅改进
            suggestions.extend([
                "🔧 提高额定功率至50MW以上，增强功率密度",
                "⚡ 提升充放电效率至92%以上，降低损耗",
                "💰 降低核定成本至150元/MWh以下，提高容量补偿",
                "📈 确保电价峰谷差≥500元/MWh，增加套利空间",
                "🔄 放宽循环次数限制至3次/日，提高利用率"
            ])
        elif improvement_needed > 0.2:  # 需要中等改进
            suggestions.extend([
                "📊 优化SOC运行范围至5%-95%，提高可用容量",
                "⚡ 提升功率爬坡速率至20MW/15min，增强响应能力",
                "💸 降低退化成本系数至0.03，减少成本负担",
                "🎯 提高调频性能指标至0.95，增加里程收益"
            ])
        else:  # 需要微调
            suggestions.extend([
                "🔧 微调功率预留比例至2%，提高功率利用率",
                "📈 优化调频活动系数至0.06，平衡收益与保护",
                "💰 适当降低运维成本，提升净利润"
            ])
    
    return suggestions

def validate_battery_params_100mwh(params):
    """
    验证100MWh储能电站电池参数
    """
    validated_params = params.copy()
    
    # 确保关键参数在合理范围内
    validated_params['E_rated'] = max(80, min(120, validated_params['E_rated']))
    validated_params['P_rated'] = max(25, min(75, validated_params['P_rated']))
    validated_params['η_charge'] = max(0.80, min(0.98, validated_params['η_charge']))
    validated_params['η_discharge'] = max(0.80, min(0.98, validated_params['η_discharge']))
    validated_params['SOC_min'] = max(0.02, min(0.15, validated_params['SOC_min']))
    validated_params['SOC_max'] = max(0.85, min(0.98, validated_params['SOC_max']))
    
    # 确保SOC范围合理
    if validated_params['SOC_max'] <= validated_params['SOC_min']:
        validated_params['SOC_max'] = validated_params['SOC_min'] + 0.8
    
    # 确保初始能量与SOC一致
    validated_params['E_0'] = validated_params['initial_soc'] * validated_params['E_rated']
    validated_params['E_T_target'] = validated_params['initial_soc'] * validated_params['E_rated']
    
    return validated_params