"""Previsão de incidência de dengue: dados, janelas, divisões, avaliação e contrato dos modelos."""

EXPERIMENT = "dengue-forecast-br"  # → experimento "atlas/dengue-forecast-br" no MLflow

# Contrato entre o pacote e o notebook do pipeline (ml/notebooks/forecast_pipeline.ipynb): sobe
# quando uma função que o notebook chama muda de forma. O notebook declara a versão mínima de que
# precisa e falha, antes de criar qualquer run, se a imagem instalada for mais antiga.
NOTEBOOK_API = 1
