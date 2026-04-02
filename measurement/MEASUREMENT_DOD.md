# DoD enxuto - Measurement (SUT/CTI)

## 1) Escopo científico fechado
- RQ1, RQ2 e RQ3 com métricas explícitas e consistentes no texto.
- Claim principal limitado ao que os artefatos realmente medem.
- Sem mistura de conteúdo administrativo na narrativa técnica.

## 2) Fonte de verdade única
- Números do paper vêm apenas de `measurement/sut/scripts/results/`.
- Tabelas e figuras do `main.tex` batem com `todo_values.json` e CSVs de auditoria.
- Qualquer número manual deve ter justificativa explícita em comentário curto.

## 3) Reprodutibilidade mínima obrigatória
- Pipeline executa de ponta a ponta sem erro.
- Saídas canônicas geradas: `todo_values.json`, `figures_data.json`, `audit/*.csv`.
- Versão do bundle ATT&CK usada é registrada no pipeline e no texto.

## 4) Integridade metodológica
- Filtro de objetos deprecated/revoked aplicado de forma consistente.
- Regras de classificação (CF/VMR/ID) documentadas e refletidas em `technique_compatibility.csv`.
- Separação clara entre CVE ilustrativo e CVE acionável.

## 5) Qualidade de escrita (sem ruído)
- Linguagem simples, direta, sem adjetivação vazia.
- Sem promessas além da evidência.
- Placeholders permanecem quando dado oficial não existe.

## 6) Qualidade de build e pacote ACM
- `latexmk -pdf` sem erro de compilação.
- Diretório `ACM CCS - Paper 2` sem artefatos desnecessários de desenvolvimento.
- Pipeline e arquivos de análise ficam fora do diretório LaTeX (em `measurement/`).

## 7) Gate de entrega
- Checklist acima 100% verde antes de enviar ao Git/submissão.
- PDF final confere com os artefatos exportados.
- Mudanças pós-resultado oficial são marcadas como exploratórias.
