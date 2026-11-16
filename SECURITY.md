# Política de segurança

## Versões suportadas

| Versão | Recebe correções de segurança |
|---|---|
| Branch `main` e a versão `X.Y` mais recente | ✅ |
| Versões `X.Y` anteriores | ❌ (atualize para a mais recente) |
| Branches `dev` e `hml` | ❌ (desenvolvimento e homologação) |

## Como reportar uma vulnerabilidade

**Não abra uma issue pública** nem comente a vulnerabilidade em pull requests ou discussões.

Use o reporte privado do GitHub:

1. Abra a aba **[Security](https://github.com/cnx-anselmooliveira/atlas_epidemiologico/security)** do repositório.
2. Clique em **Report a vulnerability**.
3. Descreva o problema, como reproduzi-lo, o impacto que você enxerga e, se tiver, uma sugestão de correção.

O relato fica visível só para você e para o mantenedor até a correção ser publicada.

## O que esperar

| Etapa | Prazo |
|---|---|
| Confirmação de recebimento | até 5 dias úteis |
| Avaliação inicial (confirmado ou não, gravidade) | até 15 dias úteis |
| Correção e divulgação | combinadas com você conforme a gravidade |

Quando a correção sair, publicamos um *security advisory* e damos crédito a quem reportou, se for do seu interesse.

## Escopo

**Dentro do escopo:**
- código deste repositório (pacote `atlas_ml`, DAGs, imagens e configurações de deploy);
- imagens publicadas no DockerHub sob `anselmomendes/atlas-epidemiologia-*`;
- o site e a API públicos do Atlas.

**Fora do escopo:**
- o ambiente de desenvolvimento local (`platform/compose.dev.yml`), que escuta só em `127.0.0.1` e usa senhas de exemplo;
- vulnerabilidades em dependências de terceiros (reporte ao projeto de origem; atualizamos assim que houver correção);
- os dados das fontes oficiais (SINAN, SIVIGILA, OPAS etc.).

## Boas práticas do projeto

- Credenciais nunca são versionadas. Chaves e `.env` ficam fora do git, e o histórico é verificado antes de mudanças de visibilidade.
- Imagens rodam com usuários sem privilégios de root.
- Serviços de produção ficam atrás de HTTPS e autenticação.
