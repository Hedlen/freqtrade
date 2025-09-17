#!/usr/bin/env python3
"""
Freqtrade数据转换脚本
将freqtrade的feather格式历史数据转换为CSV格式，供阈值分析脚本使用
"""

import pandas as pd
import argparse
import logging
from pathlib import Path
from typing import Optional

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class FreqtradeDataConverter:
    """Freqtrade数据转换器"""
    
    def __init__(self, data_dir: str = "user_data/data/okx"):
        """
        初始化转换器
        
        Args:
            data_dir: freqtrade数据目录路径
        """
        self.data_dir = Path(data_dir)
        
    def list_available_data(self) -> list:
        """
        列出可用的数据文件
        
        Returns:
            list: 可用的数据文件列表
        """
        if not self.data_dir.exists():
            logger.error(f"数据目录不存在: {self.data_dir}")
            return []
            
        feather_files = list(self.data_dir.glob("*.feather"))
        logger.info(f"找到 {len(feather_files)} 个数据文件:")
        for file in feather_files:
            logger.info(f"  - {file.name}")
        return feather_files
    
    def load_feather_data(self, file_path: Path) -> pd.DataFrame:
        """
        加载feather格式的数据
        
        Args:
            file_path: feather文件路径
            
        Returns:
            DataFrame: 加载的数据
        """
        try:
            df = pd.read_feather(file_path)
            logger.info(f"成功加载数据: {file_path.name}")
            logger.info(f"数据形状: {df.shape}")
            logger.info(f"列名: {list(df.columns)}")
            
            # 显示数据的时间范围
            if 'date' in df.columns:
                df['date'] = pd.to_datetime(df['date'])
                logger.info(f"时间范围: {df['date'].min()} 到 {df['date'].max()}")
            
            return df
            
        except Exception as e:
            logger.error(f"加载数据失败: {e}")
            raise
    
    def convert_to_csv(self, pair: str, timeframe: str, output_file: Optional[str] = None) -> str:
        """
        将指定交易对和时间框架的数据转换为CSV格式
        
        Args:
            pair: 交易对，如 "TRX/USDT"
            timeframe: 时间框架，如 "1m"
            output_file: 输出文件名，如果不指定则自动生成
            
        Returns:
            str: 输出文件路径
        """
        # 构建文件名（freqtrade使用下划线替换斜杠）
        pair_filename = pair.replace("/", "_")
        feather_file = self.data_dir / f"{pair_filename}-{timeframe}.feather"
        
        if not feather_file.exists():
            raise FileNotFoundError(f"数据文件不存在: {feather_file}")
        
        # 加载数据
        df = self.load_feather_data(feather_file)
        
        # 确保必要的列存在
        required_columns = ['date', 'open', 'high', 'low', 'close', 'volume']
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            raise ValueError(f"缺少必要的列: {missing_columns}")
        
        # 处理时间列
        if 'date' in df.columns:
            df['date'] = pd.to_datetime(df['date'])
            df = df.sort_values('date')
        
        # 生成输出文件名
        if output_file is None:
            output_file = f"{pair_filename}_{timeframe}_data.csv"
        
        # 保存为CSV
        output_path = Path(output_file)
        df.to_csv(output_path, index=False)
        
        logger.info(f"数据已转换并保存到: {output_path}")
        logger.info(f"转换的数据行数: {len(df)}")
        
        return str(output_path)
    
    def convert_all_data(self, output_dir: str = "converted_data") -> dict:
        """
        转换所有可用的数据文件
        
        Args:
            output_dir: 输出目录
            
        Returns:
            dict: 转换结果字典
        """
        output_path = Path(output_dir)
        output_path.mkdir(exist_ok=True)
        
        feather_files = self.list_available_data()
        results = {}
        
        for file_path in feather_files:
            try:
                # 解析文件名
                filename = file_path.stem  # 去掉扩展名
                if '-' in filename:
                    pair_part, timeframe = filename.rsplit('-', 1)
                    pair = pair_part.replace('_', '/')
                    
                    # 转换数据
                    output_file = output_path / f"{filename}.csv"
                    df = self.load_feather_data(file_path)
                    
                    # 处理时间列
                    if 'date' in df.columns:
                        df['date'] = pd.to_datetime(df['date'])
                        df = df.sort_values('date')
                    
                    # 保存为CSV
                    df.to_csv(output_file, index=False)
                    
                    results[f"{pair}_{timeframe}"] = {
                        'input_file': str(file_path),
                        'output_file': str(output_file),
                        'rows': len(df),
                        'time_range': f"{df['date'].min()} 到 {df['date'].max()}" if 'date' in df.columns else "未知"
                    }
                    
                    logger.info(f"✅ 转换完成: {pair} {timeframe} -> {output_file}")
                    
            except Exception as e:
                logger.error(f"❌ 转换失败 {file_path.name}: {e}")
                results[file_path.name] = {'error': str(e)}
        
        return results

def main():
    parser = argparse.ArgumentParser(description='转换Freqtrade历史数据为CSV格式')
    parser.add_argument('--data-dir', default='user_data/data/okx', 
                       help='Freqtrade数据目录路径')
    parser.add_argument('--pair', help='指定转换的交易对，如 TRX/USDT')
    parser.add_argument('--timeframe', help='指定转换的时间框架，如 1m')
    parser.add_argument('--output', help='输出文件名')
    parser.add_argument('--output-dir', default='converted_data', 
                       help='输出目录（转换所有数据时使用）')
    parser.add_argument('--list', action='store_true', 
                       help='仅列出可用的数据文件')
    parser.add_argument('--convert-all', action='store_true', 
                       help='转换所有可用的数据文件')
    
    args = parser.parse_args()
    
    # 创建转换器
    converter = FreqtradeDataConverter(args.data_dir)
    
    if args.list:
        # 仅列出可用数据
        converter.list_available_data()
        return
    
    if args.convert_all:
        # 转换所有数据
        logger.info("开始转换所有可用数据...")
        results = converter.convert_all_data(args.output_dir)
        
        logger.info("\n=== 转换结果汇总 ===")
        for key, result in results.items():
            if 'error' in result:
                logger.error(f"{key}: {result['error']}")
            else:
                logger.info(f"{key}: {result['rows']} 行数据, 时间范围: {result['time_range']}")
        
        return
    
    if args.pair and args.timeframe:
        # 转换指定的交易对和时间框架
        try:
            output_file = converter.convert_to_csv(args.pair, args.timeframe, args.output)
            logger.info(f"转换完成: {output_file}")
        except Exception as e:
            logger.error(f"转换失败: {e}")
            return
    else:
        # 显示帮助信息
        logger.info("请指定要转换的数据或使用 --convert-all 转换所有数据")
        logger.info("示例:")
        logger.info("  python convert_freqtrade_data.py --list")
        logger.info("  python convert_freqtrade_data.py --pair TRX/USDT --timeframe 1m")
        logger.info("  python convert_freqtrade_data.py --convert-all")

if __name__ == "__main__":
    main()