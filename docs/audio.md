# Áudio local

## Volume dos exemplos

Os 39 exemplos MP3 receberam ganho linear de **3× (+9,54 dB)** em 15/10/2026, a pedido do usuário. O ganho atua nos arquivos, mantendo a dinâmica, as notas e a duração; não utiliza compressor nem corte dos picos. Os MP3 foram recodificados em 320 kbit/s. O volume do player continua em 80%, portanto o aumento em relação à reprodução anterior também é de aproximadamente 3× em amplitude (isso não significa três vezes a sensação subjetiva de volume).

O script `scripts/amplify_examples.py` mede RMS, pico de amostra e estimativa do pico entre amostras com sobreamostragem 4× antes e depois da codificação. Se necessário, reduz o ganho para manter os picos abaixo de −1 dBFS. Todos os 39 arquivos admitiram 3× sem essa redução. O manifesto registra hashes originais e finais, ganho e medições. A referência web permanece intacta; os MP3 originais também estão no histórico Git anterior à amplificação.

Validação: os 206 testes passaram, incluindo decodificação dos 39 MP3 no backend real Qt, duração em amostras preservada, RMS aproximadamente 3× e picos abaixo do teto. O maior pico estimado após a codificação foi −8,50 dBFS. Nenhum teste desta alteração abriu microfone ou reproduziu som nos alto-falantes.

Para manutenção, o script aceita `--ffmpeg CAMINHO` ou usa `imageio-ffmpeg` (instalado somente na `.venv`; não é dependência de execução do aplicativo). Ele recusa aplicar ganho novamente em um manifesto já processado. Para reconstruir a partir da referência, execute a extração original e depois a amplificação. Todos os arquivos são validados antes de substituir os recursos locais.

## Captura e relógio

`CaptureEngine` usa PortAudio/sounddevice, mono float32 a 48 kHz. O callback copia os blocos sem normalizar, filtrar ou reamostrar; um worker calcula pitch em janelas de 4096 amostras, a cada 20 ms, conforme o tamanho e cadência de `trainer/app.js`. A fila de análise é limitada. Se o processamento atrasar, o PCM permanece preservado em memória e o contador `dropped_analysis_blocks` informa perdas de análise. Descontinuidades reiniciam a janela e geram um evento sem pitch.

`start()` fixa `started_at` com `perf_counter`; `elapsed_ms` permite que a interface compartilhe a referência temporal. Os eventos usam o fim da janela em amostras / taxa de captura; a primeira janela chega após aproximadamente 85 ms. Os tempos não corrigem automaticamente latências físicas de ADC/DAC do dispositivo. `drain_frames()` devolve `AnalysisEvent(t, frame, rms)`; `frame=None` deve alimentar `tracker.no_pitch(t)`. O processamento nunca chama widgets Qt.

`segment(start_ms, end_ms, label)` retorna `AudioSegment` com PCM original, taxa, tempos, etiqueta, dispositivo e diagnóstico de perdas. Os blocos e segmentos são imutáveis para o consumidor. Não há gravação automática de arquivos pessoais. O armazenamento em memória é liberado no início de uma nova captura ou ao descartar o objeto.

