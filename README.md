# Vocal Trainer Desktop

Aplicação Python nativa para os 39 treinos principais do Vocal Trainer, com sessões A–H e sessão I para exercícios personalizados por TXT, tablaturas, exemplos MP3, guia instrumental local, microfone, gráfico em tempo real e avaliação de afinação. Sem servidor, navegador ou dependência do site KingHost durante o uso.

## Executar neste computador

O ambiente já está instalado em `C:\Users\maiko\OneDrive\Desktop\vocal\.venv`.

```powershell
cd C:\Users\maiko\OneDrive\Desktop\vocal
.\.venv\Scripts\python.exe -m vocal_app
```

Também é possível abrir `iniciar_vocal.bat` ou executar `run_vocal.py` no Spyder. O launcher abre um processo separado, evitando conflito entre o Qt do Spyder e o PySide6 do aplicativo. Veja [uso com Spyder 6](docs/spyder.md).

## Instalar em outro Windows

Instale Python 3.13 x64 e, na pasta deste projeto, execute:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/install.ps1 -WithSoundFont
```

O script cria somente `.venv`, instala as versões de `requirements-lock.txt` e registra o pacote em modo editável. Com `-WithSoundFont`, baixa também o runtime e o banco instrumental das fontes oficiais, validando SHA-256. Não modifica o Python ou o ambiente principal do Spyder. O lock foi validado em Windows x64 / Python 3.13; outros sistemas precisam de sua própria resolução e validação. O pacote declara Python >=3.11, mas essas versões não foram testadas nesta entrega.

Sem o parâmetro, os 39 exemplos MP3, imagens e treinos respiratórios continuam funcionando. Para o guia, instale o banco depois com `scripts/install_audio.ps1`; outro banco GM pode ser configurado pela variável `VOCAL_SOUNDFONT`. Ausência do banco produz uma mensagem explícita; a pessoa pode optar por treinar sem referência instrumental. Consulte [áudio e licenças](docs/audio.md).

## Uso

1. Escolha uma sessão A–H ou um dos 39 exercícios. Anterior/próximo percorrem a sessão selecionada.
2. Confira a sequência e a tablatura, ajustada por inteiro ao espaço disponível. A variação original fica na dica da sequência. Use **Ampliar tablatura** para vê-la em outra janela.
3. Use **Tocar exemplo**, ao lado do título, para ouvir o MP3 original antes do treino; **Ouvir guia** reproduz a sequência no instrumento selecionado.
4. Ajuste BPM (40–180), notas/pulso (1–4), transposição (−8 a +8), direção, **Guia** e **Nível**.
5. Clique em **Início**. Há referência e quatro batidas rápidas de entrada; o gráfico acompanha os alvos e a voz. Use fones para evitar que o guia seja captado pelo microfone.
6. Durante o treino, o gráfico ocupa a área principal e enquadra a sequência inteira e a voz com margem. No fim, a tabela recebe prioridade, com o gráfico completo em miniatura ao lado. Apenas a tabela tem rolagem vertical quando há muitas notas.
7. **Tentar novamente** e **Fechar** mantêm o tom. Apenas **Concluir**, após o fim, aplica +1 ou −1 semitom, limitado a −8/+8.

As linhas do relatório usam preenchimentos suaves: verde para excelente, verde discreto para boa, amarelo para atenção, laranja para desvio e vermelho para erro. Notas incertas ou ausentes ficam neutras; os rótulos continuam visíveis e os critérios de avaliação são os mesmos.

### I · Personalizado (.txt)

Selecione a sessão **I** e clique em **Selecionar arquivo .txt…**. O treino só fica disponível depois da validação. O arquivo UTF-8 deve conter duas linhas: notas com oitava e tempos inteiros em milissegundos, separados por espaços. Exemplo disponível em [examples/personalizado.txt](examples/personalizado.txt):

```text
B3 D4 G4 E4
500 500 500 500
```

Cada nota pode ter uma duração diferente. Sustenidos (`F#4`, `F♯4`) e bemóis (`Bb3`, `B♭3`) são aceitos. A quantidade de tempos deve corresponder à de notas. Limites: 256 notas, 1–60000 ms por nota, 10 minutos no total, arquivo de até 64 KB e notas MIDI 8–119 (com espaço para transposição). Notas muito curtas podem não fornecer voz suficiente para avaliação confiável.

