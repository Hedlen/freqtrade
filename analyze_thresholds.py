#!/usr/bin/env python3
"""
阈值统计分析脚本
用于分析XGBoostStrategy中使用的收益率分位数阈值

该脚本可以：
1. 加载历史数据
2. 计算未来收益率
3. 统计分位数阈值
4. 可视化收益率分布
5. 验证现有阈值的合理性
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
import argparse
import logging
from typing import Dict, List, Tuple
import warnings
warnings.filterwarnings('ignore')

# 设置中文字体
plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei']
plt.rcParams['axes.unicode_minus'] = False

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class ThresholdAnalyzer:
    """阈值分析器"""
    
    def __init__(self, label_period: int = 10):
        """
        初始化分析器
        
        Args:
            label_period: 标签周期（K线数量），对应label_period_candles
        """
        self.label_period = label_period
        self.current_thresholds = {
            'strong_down': -0.001889,  # 10分位数
            'down': -0.000792,         # 25分位数
            'up': 0.000937,            # 75分位数
            'strong_up': 0.001871      # 90分位数
        }
        
    def load_data(self, data_path: str) -> pd.DataFrame:
        """
        加载历史数据
        
        Args:
            data_path: 数据文件路径（支持CSV、JSON格式）
            
        Returns:
            DataFrame: 包含OHLCV数据的DataFrame
        """
        try:
            if data_path.endswith('.csv'):
                df = pd.read_csv(data_path)
            elif data_path.endswith('.json'):
                df = pd.read_json(data_path)
            else:
                raise ValueError("不支持的文件格式，请使用CSV或JSON格式")
            
            # 确保必要的列存在
            required_columns = ['close']
            if not all(col in df.columns for col in required_columns):
                raise ValueError(f"数据文件必须包含以下列: {required_columns}")
            
            # 如果有时间列，设置为索引
            if 'timestamp' in df.columns:
                df['timestamp'] = pd.to_datetime(df['timestamp'])
                df.set_index('timestamp', inplace=True)
            elif 'date' in df.columns:
                df['date'] = pd.to_datetime(df['date'])
                df.set_index('date', inplace=True)
            
            logger.info(f"成功加载数据: {len(df)} 行, 时间范围: {df.index[0]} 到 {df.index[-1]}")
            return df
            
        except Exception as e:
            logger.error(f"加载数据失败: {e}")
            raise
    
    def calculate_future_returns(self, df: pd.DataFrame) -> pd.Series:
        """
        计算未来收益率
        
        Args:
            df: 包含价格数据的DataFrame
            
        Returns:
            Series: 未来收益率序列
        """
        # 计算未来收益率：(未来价格 / 当前价格) - 1
        future_return = (df["close"].shift(-self.label_period) / df["close"] - 1)
        
        # 移除NaN值
        future_return = future_return.dropna()
        
        logger.info(f"计算未来{self.label_period}期收益率，有效数据点: {len(future_return)}")
        logger.info(f"收益率统计: 均值={future_return.mean():.6f}, 标准差={future_return.std():.6f}")
        
        return future_return
    
    def calculate_quantile_thresholds(self, returns: pd.Series) -> Dict[str, float]:
        """
        计算分位数阈值
        
        Args:
            returns: 收益率序列
            
        Returns:
            Dict: 包含各分位数阈值的字典
        """
        quantiles = {
            'strong_down': 0.10,  # 10分位数
            'down': 0.25,         # 25分位数
            'up': 0.75,           # 75分位数
            'strong_up': 0.90     # 90分位数
        }
        
        thresholds = {}
        for name, quantile in quantiles.items():
            threshold = returns.quantile(quantile)
            thresholds[name] = threshold
            logger.info(f"{name} 阈值 ({quantile*100}分位数): {threshold:.6f}")
        
        return thresholds
    
    def analyze_class_distribution(self, returns: pd.Series, thresholds: Dict[str, float]) -> Dict[str, int]:
        """
        分析类别分布
        
        Args:
            returns: 收益率序列
            thresholds: 阈值字典
            
        Returns:
            Dict: 各类别的数量统计
        """
        # 根据阈值分类
        conditions = [
            returns <= thresholds['strong_down'],
            (returns > thresholds['strong_down']) & (returns <= thresholds['down']),
            (returns > thresholds['down']) & (returns < thresholds['up']),
            (returns >= thresholds['up']) & (returns < thresholds['strong_up']),
            returns >= thresholds['strong_up']
        ]
        
        choices = ['strong_down', 'down', 'sideways', 'up', 'strong_up']
        classes = np.select(conditions, choices, default='sideways')
        
        # 统计各类别数量
        class_counts = pd.Series(classes).value_counts()
        class_percentages = (class_counts / len(classes) * 100).round(2)
        
        logger.info("类别分布统计:")
        for class_name in choices:
            count = class_counts.get(class_name, 0)
            percentage = class_percentages.get(class_name, 0)
            logger.info(f"  {class_name}: {count} ({percentage}%)")
        
        return class_counts.to_dict()
    
    def compare_thresholds(self, calculated_thresholds: Dict[str, float]) -> None:
        """
        比较计算出的阈值与当前使用的阈值
        
        Args:
            calculated_thresholds: 计算出的阈值
        """
        logger.info("\n阈值比较:")
        logger.info("类别\t\t当前阈值\t\t计算阈值\t\t差异")
        logger.info("-" * 60)
        
        for name in self.current_thresholds.keys():
            current = self.current_thresholds[name]
            calculated = calculated_thresholds[name]
            diff = calculated - current
            diff_pct = (diff / abs(current)) * 100 if current != 0 else 0
            
            logger.info(f"{name:<12}\t{current:.6f}\t\t{calculated:.6f}\t\t{diff:+.6f} ({diff_pct:+.2f}%)")
    
    def plot_distribution(self, returns: pd.Series, thresholds: Dict[str, float], 
                         save_path: str = None) -> None:
        """
        绘制收益率分布图
        
        Args:
            returns: 收益率序列
            thresholds: 阈值字典
            save_path: 保存路径
        """
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 10))
        
        # 子图1: 直方图和密度图
        ax1.hist(returns, bins=100, alpha=0.7, density=True, color='lightblue', edgecolor='black')
        
        # 添加阈值线
        colors = {'strong_down': 'red', 'down': 'orange', 'up': 'green', 'strong_up': 'darkgreen'}
        for name, threshold in thresholds.items():
            ax1.axvline(threshold, color=colors[name], linestyle='--', linewidth=2, 
                       label=f'{name}: {threshold:.6f}')
        
        # 添加当前阈值线（用于比较）
        for name, threshold in self.current_thresholds.items():
            ax1.axvline(threshold, color=colors[name], linestyle=':', linewidth=1, alpha=0.7,
                       label=f'当前{name}: {threshold:.6f}')
        
        ax1.set_xlabel('未来收益率')
        ax1.set_ylabel('密度')
        ax1.set_title(f'未来{self.label_period}期收益率分布 (总样本: {len(returns)})')
        ax1.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
        ax1.grid(True, alpha=0.3)
        
        # 子图2: 箱线图
        ax2.boxplot(returns, vert=False, patch_artist=True, 
                   boxprops=dict(facecolor='lightblue', alpha=0.7))
        
        # 添加阈值标记
        for name, threshold in thresholds.items():
            ax2.axvline(threshold, color=colors[name], linestyle='--', linewidth=2)
            ax2.text(threshold, 1.1, f'{name}\n{threshold:.6f}', 
                    ha='center', va='bottom', fontsize=8, rotation=45)
        
        ax2.set_xlabel('未来收益率')
        ax2.set_title('收益率箱线图')
        ax2.grid(True, alpha=0.3)
        
        plt.tight_layout()
        
        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
            logger.info(f"图表已保存到: {save_path}")
        
        plt.show()
    
    def generate_report(self, returns: pd.Series, thresholds: Dict[str, float], 
                       class_distribution: Dict[str, int], output_path: str = None) -> str:
        """
        生成分析报告
        
        Args:
            returns: 收益率序列
            thresholds: 计算出的阈值
            class_distribution: 类别分布
            output_path: 输出文件路径
            
        Returns:
            str: 报告内容
        """
        total_samples = len(returns)
        
        report = f"""
