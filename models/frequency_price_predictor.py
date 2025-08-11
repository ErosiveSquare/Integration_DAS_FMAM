"""
调频里程价格预测模型
基于历史调频需求数据预测未来24小时的调频里程价格
"""

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.ensemble import RandomForestRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import r2_score, mean_absolute_error
import warnings
warnings.filterwarnings('ignore')

class FrequencyPricePredictor:
    def __init__(self, price_upper_limit=50.0, price_min_unit=0.1):
        """
        初始化调频价格预测器

        Args:
            price_upper_limit: 里程报价上限 (元/MW)
            price_min_unit: 价格最小单位 (元/MW)
        """
        self.price_upper_limit = price_upper_limit
        self.price_min_unit = price_min_unit
        self.model = None
        self.scaler = StandardScaler()
        self.is_trained = False

    def generate_synthetic_data(self, days=90):
        """
        生成合成的历史调频数据用于训练
        """
        np.random.seed(42)
        hours = days * 24

        # 生成时间特征
        time_data = []
        for day in range(days):
            for hour in range(24):
                time_data.append({
                    'hour': hour,
                    'day_of_week': day % 7,
                    'is_weekend': 1 if day % 7 >= 5 else 0,
                    'is_peak': 1 if 8 <= hour <= 22 else 0
                })

        df = pd.DataFrame(time_data)

        # 生成调频需求特征
        base_demand = 100 + 50 * np.sin(2 * np.pi * df['hour'] / 24)  # 日内周期
        weekend_factor = 0.8 * df['is_weekend'] + 1.0 * (1 - df['is_weekend'])
        peak_factor = 1.3 * df['is_peak'] + 0.9 * (1 - df['is_peak'])

        df['frequency_demand'] = base_demand * weekend_factor * peak_factor + np.random.normal(0, 10, hours)
        df['system_load'] = 20000 + 5000 * np.sin(2 * np.pi * df['hour'] / 24) + np.random.normal(0, 500, hours)
        df['renewable_penetration'] = 0.2 + 0.1 * np.sin(2 * np.pi * df['hour'] / 24) + np.random.normal(0, 0.05, hours)

        # 生成调频里程价格（目标变量）
        price_base = 15 + 10 * (df['frequency_demand'] - df['frequency_demand'].min()) / (df['frequency_demand'].max() - df['frequency_demand'].min())
        price_volatility = 3 * df['renewable_penetration'] + 2 * df['is_peak']

        df['frequency_price'] = price_base + price_volatility + np.random.normal(0, 2, hours)
        df['frequency_price'] = np.clip(df['frequency_price'], 5, self.price_upper_limit)

        # 应用价格最小单位约束
        df['frequency_price'] = np.round(df['frequency_price'] / self.price_min_unit) * self.price_min_unit

        return df

    def prepare_features(self, df):
        """
        准备特征矩阵
        """
        feature_cols = ['hour', 'day_of_week', 'is_weekend', 'is_peak',
                       'frequency_demand', 'system_load', 'renewable_penetration']
        return df[feature_cols].values

    def train_models(self, df):
        """
        训练多个预测模型并选择最优模型
        """
        X = self.prepare_features(df)
        y = df['frequency_price'].values

        # 数据标准化
        X_scaled = self.scaler.fit_transform(X)

        # 训练多个模型
        models = {
            'linear_regression': LinearRegression(),
            'random_forest': RandomForestRegressor(n_estimators=100, random_state=42)
        }

        best_score = -np.inf
        best_model_name = None

        results = {}

        for name, model in models.items():
            model.fit(X_scaled, y)
            y_pred = model.predict(X_scaled)

            # 应用约束
            y_pred = np.clip(y_pred, 0, self.price_upper_limit)
            y_pred = np.round(y_pred / self.price_min_unit) * self.price_min_unit

            r2 = r2_score(y, y_pred)
            mae = mean_absolute_error(y, y_pred)

            results[name] = {
                'model': model,
                'r2_score': r2,
                'mae': mae,
                'predictions': y_pred
            }

            if r2 > best_score:
                best_score = r2
                best_model_name = name

        self.model = results[best_model_name]['model']
        self.is_trained = True

        return results, best_model_name

    def predict_24h_prices(self, start_hour=0, system_load_forecast=None, renewable_forecast=None):
        """
        预测未来24小时的调频里程价格

        Args:
            start_hour: 起始小时
            system_load_forecast: 系统负荷预测
            renewable_forecast: 可再生能源渗透率预测

        Returns:
            24小时价格预测数组
        """
        if not self.is_trained:
            # 如果模型未训练，使用合成数据训练
            synthetic_data = self.generate_synthetic_data()
            self.train_models(synthetic_data)

        # 生成未来24小时的特征
        future_features = []
        for h in range(24):
            hour = (start_hour + h) % 24
            day_of_week = 1  # 假设为工作日
            is_weekend = 0
            is_peak = 1 if 8 <= hour <= 22 else 0

            # 估算调频需求
            freq_demand = 100 + 50 * np.sin(2 * np.pi * hour / 24)

            # 使用提供的预测或默认值
            if system_load_forecast is not None:
                sys_load = system_load_forecast[h] if h < len(system_load_forecast) else 22000
            else:
                sys_load = 20000 + 5000 * np.sin(2 * np.pi * hour / 24)

            if renewable_forecast is not None:
                renewable_pen = renewable_forecast[h] if h < len(renewable_forecast) else 0.25
            else:
                renewable_pen = 0.2 + 0.1 * np.sin(2 * np.pi * hour / 24)

            future_features.append([
                hour, day_of_week, is_weekend, is_peak,
                freq_demand, sys_load, renewable_pen
            ])

        X_future = np.array(future_features)
        X_future_scaled = self.scaler.transform(X_future)

        # 预测价格
        prices = self.model.predict(X_future_scaled)

        # 应用约束
        prices = np.clip(prices, 0, self.price_upper_limit)
        prices = np.round(prices / self.price_min_unit) * self.price_min_unit

        return prices

    def get_model_performance(self):
        """
        获取模型性能指标
        """
        if not self.is_trained:
            return None

        # 使用训练数据评估
        synthetic_data = self.generate_synthetic_data()
        X = self.prepare_features(synthetic_data)
        y = synthetic_data['frequency_price'].values

        X_scaled = self.scaler.transform(X)
        y_pred = self.model.predict(X_scaled)

        # 应用约束
        y_pred = np.clip(y_pred, 0, self.price_upper_limit)
        y_pred = np.round(y_pred / self.price_min_unit) * self.price_min_unit

        return {
            'r2_score': r2_score(y, y_pred),
            'mae': mean_absolute_error(y, y_pred),
            'price_range': (y_pred.min(), y_pred.max()),
            'mean_price': y_pred.mean()
        }

def create_frequency_price_predictor(price_upper_limit=50.0):
    """
    创建并训练调频价格预测器
    """
    predictor = FrequencyPricePredictor(price_upper_limit=price_upper_limit)

    # 生成训练数据并训练模型
    synthetic_data = predictor.generate_synthetic_data(days=90)
    results, best_model = predictor.train_models(synthetic_data)

    print(f"最优模型: {best_model}")
    print(f"R² 得分: {results[best_model]['r2_score']:.3f}")
    print(f"平均绝对误差: {results[best_model]['mae']:.3f}")

    return predictor

if __name__ == "__main__":
    # 测试代码
    predictor = create_frequency_price_predictor()
    prices_24h = predictor.predict_24h_prices()

    print("未来24小时调频里程价格预测:")
    for i, price in enumerate(prices_24h):
        print(f"第{i+1:2d}小时: {price:6.1f} 元/MW")