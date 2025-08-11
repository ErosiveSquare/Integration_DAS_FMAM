# OpmImprove_Integration_DAS_FMAM/app/pages/1_🗄️_电站档案.py

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import sys
import os
from datetime import datetime

# 确保可以导入项目根目录下的模块
try:
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.abspath(os.path.join(current_dir, '..', '..'))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    from utils.database import init_db, load_station_profile, save_station_profile, load_decision_records

except ImportError as e:
    st.error(f"无法导入数据库模块: {e}")
    st.error("请确保您的项目结构正确：'app' 和 'utils' 文件夹应位于同一项目根目录下。")
    st.stop()


# --- 关键修复：添加一个包装函数并禁用缓存 ---
# 我们不直接修改 utils.database 里的函数，而是在页面上包装它
# ttl=1 表示缓存最多保留1秒，实际上等于每次都重新加载
@st.cache_data(ttl=1)
def get_latest_decision_records():
    """
    一个带缓存控制的包装函数，用于获取最新的决策记录。
    每次访问页面时，由于缓存已过期，它将强制重新执行 load_decision_records()。
    """
    print("DEBUG: Forcing reload of decision records from database.")
    return load_decision_records()


def display_profile_form(profile):
    """显示用于编辑电站档案的表单"""
    with st.form(key="profile_form"):
        st.subheader("📝 编辑电站档案")
        edited_profile = {}
        col1, col2 = st.columns(2)
        with col1:
            edited_profile['station_name'] = st.text_input("电站名称", value=profile.get('station_name'))
            edited_profile['e_rated'] = st.number_input("额定容量 (MWh)", min_value=1.0,
                                                        value=float(profile.get('e_rated', 100.0)), format="%.1f")

        with col2:
            edited_profile['location'] = st.text_input("地理位置", value=profile.get('location'))
            edited_profile['p_rated'] = st.number_input("额定功率 (MW)", min_value=1.0,
                                                        value=float(profile.get('p_rated', 25.0)), format="%.1f")

        try:
            default_date = datetime.strptime(profile.get('commission_date'), '%Y-%m-%d').date()
        except (ValueError, TypeError):
            default_date = datetime.now().date()

        edited_profile['commission_date'] = st.date_input("投运日期", value=default_date).strftime('%Y-%m-%d')

        submitted = st.form_submit_button("💾 保存档案", use_container_width=True, type="primary")
        if submitted:
            save_station_profile(edited_profile)
            st.success("电站档案已成功更新！")
            st.rerun()


