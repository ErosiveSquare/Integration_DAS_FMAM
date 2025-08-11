import os
import numpy as np
import pandas as pd


def generate_price_forecast(num_steps=96):
    """
    生成模拟的电价预测数据
    """
    # 基础电价
    base_price = 0.5

    # 时段权重（模拟用电高峰和低谷）
    hourly_weights = [
        0.6, 0.5, 0.4, 0.3,  # 0-4点
        0.4, 0.5, 0.7, 0.9,  # 4-8点
        0.8, 0.9, 1.0, 1.1,  # 8-12点
        1.2, 1.1, 1.0, 0.9,  # 12-16点
        0.8, 0.9, 1.1, 1.2,  # 16-20点
        1.0, 0.8, 0.6, 0.5  # 20-24点
    ]

    # 生成96个时段的电价
    prices = []
    for hour, weight in enumerate(hourly_weights):
        # 每小时4个时段，增加一些随机波动
        for _ in range(4):
            price = base_price * weight * (1 + np.random.normal(0, 0.1))
            prices.append(max(price, 0))  # 确保价格非负

    return prices


def save_price_forecast(prices, mode='报量不报价', filename=None):
    """
    保存电价预测数据
    """
    # 确定保存路径
    if filename is None:
        # 获取项目根目录
        project_root = os.path.abspath(os.path.join(
            os.path.dirname(__file__),
            '..',
            'data'
        ))

        # 确保data目录存在
        os.makedirs(project_root, exist_ok=True)

        filename = os.path.join(project_root, 'price_forecast.csv')

    # 创建DataFrame
    df = pd.DataFrame({
        'time_step': range(len(prices)),
        'price': prices,
        'mode': mode
    })

    # 保存CSV
    df.to_csv(filename, index=False)
    print(f"电价预测数据已保存到: {filename}")
    return filename


def load_price_forecast(filename=None):
    """
    加载电价预测数据
    """
    if filename is None:
        # 获取项目根目录下的data文件夹
        project_root = os.path.abspath(os.path.join(
            os.path.dirname(__file__),
            '..',
            'data'
        ))
        filename = os.path.join(project_root, 'price_forecast.csv')

    # 检查文件是否存在
    if not os.path.exists(filename):
        # 如果文件不存在，生成并保存
        prices = generate_price_forecast()
        save_price_forecast(prices)

    return pd.read_csv(filename)['price'].values