"""
多市场可视化工具
为多市场联合优化提供可视化功能
"""

import plotly.graph_objs as go
import plotly.subplots as sp
import numpy as np
import pandas as pd
import pyomo.environ as pyo

def generate_multi_market_visualization(da_model, frequency_results, price_forecast, battery_params):
    """
    生成多市场联合优化的综合可视化图表

    Args:
        da_model: 日前市场优化模型
        frequency_results: 调频市场优化结果
        price_forecast: 电价预测
        battery_params: 电池参数
    """
    try:
        # 提取日前市场数据（15分钟 -> 小时）
        da_charge_hourly = []
        da_discharge_hourly = []
        da_soc_hourly = []

        for h in range(24):
            try:
                # 计算小时平均值
                hour_charge = sum(pyo.value(da_model.P_charge[h*4 + i]) for i in range(4)) / 4
                hour_discharge = sum(pyo.value(da_model.P_discharge[h*4 + i]) for i in range(4)) / 4
                hour_energy = pyo.value(da_model.E[h*4])
                hour_soc = hour_energy / battery_params['E_rated']

                da_charge_hourly.append(hour_charge)
                da_discharge_hourly.append(hour_discharge)
                da_soc_hourly.append(hour_soc)
            except:
                da_charge_hourly.append(0)
                da_discharge_hourly.append(0)
                da_soc_hourly.append(0.5)

        # 提取调频市场数据 - 确保数据存在
        freq_capacity = frequency_results.get('frequency_capacity', [0]*24)
        freq_prices = frequency_results.get('mileage_price_forecast', [25]*24)

        # 确保数据长度正确
        if len(freq_capacity) != 24:
            freq_capacity = [0] * 24
        if len(freq_prices) != 24:
            freq_prices = [25] * 24

        # 创建时间标签
        time_labels = [f"{h:02d}:00" for h in range(24)]

        # 创建子图
        fig = sp.make_subplots(
            rows=4, cols=1,
            subplot_titles=(
                '日前市场功率计划',
                '调频市场容量申报',
                '调频里程价格预测',
                '储能状态(SOC)'
            ),
            shared_xaxes=True,
            vertical_spacing=0.08
        )

        # 1. 日前市场功率计划
        fig.add_trace(
            go.Bar(
                x=time_labels,
                y=[-p for p in da_charge_hourly],  # 充电显示为负值
                name='充电功率',
                marker_color='blue',
                opacity=0.7
            ),
            row=1, col=1
        )

        fig.add_trace(
            go.Bar(
                x=time_labels,
                y=da_discharge_hourly,
                name='放电功率',
                marker_color='red',
                opacity=0.7
            ),
            row=1, col=1
        )

        # 2. 调频容量申报
        fig.add_trace(
            go.Scatter(
                x=time_labels,
                y=freq_capacity,
                mode='lines+markers',
                name='调频容量',
                line=dict(color='green', width=3),
                marker=dict(size=6)
            ),
            row=2, col=1
        )

        # 3. 调频里程价格预测
        fig.add_trace(
            go.Scatter(
                x=time_labels,
                y=freq_prices,
                mode='lines+markers',
                name='里程价格',
                line=dict(color='orange', width=2),
                marker=dict(size=5),
                fill='tonexty'
            ),
            row=3, col=1
        )

        # 4. SOC状态
        fig.add_trace(
            go.Scatter(
                x=time_labels,
                y=[soc*100 for soc in da_soc_hourly],
                mode='lines',
                name='荷电状态',
                line=dict(color='purple', width=3)
            ),
            row=4, col=1
        )

        # 添加SOC限制线
        fig.add_hline(
            y=battery_params['SOC_min']*100,
            line_dash="dash",
            line_color="red",
            annotation_text="SOC下限",
            row=4, col=1
        )

        fig.add_hline(
            y=battery_params['SOC_max']*100,
            line_dash="dash",
            line_color="red",
            annotation_text="SOC上限",
            row=4, col=1
        )

        # 更新布局
        fig.update_layout(
            height=1000,
            title_text="液流电池储能电站多市场联合优化分析",
            showlegend=True
        )

        # 更新x轴
        fig.update_xaxes(title_text="时间", row=4, col=1)

        # 更新y轴
        fig.update_yaxes(title_text="功率 (MW)", row=1, col=1)
        fig.update_yaxes(title_text="容量 (MW)", row=2, col=1)
        fig.update_yaxes(title_text="价格 (元/MW)", row=3, col=1)
        fig.update_yaxes(title_text="SOC (%)", row=4, col=1)

        return fig

    except Exception as e:
        print(f"生成多市场可视化时出现错误: {e}")
        # 返回空图表
        fig = go.Figure()
        fig.add_annotation(
            text="可视化生成失败",
            xref="paper", yref="paper",
            x=0.5, y=0.5, showarrow=False
        )
        return fig

