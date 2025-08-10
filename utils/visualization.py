import plotly.graph_objs as go
import plotly.subplots as sp
import pyomo.environ as pyo
import numpy as np


def generate_comprehensive_visualization(model, price_forecast, battery_params):
    # 充放电功率
    charge_power = [pyo.value(model.P_charge[t]) for t in range(len(price_forecast))]
    discharge_power = [pyo.value(model.P_discharge[t]) for t in range(len(price_forecast))]

    # 计算净功率（放电为正，充电为负）
    net_power = [dp - cp for dp, cp in zip(discharge_power, charge_power)]

    # SOC状态
    soc = [pyo.value(model.E[t]) / battery_params['E_rated'] for t in range(len(price_forecast))]

    # 创建时间标签（每小时显示一次）
    time_labels = [f"{h // 4:02d}:00" if h % 4 == 0 else '' for h in range(len(price_forecast))]

    # 创建多轴图表
    fig = sp.make_subplots(
        rows=3, cols=1,
        subplot_titles=('充放电功率', '电价', '荷电状态'),
        shared_xaxes=True,
        vertical_spacing=0.1
    )

    # 充放电功率曲线
    fig.add_trace(
        go.Bar(x=list(range(len(price_forecast))),
               y=charge_power,
               name='充电功率',
               marker_color='blue',
               opacity=0.6),
        row=1, col=1
    )
    fig.add_trace(
        go.Bar(x=list(range(len(price_forecast))),
               y=discharge_power,
               name='放电功率',
               marker_color='red',
               opacity=0.6),
        row=1, col=1
    )

    # 电价曲线
    fig.add_trace(
        go.Scatter(x=list(range(len(price_forecast))),
                   y=price_forecast,
                   mode='lines',
                   name='电价',
                   line=dict(color='green')),
        row=2, col=1
    )

    # SOC曲线
    fig.add_trace(
        go.Scatter(x=list(range(len(price_forecast))),
                   y=soc,
                   mode='lines',
                   name='荷电状态',
                   line=dict(color='purple')),
        row=3, col=1
    )

    # 更新布局
    fig.update_layout(height=800, title_text="液流电池储能电站日前市场优化分析")

    # 更新x轴
    for row in [1, 2, 3]:
        fig.update_xaxes(
            title_text="时间步",
            tickmode='array',
            tickvals=list(range(0, len(price_forecast), 4)),  # 每4个时间步显示一个刻度
            ticktext=time_labels[::4],  # 使用对应的时间标签
            row=row,
            col=1
        )

    # 更新y轴标签
    fig.update_yaxes(title_text="功率 (MW)", row=1, col=1)
    fig.update_yaxes(title_text="电价 (元/MWh)", row=2, col=1)
    fig.update_yaxes(title_text="荷电状态 (SOC)", row=3, col=1)

    return fig