def main():
    st.set_page_config(page_title="电站档案与历史决策", layout="wide")

    init_db()

    st.title("🗄️ 电站档案与历史决策中心")
    st.markdown("---")

    # --- 电站基本档案 ---
    with st.container(border=True):
        st.header("🏢 电站基本档案")
        profile = load_station_profile()

        if profile:
            col1, col2, col3 = st.columns(3)
            col1.metric("电站名称", profile['station_name'])
            col2.metric("地理位置", profile.get('location', '未设置'))
            col3.metric("投运日期", profile.get('commission_date', '未设置'))
            st.markdown("---")
            col1, col2 = st.columns(2)
            col1.metric("⚡ 额定容量 (E_rated)", f"{profile['e_rated']:.1f} MWh")
            col2.metric("⚡ 额定功率 (P_rated)", f"{profile['p_rated']:.1f} MW")

            with st.expander("编辑电站档案"):
                display_profile_form(profile)
        else:
            st.warning("未能加载电站档案。如果这是第一次运行，这是正常的。请在主应用页面运行一次或在此处刷新。")

    st.markdown("\n\n")

    # --- 历史决策记录 ---
    with st.container(border=True):
        st.header("📈 历史决策记录分析")

        # --- 关键修复：调用我们新的包装函数 ---
        records_df = get_latest_decision_records()

        if records_df.empty:
            st.info("尚无历史决策记录。请在主应用页面运行一次优化。")
        else:
            st.subheader("📊 历史性能概览")
            # --- 增强：计算更丰富的KPI ---
            total_runs = len(records_df)
            total_profit = records_df['net_profit'].sum()
            total_da_profit = records_df['da_profit'].sum()
            total_fm_profit = records_df['fm_profit'].sum()
            total_cycles = records_df['equivalent_cycles'].sum()
            avg_profit_per_run = records_df['net_profit'].mean()

            # KPI显示区域
            kpi_cols1 = st.columns(4)
            kpi_cols1[0].metric("历史总净利润", f"¥ {total_profit:,.2f}")
            kpi_cols1[1].metric("日前市场总利润", f"¥ {total_da_profit:,.2f}")
            kpi_cols1[2].metric("调频市场总利润", f"¥ {total_fm_profit:,.2f}")
            kpi_cols1[3].metric("累计等效循环", f"{total_cycles:.2f} 次")

            st.subheader("💹 决策趋势与收益分析")
            chart_col1, chart_col2 = st.columns(2)

            with chart_col1:
                # --- 增强：利润来源分布饼图 ---
                profit_sources = {'日前市场收益': total_da_profit, '调频市场收益': total_fm_profit}
                if total_da_profit > 0 or total_fm_profit > 0:
                    fig_pie = go.Figure(data=[go.Pie(
                        labels=list(profit_sources.keys()),
                        values=list(profit_sources.values()),
                        hole=.4,
                        textinfo='percent+label'
                    )])
                    fig_pie.update_layout(title="历史总利润来源分布", template="plotly_white",
                                          legend_title_text='收益来源')
                    st.plotly_chart(fig_pie, use_container_width=True)
                else:
                    st.info("尚无市场收益数据用于生成饼图。")

            with chart_col2:
                # --- 增强：市场模式与决策模式的堆叠柱状图 ---
                mode_breakdown = records_df.groupby(['market_mode', 'decision_mode']).size().unstack(fill_value=0)
                fig_stacked_bar = go.Figure()
                for dec_mode in mode_breakdown.columns:
                    fig_stacked_bar.add_trace(go.Bar(
                        name=dec_mode,
                        x=mode_breakdown.index,
                        y=mode_breakdown[dec_mode]
                    ))
                fig_stacked_bar.update_layout(
                    barmode='stack',
                    title="不同市场模式下的决策策略分布",
                    xaxis_title="市场参与模式",
                    yaxis_title="运行次数",
                    template="plotly_white",
                    legend_title_text='决策模式'
                )
                st.plotly_chart(fig_stacked_bar, use_container_width=True)

            st.subheader("💰 每次运行净利润趋势")
            fig_profit_trend = go.Figure()
            fig_profit_trend.add_trace(
                go.Scatter(x=pd.to_datetime(records_df['run_timestamp']), y=records_df['net_profit'],
                           mode='lines+markers', name='净利润',
                           hovertext=records_df['market_mode'] + ' | ' + records_df['decision_mode'])
            )
            fig_profit_trend.update_layout(xaxis_title="运行时间", yaxis_title="净利润 (元)",
                                           template="plotly_white")
            st.plotly_chart(fig_profit_trend, use_container_width=True)

            with st.expander("👁️ 查看详细历史数据"):
                display_columns = [
                    'id', 'run_timestamp', 'station_name', 'market_mode', 'decision_mode',
                    'net_profit', 'da_profit', 'fm_profit', 'total_throughput', 'equivalent_cycles'
                ]
                existing_columns = [col for col in display_columns if col in records_df.columns]
                st.dataframe(records_df[existing_columns].style.format({
                    'net_profit': '¥ {:,.2f}',
                    'da_profit': '¥ {:,.2f}',
                    'fm_profit': '¥ {:,.2f}',
                    'total_throughput': '{:.2f} MWh',
                    'equivalent_cycles': '{:.3f} 次'
                }), use_container_width=True)


if __name__ == "__main__":
    main()

