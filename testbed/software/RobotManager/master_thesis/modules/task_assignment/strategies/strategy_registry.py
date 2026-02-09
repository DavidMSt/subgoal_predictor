from enum import Enum
from master_thesis.modules.task_assignment.strategies.centralized_strategies import (
    HungarianStrategyCent, 
    RandomStrategyCent
)
from master_thesis.modules.task_assignment.strategies.decentralized_strategies import (
    GreedyNearestStrategy,
    CBBAStrategy,
    DGNNGAStrategy,
    TwoTowersStrategy
)

class StrategyType(Enum):
    """All available task assignment strategies"""
    # Centralized
    HUNGARIAN = 'hungarian'
    RANDOM = 'random'
    
    # Decentralized
    GREEDY_NEAREST = 'greedy_nearest'
    CBBA = 'cbba'
    DGNNGA = 'dgnnga'
    TWO_TOWERS = 'two_towers'

class StrategyRegistry:
    """Unified registry for all task assignment strategies"""
    
    _CENTRALIZED = {
        StrategyType.HUNGARIAN: HungarianStrategyCent,
        StrategyType.RANDOM: RandomStrategyCent,
    }
    
    _DECENTRALIZED = {
        StrategyType.GREEDY_NEAREST: GreedyNearestStrategy,
        StrategyType.CBBA: CBBAStrategy,
        StrategyType.DGNNGA: DGNNGAStrategy,
        StrategyType.TWO_TOWERS: TwoTowersStrategy,
    }
    
    @classmethod
    def get_centralized(cls, strategy: StrategyType | str):
        """Get centralized strategy class"""
        if isinstance(strategy, str):
            strategy = StrategyType(strategy)
        
        if strategy not in cls._CENTRALIZED:
            raise ValueError(f"{strategy} is not a centralized strategy")
        return cls._CENTRALIZED[strategy]
    
    @classmethod
    def get_decentralized(cls, strategy: StrategyType | str):
        """Get decentralized strategy instance"""
        if isinstance(strategy, str):
            strategy = StrategyType(strategy)
        
        if strategy not in cls._DECENTRALIZED:
            raise ValueError(f"{strategy} is not a decentralized strategy")
        return cls._DECENTRALIZED[strategy]()  # Return instance
    
    @classmethod
    def is_centralized(cls, strategy: StrategyType | str) -> bool:
        """Check if strategy is centralized"""
        if isinstance(strategy, str):
            strategy = StrategyType(strategy)
        return strategy in cls._CENTRALIZED
    
    @classmethod
    def is_decentralized(cls, strategy: StrategyType | str) -> bool:
        """Check if strategy is decentralized"""
        if isinstance(strategy, str):
            strategy = StrategyType(strategy)
        return strategy in cls._DECENTRALIZED