Use `CaptureEngine.devices()` e `diagnostics()` para consultar entradas, saídas e erros. A versão desktop não aplica a supressão de eco opcional do navegador. Use fones com guia simultâneo; retorno instrumental pode contaminar a análise. [Referência sounddevice](https://python-sounddevice.readthedocs.io/en/latest/api/streams.html).

## Guia instrumental

O guia usa instrumentos sampleados de um banco SoundFont local, renderizado por FluidSynth via ctypes e enviado ao sounddevice em um worker. Os programas GM de base zero são 24 (violão nylon), 25 (violão aço) e 0 (piano acústico). A seleção verifica a existência do preset no banco. O metrônomo é um clique quadrado de 65 ms, com ataque/cauda e acentos de 880/1320 Hz da aplicação original; somente esse clique é sintetizado dessa forma. Não há substituição dos instrumentos por ondas simples.

`GuidePlayer.prepare(path, instrument)` retorna um `Future`, permitindo acompanhar o carregamento sem bloquear Qt. Use `note_on(midi, velocity=100, duration=segundos)`, `note_off`, `click`, `stop` e `close`. `stop` invalida notas enfileiradas, interrompe vozes e cliques; a interface é responsável pela sequência, pausas e relógio dos alvos. Erros aparecem no Future e em `last_error`; o metrônomo funciona mesmo sem banco. [API oficial de renderização FluidSynth](https://www.fluidsynth.org/wiki/api/audio-rendering/).

O SoundFont é localizado por `VOCAL_SOUNDFONT` ou pelo caminho padrão `soundfonts/GeneralUser-GS.sf2`. Para a biblioteca, `VOCAL_FLUIDSYNTH` pode apontar para a DLL completa; no Windows também se busca `runtime/fluidsynth/**/libfluidsynth*.dll`. Preserve as DLLs adjacentes do pacote. O aplicativo não baixa nada ao iniciar e os 39 MP3 são independentes desse motor.

## Instalação efetivamente realizada

Foram obtidos das fontes oficiais e instalados somente dentro deste projeto:

- [FluidSynth 2.6.1 Windows x64 cpp11](https://github.com/FluidSynth/fluidsynth/releases/tag/v2.6.1), arquivo `fluidsynth-v2.6.1-win10-x64-cpp11.zip`, 2.727.529 bytes. Extraído em `runtime/fluidsynth/`, com licença em `LICENSE-FluidSynth.txt`.
- [GeneralUser GS de S. Christian Collins](https://github.com/mrbumpy409/GeneralUser-GS), revisão `684543d5e5efaef08d02be50dcda8d552478fa60`, arquivo `GeneralUser-GS.sf2`, 32.319.396 bytes. Instalado em `soundfonts/`, com `LICENSE-GeneralUser-GS.txt` e `SOURCE_REVISION.txt`.

SHA-256 do ZIP FluidSynth: `fab7a2e4b85675b66970f97a39bbc239729c5e0f237198b5922a6a73cbc8677c`.

SHA-256 do banco GeneralUser: `9575028c7a1f589f5770fccc8cff2734566af40cd26ed836944e9a5152688cfe`.

Para reproduzir, obtenha o ZIP x64 no release acima, extraia seu conteúdo em `runtime/fluidsynth/` e obtenha o banco e sua licença na revisão indicada. É possível usar outro banco GM legalmente obtido pela variável `VOCAL_SOUNDFONT`. Runtime e bancos ficam ignorados pelo Git; um clone novo precisa dessa instalação opcional para o guia.

FluidSynth é distribuído sob LGPL 2.1, com detalhes e componentes listados na [licença oficial](https://github.com/FluidSynth/fluidsynth/blob/v2.6.1/LICENSE). A [licença GeneralUser GS](https://github.com/mrbumpy409/GeneralUser-GS/blob/684543d5e5efaef08d02be50dcda8d552478fa60/documentation/LICENSE.txt) permite uso musical privado/comercial e inclusão em projetos de software; o autor registra incerteza histórica sobre a origem de algumas amostras. O banco não é redistribuído neste repositório. A execução é local, mas o timbre não é idêntico ao MusyngKite usado na web.

## Validação no Windows

Os testes automatizados de `tests/test_audio.py` usam mocks e PCM determinístico, sem depender de hardware. Cobrem preservação das amostras, fila cheia, janelas sobrepostas, timestamps, silêncios, erros de banco ausente, metrônomo e ciclo de reprodução.

Além disso, uma captura breve na entrada padrão Intel Smart Sound entregou 17.280 amostras, sem perda de blocos; nenhum arquivo de gravação foi salvo. O banco foi carregado pelo runtime e os três instrumentos produziram PCM não nulo. Uma nota curta e um clique foram enviados à saída padrão Beyond TV, com preparação e encerramento sem erro. Isso confirma acesso às APIs e fluxo de áudio, mas não equivale a uma avaliação perceptiva dos alto-falantes nem a uma sessão de canto validada pelo usuário.
