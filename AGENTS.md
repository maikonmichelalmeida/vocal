# Vocal Trainer Desktop

- Este repositório é o destino Python. A referência web está no repositório `maikonmichelalmeida/kinghost_www`, diretório `vocal/`, e deve permanecer somente leitura.
- Preserve `VocalSet11/` como dado local ignorado. Não versione ambientes, bancos SoundFont, runtime nativo, gravações pessoais, modelos, caches ou logs.
- Use `.venv/Scripts/python.exe` no Windows; não instale pacotes no ambiente principal do Spyder. Não execute dois pip simultaneamente na mesma `.venv`.
- Execute `python -m vocal_app` em processo separado do Spyder. A interface é PySide6, sem servidor ou navegador.
- Catálogo e manifesto em `assets/` são extraídos da origem; não reconstrua caminhos a partir dos nomes. IDs 1–3 não têm PNG.
- Consulte `docs/migration.md`, `docs/catalog-audit.md` e `docs/audio.md` antes de alterar regras musicais, avaliação ou recursos.
- Testes normais: `.venv/Scripts/python.exe -m pytest -q`. `scripts/validate_local.py` é um teste explícito de hardware que abre microfone e reproduz áudio; não salva PCM.
- A etapa atual não implementa IA, VocalSet, Golden Notes ou modelos de qualidade vocal. Mantenha aquisição, detector, rastreamento, avaliação e interface desacoplados.
