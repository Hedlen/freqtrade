
# --- Do not remove these libs ---
from freqtrade.strategy import IStrategy, merge_informative_pair
from typing import Dict, List
from functools import reduce
from pandas import DataFrame
# --------------------------------

import talib.abstract as ta
import freqtrade.vendor.qtpylib.indicators as qtpylib
import numpy # noqa


class Strategy002(IStrategy):
    """
    Strategy 002
    author@: Gerald Lonlas
    github@: https://github.com/freqtrade/freqtrade-strategies

    How to use it?
    > python3 ./freqtrade/main.py -s Strategy002
    """

    INTERFACE_VERSION: int = 3
    # Minimal ROI designed for the strategy.
    # This attribute will be overridden if the config file contains "minimal_roi"
    minimal_roi = {
        "0": 0.05  # 5% 最小利润目标 - 更高的目标
    }

    # Optimal stoploss designed for the strategy
    # This attribute will be overridden if the config file contains "stoploss"
    stoploss = -0.05  # 5% 固定止损 - 给更多空间

    # Optimal timeframe for the strategy
    timeframe = '1m'

    # 关闭动态止损，让利润充分增长
    trailing_stop = False

    # run "populate_indicators" only for new candle
    process_only_new_candles = True

    # Experimental settings (configuration will overide these if set)
    use_exit_signal = True
    exit_profit_only = True
    ignore_roi_if_entry_signal = False

    # Optional order type mapping
    order_types = {
        'entry': 'limit',
        'exit': 'limit',
        'stoploss': 'market',
        'stoploss_on_exchange': False
    }

    def informative_pairs(self):
        """
        定义需要获取的额外时间框架数据
        """
        pairs = self.dp.current_whitelist()
        informative_pairs = []
        for pair in pairs:
            # 获取5m数据
            informative_pairs.append((pair, '5m'))
            # 获取15m数据  
            informative_pairs.append((pair, '15m'))
        return informative_pairs

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Adds several different TA indicators to the given DataFrame

        Performance Note: For the best performance be frugal on the number of indicators
        you are using. Let uncomment only the indicator you are using in your strategies
        or your hyperopt configuration, otherwise you will waste your memory and CPU usage.
        :param dataframe: Dataframe with data from the exchange
        :param metadata: Additional information, like the currently traded pair
        :return: a Dataframe with all mandatory indicators for the strategies
        """
        
        # === 主时间框架(1m)指标 ===
        # RSI
        dataframe['rsi'] = ta.RSI(dataframe)
        
        # EMA
        dataframe['ema12'] = ta.EMA(dataframe, timeperiod=12)
        dataframe['ema26'] = ta.EMA(dataframe, timeperiod=26)
        
        # MACD
        macd = ta.MACD(dataframe)
        dataframe['macd'] = macd['macd']
        dataframe['macdsignal'] = macd['macdsignal']
        dataframe['macdhist'] = macd['macdhist']
        
        # 布林带
        bollinger = qtpylib.bollinger_bands(qtpylib.typical_price(dataframe), window=20, stds=2)
        dataframe['bb_lowerband'] = bollinger['lower']
        dataframe['bb_middleband'] = bollinger['mid']
        dataframe['bb_upperband'] = bollinger['upper']
        
        # 成交量指标
        dataframe['volume_sma'] = dataframe['volume'].rolling(window=20).mean()
        
        # ADX
        dataframe['adx'] = ta.ADX(dataframe)
        
        # === 多时间框架特征工程 ===
        if self.dp:
            # === 5m时间框架指标 ===
            inf_5m = self.dp.get_pair_dataframe(pair=metadata['pair'], timeframe='5m')
            
            # 5m RSI
            inf_5m['rsi_5m'] = ta.RSI(inf_5m, timeperiod=14)
            
            # 5m EMA
            inf_5m['ema12_5m'] = ta.EMA(inf_5m, timeperiod=12)
            inf_5m['ema26_5m'] = ta.EMA(inf_5m, timeperiod=26)
            
            # 5m MACD
            macd_5m = ta.MACD(inf_5m)
            inf_5m['macd_5m'] = macd_5m['macd']
            inf_5m['macdsignal_5m'] = macd_5m['macdsignal']
            inf_5m['macdhist_5m'] = macd_5m['macdhist']
            
            # 5m 成交量
            inf_5m['volume_sma_5m'] = inf_5m['volume'].rolling(window=20).mean()
            
            # 5m ADX
            inf_5m['adx_5m'] = ta.ADX(inf_5m)
            
            # 合并5m数据到主时间框架
            dataframe = merge_informative_pair(dataframe, inf_5m, self.timeframe, '5m', ffill=True)
            
            # === 15m时间框架指标 ===
            inf_15m = self.dp.get_pair_dataframe(pair=metadata['pair'], timeframe='15m')
            
            # 15m RSI
            inf_15m['rsi_15m'] = ta.RSI(inf_15m, timeperiod=14)
            
            # 15m EMA
            inf_15m['ema12_15m'] = ta.EMA(inf_15m, timeperiod=12)
            inf_15m['ema26_15m'] = ta.EMA(inf_15m, timeperiod=26)
            
            # 15m MACD
            macd_15m = ta.MACD(inf_15m)
            inf_15m['macd_15m'] = macd_15m['macd']
            inf_15m['macdsignal_15m'] = macd_15m['macdsignal']
            inf_15m['macdhist_15m'] = macd_15m['macdhist']
            
            # 15m 布林带
            bollinger_15m = qtpylib.bollinger_bands(qtpylib.typical_price(inf_15m), window=20, stds=2)
            inf_15m['bb_lowerband_15m'] = bollinger_15m['lower']
            inf_15m['bb_middleband_15m'] = bollinger_15m['mid']
            inf_15m['bb_upperband_15m'] = bollinger_15m['upper']
            
            # 合并15m数据到主时间框架  
            dataframe = merge_informative_pair(dataframe, inf_15m, self.timeframe, '15m', ffill=True)
            
            # === 多时间框架组合特征 ===
            # RSI多时间框架确认
            if 'rsi_5m' in dataframe.columns and 'rsi_15m' in dataframe.columns:
                dataframe['rsi_multi_confirm'] = (
                    (dataframe['rsi'] < 30) &  # 1m RSI超卖
                    (dataframe['rsi_5m'] < 35) &  # 5m RSI也接近超卖
                    (dataframe['rsi_15m'] > 25)   # 15m RSI不要太极端
                )
            else:
                dataframe['rsi_multi_confirm'] = False
            
            # EMA多时间框架趋势确认
            if 'ema12_5m' in dataframe.columns and 'ema26_5m' in dataframe.columns and 'ema12_15m' in dataframe.columns and 'ema26_15m' in dataframe.columns:
                dataframe['ema_multi_trend'] = (
                    (dataframe['ema12'] > dataframe['ema26']) &  # 1m短期趋势向上
                    (dataframe['ema12_5m'] > dataframe['ema26_5m']) &  # 5m短期趋势向上
                    (dataframe['ema12_15m'] > dataframe['ema26_15m'])   # 15m中期趋势向上
                )
            else:
                dataframe['ema_multi_trend'] = False

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Based on TA indicators, populates the buy signal for the given dataframe
        :param dataframe: DataFrame populated with indicators
        :param metadata: Additional information, like the currently traded pair
        :return: DataFrame with buy column
        """
        
        # 优化的买入条件 - 增加趋势确认和质量过滤
        
        # 极简买入策略 - 只在最佳条件下买入
        minimal_buy = (
            # 强势趋势确认
            (dataframe['ema12'] > dataframe['ema26']) &  # 短期趋势向上
            (dataframe['ema26'] > dataframe['ema26'].shift(10)) &  # 长期趋势向上
            
            # 价格位置良好
            (dataframe['close'] > dataframe['ema12']) &  # 价格在短期趋势之上
            (dataframe['rsi'] > 45) &  # RSI不要太低
            (dataframe['rsi'] < 70) &  # RSI不要太高
            
            # MACD确认
            (dataframe['macd'] > dataframe['macdsignal']) &  # MACD金叉
            (dataframe['macd'] > 0) &  # MACD在零轴之上
            
            # 成交量正常
            (dataframe['volume'] > dataframe['volume_sma'] * 0.8) &  # 成交量不要太低
            (dataframe['volume'] > 0)
        )
        
        # 多时间框架确认 - 更严格的过滤
        multi_timeframe_confirm = True
        
        # 如果有5m数据，增加确认
        if 'rsi_5m' in dataframe.columns and 'macd_5m' in dataframe.columns:
            multi_timeframe_confirm = multi_timeframe_confirm & (
                (dataframe['rsi_5m'] < 60) &  # 5m RSI不要太高
                (dataframe['macd_5m'] > dataframe['macdsignal_5m'])  # 5m MACD趋势向上
            )
        
        # 如果有15m数据，增加确认  
        if 'rsi_15m' in dataframe.columns:
            multi_timeframe_confirm = multi_timeframe_confirm & (
                (dataframe['rsi_15m'] < 70) &  # 15m RSI不要太高
                (dataframe['rsi_15m'] > 25)    # 15m RSI不要太低
            )
        
        # 最终买入信号：极简买入策略
        dataframe.loc[
            minimal_buy,
            'enter_long'] = 1

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Based on TA indicators, populates the sell signal for the given dataframe
        :param dataframe: DataFrame populated with indicators
        :param metadata: Additional information, like the currently traded pair
        :return: DataFrame with sell column
        """
        
        # 极简卖出策略 - 只在明确趋势转弱时卖出
        minimal_sell = (
            # 趋势明确转弱
            (dataframe['ema12'] < dataframe['ema26']) &  # 短期趋势转向
            (dataframe['close'] < dataframe['ema12']) &  # 价格跌破短期趋势
            (dataframe['rsi'] < 40) &  # RSI转弱
            (dataframe['macd'] < dataframe['macdsignal']) &  # MACD死叉
            (dataframe['volume'] > 0)
        )
        
        # 多时间框架确认 - 避免过早卖出
        multi_timeframe_confirm = True
        
        # 如果有5m数据，增加确认
        if 'rsi_5m' in dataframe.columns and 'macd_5m' in dataframe.columns:
            multi_timeframe_confirm = multi_timeframe_confirm & (
                (dataframe['rsi_5m'] > 50) |  # 5m RSI偏高，或
                (dataframe['macd_5m'] < dataframe['macdsignal_5m'])  # 5m MACD转向
            )
        
        # 如果有15m数据，增加确认
        if 'rsi_15m' in dataframe.columns:
            multi_timeframe_confirm = multi_timeframe_confirm & (
                (dataframe['rsi_15m'] > 60) |  # 15m RSI偏高，或
                (dataframe['rsi_15m'] < 30)    # 15m RSI极低(可能反转)
            )
        
        # 最终卖出信号：极简卖出策略
        dataframe.loc[
            minimal_sell,
            'exit_long'] = 1

        return dataframe
