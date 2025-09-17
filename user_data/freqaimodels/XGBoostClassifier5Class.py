import logging
from typing import Any, Dict

import numpy as np
import pandas as pd
from xgboost import XGBClassifier

from freqtrade.freqai.base_models.BaseClassifierModel import BaseClassifierModel
from freqtrade.freqai.data_kitchen import FreqaiDataKitchen

logger = logging.getLogger(__name__)


class XGBoostClassifier5Class(BaseClassifierModel):
    """
    用户创建的XGBoost分类器模型，专门用于5分类任务
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.model = None

    def fit(self, data_dictionary: Dict, dk: FreqaiDataKitchen, **kwargs) -> Any:
        """
        用户设置训练参数并调用fit函数
        :param data_dictionary: 包含训练数据的字典
        :param dk: FreqaiDataKitchen对象
        :return: 训练好的模型
        """

        # 获取训练参数
        train_params = self.freqai_info.get("model_training_parameters", {})
        
        # 设置默认参数（优化后防止过拟合）
        default_params = {
            'objective': 'multi:softprob',  # 多分类概率输出
            'num_class': 5,  # 5分类
            'n_estimators': 100,  # 减少树的数量防止过拟合
            'max_depth': 6,
            'learning_rate': 0.05,  # 降低学习率
            'subsample': 0.8,
            'colsample_bytree': 0.8,
            'reg_alpha': 1,  # L1正则化
            'reg_lambda': 1,  # L2正则化
            'random_state': 42,
            'n_jobs': -1,
            'eval_metric': ['mlogloss', 'merror']  # 多分类对数损失和分类错误率
        }
        
        # 合并用户参数
        params = {**default_params, **train_params}
        
        # 创建XGBoost分类器
        self.model = XGBClassifier(**params)
        
        # 训练模型
        X = data_dictionary["train_features"]
        y = data_dictionary["train_labels"]
        
        logger.info(f"Training XGBoost 5-class classifier with {len(X)} samples")
        logger.info(f"Target distribution: {y.value_counts().sort_index()}")
        
        # 训练XGBoost模型。
        # 处理y的格式 - 如果是DataFrame取第一列，如果是Series直接使用
        if isinstance(y, pd.DataFrame):
            y_train = y.iloc[:, 0]
        else:
            y_train = y
            
        # 标签编码：将字符串标签转换为整数
        from sklearn.preprocessing import LabelEncoder
        self.label_encoder = LabelEncoder()
        
        # 如果标签是字符串类型，进行编码
        if y_train.dtype == 'object' or isinstance(y_train.iloc[0], str):
            y_train_encoded = self.label_encoder.fit_transform(y_train)
            logger.info(f"Label encoding: {dict(zip(self.label_encoder.classes_, range(len(self.label_encoder.classes_))))}")
        else:
            y_train_encoded = y_train
            self.label_encoder = None
            
        # 处理测试标签
        if "test_labels" in data_dictionary:
            test_labels = data_dictionary["test_labels"]
            if isinstance(test_labels, pd.DataFrame):
                test_labels = test_labels.iloc[:, 0]
            
            # 对测试标签也进行编码
            if self.label_encoder is not None:
                test_labels_encoded = self.label_encoder.transform(test_labels)
            else:
                test_labels_encoded = test_labels
                
            eval_set = [(data_dictionary["test_features"], test_labels_encoded)]
        else:
            eval_set = None
            
        self.model.fit(
            X=X,
            y=y_train_encoded,
            eval_set=eval_set,
            verbose=True
        )
        
        # 训练完成后输出日志信息
        if eval_set is not None:
            # 由于没有使用early stopping，best_iteration和best_score不可用
            logger.info("Training completed with validation set.")
            logger.info(f"Final training iterations: {self.model.n_estimators}")
        else:
            logger.info("Training completed without validation set.")
        
        return self.model

    def predict(
        self, unfiltered_df: pd.DataFrame, dk: FreqaiDataKitchen, **kwargs
    ) -> tuple[pd.DataFrame, np.ndarray]:
        """
        过滤数据并进行预测
        :param unfiltered_df: 完整的数据框
        :param dk: FreqaiDataKitchen对象
        :return: 预测结果和do_predict数组
        """

        # 检查模型是否已训练
        if self.model is None:
            logger.warning("Model not trained yet, returning default predictions")
            # 返回默认预测结果
            pred_df = pd.DataFrame(index=unfiltered_df.index)
            pred_df[dk.label_list[0]] = "sideways"  # 默认预测为横盘
            pred_df[f"{dk.label_list[0]}_proba"] = 0.2  # 默认概率
            return (pred_df, np.ones(len(unfiltered_df), dtype=np.int8))
        
        # 调用父类的predict方法，获取标准的预测流程
        (pred_df, dk.do_predict) = super().predict(unfiltered_df, dk, **kwargs)
        
        # 处理标签编码 - 如果训练时使用了标签编码器
        if hasattr(self, 'label_encoder') and self.label_encoder is not None:
            label = dk.label_list[0]
            
            # 处理NaN值，将其填充为默认值（例如最常见的类别）
            pred_df[label] = pred_df[label].fillna(2)  # 假设2对应'sideways'
            
            # 将数值预测结果转换回原始标签
            pred_df[label] = self.label_encoder.inverse_transform(pred_df[label].astype(int))
            
            # 重命名概率列：从数值标签到字符串标签
            prob_columns_mapping = {}
            for i, class_name in enumerate(self.label_encoder.classes_):
                if i in pred_df.columns:
                    prob_columns_mapping[i] = class_name
            
            pred_df = pred_df.rename(columns=prob_columns_mapping)
        
        return (pred_df, dk.do_predict)