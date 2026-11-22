"""Chronos simulado para os testes dos notebooks (sem baixar o checkpoint).

Fica numa pasta que o teste coloca no PYTHONPATH do kernel, de modo que `from chronos import
BaseChronosPipeline` no notebook encontre esta classe no lugar da biblioteca real. A previsão é
determinística: os quantis 0,1, 0,5 e 0,9 são 0,8, 1,0 e 1,2 vezes o último valor do contexto.
"""

import numpy as np


class FakePipeline:
    FATORES = np.array([0.8, 1.0, 1.2])

    def predict_quantiles(self, contextos, prediction_length, quantile_levels):
        ultimo = np.array([float(c[-1]) for c in contextos])
        q = ultimo[:, None, None] * self.FATORES[None, None, :]
        q = np.repeat(q, prediction_length, axis=1)
        return q, q[:, :, 1]


class BaseChronosPipeline:
    @classmethod
    def from_pretrained(cls, checkpoint, revision=None, device_map=None, torch_dtype=None):
        return FakePipeline()