def generate_frequency_market_analysis(frequency_results):
    """
    生成调频市场专项分析图表
    """
    try:
        if not frequency_results:
            return create_empty_chart("无调频市场数据")

        solver_status = frequency_results.get('solver_status', 'unknown')

        # 即使是启发式解决方案也要显示
        if solver_status in ['error', 'failed'] and sum(frequency_results.get('frequency_capacity', [0]*24)) == 0:
            return create_empty_chart("调频市场求解失败，无法生成分析图表")

        time_labels = [f"{h:02d}:00" for h in range(24)]

        # 创建子图
        fig = sp.make_subplots(
            rows=2, cols=2,
            subplot_titles=(
                f'调频容量申报策略 ({solver_status})',
                '收益成本分析',
                '小时净收益分布',
                '累计收益趋势'
            ),
            specs=[[{"secondary_y": False}, {"secondary_y": False}],
                   [{"secondary_y": False}, {"secondary_y": False}]]
        )

        # 1. 调频容量申报策略
        freq_capacity = frequency_results.get('frequency_capacity', [0]*24)
        fig.add_trace(
            go.Scatter(
                x=time_labels,
                y=freq_capacity,
                mode='lines+markers',
                name='申报容量',
                line=dict(color='green', width=3)
            ),
            row=1, col=1
        )

        # 2. 收益成本分析
        capacity_revenues = frequency_results.get('capacity_revenues', [0]*24)
        mileage_revenues = frequency_results.get('mileage_revenues', [0]*24)
        degradation_costs = frequency_results.get('degradation_costs', [0]*24)
        efficiency_costs = frequency_results.get('efficiency_costs', [0]*24)
        om_costs = frequency_results.get('om_costs', [0]*24)

        total_costs = [d + e + o for d, e, o in zip(degradation_costs, efficiency_costs, om_costs)]

        fig.add_trace(
            go.Bar(
                x=time_labels,
                y=capacity_revenues,
                name='容量补偿',
                marker_color='lightblue'
            ),
            row=1, col=2
        )

        fig.add_trace(
            go.Bar(
                x=time_labels,
                y=mileage_revenues,
                name='里程补偿',
                marker_color='lightgreen'
            ),
            row=1, col=2
        )

        fig.add_trace(
            go.Bar(
                x=time_labels,
                y=[-c for c in total_costs],
                name='运行成本',
                marker_color='lightcoral'
            ),
            row=1, col=2
        )

        # 3. 小时净收益分布
        net_profits = [cr + mr - tc for cr, mr, tc in zip(capacity_revenues, mileage_revenues, total_costs)]

        fig.add_trace(
            go.Bar(
                x=time_labels,
                y=net_profits,
                name='净收益',
                marker_color=['green' if p >= 0 else 'red' for p in net_profits]
            ),
            row=2, col=1
        )

        # 4. 累计收益趋势
        cumulative_profit = np.cumsum(net_profits)

        fig.add_trace(
            go.Scatter(
                x=time_labels,
                y=cumulative_profit,
                mode='lines+markers',
                name='累计净收益',
                line=dict(color='darkgreen', width=3)
            ),
            row=2, col=2
        )

        # 更新布局
        fig.update_layout(
            height=800,
            title_text="调频市场专项分析",
            showlegend=True
        )

        # 更新坐标轴标签
        fig.update_yaxes(title_text="容量 (MW)", row=1, col=1)
        fig.update_yaxes(title_text="金额 (元)", row=1, col=2)
        fig.update_yaxes(title_text="净收益 (元)", row=2, col=1)
        fig.update_yaxes(title_text="累计收益 (元)", row=2, col=2)

        return fig

    except Exception as e:
        print(f"生成调频市场分析图表时出现错误: {e}")
        return create_empty_chart("调频市场分析图表生成失败")

def generate_cost_breakdown_chart(frequency_results):
    """
    生成成本分解饼图
    """
    try:
        if not frequency_results:
            return create_empty_chart("无调频成本数据")

        solver_status = frequency_results.get('solver_status', 'unknown')
        if solver_status in ['error', 'failed'] and sum(frequency_results.get('frequency_capacity', [0]*24)) == 0:
            return create_empty_chart("无调频成本数据")

        # 计算各项成本总和
        total_degradation = sum(frequency_results.get('degradation_costs', [0]*24))
        total_efficiency = sum(frequency_results.get('efficiency_costs', [0]*24))
        total_om = sum(frequency_results.get('om_costs', [0]*24))

        if total_degradation + total_efficiency + total_om == 0:
            return create_empty_chart("无调频成本产生")

        # 创建饼图
        fig = go.Figure(data=[go.Pie(
            labels=['退化成本', '效率损失成本', '运维成本'],
            values=[total_degradation, total_efficiency, total_om],
            hole=0.3,
            marker_colors=['#ff9999', '#66b3ff', '#99ff99']
        )])

        fig.update_layout(
            title_text=f"调频市场运行成本分解 ({frequency_results.get('solver_status', 'unknown')})",
            annotations=[dict(text='成本构成', x=0.5, y=0.5, font_size=16, showarrow=False)]
        )

        return fig

    except Exception as e:
        print(f"生成成本分解图表时出现错误: {e}")
        return create_empty_chart("成本分解图表生成失败")

