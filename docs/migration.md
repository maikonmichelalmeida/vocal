# Migração e validação

## Origem auditada

Repositório somente leitura: `https://github.com/maikonmichelalmeida/kinghost_www`, commit `41a5ec8dc9c6574cb025e6a4b3389d4a9c0a1009`. Cópia separada em `C:\Users\maiko\OneDrive\Desktop\vocal-web-reference`, com checkout esparso de `vocal/`. O destino Python é `C:\Users\maiko\OneDrive\Desktop\vocal`.

Arquivos analisados: `index.htm`, `style.js`, `style.css`, `lesson-trainer.js`, `trainer/index.html`, `trainer/app.js`, `trainer/style.css` e `LEIA-ME.txt`, além de inspeção de `htm/`, `tablaturas/` e `sample_vocal/`. O catálogo e os parâmetros vieram de `EXERCISES`, `SESSIONS`, `SESSION_FOCUS`, `EXERCISE_TEMPO_DEFAULTS` e da execução da função original `buildTrainingConfig` sem subseção. [Detalhes do catálogo](catalog-audit.md).

As páginas HTML individuais e seu gerador de treinos adicionais foram excluídos deliberadamente. Há exatamente 39 treinos principais: três respiratórios e 36 de pitch. Todos os objetivos são compactos e vêm do catálogo.

## Correspondência do motor

O rastreador Python é um porte da lógica JavaScript, preservando:

- janela de 4096 amostras e análise a cada 20 ms;
- gates de clareza 0,86, RMS 0,008 e faixa 65–1200 Hz;
- aquisição inicial de três frames coerentes, rejeição de espúrios e buffer de aquisição;
- permanência da nota até 75 cents, candidatos confirmados por três frames, distância mínima de 80 cents e dispersão de 38 cents;
- pausas de até 180 ms, repetidas por articulação de 50 ms ou fallback temporal com tolerância de 35 ms;
- segmentos mínimos de 75 ms, remoção de bordas e filtro robusto por MAD;
- alinhamento de sequências por programação dinâmica, com posições ausentes e segmentos extras;
- mediana do erro central, MAE, P90, desvio padrão, RMSE, classificação e confiança;
- score 0–100, com parcelas de viés, estabilidade e cobertura. Posições ausentes ou sem confiança suficiente contribuem zero.

A classificação da afinação usa o viés central. Uma nota centrada e oscilante pode receber boa classificação de afinação e estabilidade variável; os dois conceitos não são confundidos.

