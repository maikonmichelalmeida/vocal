# Auditoria do catálogo e dos recursos

Origem consultada somente para leitura: `maikonmichelalmeida/kinghost_www`,
diretório `vocal/`, revisão `41a5ec8dc9c6574cb025e6a4b3389d4a9c0a1009`.

## Fonte da verdade e extração

Foram lidos `style.js` e `lesson-trainer.js` e inspecionadas as pastas
`htm/`, `sample_vocal/` e `tablaturas/`. `style.js` contém os 39 registros
EXERCISES, as oito SESSIONS, SESSION_FOCUS e EXERCISE_TEMPO_DEFAULTS.
Esses dados foram extraídos diretamente, preservando nomes, objetivos,
categorias, notas, variações, ordem de sessões, andamento e subdivisão.

`scripts/migrate_catalog.mjs` executa as funções puras originais necessárias a
`buildTrainingConfig(exercise)` dentro de um contexto JavaScript sem APIs de
DOM, rede ou arquivos. Somente a persistência de estado inicial é substituída
por uma atribuição em memória. Nenhuma reinterpretação Python decide as notas
ou o andamento de cada exercício. Os 39 resultados originais estão em
`assets/principal-configs.json` como referência de regressão; o carregador
Python usa `assets/catalog.json`.

Para repetir a extração, com Node.js instalado:

```powershell
node scripts/migrate_catalog.mjs C:\caminho\referencia\vocal
```

A origem é separada do destino e nunca recebe escritas pelo script.

## Semântica preservada

- IDs 1, 2 e 3 são respiratórios, sem imagem e sem sequência de pitch. O
  treino principal original dura 30 segundos, independentemente do BPM.
- IDs 4–39 têm sequência vocal igual à sequência do guia no treino principal.
  As repetições de notas são posições distintas, preservadas sem deduplicação.
- As notas fantasma, referências instrumentais removidas e variantes com
  silêncio são produzidas pelo conteúdo das subseções HTML; **nenhum dos 39
  treinos principais originais contém essas posições**. Não foram inventadas
  variantes adicionais. Os tipos de `vocal_notes` e `guide_notes` aceitam `None`
  para conservar a representação de posições mudas quando fornecidas ao motor.
- O caminho das lições, o título curto duplicado e o texto didático não foram
  incorporados ao catálogo desktop. `htm/` tem 40 arquivos, incluindo dois
  nomes históricos da lição Minor Scale Asc. Intervals. Sua inspeção confirmou
  o sistema extenso de subseções práticas, deliberadamente fora do escopo.
- `lesson-trainer.js` gera controles a partir de títulos h3/h4, escolhe
  andamentos por texto e comunica configurações ao pai. Esse mecanismo não
  foi migrado: há exatamente um treino principal por exercício.

## Integridade dos arquivos

Foram copiados 39 MP3 e 36 PNG. `assets/manifest.json` vincula explicitamente
ID, tipo, caminho real, tamanho e SHA-256 de cada recurso e registra os hashes
dos dois JavaScripts auditados. Cada cópia foi comparada byte a byte com a
origem. O carregador valida correspondência catálogo/manifesto, existência e
tamanho; `load_catalog(verify_hashes=True)` valida também todos os SHA-256.

Grafias e capitalização históricas preservadas incluem:

| Exercício | Recurso original |
| --- | --- |
| Chewy Chrrey | áudio `Chewy Cherry.mp3`, imagem `Chewy Chrrey.png` |
| Three-Note Run | áudio `Thee-Note Run.mp3`, imagem `Three-Note run.png` |
| Bouncing Eh | áudio `bouncing Eh.mp3` |
| Octave Repeat Nay | imagem `Octave repeat Nay.png` |
| Swift Build-Up | imagem `Swift Bullid-Up.png` |
| Minor Scale Ascending | imagem `Minor Sacale Ascending.png` |
| Minor Scale Desc. Intervals | imagem `Minor Sale Desc. Intervals.png` |

Nenhum caminho é calculado a partir do título. Os testes percorrem todos os
exercícios, verificam os hashes, comparam suas configurações às saídas do
JavaScript original e conferem a ordem completa das sessões A–H. O carregador
localiza os recursos tanto no checkout/editable quanto em uma instalação
wheel em `sys.prefix/share/vocal_app/assets`, sem depender da pasta atual.

Os MP3 e PNG continuam recursos originais do projeto do usuário; a migração
não declara nem altera a licença desses recursos. Nenhuma parte do VocalSet
foi copiada ou incorporada.