def generate_market_comparison_chart(da_kpis, freq_kpis):
    """
    生成市场对比图表
    """
    try:
        # 创建对比数据
        markets = ['日前市场', '调频市场']
        revenues = [da_kpis.get('总放电收益', 0), freq_kpis.get('调频总收益', 0)]
        profits = [da_kpis.get('总净利润', 0), freq_kpis.get('调频净利润', 0)]

        fig = go.Figure()

        # 添加收益对比
        fig.add_trace(go.Bar(
            name='总收益',
            x=markets,
            y=revenues,
            marker_color='lightblue'
        ))

        # 添加利润对比
        fig.add_trace(go.Bar(
            name='净利润',
            x=markets,
            y=profits,
            marker_color='lightgreen'
        ))

        fig.update_layout(
            title='日前市场 vs 调频市场收益对比',
            xaxis_title='市场类型',
            yaxis_title='金额 (元)',
            barmode='group'
        )

        return fig

    except Exception as e:
        print(f"生成市场对比图表时出现错误: {e}")
        return create_empty_chart("市场对比图表生成失败")

def create_kpi_metrics_display(joint_kpis):
    """
    创建KPI指标展示数据
    """
    try:
        if not joint_kpis:
            return {
                'da_market': {},
                'frequency_market': {},
                'joint_market': {}
            }

        da_kpis = joint_kpis.get('da_market', {})
        freq_kpis = joint_kpis.get('frequency_market', {})
        joint_market_kpis = joint_kpis.get('joint_market', {})

        return {
            'da_market': {
                '💰 日前净利润': f"{da_kpis.get('总净利润', 0):.2f} 元",
                '💡 日前总收益': f"{da_kpis.get('总放电收益', 0):.2f} 元",
                '🔄 等效循环次数': f"{da_kpis.get('等效循环次数', 0):.3f} 次",
                '⚡ 总能量吞吐': f"{da_kpis.get('总能量吞吐', 0):.2f} MWh",
                '💎 平均度电利润': f"{da_kpis.get('平均度电利润', 0):.2f} 元/MWh"
            },
            'frequency_market': {
                '🎯 调频净利润': f"{freq_kpis.get('调频净利润', 0):.2f} 元",
                '📈 调频总收益': f"{freq_kpis.get('调频总收益', 0):.2f} 元",
                '⚙️ 调频总容量': f"{freq_kpis.get('调频总容量', 0):.2f} MW",
                '💸 调频总成本': f"{freq_kpis.get('调频总成本', 0):.2f} 元",
                '📊 调频利润率': f"{freq_kpis.get('调频利润率', 0)*100:.1f} %"
            },
            'joint_market': {
                '🏆 联合净利润': f"{joint_market_kpis.get('联合净利润', 0):.2f} 元",
                '💰 联合总收益': f"{joint_market_kpis.get('联合总收益', 0):.2f} 元",
                '📈 联合利润率': f"{joint_market_kpis.get('联合利润率', 0)*100:.1f} %",
                '🎯 调频收益占比': f"{joint_market_kpis.get('调频收益占比', 0)*100:.1f} %"
            }
        }

    except Exception as e:
        print(f"创建KPI展示数据时出现错误: {e}")
        return {
            'da_market': {},
            'frequency_market': {},
            'joint_market': {}
        }

def create_empty_chart(message):
    """
    创建空图表显示错误信息
    """
    fig = go.Figure()
    fig.add_annotation(
        text=message,
        xref="paper", yref="paper",
        x=0.5, y=0.5, showarrow=False,
        font=dict(size=16)
    )
    fig.update_layout(
        xaxis=dict(showgrid=False, showticklabels=False, zeroline=False),
        yaxis=dict(showgrid=False, showticklabels=False, zeroline=False),
        plot_bgcolor='white'
    )
    return fig

def generate_sensitivity_analysis_chart(base_results, sensitivity_params):
    """
    生成敏感性分析图表
    """
    # 这里可以实现参数敏感性分析
    # 例如：调频价格上限、性能指标、成本参数等对收益的影响
    pass

if __name__ == "__main__":
    print("多市场可视化工具模块加载完成")