O gráfico mostra a sequência importada; **Ouvir guia**, transposição e níveis fantasmas continuam disponíveis. BPM e notas/pulso ficam desabilitados porque os tempos vêm do arquivo. O TXT não contém gravação MP3: a prévia deste exercício é instrumental. Ao entrar novamente na sessão I, selecione o arquivo; o aplicativo não copia nem envia seu conteúdo. Os 39 exercícios e recursos originais permanecem intactos.

Os exercícios 1–3 duram 30 segundos e usam cronômetro/metrônomo, sem abrir microfone nem calcular pitch. O guia simultâneo desmarcado limita a ajuda à referência inicial ou à contagem, conforme o tipo de exercício. Preferências por exercício, sessão e instrumento são salvas em `%LOCALAPPDATA%\VocalTrainer\settings.json`.

### Níveis de notas fantasmas

O seletor **Nível** aparece antes do treino e sua escolha fica salva por exercício. **Ouvir guia** respeita as mesmas posições. Os alvos vermelhos continuam visíveis; nas posições fantasmas, o instrumento e a correção ao vivo (traço azul e leitura de pitch) ficam ocultos. Toda a voz é avaliada e reaparece no relatório.

| Nível | Referências |
| --- | --- |
| 1 · Integral (padrão) | Todas as notas |
| 2 · Final | Último quarto da sequência fica fantasma, arredondado para cima |
| 3 · Meio | De uma a três notas centrais ficam fantasmas; preserva início e fim |
| 4 · Apenas guias | Primeira nota e uma central; com 9 ou mais notas, referências em cerca de 1/3 e 2/3 |
| 5 · Total | Somente a primeira nota |

A primeira nota é preservada em todos os níveis. Em sequências de até duas notas, Meio permanece integral e Apenas guias usa só a primeira. O nível não altera a sequência vocal, a transposição, o score ou a progressão. Com **Guia** desmarcado, somente a referência inicial toca, independentemente do nível; a ocultação da correção visual continua seguindo o nível escolhido. O seletor fica desabilitado nos respiratórios.

## Estrutura

```text
src/vocal_app/
  __main__.py             entrada python -m vocal_app
  ui/                     janela, tablaturas, player, gráfico e treino
  audio/                  captura PCM, detector e guia SoundFont
  core/                   catálogo, notas, relógio, rastreador, avaliação e preferências
assets/                   catálogo/manifesto, 39 MP3, 36 PNG
tests/                    testes sem microfone e fixtures do JavaScript
scripts/                  instalação, extração e validação local de hardware
docs/                     auditoria, diferenças, Spyder e áudio
```

`VocalSet11/`, `.venv/`, `runtime/`, `soundfonts/`, gravações, modelos, caches e logs ficam fora do Git. Não há implementação de IA nem importação do VocalSet. O PCM da tentativa existe apenas em memória e pode ser consultado por segmentos tipados na camada de áudio.

## Validar

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m vocal_app --smoke-test
```

Os testes incluem decodificação real dos 39 MP3 via Qt, mas não dependem de entrada/saída física. Para um teste adicional que **reproduz áudio e abre brevemente o microfone**, sem salvar gravação:

```powershell
.\.venv\Scripts\python.exe scripts/validate_local.py
```

Resultados, limites da validação e divergências estão em [docs/migration.md](docs/migration.md). A origem foi consultada na revisão `41a5ec8dc9c6574cb025e6a4b3389d4a9c0a1009`, sem alterações ou commits no repositório web.