O detector substitui Pitchy por McLeod/NSDF com autocorrelação FFT, normalização por energia e interpolação parabólica, implementado em NumPy/SciPy. É a mesma família de método, mas não se afirma identidade numérica com Pitchy. A versão Python remove DC antes de medir RMS útil. Clareza é periodicidade normalizada, não probabilidade de acerto. Testes sintéticos cobrem 65,5–1190 Hz, amostragem 44,1/48 kHz, harmônicos fortes, ruído e silêncio. [Artigo do método](https://quod.lib.umich.edu/i/icmc/bbp2372.2005.107/1/).

Onze fixtures em `tests/fixtures/js_tracker_reference.json` foram geradas executando funções reais da revisão JavaScript com Node. Elas verificam segmentos, tempos, transições, alinhamento, métricas e score. Não são resultados fabricados por uma reimplementação JavaScript. Para regenerar:

```powershell
node tests/generate_js_reference.cjs C:\Users\maiko\OneDrive\Desktop\vocal-web-reference\vocal\trainer\app.js
```

## Relógio e guia

O `LEIA-ME.txt` descreve um guia adaptativo antigo. **O código auditado usa tempo fixo**, através de `startFixedGuide`, antecipando o instrumento em 20% da duração da nota em relação ao alvo visual. Essa semântica foi preservada. Contagem rápida: quatro batidas de 300 ms; referência inicial de 420 ms com sustentação no modo simultâneo. Os treinos respiratórios mantêm 30 s e metrônomo no BPM selecionado.

As posições sem guia preservam o alvo vermelho, o nome e a posição verde, ocultando o traço corretivo azul durante a execução. O relatório restaura todo o traço. Nenhum treino principal da origem tem posições fantasma; elas pertenciam às subseções excluídas. Após a migração, a pedido do usuário, foram adicionados cinco níveis selecionáveis (Integral, Final, Meio, Apenas guias e Total), aplicados por posição sem alterar o catálogo original. A leitura numérica de pitch também fica oculta nas posições fantasmas. As regras estão no README e em `core/guide.py`.

A aplicação preserva o gráfico inteiro após o fim, inclusive tentativas longas (a versão web descartava frames anteriores a 30 s). O eixo vertical usa altura MIDI com rótulos de nota, como a escala logarítmica do original; a leitura numérica também mostra Hz e cents.

A janela de execução foi revista para remover a rolagem externa: cabeçalho em duas linhas, gráfico expandido e controles fixos. Os eixos enquadram a sequência inteira e as amostras visíveis com margem, inclusive durante o treino. O relatório usa gráfico reduzido ao lado da tabela, com todas as colunas ajustadas à largura. A tabela mantém rolagem própria para sequências longas. A classificação detalhada de estabilidade está nos tooltips, junto ao desvio em cents.

Na sessão I, o TXT define tempos na base de 120 BPM. `TrainingSettings.custom_durations_ms` calcula os tempos efetivos com o fator `120 / BPM`, usado na prévia, no relógio do treino, na segmentação de repetidas e nos gráficos. O arquivo original não é modificado. No relatório, sobreposições grossas coloridas usam os frames reais dentro dos segmentos alinhados à avaliação, preservando pausas e mostrando também os trechos fantasmas. As barras-alvo ficam intactas. O maior desvio confiável é destacado em vermelho somente abaixo de Boa; posições ausentes não produzem voz fictícia.

As pausas explícitas `P` do TXT ocupam posições no relógio, mas não viram alvos nem entram na cobertura da avaliação. O rastreador encerra a nota na pausa deliberada, mesmo quando ela é menor que a tolerância normal de silêncio, e o gráfico interrompe o traço. As máscaras fantasmas contam somente as notas. O Three-Note Run expande o motivo original em cinco grupos com quatro pausas de meia posição; essa correção desktop é documentada na auditoria do catálogo.

Todos os exercícios de pitch calculam limites de transposição pelas notas extremas, dentro de C2–D6 (notas inteiras na faixa de 65–1200 Hz do detector). Ao concluir uma tentativa com score >=75, o relatório publica uma única progressão de semitom e atualiza a preferência e o controle da janela principal. Espaço inicia a próxima tentativa na mesma janela; abaixo de 75, repete o tom. Repetir tom preserva o tom tocado; Concluir/fechar não reaplica a progressão. Espaço durante o treino é ignorado. A direção, os limites e o score são compartilhados pela janela principal e pelo diálogo.

## Áudio e arquitetura

`audio/capture.py` copia PCM no callback PortAudio e processa em worker. `audio/pitch.py` detecta frequência. `core/tracking.py` segmenta; `core/evaluation.py` alinha e avalia; `core/training.py` define o relógio musical. Qt atualiza o gráfico em timer de 20 ms sem executar FFT na thread da interface. `audio/playback.py` carrega e renderiza SoundFont em outro worker. MP3 usa QtMultimedia independente.

`AudioSegment` expõe PCM original mono float32, taxa, tempo, etiqueta, dispositivo e perdas da análise. Os tempos dos segmentos de pitch permitem obter o PCM correspondente em `CaptureEngine.segment`. Nada é salvo automaticamente. Esses contratos permitem análise acústica futura sem implementar agora importação VocalSet, modelos, Golden Notes ou gravações pessoais.

## Dependências verificadas no Windows

Ambiente exclusivo `.venv`, Python 3.13 x64. Versões instaladas e importadas:

| Componente | Versão |
| --- | --- |
| PySide6 | 6.12.0 |
| PyQtGraph | 0.14.0 |
| NumPy | 2.5.4 |
| SciPy | 1.18.1 |
| sounddevice | 0.5.6 |
| pytest | 9.1.1 |
| pytest-qt | 4.5.0 |
| spyder-kernels | 3.1.6 |
| FluidSynth nativo local | 2.6.1 |
| GeneralUser GS local | 2.0.3, revisão registrada em docs/audio.md |

Todas as dependências Python transitivas constam em `requirements-lock.txt`. PySide6 instala componentes adicionais Qt, mas o aplicativo não usa WebEngine/HTML. Não foram instaladas bibliotecas de IA.

## Validação realizada

Progressão automática, transposição por extensão e pausas: **283 testes passaram**. A cobertura inclui o limiar 74/75/100, subida e descida, persistência imediata, Espaço com foco no botão Concluir, duas tentativas seguidas sem progressão duplicada, repetição no mesmo tom e limites de todos os 39 exercícios. Pausas curtas e notas repetidas foram verificadas com frames sintéticos; o Three-Note Run produz 15 resultados, sem contar as quatro pausas como ausências. A preparação e o relatório completo foram inspecionados visualmente, incluindo a retomada pelo Espaço. Nenhum teste desta revisão abriu microfone ou reproduziu som nos alto-falantes.

Ajuste de BPM do personalizado e destaque da voz no relatório: **213 testes passaram**. Foram verificados tempos a 60, 120 e 180 BPM, persistência do andamento, prévia, gráfico, avaliação e repetição. Os destaques usam amostras reais, preservam lacunas de voz, não marcam notas boas como piores e não alteram dados, cor ou espessura das barras-alvo. O relatório foi inspecionado visualmente com execução sintética.

Revisão da preparação, cores e importação TXT: **206 testes passaram**. A tela de preparação não tem rolagem externa; a tablatura se ajusta inteira e o player MP3 fica junto ao título. O seletor técnico de SoundFont saiu da interface, mantendo configuração local/variável de ambiente. As linhas do relatório recebem cores suaves segundo as classificações existentes, sem mudar os limiares.

A sessão I é uma extensão desktop separada do catálogo original. Valida um arquivo UTF-8 com duas linhas, preserva durações individuais em milissegundos no guia, alvos, marcador, término e segmentação de notas repetidas. Os testes cobrem entradas inválidas, navegação, prévia, progressão, relatório e repetição. A preparação foi inspecionada visualmente a 850×550 e 1100×650 pixels lógicos; testes também cobrem 1280×800. Nenhum teste desta revisão abriu o microfone. Os 39 MP3 passaram novamente pela decodificação real Qt, e a abertura/encerramento do aplicativo e `pip check` passaram.

Após a revisão da janela e a inclusão dos níveis fantasmas: **183 testes passaram**. Foram acrescentados testes de persistência/migração de preferências, máscaras por posição, prévia sonora, ocultação sem perda de avaliação e enquadramento integral. O layout foi verificado a 800×500, 1100×650 e 1280×800 pixels lógicos; as capturas de treino e relatório foram inspecionadas com dados sintéticos, sem abrir o microfone.

Verificação local em 15/10/2026: **161 testes passaram**, com Python 3.13.15 / Windows 11 x64. A distribuição wheel foi construída com os recursos locais incluídos; ela não embute ambiente virtual, banco SoundFont ou VocalSet.

- Catálogo: 54 testes de recursos, hashes, parâmetros e sessões.
- Pitch/rastreamento: 49 testes, incluindo 11 cenários de regressão JavaScript.
- Infraestrutura de áudio: 7 testes sem dispositivos.
- Interface: 12 testes de navegação, preferências, progressão, relatório, silêncio, respiração e ocultação do traço.
- Mídia: 39 testes de decodificação dos MP3 pelo backend real Qt.
- Abertura e encerramento: `python -m vocal_app --smoke-test`, código de saída 0; captura da própria janela inspecionada.
- `pip check`: sem incompatibilidades.
- Hardware Windows: MP3 atingiu 1.440 ms de reprodução sem erro. Um ciclo de treino com guia local e microfone terminou em `DONE`, com 122.880 amostras, zero perdas e cinco posições avaliadas. Sem voz cantada, o resultado foi corretamente 0/100. Nenhuma gravação foi escrita em disco.
- FluidSynth carregou os três presets, produziu PCM não nulo e enviou uma nota e um clique à saída padrão. Captura breve adicional confirmou acesso à entrada Intel Smart Sound.

Os registros locais de verificação ficam em `test-results/`, ignorado pelo Git. O teste de hardware comprova acesso e integração, mas não comprova qualidade perceptiva, calibração de latência nem precisão para a voz real do usuário.

## Diferenças e pendências reais

1. GeneralUser GS substitui MusyngKite: instrumentos sampleados e programas GM correspondentes, timbres diferentes. Banco/runtime locais ficam fora do Git, com licenças e instalação reproduzível. [Detalhes](audio.md).
2. O detector Python foi validado funcionalmente; não foi comparado frame a frame com Pitchy em gravações humanas. Os testes de equivalência exata se aplicam ao rastreador/avaliador com os mesmos frames de entrada.
3. A captura usa a entrada padrão do Windows e 48 kHz. Não aplica cancelamento de eco/supressão de ruído do navegador; use fones. Latências físicas de ADC/DAC não são calibradas automaticamente. Resta uma sessão de canto pelo usuário para validar seu dispositivo, volume e latência percebida.
4. A avaliação conserva os limiares da web. Notas muito rápidas podem ter confiança baixa por duração insuficiente; não houve alteração silenciosa das regras para melhorar scores.
5. Não foi criada distribuição `.exe` nem instalador de sistema. A execução é pelo ambiente virtual; Spyder e terminal estão documentados.

A origem e o site publicado permaneceram intactos. A migração não depende da cópia de referência nem da internet em execução normal.
