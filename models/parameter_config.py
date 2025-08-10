def get_default_battery_params():
    """
    提供默认的电池技术参数，完全对应数学模型
    """
    return {
        # 额定参数
        'E_rated': 50,  # 额定容量 (MWh)
        'P_rated': 10,  # 额定功率 (MW)

        # 初始和目标能量
        'E_0': 25,  # 初始能量 (MWh)
        'E_T_target': 25,  # 目标结束能量 (MWh)

        # 充放电效率
        'η_charge': 0.9,  # 充电效率
        'η_discharge': 0.9,  # 放电效率

        # SOC安全范围
        'SOC_min': 0.2,  # 最小荷电状态
        'SOC_max': 0.8,  # 最大荷电状态

        # 循环和退化
        'N_cycle_max': 1,  # 最大等效循环次数
        'k': 0.05,  # 度电退化成本系数

        # 运维成本
        'C_OM': 1000,  # 固定运维成本

        # 功率爬坡速率
        'R_ramp': 2,  # 功率爬坡速率 (MW/15min)

        # 电解液流量范围
        'Q_flow_min': 0,
        'Q_flow_max': 100,

        # 初始荷电状态
        'initial_soc': 0.5
    }


def validate_battery_params(params):
    """
    验证电池参数的有效性
    """
    required_keys = [
        'E_rated', 'P_rated', 'E_0', 'E_T_target',
        'η_charge', 'η_discharge',
        'SOC_min', 'SOC_max',
        'N_cycle_max', 'k', 'C_OM',
        'R_ramp', 'Q_flow_min', 'Q_flow_max',
        'initial_soc'
    ]

    for key in required_keys:
        if key not in params:
            raise ValueError(f"缺少必要参数: {key}")

    # 添加额外的参数校验逻辑
    assert params['E_rated'] > 0, "额定容量必须为正"
    assert params['P_rated'] > 0, "额定功率必须为正"
    assert 0 <= params['SOC_min'] < params['SOC_max'] <= 1, "SOC范围设置不合理"
    assert 0 <= params['η_charge'] <= 1, "充电效率必须在0-1之间"
    assert 0 <= params['η_discharge'] <= 1, "放电效率必须在0-1之间"

    return params