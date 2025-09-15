#!/usr/bin/env python3
"""
离线XGBoost模型训练和验证脚本
使用本地下载的数据进行模型训练，避免网络连接问题
"""

import pandas as pd
import numpy as np
from pathlib import Path
import json
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

# 机器学习相关库
from sklearn.model_selection import train_test_split, TimeSeriesSplit
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score
from sklearn.preprocessing import StandardScaler
import xgboost as xgb

# 绘图库
import matplotlib.pyplot as plt
import seaborn as sns
plt.rcParams['font.sans-serif'] = ['SimHei']  # 支持中文显示
plt.rcParams['axes.unicode_minus'] = False

class OfflineXGBoostTrainer:
    def __init__(self, data_dir="user_data/data/okx"):
        self.data_dir = Path(data_dir)
        self.pairs = ['TRX_USDT', 'BTC_USDT', 'ETH_USDT']
        self.timeframes = ['1m', '1h']
        self.models = {}
        self.scalers = {}
        self.results = {}
        
    def load_data(self, pair, timeframe):
        """加载指定交易对和时间框架的数据"""
        file_path = self.data_dir / f"{pair}-{timeframe}.feather"
        if not file_path.exists():
            print(f"警告: 文件 {file_path} 不存在")
            return None
            
        try:
            df = pd.read_feather(file_path)
            df['date'] = pd.to_datetime(df['date'])
            df.set_index('date', inplace=True)
            print(f"成功加载 {pair} {timeframe} 数据: {len(df)} 条记录")
            return df
        except Exception as e:
            print(f"加载数据失败 {file_path}: {e}")
            return None
    
    def calculate_technical_indicators(self, df):
        """计算技术指标"""
        # 基础价格特征
        df['price_change'] = df['close'].pct_change()
        df['high_low_ratio'] = df['high'] / df['low']
        df['close_open_ratio'] = df['close'] / df['open']
        
        # 移动平均线
        for period in [5, 10, 20, 50]:
            df[f'sma_{period}'] = df['close'].rolling(window=period).mean()
            df[f'price_sma_{period}_ratio'] = df['close'] / df[f'sma_{period}']
        
        # 指数移动平均线
        for period in [12, 26]:
            df[f'ema_{period}'] = df['close'].ewm(span=period).mean()
        
        # MACD
        df['macd'] = df['ema_12'] - df['ema_26']
        df['macd_signal'] = df['macd'].ewm(span=9).mean()
        df['macd_histogram'] = df['macd'] - df['macd_signal']
        
        # RSI
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))
        
        # 布林带
        df['bb_middle'] = df['close'].rolling(window=20).mean()
        bb_std = df['close'].rolling(window=20).std()
        df['bb_upper'] = df['bb_middle'] + (bb_std * 2)
        df['bb_lower'] = df['bb_middle'] - (bb_std * 2)
        df['bb_position'] = (df['close'] - df['bb_lower']) / (df['bb_upper'] - df['bb_lower'])
        
        # 成交量特征
        df['volume_sma_10'] = df['volume'].rolling(window=10).mean()
        df['volume_ratio'] = df['volume'] / df['volume_sma_10']
        
        # 波动率
        df['volatility_10'] = df['price_change'].rolling(window=10).std()
        df['volatility_20'] = df['price_change'].rolling(window=20).std()
        
        return df
    
    def create_target_labels(self, df, forward_periods=24):
        """创建目标标签 - 预测未来价格变化"""
        # 未来收益率
        df['future_return'] = df['close'].shift(-forward_periods) / df['close'] - 1
        
        # 分类标签 (上涨/下跌)
        df['target_direction'] = (df['future_return'] > 0).astype(int)
        
        # 回归标签 (收益率)
        df['target_return'] = df['future_return']
        
        return df
    
    def prepare_features(self, df):
        """准备特征数据"""
        # 选择特征列
        feature_cols = [
            'price_change', 'high_low_ratio', 'close_open_ratio',
            'price_sma_5_ratio', 'price_sma_10_ratio', 'price_sma_20_ratio', 'price_sma_50_ratio',
            'macd', 'macd_signal', 'macd_histogram',
            'rsi', 'bb_position', 'volume_ratio',
            'volatility_10', 'volatility_20'
        ]
        
        # 添加滞后特征
        for col in ['price_change', 'rsi', 'macd']:
            for lag in [1, 2, 3, 5]:
                df[f'{col}_lag_{lag}'] = df[col].shift(lag)
                feature_cols.append(f'{col}_lag_{lag}')
        
        # 移除缺失值
        df_clean = df.dropna()
        
        # 提取特征和目标
        X = df_clean[feature_cols]
        y_regression = df_clean['target_return']
        y_classification = df_clean['target_direction']
        
        return X, y_regression, y_classification, df_clean
    
    def train_model(self, pair, timeframe='1m'):
        """训练XGBoost模型"""
        print(f"\n开始训练 {pair} {timeframe} 模型...")
        
        # 加载数据
        df = self.load_data(pair, timeframe)
        if df is None:
            return None
        
        # 计算技术指标
        df = self.calculate_technical_indicators(df)
        
        # 创建目标标签
        df = self.create_target_labels(df)
        
        # 准备特征
        X, y_reg, y_clf, df_clean = self.prepare_features(df)
        
        if len(X) < 1000:
            print(f"数据量不足: {len(X)} < 1000")
            return None
        
        # 时间序列分割
        tscv = TimeSeriesSplit(n_splits=5)
        
        # 训练回归模型
        print("训练回归模型...")
        reg_model = xgb.XGBRegressor(
            n_estimators=1000,
            max_depth=6,
            learning_rate=0.1,
            subsample=0.8,
            colsample_bytree=0.8,
            random_state=42,
            n_jobs=-1
        )
        
        # 使用最后的分割进行训练和测试
        train_idx, test_idx = list(tscv.split(X))[-1]
        X_train, X_test = X.iloc[train_idx], X.iloc[test_idx]
        y_train, y_test = y_reg.iloc[train_idx], y_reg.iloc[test_idx]
        
        # 特征缩放
        scaler = StandardScaler()
        X_train_scaled = scaler.fit_transform(X_train)
        X_test_scaled = scaler.transform(X_test)
        
        # 训练模型
        reg_model.fit(X_train_scaled, y_train)
        
        # 预测
        y_pred = reg_model.predict(X_test_scaled)
        
        # 评估
        mse = mean_squared_error(y_test, y_pred)
        mae = mean_absolute_error(y_test, y_pred)
        r2 = r2_score(y_test, y_pred)
        
        # 保存模型和结果
        model_key = f"{pair}_{timeframe}"
        self.models[model_key] = reg_model
        self.scalers[model_key] = scaler
        self.results[model_key] = {
            'mse': mse,
            'mae': mae,
            'r2': r2,
            'feature_importance': dict(zip(X.columns, reg_model.feature_importances_)),
            'test_predictions': y_pred,
            'test_actual': y_test.values,
            'test_dates': df_clean.index[test_idx]
        }
        
        print(f"模型训练完成:")
        print(f"  MSE: {mse:.6f}")
        print(f"  MAE: {mae:.6f}")
        print(f"  R²: {r2:.4f}")
        
        return reg_model
    
    def plot_results(self, pair, timeframe='1m'):
        """绘制结果图表"""
        model_key = f"{pair}_{timeframe}"
        if model_key not in self.results:
            print(f"没有找到 {model_key} 的结果")
            return
        
        result = self.results[model_key]
        
        # 创建图表
        fig, axes = plt.subplots(2, 2, figsize=(15, 10))
        fig.suptitle(f'{pair} {timeframe} XGBoost模型结果', fontsize=16)
        
        # 1. 预测 vs 实际值
        axes[0, 0].scatter(result['test_actual'], result['test_predictions'], alpha=0.6)
        axes[0, 0].plot([result['test_actual'].min(), result['test_actual'].max()], 
                       [result['test_actual'].min(), result['test_actual'].max()], 'r--')
        axes[0, 0].set_xlabel('实际收益率')
        axes[0, 0].set_ylabel('预测收益率')
        axes[0, 0].set_title('预测 vs 实际值')
        
        # 2. 时间序列预测
        dates = result['test_dates'][-100:]  # 显示最后100个点
        actual = result['test_actual'][-100:]
        pred = result['test_predictions'][-100:]
        
        axes[0, 1].plot(dates, actual, label='实际值', alpha=0.7)
        axes[0, 1].plot(dates, pred, label='预测值', alpha=0.7)
        axes[0, 1].set_xlabel('时间')
        axes[0, 1].set_ylabel('收益率')
        axes[0, 1].set_title('时间序列预测 (最后100个点)')
        axes[0, 1].legend()
        axes[0, 1].tick_params(axis='x', rotation=45)
        
        # 3. 特征重要性
        importance = result['feature_importance']
        top_features = sorted(importance.items(), key=lambda x: x[1], reverse=True)[:15]
        features, values = zip(*top_features)
        
        axes[1, 0].barh(range(len(features)), values)
        axes[1, 0].set_yticks(range(len(features)))
        axes[1, 0].set_yticklabels(features)
        axes[1, 0].set_xlabel('重要性')
        axes[1, 0].set_title('特征重要性 (Top 15)')
        
        # 4. 残差分布
        residuals = result['test_actual'] - result['test_predictions']
        axes[1, 1].hist(residuals, bins=50, alpha=0.7)
        axes[1, 1].set_xlabel('残差')
        axes[1, 1].set_ylabel('频次')
        axes[1, 1].set_title('残差分布')
        
        plt.tight_layout()
        
        # 保存图表
        output_dir = Path('user_data/models/plots')
        output_dir.mkdir(parents=True, exist_ok=True)
        plt.savefig(output_dir / f'{model_key}_results.png', dpi=300, bbox_inches='tight')
        plt.show()
    
    def generate_report(self):
        """生成训练报告"""
        print("\n" + "="*60)
        print("XGBoost模型训练报告")
        print("="*60)
        
        for model_key, result in self.results.items():
            print(f"\n模型: {model_key}")
            print(f"  均方误差 (MSE): {result['mse']:.6f}")
            print(f"  平均绝对误差 (MAE): {result['mae']:.6f}")
            print(f"  决定系数 (R²): {result['r2']:.4f}")
            
            # 前5个重要特征
            top_features = sorted(result['feature_importance'].items(), 
                                key=lambda x: x[1], reverse=True)[:5]
            print(f"  重要特征:")
            for feature, importance in top_features:
                print(f"    {feature}: {importance:.4f}")
        
        # 保存报告
        report_data = {
            'timestamp': datetime.now().isoformat(),
            'models': self.results
        }
        
        output_dir = Path('user_data/models')
        output_dir.mkdir(parents=True, exist_ok=True)
        
        with open(output_dir / 'training_report.json', 'w', encoding='utf-8') as f:
            json.dump(report_data, f, indent=2, ensure_ascii=False, default=str)
        
        print(f"\n报告已保存到: {output_dir / 'training_report.json'}")
    
    def run_full_training(self):
        """运行完整的训练流程"""
        print("开始离线XGBoost模型训练...")
        print(f"数据目录: {self.data_dir}")
        print(f"交易对: {self.pairs}")
        print(f"时间框架: {self.timeframes}")
        
        # 训练所有模型
        for pair in self.pairs:
            for timeframe in self.timeframes:
                try:
                    self.train_model(pair, timeframe)
                    self.plot_results(pair, timeframe)
                except Exception as e:
                    print(f"训练 {pair} {timeframe} 失败: {e}")
        
        # 生成报告
        self.generate_report()
        
        print("\n训练完成!")
        return self.models, self.results

def main():
    """主函数"""
    trainer = OfflineXGBoostTrainer()
    models, results = trainer.run_full_training()
    
    print("\n训练总结:")
    print(f"成功训练 {len(models)} 个模型")
    
    if results:
        avg_r2 = np.mean([r['r2'] for r in results.values()])
        print(f"平均R²得分: {avg_r2:.4f}")
        
        best_model = max(results.items(), key=lambda x: x[1]['r2'])
        print(f"最佳模型: {best_model[0]} (R² = {best_model[1]['r2']:.4f})")

if __name__ == "__main__":
    main()