# 收益率阈值分析报告

## 数据概览
- 总样本数: {total_samples:,}
- 标签周期: {self.label_period} 个K线
- 收益率均值: {returns.mean():.6f}
- 收益率标准差: {returns.std():.6f}
- 收益率范围: [{returns.min():.6f}, {returns.max():.6f}]

## 分位数阈值
"""
        
        for name, threshold in thresholds.items():
            quantile_map = {'strong_down': 10, 'down': 25, 'up': 75, 'strong_up': 90}
            report += f"- {name}: {threshold:.6f} ({quantile_map[name]}分位数)\n"
        
        report += "\n## 当前阈值比较\n"
        for name in self.current_thresholds.keys():
            current = self.current_thresholds[name]
            calculated = thresholds[name]
            diff = calculated - current
            diff_pct = (diff / abs(current)) * 100 if current != 0 else 0
            report += f"- {name}: 当前={current:.6f}, 计算={calculated:.6f}, 差异={diff:+.6f} ({diff_pct:+.2f}%)\n"
        
        report += "\n## 类别分布\n"
        for class_name, count in class_distribution.items():
            percentage = (count / total_samples) * 100
            report += f"- {class_name}: {count:,} ({percentage:.2f}%)\n"
        
        report += f"\n## 建议\n"
        
        # 检查类别平衡性
        percentages = [(count / total_samples) * 100 for count in class_distribution.values()]
        if max(percentages) - min(percentages) > 10:
            report += "- 类别分布不够平衡，考虑调整阈值以获得更均匀的分布\n"
        else:
            report += "- 类别分布相对平衡\n"
        
        # 检查阈值差异
        max_diff = max(abs(thresholds[name] - self.current_thresholds[name]) 
                      for name in self.current_thresholds.keys())
        if max_diff > 0.001:
            report += "- 计算出的阈值与当前阈值差异较大，建议更新阈值\n"
        else:
            report += "- 当前阈值与计算结果接近，可以继续使用\n"
        
        if output_path:
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(report)
            logger.info(f"报告已保存到: {output_path}")
        
        return report
    
    def run_analysis(self, data_path: str, output_dir: str = "threshold_analysis") -> None:
        """
        运行完整的阈值分析
        
        Args:
            data_path: 数据文件路径
            output_dir: 输出目录
        """
        # 创建输出目录
        output_path = Path(output_dir)
        output_path.mkdir(exist_ok=True)
        
        logger.info("开始阈值分析...")
        
        # 1. 加载数据
        df = self.load_data(data_path)
        
        # 2. 计算未来收益率
        returns = self.calculate_future_returns(df)
        
        # 3. 计算分位数阈值
        thresholds = self.calculate_quantile_thresholds(returns)
        
        # 4. 分析类别分布
        class_distribution = self.analyze_class_distribution(returns, thresholds)
        
        # 5. 比较阈值
        self.compare_thresholds(thresholds)
        
        # 6. 生成可视化
        plot_path = output_path / "return_distribution.png"
        self.plot_distribution(returns, thresholds, str(plot_path))
        
        # 7. 生成报告
        report_path = output_path / "threshold_analysis_report.md"
        report = self.generate_report(returns, thresholds, class_distribution, str(report_path))
        
        logger.info("分析完成!")
        logger.info(f"结果保存在: {output_path}")
        
        return thresholds, class_distribution, report


def create_sample_data(output_path: str = "sample_data.csv", n_samples: int = 10000) -> None:
    """
    创建示例数据用于测试
    
    Args:
        output_path: 输出文件路径
        n_samples: 样本数量
    """
    logger.info(f"创建示例数据: {n_samples} 个样本")
    
    # 生成模拟的价格数据
    np.random.seed(42)
    
    # 模拟价格走势（随机游走 + 趋势）
    returns = np.random.normal(0.0001, 0.002, n_samples)  # 日收益率
    prices = [100.0]  # 初始价格
    
    for ret in returns:
        prices.append(prices[-1] * (1 + ret))
    
    # 创建DataFrame
    dates = pd.date_range(start='2020-01-01', periods=n_samples, freq='1H')
    df = pd.DataFrame({
        'timestamp': dates,
        'open': prices[:-1],
        'high': [p * (1 + abs(np.random.normal(0, 0.001))) for p in prices[:-1]],
        'low': [p * (1 - abs(np.random.normal(0, 0.001))) for p in prices[:-1]],
        'close': prices[1:],
        'volume': np.random.randint(1000, 10000, n_samples)
    })
    
    df.to_csv(output_path, index=False)
    logger.info(f"示例数据已保存到: {output_path}")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='分析XGBoost策略的收益率阈值')
    parser.add_argument('--data', type=str, help='历史数据文件路径 (CSV或JSON格式)')
    parser.add_argument('--label-period', type=int, default=10, 
                       help='标签周期 (对应label_period_candles, 默认: 10)')
    parser.add_argument('--output', type=str, default='threshold_analysis',
                       help='输出目录 (默认: threshold_analysis)')
    parser.add_argument('--create-sample', action='store_true',
                       help='创建示例数据用于测试')
    
    args = parser.parse_args()
    
    # 如果需要创建示例数据
    if args.create_sample:
        create_sample_data("sample_data.csv")
        logger.info("示例数据创建完成，可以使用 --data sample_data.csv 进行测试")
        return
    
    # 检查数据文件
    if not args.data:
        logger.error("请提供数据文件路径，或使用 --create-sample 创建示例数据")
        return
    
    if not Path(args.data).exists():
        logger.error(f"数据文件不存在: {args.data}")
        return
    
    # 运行分析
    analyzer = ThresholdAnalyzer(label_period=args.label_period)
    analyzer.run_analysis(args.data, args.output)


if __name__ == "__main__":
    main()