# Usar com Spyder 6

## Fluxo recomendado: interface em processo separado

Abra a pasta `C:\Users\maiko\OneDrive\Desktop\vocal` como projeto no Spyder e execute `run_vocal.py` com F5. Ele usa explicitamente `.venv\Scripts\python.exe`, abre a janela em outro processo e devolve o controle ao console. Nenhum kernel ou pacote do ambiente principal do Spyder precisa ser alterado.

O launcher remove do processo filho caminhos de plugins Qt herdados do Spyder. O aplicativo cria seu próprio `QApplication`; não execute `vocal_app.__main__.main()` dentro de um console que já possui um loop Qt.

No terminal, o equivalente é:

```powershell
cd C:\Users\maiko\OneDrive\Desktop\vocal
.\.venv\Scripts\python.exe -m vocal_app
```

## Interpretador do projeto e depuração dos módulos

Para importar ou depurar os módulos Python no console do Spyder:

1. Abra **Ferramentas → Preferências → Interpretador Python**.
2. Selecione o interpretador personalizado `C:\Users\maiko\OneDrive\Desktop\vocal\.venv\Scripts\python.exe`.
3. Reinicie o kernel pelo menu Consoles.
4. Confira `import sys; print(sys.executable)` e importe, por exemplo, `from vocal_app.core.catalog import load_catalog`.

O ambiente inclui `spyder-kernels 3.1.6`, compatível com a faixa exigida pelo Spyder 6.1. A linha Spyder 6.0 requer `spyder-kernels >=3.0.5,<3.1`; outras versões podem exigir outra faixa. Use a instrução de versão apresentada pelo próprio Spyder, aplicando-a **somente ao Python da `.venv`**, caso deseje conectar seu console. Essa troca não é necessária para o launcher separado e deixa o ambiente diferente do lock desta entrega.

Exemplo para Spyder 6.0:

```powershell
.\.venv\Scripts\python.exe -m pip install "spyder-kernels>=3.0.5,<3.1"
```

Os módulos `core` e o detector não dependem do loop Qt e podem ser depurados normalmente no Spyder. O processo iniciado pelo launcher é independente; breakpoints no console do Spyder não são automaticamente anexados a ele. Para depurar a interface, configure execução em terminal externo ou use um depurador de processo separado.

Referências oficiais: [trocar interpretador e reiniciar kernel](https://docs.spyder-ide.org/current/faq.html), [compatibilidade do kernel](https://docs.spyder-ide.org/current/troubleshooting/common-illnesses.html), [requisitos Spyder 6.1](https://github.com/spyder-ide/spyder/blob/v6.1.0/setup.py), [requisitos Spyder 6.0.8](https://github.com/spyder-ide/spyder/blob/v6.0.8/setup.py).
