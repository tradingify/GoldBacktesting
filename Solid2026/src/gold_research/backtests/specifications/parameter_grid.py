"""
Parameter Grid Definitions.

Utilities defining and expanding search spaces for hyperparameter 
optimization orchestrators (Grid Search, Random Search).
"""
import itertools
import random
from typing import Dict, Any, List, Iterator

class ParameterGrid:
    """
    Takes a dictionary of parameters mapped to lists of values, 
    and generates cartesian products for comprehensive exploring.
    """
    
    def __init__(self, param_space: Dict[str, List[Any]]):
        self.param_space = param_space
        
    def generate_grid(self) -> Iterator[Dict[str, Any]]:
        """Yields exhaustive cartesian product."""
        keys = self.param_space.keys()
        vals = self.param_space.values()
        for instance in itertools.product(*vals):
            yield dict(zip(keys, instance))
            
    def generate_random(self, n_samples: int) -> Iterator[Dict[str, Any]]:
        """Yields N randomly sampled parameter configurations."""
        keys = list(self.param_space.keys())
        for _ in range(n_samples):
            sample = {}
            for k in keys:
                sample[k] = random.choice(self.param_space[k])
            yield sample