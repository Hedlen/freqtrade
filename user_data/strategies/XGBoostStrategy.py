import logging
from functools import reduce
import numpy as np
import pandas as pd
import talib.abstract as ta
from pandas import DataFrame
from technical import qtpylib

from freqtrade.strategy import IStrategy

logger = logging.getLogger(__name__)

class XGBoostStrategy(IStrategy):
    """
    XGBoost策略用于加密货币交易
    使用FreqAI进行机器学习预测
    """
    
    # 策略接口版本
    INTERFACE_VERSION = 3
    
    # 基本策略参数
    timeframe = '1m'
    startup_candle_count: int = 200  # 适合1分钟数据的启动蜡烛数量
    can_short = False  # 现货市场不支持做空
    process_only_new_candles = True
    
    # FreqAI模型配置
    freqai_info = {
        "model_save_type": "joblib",
        "conv_width": 1,
        "model_type": "XGBoostClassifier5Class",
    }
    
    # 风险管理
    stoploss = -0.015  # 1.5% 止损
    minimal_roi = {
        "0": 0.02,   # 2% 立即止盈
        "3": 0.015,  # 3分钟后1.5%止盈
        "10": 0.01,  # 10分钟后1%止盈
        "20": 0.005, # 20分钟后0.5%止盈
        "40": 0      # 40分钟后无条件出场
    }
    
    # 交易设置
    process_only_new_candles = True
    use_exit_signal = True
    exit_profit_only = False
    ignore_roi_if_entry_signal = False
    
    # 绘图配置
    plot_config = {
        "main_plot": {},
        "subplots": {
            "&-s_close": {"&-s_close": {"color": "blue"}},
            "do_predict": {
                "do_predict": {"color": "brown"},
            },
        },
    }
    
    def feature_engineering_expand_all(
        self, dataframe: DataFrame, period: int, metadata: dict, **kwargs
    ) -> DataFrame:
        """
        自动扩展特征工程函数
        所有特征必须以%开头才能被FreqAI识别
        """
        
        # 技术指标
        dataframe[f"%-rsi-{period}"] = ta.RSI(dataframe, timeperiod=period)
        dataframe[f"%-mfi-{period}"] = ta.MFI(dataframe, timeperiod=period)
        dataframe[f"%-adx-{period}"] = ta.ADX(dataframe, timeperiod=period)
        dataframe[f"%-sma-{period}"] = ta.SMA(dataframe, timeperiod=period)
        dataframe[f"%-ema-{period}"] = ta.EMA(dataframe, timeperiod=period)
        dataframe[f"%-wma-{period}"] = ta.WMA(dataframe, timeperiod=period)
        
        # MACD指标
        macd = ta.MACD(dataframe, fastperiod=12, slowperiod=26, signalperiod=9)
        dataframe[f"%-macd-{period}"] = macd['macd']
        dataframe[f"%-macdsignal-{period}"] = macd['macdsignal']
        dataframe[f"%-macdhist-{period}"] = macd['macdhist']
        
        # 布林带
        bollinger = qtpylib.bollinger_bands(
            qtpylib.typical_price(dataframe), window=period, stds=2.2
        )
        dataframe[f"%-bb_lowerband-{period}"] = bollinger["lower"]
        dataframe[f"%-bb_middleband-{period}"] = bollinger["mid"]
        dataframe[f"%-bb_upperband-{period}"] = bollinger["upper"]
        
        dataframe[f"%-bb_width-{period}"] = (
            dataframe[f"%-bb_upperband-{period}"] - dataframe[f"%-bb_lowerband-{period}"]
        ) / dataframe[f"%-bb_middleband-{period}"]
        
        dataframe[f"%-close-bb_lower-{period}"] = (
            dataframe["close"] / dataframe[f"%-bb_lowerband-{period}"]
        )
        
        # 动量指标
        dataframe[f"%-roc-{period}"] = ta.ROC(dataframe, timeperiod=period)
        dataframe[f"%-cci-{period}"] = ta.CCI(dataframe, timeperiod=period)
        dataframe[f"%-williams_r-{period}"] = ta.WILLR(dataframe, timeperiod=period)
        
        # 成交量指标
        dataframe[f"%-relative_volume-{period}"] = (
            dataframe["volume"] / dataframe["volume"].rolling(period).mean()
        )
        dataframe[f"%-obv-{period}"] = ta.OBV(dataframe)
        
        # 波动率指标
        dataframe[f"%-atr-{period}"] = ta.ATR(dataframe, timeperiod=period)
        dataframe[f"%-natr-{period}"] = ta.NATR(dataframe, timeperiod=period)
        
        # 价格变化率
        dataframe[f"%-price_change-{period}"] = dataframe["close"].pct_change(period)
        dataframe[f"%-high_low_ratio-{period}"] = dataframe["high"] / dataframe["low"]
        
        return dataframe
    
    def feature_engineering_expand_basic(
        self, dataframe: DataFrame, metadata: dict, **kwargs
    ) -> DataFrame:
        """
        基础特征工程函数
        """
        
        # 基础价格特征
        dataframe["%-pct-change"] = dataframe["close"].pct_change()
        dataframe["%-raw_volume"] = dataframe["volume"]
        dataframe["%-raw_price"] = dataframe["close"]
        dataframe["%-raw_high"] = dataframe["high"]
        dataframe["%-raw_low"] = dataframe["low"]
        
        # 长期移动平均线
        dataframe["%-ema-50"] = ta.EMA(dataframe, timeperiod=50)
        dataframe["%-ema-100"] = ta.EMA(dataframe, timeperiod=100)
        dataframe["%-ema-200"] = ta.EMA(dataframe, timeperiod=200)
        
        # 价格相对位置
        dataframe["%-close_ema50_ratio"] = dataframe["close"] / dataframe["%-ema-50"]
        dataframe["%-close_ema200_ratio"] = dataframe["close"] / dataframe["%-ema-200"]
        
        # 成交量加权平均价格
        dataframe["%-vwap"] = qtpylib.rolling_vwap(dataframe, window=20)
        dataframe["%-close_vwap_ratio"] = dataframe["close"] / dataframe["%-vwap"]
        
        return dataframe
    
    def feature_engineering_standard(
        self, dataframe: DataFrame, metadata: dict, **kwargs
    ) -> DataFrame:
        """
        标准特征工程函数
        添加时间特征和自定义特征
        """
        
        # 时间特征
        dataframe["%-day_of_week"] = dataframe["date"].dt.dayofweek
        dataframe["%-hour_of_day"] = dataframe["date"].dt.hour
        dataframe["%-month_of_year"] = dataframe["date"].dt.month
        
        # 市场结构特征
        dataframe["%-is_weekend"] = (dataframe["date"].dt.dayofweek >= 5).astype(int)
        
        # 价格动量特征
        for period in [3, 7, 14, 21]:
            dataframe[f"%-momentum-{period}"] = (
                dataframe["close"] / dataframe["close"].shift(period) - 1
            )
        
        # 波动率特征
        for period in [7, 14, 30]:
            dataframe[f"%-volatility-{period}"] = (
                dataframe["close"].pct_change().rolling(period).std()
            )
        
        return dataframe
    
    def set_freqai_targets(self, dataframe: DataFrame, metadata: dict, **kwargs) -> DataFrame:
        """
        设置机器学习目标标签
        """
        
        # 设置分类器的类别名称
        self.freqai.class_names = ["strong_down", "down", "sideways", "up", "strong_up"]
        
        # 预测未来价格变化（分类目标）
        label_period = self.freqai_info["feature_parameters"]["label_period_candles"]
        
        # 5分类目标：强烈下跌、下跌、横盘、上涨、强烈上涨
        future_return = (
            dataframe["close"].shift(-label_period) / dataframe["close"] - 1
        )
        
        # 使用基于历史数据分位数的平衡阈值
        strong_down_threshold = -0.001570  # 10分位数
        down_threshold = -0.000654         # 25分位数  
        up_threshold = 0.000732            # 75分位数
        strong_up_threshold = 0.001584     # 90分位数
        
        # 基于固定阈值定义5个类别
        dataframe["&s-direction_5class"] = np.select(
            [
                future_return <= strong_down_threshold,  # 强烈下跌
                (future_return > strong_down_threshold) & (future_return <= down_threshold),  # 下跌
                (future_return > down_threshold) & (future_return < up_threshold),   # 横盘
                (future_return >= up_threshold) & (future_return < strong_up_threshold),  # 上涨
                future_return >= strong_up_threshold,   # 强烈上涨
            ],
            ["strong_down", "down", "sideways", "up", "strong_up"],  # 字符串类别标签
            default="sideways"  # 默认为横盘
        )
        
        # 添加数值型概率标签（FreqAI需要）
        dataframe["&s-direction_5class_proba"] = np.select(
            [
                future_return <= strong_down_threshold,  # 强烈下跌
                (future_return > strong_down_threshold) & (future_return <= down_threshold),  # 下跌
                (future_return > down_threshold) & (future_return < up_threshold),   # 横盘
                (future_return >= up_threshold) & (future_return < strong_up_threshold),  # 上涨
                future_return >= strong_up_threshold,   # 强烈上涨
            ],
            [0, 1, 2, 3, 4],  # 数值类别标签
            default=2  # 默认为横盘(2)
        )
        
        # 添加调试信息
        if len(dataframe) > 0:
            class_counts = dataframe["&s-direction_5class"].value_counts()
            logger.info(f"Label distribution: {class_counts.to_dict()}")
        
        return dataframe
    
    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        填充指标
        """
        # FreqAI处理所有特征工程
        dataframe = self.freqai.start(dataframe, metadata, self)
        return dataframe
    
    def populate_entry_trend(self, df: DataFrame, metadata: dict) -> DataFrame:
        """
        入场信号 - 优化后的多层过滤逻辑
        """
        
        # 计算技术指标用于确认
        df['rsi'] = ta.RSI(df, timeperiod=14)
        df['macd'], df['macdsignal'], df['macdhist'] = ta.MACD(df)
        df['bb_upper'], df['bb_middle'], df['bb_lower'] = ta.BBANDS(df, timeperiod=20)
        df['ema_20'] = ta.EMA(df, timeperiod=20)
        df['ema_50'] = ta.EMA(df, timeperiod=50)
        
        # 确保技术指标为数值类型，处理可能的字符串值
        numeric_columns = ['rsi', 'macd', 'macdsignal', 'macdhist', 'bb_upper', 'bb_middle', 'bb_lower', 'ema_20', 'ema_50']
        for col in numeric_columns:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
                df[col] = df[col].fillna(0)  # 用0填充NaN值
        
        # 做多条件 - 优化后的入场条件
        enter_long_conditions = [
            df["do_predict"] == 1,  # 模型预测可用
            # AI信号条件：上涨或强烈上涨
            df["&s-direction_5class"].isin(["up", "strong_up"]),
            # 基本风险控制：RSI不超买
            df["rsi"] < 70,
            # 趋势确认：价格在短期均线之上
            df["close"] > df["ema_20"],
        ]
        
        if enter_long_conditions:
            long_mask = reduce(lambda x, y: x & y, enter_long_conditions)
            df.loc[long_mask, ["enter_long", "enter_tag"]] = (1, "xgb_long_optimized")
            
            # 添加调试日志
            long_signals = long_mask.sum()
            if long_signals > 0:
                logger.info(f"Generated {long_signals} optimized long entry signals for {metadata['pair']}")
        
        # 现货市场不支持做空，移除做空逻辑
        
        return df
    
    def populate_exit_trend(self, df: DataFrame, metadata: dict) -> DataFrame:
        """
        出场信号 - 优化后的多层出场逻辑
        """
        
        # 计算出场所需的技术指标
        df['rsi'] = ta.RSI(df, timeperiod=14)
        df['macd'], df['macdsignal'], df['macdhist'] = ta.MACD(df)
        df['bb_upper'], df['bb_middle'], df['bb_lower'] = ta.BBANDS(df, timeperiod=20)
        df['ema_20'] = ta.EMA(df, timeperiod=20)
        
        # 确保技术指标为数值类型，处理可能的字符串值
        numeric_columns = ['rsi', 'macd', 'macdsignal', 'macdhist', 'bb_upper', 'bb_middle', 'bb_lower', 'ema_20']
        for col in numeric_columns:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
                df[col] = df[col].fillna(0)  # 用0填充NaN值
        
        # 做多出场条件 - 简化出场信号
        exit_long_conditions = [
            df["do_predict"] == 1,  # 模型预测可用
            (
                # AI信号出场：明确下跌信号
                df["&s-direction_5class"].isin(["strong_down", "down"]) |
                # 价格跌破短期均线
                (df["close"] < df["ema_20"]) |
                # RSI超买出场
                (df["rsi"] > 75)
            )
        ]
        
        if exit_long_conditions:
            exit_long_mask = reduce(lambda x, y: x & y, exit_long_conditions)
            df.loc[exit_long_mask, "exit_long"] = 1
            
            # 添加调试日志
            exit_long_signals = exit_long_mask.sum()
            if exit_long_signals > 0:
                logger.info(f"Generated {exit_long_signals} optimized long exit signals for {metadata['pair']}")
        
        # 现货市场不支持做空，移除做空出场逻辑
        
        return df
    
    def confirm_trade_entry(
        self,
        pair: str,
        order_type: str,
        amount: float,
        rate: float,
        time_in_force: str,
        current_time,
        entry_tag,
        side: str,
        **kwargs,
    ) -> bool:
        """
        确认交易入场
        """
        df, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        last_candle = df.iloc[-1].squeeze()
        
        # 价格滑点检查
        if side == "long":
            if rate > (last_candle["close"] * 1.005):  # 0.5%滑点限制
                return False
        else:
            if rate < (last_candle["close"] * 0.995):
                return False
        
        return True